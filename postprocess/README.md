# postprocess/ — NDLOCR出力の後処理スクリプト群

NDLOCRが生成する標準出力（`.txt` / `.xml` / `.json`）を後処理し、PDF資料の全文検索に最適化された統合テキスト・ページ索引・閲覧用テキストを生成するツール群。

設計の経緯と仕様は [Issue #1](https://github.com/yukikase0422/ndlocr-lite/issues/1) を参照。

> 本ディレクトリは本家 `ndl-lab/ndlocr-lite` には存在しない、fork独自の追加物である。`git merge upstream/master` でも衝突することはない。

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
| `build_merged_text.py` | NDLOCR出力XMLを走査し、統合テキスト・ページ索引・閲覧用テキストを生成 |
| `search_ocr.py` | `build_merged_text.py` の出力に対して `ripgrep` ベースの検索を行い、ヒット箇所のページ番号と文脈を表示 |
| `README.md` | 本ファイル |

実装言語: Python 3.10以上。**外部依存なし**（標準ライブラリのみで完結）。検索にも `ripgrep` 等の外部コマンドは不要で、Python の ``re`` モジュールを直接利用する。

---

## 使い方

### 1. NDLOCRで書籍をOCR

事前準備として、書籍PDFを各ページ画像に変換し、NDLOCRを実行して `page_XXXX.xml` などの出力を得る。これは既存のワークフロー（`ndlocr-lite --sourcedir ... --output ...`）で行う。

### 2. 統合テキストの生成

```bash
python postprocess/build_merged_text.py <ocr_output_dir> \
    --out-dir <merged_output_dir> \
    --title "書籍タイトル" \
    --source-pdf "元PDFパス"
```

生成物：

| ファイル | 用途 |
|---|---|
| `body.txt` | **検索専用** 本文のみを全ページ通して連結、ページマーカーなし |
| `page_index.json` | バイトオフセット→ページ番号の対応表 |
| `indexed.txt` | **人間閲覧用** ページマーカー `<<<PAGE N>>>` と章見出しマーカー入り |

### 3. 検索

```bash
python postprocess/search_ocr.py <merged_output_dir> "検索語"
```

出力例：

```
p.54	(offset=1523)	...諸国民の法を普遍人類法と見る見方があった。【グロティウス】は国際法...
p.122	(offset=45120)	...【国際慣習法】の成立には一般慣行と法的確信が...
```

主なオプション：

- `-i, --ignore-case`: 大文字小文字を区別しない
- `-F, --fixed-strings`: 検索パターンを正規表現ではなくリテラル文字列として扱う
- `-c, --context N`: ヒット前後の文脈**文字数**（既定 30）

---

## 内部仕様

### `build_merged_text.py` の処理ルール

XML中の各 `<LINE>` を**XML文書順**で処理する（NDLOCR本家の `.txt` 出力と同じ順序。`ORDER` 属性はXY-cut評価時の内部指標であり最終読み順ではないため採用しない）。`TYPE` に応じて以下のように扱う。

| `TYPE` | `body.txt` への扱い | `indexed.txt` への扱い |
|---|---|---|
| `本文` | そのまま連結（改行なし） | そのまま1行として出力 |
| `タイトル本文` | 直前が本文なら改行を1つ挿入（章境界として分離） | `[見出し] ...` プレフィックス付きで出力 |
| `キャプション` / `頭注` / `割注` / `広告文字` | 除外 | 除外 |
| （`<BLOCK TYPE="柱">`） | もともと `LINE` ではないため自然に除外 | 同左 |

ページ境界は `body.txt` には一切マーカーを入れず、`indexed.txt` にのみ `<<<PAGE N>>>` を入れる。これにより `body.txt` はページ跨ぎ検索語にも対応可能。

### `page_index.json` の形式

```json
{
  "meta": {
    "title": "...",
    "source_pdf": "...",
    "generated_at": "2026-04-23T10:00:00",
    "ocr_dir": "...",
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

### `search_ocr.py` の動作

1. Python の ``re.finditer(pattern, body_text)`` でヒット箇所を列挙
2. 各ヒットの文字オフセットをUTF-8バイトオフセットに変換
3. `page_index.json` を読み込み、`bisect.bisect_right` で該当ページを特定
4. 各ヒットの前後N byte を `body.txt` のバイト列から切り出し、一致部を `【…】` で囲った文脈として表示

---

## 設計上の考慮事項

- **TEXTBLOCK単位の改行は入れない**: NDLOCRのTEXTBLOCKは物理的な領域ブロックであり、意味的な段落ではない。改行を入れるとページ跨ぎ連結が阻害されるため、本文内の区切りは `タイトル本文` 行との境目だけに限定している。
- **ページ索引の空ページ対応**: 本文の無いページ（白紙・索引ページ等）もエントリを記録する。同一バイトオフセットの複数ページが並ぶが、`bisect_right` で正しく直近の実本文ページに解決される。
- **改行コード**: `body.txt` / `page_index.json` / `indexed.txt` すべてLF（`\n`）で統一（Windows環境でもそのまま `rg` が動作する）。
- **本家との衝突回避**: `postprocess/` ディレクトリは本家 `ndl-lab/ndlocr-lite` には存在しないため、`git merge upstream/master` で衝突しない。
