"""build_merged_text.py が生成した <prefix>.ndlocr-body.txt に対して検索を行い、
ヒット箇所の該当ページ番号と前後の文脈を表示する。

<prefix>.ndlocr-index.json (バイトオフセット→ページ番号のサイドカー索引) を
突き合わせてページ番号を逆引きする。検索は Python の標準ライブラリ ``re`` を
用いるため、外部コマンド (ripgrep 等) のインストールは不要。

対象指定方法:
  - 第1引数にディレクトリを渡すと、その中の ``*.ndlocr-body.txt`` を自動検出
    （複数ある場合は ``--prefix`` で明示指定が必要）
  - 第1引数に ``*.ndlocr-body.txt`` ファイルを直接渡すこともできる

Issue: https://github.com/yukikase0422/ndlocr-lite/issues/1
      https://github.com/yukikase0422/ndlocr-lite/issues/2
"""

from __future__ import annotations

import argparse
import bisect
import json
import re
import sys
from pathlib import Path

# Windows の cp932 環境でも UTF-8 で安全に出力できるようにする。
# Python 3.7+ の reconfigure が利用可能な場合のみ適用する。
for _stream in (sys.stdout, sys.stderr):
    reconf = getattr(_stream, "reconfigure", None)
    if callable(reconf):
        try:
            reconf(encoding="utf-8", errors="replace")
        except Exception:
            pass


def load_page_index(index_path: Path):
    data = json.loads(index_path.read_text(encoding="utf-8"))
    pages = data.get("pages", [])
    offsets = [int(p[0]) for p in pages]
    numbers = [int(p[1]) for p in pages]
    return offsets, numbers, data.get("meta", {})


def find_page(offsets: list[int], numbers: list[int], byte_offset: int) -> int:
    idx = bisect.bisect_right(offsets, byte_offset) - 1
    if idx < 0:
        idx = 0
    return numbers[idx]


def make_context_snippet(body_text: str, char_start: int, char_end: int, context_chars: int) -> str:
    """文字インデックスベースでヒット前後の文脈を切り出す。

    バイト境界でUTF-8を切ると文字化けするため、文字インデックスで処理する。
    """
    ctx_start = max(0, char_start - context_chars)
    ctx_end = min(len(body_text), char_end + context_chars)
    before = body_text[ctx_start:char_start]
    hit = body_text[char_start:char_end]
    after = body_text[char_end:ctx_end]
    return f"{before}【{hit}】{after}".replace("\n", "\\n")


def resolve_body_and_index(target: Path, prefix: str | None) -> tuple[Path, Path]:
    """対象指定から body.txt と index.json のパスを確定する。

    - target がファイル: `*.ndlocr-body.txt` とみなし、同所の `*.ndlocr-index.json` を採る
    - target がディレクトリ: 中の `*.ndlocr-body.txt` を探索。prefix指定があれば `<prefix>.ndlocr-body.txt`
    """
    if target.is_file():
        body_path = target
        stem = body_path.name.removesuffix(".ndlocr-body.txt")
        if stem == body_path.name:
            sys.exit(f"指定ファイルが *.ndlocr-body.txt 形式ではありません: {target}")
        index_path = body_path.parent / f"{stem}.ndlocr-index.json"
        return body_path, index_path

    if not target.is_dir():
        sys.exit(f"ディレクトリまたはファイルが見つかりません: {target}")

    if prefix:
        body_path = target / f"{prefix}.ndlocr-body.txt"
        index_path = target / f"{prefix}.ndlocr-index.json"
        return body_path, index_path

    candidates = sorted(target.glob("*.ndlocr-body.txt"))
    if len(candidates) == 0:
        sys.exit(f"*.ndlocr-body.txt が見つかりません: {target}")
    if len(candidates) > 1:
        names = ", ".join(p.name for p in candidates)
        sys.exit(f"複数の *.ndlocr-body.txt が見つかりました。--prefix で指定してください: {names}")
    body_path = candidates[0]
    stem = body_path.name.removesuffix(".ndlocr-body.txt")
    index_path = body_path.parent / f"{stem}.ndlocr-index.json"
    return body_path, index_path


def search(target: Path, prefix: str | None, pattern: str, context: int, ignore_case: bool, fixed_strings: bool) -> int:
    body_path, index_path = resolve_body_and_index(target, prefix)
    for p in (body_path, index_path):
        if not p.is_file():
            sys.exit(f"必須ファイルが見つかりません: {p}")

    offsets, numbers, meta = load_page_index(index_path)
    body_text = body_path.read_text(encoding="utf-8")

    flags = re.IGNORECASE if ignore_case else 0
    regex = re.compile(re.escape(pattern) if fixed_strings else pattern, flags)

    # 文字オフセットからUTF-8バイトオフセットへの変換は、部分文字列のエンコードで
    # 1ヒットごとに算出する。書籍1冊の本文サイズ（数百万byte以下）では十分高速。
    hits = 0
    for match in regex.finditer(body_text):
        char_start, char_end = match.start(), match.end()
        byte_start = len(body_text[:char_start].encode("utf-8"))
        page = find_page(offsets, numbers, byte_start)
        snippet = make_context_snippet(body_text, char_start, char_end, context)
        print(f"p.{page}\t(offset={byte_start})\t...{snippet}...")
        hits += 1

    if hits == 0:
        print("(マッチなし)")
        return 1
    title = meta.get("title") or "(untitled)"
    page_count = meta.get("page_count", "?")
    sys.stderr.write(f"\n-- {hits} 件ヒット / 書籍: {title} (全{page_count}ページ) --\n")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(
        description="build_merged_text.py の出力に対してページ番号付き検索を行う。"
    )
    p.add_argument("target", type=Path,
                   help="*.ndlocr-body.txt ファイル、またはそれを含むディレクトリ")
    p.add_argument("pattern", type=str, help="検索パターン（Python re 形式、既定）")
    p.add_argument("--prefix", type=str, default=None,
                   help="同一ディレクトリに複数の *.ndlocr-body.txt がある場合にprefixを指定")
    p.add_argument("-c", "--context", type=int, default=30, help="ヒット前後の文脈文字数（既定30）")
    p.add_argument("-i", "--ignore-case", action="store_true", help="大文字小文字を区別しない")
    p.add_argument("-F", "--fixed-strings", action="store_true", help="パターンを正規表現でなくリテラル文字列として扱う")
    args = p.parse_args()
    sys.exit(search(args.target, args.prefix, args.pattern, args.context, args.ignore_case, args.fixed_strings))


if __name__ == "__main__":
    main()
