# postprocess/ — NDLOCR入力から後処理まで一貫実行するツール群

PDF / 画像ファイルを入力として、NDLOCR実行から後処理（統合テキスト・ページ索引・閲覧用テキスト生成）まで一貫して実行するオーケストレーター。

設計の経緯と仕様は [Issue #1](https://github.com/yukikase0422/ndlocr-lite/issues/1)（後処理ツール本体）および [Issue #2](https://github.com/yukikase0422/ndlocr-lite/issues/2)（命名規則・構造改修）を参照。

> 本ディレクトリは本家 `ndl-lab/ndlocr-lite` には存在しない、fork独自の追加物である。`git merge upstream/master` でも衝突することはない。

---

## 出力ファイル命名規則

| ファイル | 用途 |
|---|---|
| `{stem}_NDLOCR結果（本文のみ結合済）.txt` | 検索用本文（改行除去・ページ跨ぎ連結） |
| `{stem}_NDLOCR結果（閲覧用ページ番号付き）.txt` | `<page number="N">...</page>` 形式でXMLラップ |
| `{stem}_NDLOCR結果（ページ索引）.json` | バイトオフセット→ページ番号の対応表 |
| `{stem}_NDLOCR/` | 中間物ディレクトリ（`page_001.png` / `page_001.txt` / `page_001.xml` / `page_001.json`） |

`{stem}` は元ファイルのbasename（拡張子なし）から自動決定される。

---

## 解決する課題

本家NDLOCRの標準出力をそのまま `grep` / `ripgrep` で検索すると、以下の問題が生じる。

1. **ページ跨ぎ検索語の取りこぼし** — 本文がページ境界で分断され、検索語がページ末～次ページ頭にまたがる場合、検出できない。
2. **物理行の改行による検索語分断** — OCRは原紙面の行折り返し位置で改行を入れるため、検索語が行をまたぐ場合（例: 「国際慣\n習法」）、通常のgrepでは拾えない。
3. **章タイトル・柱（ランニングヘッダ）・脚注等のノイズ混入** — 本文以外の行が検索結果を濁らせる、もしくは偽陽性マッチを生む。

本ツールはこれらを、XML中の `<LINE TYPE>` 属性を活用した**論理種別ベースの本文抽出**と、**バイトオフセット→ページ番号のサイドカー索引**によって解決する。

---

## 構成

| ファイル | 役割 |
|---|---|
| `build_merged_text.py` | PDF/画像からNDLOCR実行→後処理まで一貫実行するオーケストレーター |
| `search_ocr.py` | 統合テキストに対してページ番号付き検索を行う |
| `README.md` | 本ファイル |

実装言語: Python 3.10以上。

依存ライブラリ:
- `pypdfium2`: PDF画像化（PDFを入力する場合のみ必要）
- `Pillow`: 画像フォーマット変換（オプション）

検索には外部コマンド（`ripgrep` 等）は不要で、Python の `re` モジュールを直接利用する。

---

## 使い方

### 入力パターン

#### (a) PDFファイル入力

```bash
python postprocess/build_merged_text.py <pdf_file>
```

1. PDFを画像化し `{stem}_NDLOCR/page_XXX.png` に配置
2. NDLOCR実行
3. 後処理で統合テキスト3種を生成

出力は元PDFの親ディレクトリに配置される。

#### (b) 単一画像ファイル入力

```bash
python postprocess/build_merged_text.py <image_file>
```

1. `{stem}_NDLOCR/` を作成し、元画像を `page_001.png` にリネーム配置
2. NDLOCR実行
3. 後処理

#### (c) 画像フォルダ入力

```bash
python postprocess/build_merged_text.py <image_folder>
```

フォルダ内の各画像を独立処理する。各画像ごとに `{画像stem}_NDLOCR結果～` ファイルと `{画像stem}_NDLOCR/` ディレクトリが生成される。

#### (d) 複数ファイル引数入力

```bash
python postprocess/build_merged_text.py <file1> <file2> <file3> ...
```

各ファイルを独立処理する（上記a,bの繰り返し）。

#### (e) 既存NDLOCR出力ディレクトリ入力

```bash
python postprocess/build_merged_text.py <existing_ndlocr_dir>
```

`page_XXX.xml` が既に存在するディレクトリを渡した場合、後処理のみ実行する。

---

## 全体結合オプション（画像フォルダ入力時）

画像フォルダ入力時に、全ファイルを連結した統合テキストを追加生成できる。

### `--combine none`（既定）

全体結合テキストを作成しない。各画像は独立した結果ファイルを持つ。

### `--combine name-order`

ファイル名昇順で連結し、`{フォルダ名}_NDLOCR結果～` を出力する。

```bash
python postprocess/build_merged_text.py <image_folder> --combine name-order
```

### `--combine custom-order`

任意の順序で連結する。2段階で実行する。

**1回目実行（テンプレート生成）:**

```bash
python postprocess/build_merged_text.py <image_folder> --combine custom-order
```

連番付きファイル一覧が標準出力に表示され、`{フォルダ名}_NDLOCR_ordering_template.txt` が生成される。

**2回目実行（順序指定ファイルを渡す）:**

順序指定ファイルを編集し、希望の順序に並べ替えた後、`--order-file` で指定する。

```bash
python postprocess/build_merged_text.py <image_folder> --combine custom-order \
    --order-file <image_folder>/<フォルダ名>_NDLOCR_ordering_template.txt
```

**エラー条件:**
- 欠番（1〜Nを網羅しない）
- 重複（同じファイル名が複数現れる）

---

## 検索

```bash
# ディレクトリ指定（中の *_NDLOCR結果（本文のみ結合済）.txt を自動検出）
python postprocess/search_ocr.py <output_dir> "検索語"

# ファイル直接指定
python postprocess/search_ocr.py <output_dir>/<stem>_NDLOCR結果（本文のみ結合済）.txt "検索語"

# 同一ディレクトリに複数の本文ファイルがある場合
python postprocess/search_ocr.py <output_dir> "検索語" --prefix <stem>
```

出力例:

```
p.54	(offset=1523)	...諸国民の法を普遍人類法と見る見方があった。【グロティウス】は国際法...
p.122	(offset=45120)	...【国際慣習法】の成立には一般慣行と法的確信が...
```

主なオプション:

- `-i, --ignore-case`: 大文字小文字を区別しない
- `-F, --fixed-strings`: 検索パターンを正規表現ではなくリテラル文字列として扱う
- `-c, --context N`: ヒット前後の文脈**文字数**（既定 30）

---

## その他のオプション

| オプション | 説明 |
|---|---|
| `--skip-ocr` | NDLOCR実行をスキップし、後処理のみ行う（デバッグ用） |
| `--dpi N` | PDF画像化時のDPI（既定: 300） |

---

## 内部仕様

### 後処理のルール

XML中の各 `<LINE>` を**XML文書順**で処理する（NDLOCR本家の `.txt` 出力と同じ順序。`ORDER` 属性はXY-cut評価時の内部指標であり最終読み順ではないため採用しない）。`TYPE` に応じて以下のように扱う。

| `TYPE` | 本文結合済.txt への扱い | 閲覧用.txt への扱い |
|---|---|---|
| `本文` | そのまま連結（改行なし） | そのまま1行として出力 |
| `タイトル本文` | 直前が本文なら改行を1つ挿入（章境界として分離） | `[見出し] ...` プレフィックス付きで出力 |
| `キャプション` / `頭注` / `割注` / `広告文字` | 除外 | 除外 |
| （`<BLOCK TYPE="柱">`） | もともと `LINE` ではないため自然に除外 | 同左 |

### ページ索引 JSON の形式

```json
{
  "meta": {
    "title": "...",
    "source": "...",
    "generated_at": "2026-04-23T10:00:00",
    "ndlocr_dir": "...",
    "page_count": 860,
    "body_bytes": 1234567
  },
  "pages": [
    [0, 1],
    [523, 2],
    [1047, 3],
    ...
  ]
}
```

`pages` 配列の各要素は `[byte_offset_in_body_txt, page_number]` の2要素リスト。`byte_offset` は UTF-8 バイトでの位置。

### 閲覧用テキストの形式

```xml
<!-- title     : 書籍タイトル -->
<!-- source    : 元ファイルパス -->
<!-- generated : 2026-04-23T10:00:00 -->
<!-- pages     : 860 -->

<page number="1">
本文行1
本文行2
[見出し] 第1章 はじめに
本文行3
</page>
<page number="2">
...
</page>
```

WindowsPDFOCRの出力形式を踏襲し、`<page number="N">...</page>` でXMLラップする。

---

## 設計上の考慮事項

- **TEXTBLOCK単位の改行は入れない**: NDLOCRのTEXTBLOCKは物理的な領域ブロックであり、意味的な段落ではない。改行を入れるとページ跨ぎ連結が阻害されるため、本文内の区切りは `タイトル本文` 行との境目だけに限定している。
- **ページ索引の空ページ対応**: 本文の無いページ（白紙・索引ページ等）もエントリを記録する。同一バイトオフセットの複数ページが並ぶが、`bisect_right` で正しく直近の実本文ページに解決される。
- **改行コード**: すべてLF（`\n`）で統一（Windows環境でもそのまま動作する）。
- **本家との衝突回避**: `postprocess/` ディレクトリは本家 `ndl-lab/ndlocr-lite` には存在しないため、`git merge upstream/master` で衝突しない。
