"""PDF / 画像からNDLOCR実行→後処理まで一貫して行うオーケストレーター。

入力種別:
  - PDF: pypdfium2で画像化し ``{stem}_NDLOCR/page_XXX.png`` に配置 → NDLOCR実行 → 後処理
  - 単一画像: ``{stem}_NDLOCR/`` を作成し ``page_001.png`` にリネーム配置 → NDLOCR実行 → 後処理
  - 画像フォルダ: フォルダ内各画像を独立処理 + オプションで全体結合
  - 複数ファイル引数: 各ファイルを独立処理（上記の繰り返し）

出力ファイル命名規則:
  - ``{stem}_NDLOCR結果（本文のみ結合済）.txt`` — 検索用本文（改行除去・ページ跨ぎ連結）
  - ``{stem}_NDLOCR結果（閲覧用ページ番号付き）.txt`` — ``<page number="N">...</page>`` 形式
  - ``{stem}_NDLOCR結果（ページ索引）.json`` — バイトオフセット→ページ番号
  - ``{stem}_NDLOCR/`` — 中間物ディレクトリ（page_XXX.png/txt/xml/json）

中断再開（resume）対応:
  - 画像化: 既存PNG（サイズ > 0）があればスキップ
  - OCR: 全ページの .xml/.txt/.json が揃っていればスキップ、未処理があれば全量実行
  - 集約: 常に中間物から再生成（上書き）

Issue: https://github.com/yukikase0422/ndlocr-lite/issues/1
      https://github.com/yukikase0422/ndlocr-lite/issues/2
      https://github.com/yukikase0422/ndlocr-lite/issues/4
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

# Windows の cp932 環境でも UTF-8 で安全に出力できるようにする
for _stream in (sys.stdout, sys.stderr):
    reconf = getattr(_stream, "reconfigure", None)
    if callable(reconf):
        try:
            reconf(encoding="utf-8", errors="replace")
        except Exception:
            pass

PAGE_FILE_RE = re.compile(r"page_(\d+)\.xml$", re.IGNORECASE)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".gif", ".webp"}

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


def calculate_zero_padding(total_pages: int) -> int:
    """全ページ数に基づいてゼロ埋め桁数を計算する。"""
    if total_pages <= 0:
        return 3
    return max(3, len(str(total_pages)))


def pdf_to_images(
    pdf_path: Path,
    output_dir: Path,
    dpi: int = 300,
    force_rerender: bool = False,
) -> list[Path]:
    """PDFを画像に変換し、output_dir内にpage_XXX.pngとして保存する。

    中断再開対応:
      - 既存の page_N.png が存在しサイズ > 0 ならスキップ
      - force_rerender=True なら既存ファイルを無視して全ページ再生成
    """
    try:
        import pypdfium2 as pdfium
    except ImportError:
        sys.exit("エラー: pypdfium2がインストールされていません。`pip install pypdfium2` を実行してください。")

    output_dir.mkdir(parents=True, exist_ok=True)

    pdf = pdfium.PdfDocument(str(pdf_path))
    total_pages = len(pdf)
    zero_pad = calculate_zero_padding(total_pages)

    image_paths: list[Path] = []
    scale = dpi / 72  # 72 DPI is the default PDF unit
    new_count = 0
    skip_count = 0

    for i, page in enumerate(pdf):
        page_num = i + 1
        output_path = output_dir / f"page_{page_num:0{zero_pad}d}.png"

        # 既存ファイルチェック（サイズ > 0）
        if not force_rerender and output_path.exists() and output_path.stat().st_size > 0:
            skip_count += 1
            image_paths.append(output_path)
            page.close()
            continue

        # 新規レンダリング
        bitmap = page.render(scale=scale)
        pil_image = bitmap.to_pil()
        pil_image.save(str(output_path), "PNG")
        image_paths.append(output_path)
        new_count += 1
        page.close()

    pdf.close()
    print(f"[INFO] PDF画像化: 新規 {new_count}ページ / スキップ {skip_count}ページ / 合計 {total_pages}ページ")
    return image_paths


def _is_page_ocr_complete(ndlocr_dir: Path, png_path: Path) -> bool:
    """当該PNGのOCR結果（.xml/.txt/.json）が揃っているかを判定する。

    判定条件: page_N.xml / page_N.json がサイズ > 0 で存在、page_N.txt は存在。
    （.txt はNDLOCRで空出力のページが正常にあり得るためサイズ条件を緩める）
    """
    stem = png_path.stem  # "page_001"
    xml_p = ndlocr_dir / f"{stem}.xml"
    txt_p = ndlocr_dir / f"{stem}.txt"
    json_p = ndlocr_dir / f"{stem}.json"
    return (
        xml_p.is_file() and xml_p.stat().st_size > 0
        and txt_p.is_file()
        and json_p.is_file() and json_p.stat().st_size > 0
    )


def run_ndlocr(ndlocr_dir: Path, force_reocr: bool = False) -> bool:
    """NDLOCRを実行する。ndlocr_dir内のpage_XXX.pngを処理する。

    中断再開対応（案1: 全量実行で本家に任せる方式）:
      - ndlocr_dir内の全page_*.pngについて、対応する.xml/.txt/.jsonが既に揃っていれば
        NDLOCR呼び出しをスキップ（既処理とみなす）
      - 一部でも未処理があれば全量実行する（NDLOCR本家は既存出力を上書きする挙動）
      - force_reocr=True なら既存出力を無視して全量実行
    """
    png_files = sorted(ndlocr_dir.glob("page_*.png"))
    if not png_files:
        print(f"[WARN] page_*.pngが見つかりません: {ndlocr_dir}")
        return False

    total = len(png_files)
    if not force_reocr:
        completed = [p for p in png_files if _is_page_ocr_complete(ndlocr_dir, p)]
        if len(completed) == total:
            print(f"[INFO] NDLOCR: 全{total}ページのOCR結果が既に揃っています。スキップします。")
            return True
        pending_count = total - len(completed)
        print(f"[INFO] NDLOCR: 未処理 {pending_count}ページ / 既存 {len(completed)}ページ / 合計 {total}ページ")
        print(f"[INFO] 案1方針により全量実行します（既存出力は本家側で上書きされます）")
    else:
        print(f"[INFO] NDLOCR: --force-reocr 指定により全{total}ページ強制再実行")

    cmd = [
        "ndlocr-lite",
        "--sourcedir", str(ndlocr_dir),
        "--output", str(ndlocr_dir),
    ]
    print(f"[INFO] NDLOCR実行: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            print(f"[ERROR] NDLOCR実行失敗:\n{result.stderr}")
            return False
        print(f"[INFO] NDLOCR実行完了")
        return True
    except FileNotFoundError:
        print("[ERROR] ndlocr-liteコマンドが見つかりません。`uv tool install ndlocr-lite` を実行してください。")
        return False


def build_merged_text(
    ndlocr_dir: Path,
    output_dir: Path,
    stem: str,
    title: str | None,
    source_path: str | None,
) -> tuple[Path, Path, Path] | None:
    """NDLOCR出力XMLから統合テキスト・ページ索引・閲覧用テキストを生成する。

    Returns:
        (body_path, index_path, indexed_path) のタプル、または失敗時はNone
    """
    xml_files = sorted(
        (p for p in ndlocr_dir.glob("page_*.xml") if PAGE_FILE_RE.search(p.name)),
        key=lambda p: int(PAGE_FILE_RE.search(p.name).group(1)),
    )
    if not xml_files:
        print(f"[WARN] ページXML (page_XXXX.xml) が見つかりません: {ndlocr_dir}")
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    body_path = output_dir / f"{stem}_NDLOCR結果（本文のみ結合済）.txt"
    index_path = output_dir / f"{stem}_NDLOCR結果（ページ索引）.json"
    indexed_path = output_dir / f"{stem}_NDLOCR結果（閲覧用ページ番号付き）.txt"

    body_parts: list[str] = []
    indexed_parts: list[str] = []
    body_byte_count = 0
    page_entries: list[list[int]] = []

    for xml_file in xml_files:
        m = PAGE_FILE_RE.search(xml_file.name)
        assert m is not None
        page_num = int(m.group(1))
        page_entries.append([body_byte_count, page_num])
        indexed_parts.append(f'<page number="{page_num}">\n')

        for ltype, text in iter_lines_in_reading_order(xml_file):
            if not text:
                continue
            if ltype == TYPE_BODY:
                body_parts.append(text)
                body_byte_count += len(text.encode("utf-8"))
                indexed_parts.append(text)
                indexed_parts.append("\n")
            elif ltype == TYPE_TITLE:
                # 章境界の疑似改行。body.txt 側は LF を1つだけ挿入
                if body_parts and not body_parts[-1].endswith("\n"):
                    body_parts.append("\n")
                    body_byte_count += 1
                indexed_parts.append(f"[見出し] {text}\n")
            else:
                # キャプション・頭注・割注・広告文字 等は検索対象外
                pass

        indexed_parts.append("</page>\n")

    body_text = "".join(body_parts)
    if not body_text.endswith("\n"):
        body_text += "\n"

    meta = {
        "title": title or "",
        "source": source_path or "",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ndlocr_dir": str(ndlocr_dir),
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
        f"<!-- title     : {meta['title']} -->\n"
        f"<!-- source    : {meta['source']} -->\n"
        f"<!-- generated : {meta['generated_at']} -->\n"
        f"<!-- pages     : {meta['page_count']} -->\n\n"
        + "".join(indexed_parts),
        encoding="utf-8",
        newline="\n",
    )

    print(f"[OK] {body_path.name}: {body_path} ({meta['body_bytes']} bytes)")
    print(f"[OK] {index_path.name}: {index_path} ({len(page_entries)} pages)")
    print(f"[OK] {indexed_path.name}: {indexed_path}")

    return body_path, index_path, indexed_path


def process_pdf(
    pdf_path: Path,
    skip_ocr: bool = False,
    dpi: int = 300,
    force_rerender: bool = False,
    force_reocr: bool = False,
) -> tuple[Path, Path, Path] | None:
    """PDFを処理する: 画像化 → NDLOCR実行 → 後処理。"""
    stem = pdf_path.stem
    parent_dir = pdf_path.parent
    ndlocr_dir = parent_dir / f"{stem}_NDLOCR"

    # PDF画像化（resume対応）
    pdf_to_images(pdf_path, ndlocr_dir, dpi, force_rerender=force_rerender)

    # NDLOCR実行（resume対応）
    if not skip_ocr:
        if not run_ndlocr(ndlocr_dir, force_reocr=force_reocr):
            return None

    # 後処理（常に再生成）
    return build_merged_text(
        ndlocr_dir=ndlocr_dir,
        output_dir=parent_dir,
        stem=stem,
        title=stem,
        source_path=str(pdf_path),
    )


def process_single_image(
    image_path: Path,
    skip_ocr: bool = False,
    force_reocr: bool = False,
) -> tuple[Path, Path, Path] | None:
    """単一画像を処理する: _NDLOCRディレクトリ作成 → page_001.pngにコピー → NDLOCR実行 → 後処理。"""
    stem = image_path.stem
    parent_dir = image_path.parent
    ndlocr_dir = parent_dir / f"{stem}_NDLOCR"
    ndlocr_dir.mkdir(parents=True, exist_ok=True)

    # 画像をpage_001.pngとしてコピー
    dest_path = ndlocr_dir / "page_001.png"
    if image_path.suffix.lower() in {".png"}:
        shutil.copy2(image_path, dest_path)
    else:
        # PNG以外はPILで変換
        try:
            from PIL import Image
            img = Image.open(image_path)
            img.save(dest_path, "PNG")
        except ImportError:
            # PILがなければそのままコピー（NDLOCRがサポートしていれば動く）
            shutil.copy2(image_path, ndlocr_dir / f"page_001{image_path.suffix}")
            dest_path = ndlocr_dir / f"page_001{image_path.suffix}"

    print(f"[INFO] 画像配置完了: {dest_path}")

    # NDLOCR実行（resume対応）
    if not skip_ocr:
        if not run_ndlocr(ndlocr_dir, force_reocr=force_reocr):
            return None

    # 後処理（常に再生成）
    return build_merged_text(
        ndlocr_dir=ndlocr_dir,
        output_dir=parent_dir,
        stem=stem,
        title=stem,
        source_path=str(image_path),
    )


def process_image_folder(
    folder_path: Path,
    combine: str,
    order_file: Path | None,
    skip_ocr: bool = False,
    force_reocr: bool = False,
) -> list[tuple[Path, Path, Path]]:
    """画像フォルダを処理する: 各画像を独立処理 + オプションで全体結合。"""
    image_files = sorted([
        p for p in folder_path.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ])

    if not image_files:
        print(f"[WARN] 画像ファイルが見つかりません: {folder_path}")
        return []

    # custom-order の1回目: テンプレート生成して終了
    if combine == "custom-order" and order_file is None:
        template_path = folder_path / f"{folder_path.name}_NDLOCR_ordering_template.txt"
        lines = [f"{i+1}\t{p.name}" for i, p in enumerate(image_files)]
        template_content = "\n".join(lines) + "\n"
        template_path.write_text(template_content, encoding="utf-8", newline="\n")
        print(f"[INFO] 順序指定テンプレートを生成しました: {template_path}")
        print("[INFO] テンプレートを編集後、--order-file オプションで指定して再実行してください。")
        print("\n--- テンプレート内容 ---")
        print(template_content)
        return []

    results: list[tuple[Path, Path, Path]] = []

    # 各画像を独立処理
    for image_path in image_files:
        result = process_single_image(image_path, skip_ocr=skip_ocr, force_reocr=force_reocr)
        if result:
            results.append(result)

    # 全体結合
    if combine != "none" and results:
        if combine == "name-order":
            # ファイル名昇順で連結
            combine_results(
                results=results,
                output_dir=folder_path,
                stem=folder_path.name,
            )
        elif combine == "custom-order" and order_file is not None:
            # 順序指定ファイルに従って連結
            ordered_results = reorder_by_order_file(results, order_file, image_files)
            if ordered_results:
                combine_results(
                    results=ordered_results,
                    output_dir=folder_path,
                    stem=folder_path.name,
                )

    return results


def reorder_by_order_file(
    results: list[tuple[Path, Path, Path]],
    order_file: Path,
    original_images: list[Path],
) -> list[tuple[Path, Path, Path]] | None:
    """順序指定ファイルに従ってresultsを並べ替える。"""
    order_lines = order_file.read_text(encoding="utf-8").strip().split("\n")
    order_map: dict[str, int] = {}

    for i, line in enumerate(order_lines):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # 形式: "番号\tファイル名" または "ファイル名"
        parts = line.split("\t")
        if len(parts) >= 2:
            filename = parts[1].strip()
        else:
            filename = parts[0].strip()
        if filename in order_map:
            print(f"[ERROR] 重複するファイル名: {filename}")
            return None
        order_map[filename] = i

    # 結果をファイル名でマップ
    result_map: dict[str, tuple[Path, Path, Path]] = {}
    for r in results:
        # body_pathから元画像名を逆算
        body_path = r[0]
        stem = body_path.stem.removesuffix("_NDLOCR結果（本文のみ結合済）")
        # 元画像ファイルを探す
        for img in original_images:
            if img.stem == stem:
                result_map[img.name] = r
                break

    # 順序通りに並べ替え
    ordered_results: list[tuple[Path, Path, Path]] = []
    for filename in sorted(order_map.keys(), key=lambda f: order_map[f]):
        if filename not in result_map:
            print(f"[ERROR] 順序指定ファイルに含まれるが結果が見つからない: {filename}")
            return None
        ordered_results.append(result_map[filename])

    # 全ファイルが指定されているか確認
    if len(ordered_results) != len(results):
        print(f"[ERROR] 順序指定が不完全です。指定: {len(ordered_results)}, 結果: {len(results)}")
        return None

    return ordered_results


def combine_results(
    results: list[tuple[Path, Path, Path]],
    output_dir: Path,
    stem: str,
) -> None:
    """複数の処理結果を結合して全体テキストを生成する。"""
    combined_body_parts: list[str] = []
    combined_indexed_parts: list[str] = []
    combined_pages: list[list[int]] = []
    body_byte_offset = 0
    total_page_count = 0

    for body_path, index_path, indexed_path in results:
        # 本文を読み込み
        body_text = body_path.read_text(encoding="utf-8")
        combined_body_parts.append(body_text)

        # ページ索引を読み込み、オフセットを調整
        index_data = json.loads(index_path.read_text(encoding="utf-8"))
        for offset, page_num in index_data.get("pages", []):
            combined_pages.append([body_byte_offset + offset, total_page_count + page_num])

        # 閲覧用テキストを読み込み（ヘッダー部分を除去）
        indexed_text = indexed_path.read_text(encoding="utf-8")
        # ヘッダー（<!-- で始まる行）をスキップ
        lines = indexed_text.split("\n")
        content_started = False
        for line in lines:
            if not content_started:
                if line.startswith("<!--") or line.strip() == "":
                    continue
                content_started = True
            combined_indexed_parts.append(line + "\n")

        body_byte_offset += len(body_text.encode("utf-8"))
        page_meta = index_data.get("meta", {})
        total_page_count += page_meta.get("page_count", 0)

    combined_body = "".join(combined_body_parts)
    combined_indexed = "".join(combined_indexed_parts)

    # 出力
    combined_body_path = output_dir / f"{stem}_NDLOCR結果（本文のみ結合済）.txt"
    combined_index_path = output_dir / f"{stem}_NDLOCR結果（ページ索引）.json"
    combined_indexed_path = output_dir / f"{stem}_NDLOCR結果（閲覧用ページ番号付き）.txt"

    meta = {
        "title": stem,
        "source": str(output_dir),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "combined_from": [str(r[0]) for r in results],
        "page_count": total_page_count,
        "body_bytes": len(combined_body.encode("utf-8")),
    }

    combined_body_path.write_text(combined_body, encoding="utf-8", newline="\n")
    combined_index_path.write_text(
        json.dumps({"meta": meta, "pages": combined_pages}, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    combined_indexed_path.write_text(
        f"<!-- title     : {meta['title']} -->\n"
        f"<!-- source    : {meta['source']} -->\n"
        f"<!-- generated : {meta['generated_at']} -->\n"
        f"<!-- pages     : {meta['page_count']} -->\n\n"
        + combined_indexed,
        encoding="utf-8",
        newline="\n",
    )

    print(f"\n[COMBINED] {combined_body_path.name}: {combined_body_path}")
    print(f"[COMBINED] {combined_index_path.name}: {combined_index_path}")
    print(f"[COMBINED] {combined_indexed_path.name}: {combined_indexed_path}")


def is_pdf(path: Path) -> bool:
    return path.suffix.lower() == ".pdf"


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def is_ndlocr_output_dir(path: Path) -> bool:
    """既存のNDLOCR出力ディレクトリかどうかを判定する。"""
    if not path.is_dir():
        return False
    return any(p.name.startswith("page_") and p.suffix == ".xml" for p in path.iterdir())


def process_input(
    input_path: Path,
    combine: str,
    order_file: Path | None,
    skip_ocr: bool = False,
    dpi: int = 300,
    force_rerender: bool = False,
    force_reocr: bool = False,
) -> list[tuple[Path, Path, Path]]:
    """入力パスを判定して適切な処理を実行する。"""
    if not input_path.exists():
        print(f"[ERROR] パスが存在しません: {input_path}")
        return []

    if input_path.is_file():
        if is_pdf(input_path):
            result = process_pdf(
                input_path,
                skip_ocr=skip_ocr,
                dpi=dpi,
                force_rerender=force_rerender,
                force_reocr=force_reocr,
            )
            return [result] if result else []
        elif is_image(input_path):
            result = process_single_image(
                input_path,
                skip_ocr=skip_ocr,
                force_reocr=force_reocr,
            )
            return [result] if result else []
        else:
            print(f"[ERROR] 未対応のファイル形式: {input_path}")
            return []
    elif input_path.is_dir():
        if is_ndlocr_output_dir(input_path):
            # 既存のNDLOCR出力ディレクトリの場合、後処理のみ実行
            # （集約は常に再生成 = resume設計の集約フェーズに該当）
            stem = input_path.name.removesuffix("_NDLOCR")
            result = build_merged_text(
                ndlocr_dir=input_path,
                output_dir=input_path.parent,
                stem=stem,
                title=stem,
                source_path=str(input_path),
            )
            return [result] if result else []
        else:
            # 画像フォルダとして処理
            return process_image_folder(
                input_path,
                combine,
                order_file,
                skip_ocr=skip_ocr,
                force_reocr=force_reocr,
            )
    else:
        print(f"[ERROR] 不明なパス種別: {input_path}")
        return []


def main() -> None:
    p = argparse.ArgumentParser(
        description="PDF / 画像からNDLOCR実行→後処理まで一貫して実行するオーケストレーター。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
入力パターン:
  PDFファイル      → 画像化 → NDLOCR実行 → 後処理
  単一画像ファイル → _NDLOCRディレクトリ作成 → NDLOCR実行 → 後処理
  画像フォルダ     → 各画像を独立処理 + オプションで全体結合
  複数ファイル     → 各ファイルを独立処理

出力ファイル:
  {stem}_NDLOCR結果（本文のみ結合済）.txt       # 検索用本文
  {stem}_NDLOCR結果（閲覧用ページ番号付き）.txt # <page number="N">...</page>形式
  {stem}_NDLOCR結果（ページ索引）.json          # バイトオフセット→ページ番号
  {stem}_NDLOCR/                               # 中間物ディレクトリ
""",
    )
    p.add_argument(
        "inputs",
        type=Path,
        nargs="+",
        help="入力ファイル/ディレクトリ（PDF / 画像 / 画像フォルダ / NDLOCR出力ディレクトリ）",
    )
    p.add_argument(
        "--combine",
        choices=["none", "name-order", "custom-order"],
        default="none",
        help="画像フォルダ入力時の全体結合オプション（既定: none）",
    )
    p.add_argument(
        "--order-file",
        type=Path,
        default=None,
        help="custom-order時の順序指定ファイル（1行1ファイル名）",
    )
    p.add_argument(
        "--skip-ocr",
        action="store_true",
        help="NDLOCR実行をスキップし、後処理のみ行う（デバッグ・集約のみ再生成用）",
    )
    p.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="PDF画像化時のDPI（既定: 300）",
    )
    p.add_argument(
        "--force-rerender",
        action="store_true",
        help="PDF画像化を強制再実行（既存page_N.pngを無視）",
    )
    p.add_argument(
        "--force-reocr",
        action="store_true",
        help="NDLOCR実行を強制再実行（既存page_N.xml/txt/jsonを無視）",
    )
    args = p.parse_args()

    all_results: list[tuple[Path, Path, Path]] = []

    for input_path in args.inputs:
        results = process_input(
            input_path,
            combine=args.combine,
            order_file=args.order_file,
            skip_ocr=args.skip_ocr,
            dpi=args.dpi,
            force_rerender=args.force_rerender,
            force_reocr=args.force_reocr,
        )
        all_results.extend(results)

    if not all_results:
        print("\n[WARN] 処理結果がありません。")
        sys.exit(1)

    print(f"\n[DONE] 合計 {len(all_results)} 件の処理が完了しました。")


if __name__ == "__main__":
    main()
