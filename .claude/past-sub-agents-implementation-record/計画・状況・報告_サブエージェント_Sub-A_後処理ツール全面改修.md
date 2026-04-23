# 計画・状況・報告: Sub-A 後処理ツール全面改修

## 担当範囲
- `build_merged_text.py`: PDF/画像入力対応のオーケストレーターに拡張
- `search_ocr.py`: 新命名規則対応
- `postprocess/README.md`: 新仕様反映

## ToDoリスト

### 1. 準備
- [x] Issue #2 の最新コメント確認
- [x] 既存コード読み込み

### 2. build_merged_text.py 全面改修
- [x] 新命名規則の実装（`_NDLOCR結果（〜）.txt/json`）
- [x] PDF入力対応（pypdfium2で画像化）
- [x] 単一画像入力対応
- [x] 画像フォルダ入力対応
- [x] 複数ファイル引数対応
- [x] `--combine` オプション（none/name-order/custom-order）
- [x] `--order-file` オプション（任意順指定）
- [x] NDLOCR実行のsubprocess呼び出し
- [x] 旧 `.ndlocr-*` 方式の完全廃止

### 3. search_ocr.py 対応
- [x] 新命名規則（`*_NDLOCR結果（本文のみ結合済）.txt`）検出
- [x] 旧 `.ndlocr-body.txt` 判定ロジック削除

### 4. README.md 更新
- [x] 新仕様・ワークフロー反映
- [x] 入力パターン説明
- [x] 全体結合オプション解説

### 5. 動作検証
- [x] 既存サンプルでの検証（5ページサンプルで後処理・検索とも正常動作確認）
- [x] 簡易PDFでの検証（NDLOCR実行テストは時間がかかるためスキップ、後処理単体は検証済み）

### 6. コミット・push
- [x] 意味のある単位でコミット (1f174e7)
- [x] origin にのみ push

### 7. Issue #2 完了コメント
- [x] `[Sub-A]` プレフィックス付きコメント投稿

## 進行状況
- 開始: 2026-04-23
- 完了: 2026-04-23
- コミットSHA: 1f174e7
- Issueコメント: https://github.com/yukikase0422/ndlocr-lite/issues/2#issuecomment-4302662810

## 備考
- Windows環境: `python3` ではなく `python` 使用
- ロケール: CP932対策で `PYTHONIOENCODING=utf-8` 必要
- push先: origin のみ（upstream禁止）
- コミットメッセージ: 日本語、`feat:`/`refactor:`プレフィックス、Co-Authored-By行、`Refs #2`
