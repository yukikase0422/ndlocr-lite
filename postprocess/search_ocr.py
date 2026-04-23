"""build_merged_text.py が生成した統合テキストに対して検索を行い、
ヒット箇所の該当ページ番号と前後の文脈を表示する。

対象ファイル（新命名規則）:
  - ``{stem}_NDLOCR結果（本文のみ結合済）.txt`` — 検索対象本文
  - ``{stem}_NDLOCR結果（ページ索引）.json`` — バイトオフセット→ページ番号のサイドカー索引

対象指定方法:
  - 第1引数にディレクトリを渡すと、その中の ``*_NDLOCR結果（本文のみ結合済）.txt`` を自動検出
  - 第1引数に本文ファイルを直接渡すこともできる

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

# 新命名規則のサフィックス
BODY_SUFFIX = "_NDLOCR結果（本文のみ結合済）.txt"
INDEX_SUFFIX = "_NDLOCR結果（ページ索引）.json"


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
    """対象指定から本文ファイルとページ索引ファイルのパスを確定する。

    - target がファイル: 本文ファイルとみなし、同所のページ索引を採る
    - target がディレクトリ: 中の本文ファイルを探索。prefix指定があれば ``{prefix}_NDLOCR結果（本文のみ結合済）.txt``
    """
    if target.is_file():
        body_path = target
        # 新命名規則のサフィックスを除去してstemを取得
        if body_path.name.endswith(BODY_SUFFIX):
            stem = body_path.name[:-len(BODY_SUFFIX)]
        else:
            # サフィックスが一致しない場合はそのまま使用を試みる
            stem = body_path.stem
            # 同名のjsonを探す
            index_path = body_path.parent / f"{stem}{INDEX_SUFFIX}"
            if not index_path.exists():
                # 拡張子を除去して再試行
                index_path = body_path.parent / f"{stem}_NDLOCR結果（ページ索引）.json"
            return body_path, index_path
        index_path = body_path.parent / f"{stem}{INDEX_SUFFIX}"
        return body_path, index_path

    if not target.is_dir():
        sys.exit(f"ディレクトリまたはファイルが見つかりません: {target}")

    if prefix:
        body_path = target / f"{prefix}{BODY_SUFFIX}"
        index_path = target / f"{prefix}{INDEX_SUFFIX}"
        return body_path, index_path

    # 新命名規則でファイルを探す
    candidates = sorted([
        p for p in target.iterdir()
        if p.name.endswith(BODY_SUFFIX)
    ])
    if len(candidates) == 0:
        sys.exit(f"本文ファイル (*{BODY_SUFFIX}) が見つかりません: {target}")
    if len(candidates) > 1:
        names = ", ".join(p.name for p in candidates)
        sys.exit(f"複数の本文ファイルが見つかりました。--prefix で指定してください: {names}")
    body_path = candidates[0]
    stem = body_path.name[:-len(BODY_SUFFIX)]
    index_path = body_path.parent / f"{stem}{INDEX_SUFFIX}"
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
                   help="本文ファイル (*_NDLOCR結果（本文のみ結合済）.txt)、またはそれを含むディレクトリ")
    p.add_argument("pattern", type=str, help="検索パターン（Python re 形式、既定）")
    p.add_argument("--prefix", type=str, default=None,
                   help="同一ディレクトリに複数の本文ファイルがある場合にprefixを指定")
    p.add_argument("-c", "--context", type=int, default=30, help="ヒット前後の文脈文字数（既定30）")
    p.add_argument("-i", "--ignore-case", action="store_true", help="大文字小文字を区別しない")
    p.add_argument("-F", "--fixed-strings", action="store_true", help="パターンを正規表現でなくリテラル文字列として扱う")
    args = p.parse_args()
    sys.exit(search(args.target, args.prefix, args.pattern, args.context, args.ignore_case, args.fixed_strings))


if __name__ == "__main__":
    main()
