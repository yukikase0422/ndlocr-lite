"""NDLOCR出力XMLから検索用統合テキスト・ページ索引・閲覧用テキストを生成する。

Issue: https://github.com/yukikase0422/ndlocr-lite/issues/1
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Iterable

PAGE_FILE_RE = re.compile(r"page_(\d+)\.xml$", re.IGNORECASE)

TYPE_BODY = "本文"
TYPE_TITLE = "タイトル本文"


def iter_lines_in_reading_order(xml_path: Path) -> Iterable[tuple[str, str]]:
    """1ページ分のXMLからLINE要素をXML文書順（= NDLOCRが整序した読み順）で返す。

    NDLOCR本家の ``.txt`` 出力も ``root.findall(".//LINE")`` の走査順、すなわちXML
    文書順で書き出されており、``ORDER`` 属性はXY-cut評価時の内部指標であって最終
    読み順ではないため、ここでも文書順を採用する。
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    for line in root.iter("LINE"):
        ltype = line.get("TYPE", "") or ""
        text = line.get("STRING", "") or ""
        yield ltype, text


def build(
    ocr_dir: Path,
    out_dir: Path,
    title: str | None,
    source_pdf: str | None,
) -> None:
    xml_files = sorted(
        (p for p in ocr_dir.glob("page_*.xml") if PAGE_FILE_RE.search(p.name)),
        key=lambda p: int(PAGE_FILE_RE.search(p.name).group(1)),
    )
    if not xml_files:
        sys.exit(f"ページXML (page_XXXX.xml) が見つかりません: {ocr_dir}")

    out_dir.mkdir(parents=True, exist_ok=True)
    body_path = out_dir / "body.txt"
    index_path = out_dir / "page_index.json"
    indexed_path = out_dir / "indexed.txt"

    body_parts: list[str] = []
    indexed_parts: list[str] = []
    body_byte_count = 0
    page_entries: list[list[int]] = []

    for xml_file in xml_files:
        m = PAGE_FILE_RE.search(xml_file.name)
        assert m is not None
        page_num = int(m.group(1))
        page_entries.append([body_byte_count, page_num])
        indexed_parts.append(f"<<<PAGE {page_num}>>>\n")

        prev_type_in_body: str | None = None
        for ltype, text in iter_lines_in_reading_order(xml_file):
            if not text:
                continue
            if ltype == TYPE_BODY:
                body_parts.append(text)
                body_byte_count += len(text.encode("utf-8"))
                indexed_parts.append(text)
                indexed_parts.append("\n")
                prev_type_in_body = ltype
            elif ltype == TYPE_TITLE:
                # 章境界の疑似改行。body.txt 側は LF を1つだけ挿入
                # （直前が本文で、かつ末尾が改行でない場合のみ）
                if body_parts and not body_parts[-1].endswith("\n"):
                    body_parts.append("\n")
                    body_byte_count += 1
                indexed_parts.append(f"[見出し] {text}\n")
                prev_type_in_body = None
            else:
                # キャプション・頭注・割注・広告文字 等は検索対象外
                pass

    body_text = "".join(body_parts)
    if not body_text.endswith("\n"):
        body_text += "\n"

    meta = {
        "title": title or "",
        "source_pdf": source_pdf or "",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ocr_dir": str(ocr_dir),
        "page_count": len(xml_files),
        "body_bytes": len(body_text.encode("utf-8")),
    }

    body_path.write_text(body_text, encoding="utf-8", newline="\n")
    index_path.write_text(
        json.dumps({"meta": meta, "pages": page_entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    indexed_path.write_text(
        f"# title     : {meta['title']}\n"
        f"# source    : {meta['source_pdf']}\n"
        f"# generated : {meta['generated_at']}\n"
        f"# pages     : {meta['page_count']}\n\n"
        + "".join(indexed_parts),
        encoding="utf-8",
        newline="\n",
    )

    print(f"[OK] body.txt        : {body_path}  ({meta['body_bytes']} bytes)")
    print(f"[OK] page_index.json : {index_path}  ({len(page_entries)} pages)")
    print(f"[OK] indexed.txt     : {indexed_path}")


def main() -> None:
    p = argparse.ArgumentParser(
        description="NDLOCR出力から検索用統合テキスト・ページ索引・閲覧用テキストを生成する。"
    )
    p.add_argument("ocr_dir", type=Path, help="NDLOCR出力ディレクトリ（page_XXXX.xml を含む）")
    p.add_argument("--out-dir", type=Path, required=True, help="出力先ディレクトリ（自動作成）")
    p.add_argument("--title", type=str, default=None, help="書籍タイトル（メタ情報に記録）")
    p.add_argument("--source-pdf", type=str, default=None, help="元PDFパス（メタ情報に記録）")
    args = p.parse_args()
    build(args.ocr_dir, args.out_dir, args.title, args.source_pdf)


if __name__ == "__main__":
    main()
