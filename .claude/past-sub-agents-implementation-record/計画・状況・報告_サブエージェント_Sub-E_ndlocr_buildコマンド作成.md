# 計画・状況・報告 - Sub-E: ndlocr-buildコマンド作成

## 指示内容

Claude Code カスタムスラッシュコマンド `/ndlocr-build` を作成する。

## 目的

PDF/画像からNDLOCR文字起こしを一括生成するスラッシュコマンドを作成し、ユーザがコマンド一発でOCR処理を実行できるようにする。

## 配置先

`C:/Users/yukik/.claude/commands/ndlocr-build.md`

## 設計根拠

Sub-C の調査結果（Issue #2 コメント参照）により以下が確定済み:

1. `commands/` と `skills/` は統合されており `/name` で呼び出せる
2. `disable-model-invocation: true` を指定するとスキル一覧に表示されない
3. これによりコンテキスト圧迫なしで手動呼び出しのみのコマンドを実現可能

## 制約

- fork repo (`yukikase0422/ndlocr-lite`) へのコマンドファイルのコミットは行わない
- 本作業記録ファイルのみ fork repo 内に配置

---

## ToDoリスト

- [x] Issue #2 のコメント確認（Sub-C 調査結果含む）
- [x] 既存の commands ディレクトリ構造確認
- [x] `build_merged_text.py` の引数・オプション確認
- [x] 指示作成の原則に従ったコマンドファイル作成
- [x] コマンドファイル配置
- [x] YAML frontmatter 構文妥当性検証
- [x] スキル一覧への非表示確認（disable-model-invocation の効果）
- [x] Issue #2 へのコメント投稿
- [x] 作業記録ファイル最終更新

---

## 作業ログ

### 2026-04-23 開始

#### 確認した情報

1. **Issue #2 コメント**: Sub-C の調査結果を確認。`disable-model-invocation: true` でスキル一覧に載らないことが確定。

2. **既存 commands ディレクトリ**: 
   - `C:/Users/yukik/.claude/commands/` に複数のコマンドが存在
   - 全て `disable-model-invocation: true` を使用

3. **既存コマンド形式の参考例** (`setup-obsidian-jp.md`):
   ```yaml
   ---
   description: Obsidian Vaultに日本語段落字下げ設定を一括適用
   argument-hint: [vaultパス | --all]
   disable-model-invocation: true
   ---
   ```

4. **`build_merged_text.py` の仕様**:
   - 入力種別: PDF / 単一画像 / 画像フォルダ / 複数ファイル引数
   - オプション:
     - `--combine none|name-order|custom-order`: 画像フォルダ入力時の結合方針
     - `--order-file <path>`: custom-order用順序指定ファイル
     - `--skip-ocr`: OCR実行スキップ（後処理のみ）
     - `--dpi N`: PDF画像化DPI（既定300）

#### コマンドファイル作成

初回作成時に `argument-hint` の `[` と `|` が YAML 特殊文字として解釈されてエラーとなった。引用符で囲んで修正。

#### 動作確認

1. **YAML構文妥当性**: Python `yaml.safe_load()` で検証し、正常に解析されることを確認
2. **スキル一覧非表示**: system-reminder のスキル一覧に `ndlocr-build` が含まれていないことを確認（`disable-model-invocation: true` の効果）

#### Issue コメント投稿

https://github.com/yukikase0422/ndlocr-lite/issues/2#issuecomment-4302862824

---

## 成果物

### 作成したファイル

- `C:/Users/yukik/.claude/commands/ndlocr-build.md`

### 未検証項目

1. 実セッションでの `/ndlocr-build <path>` 呼び出し
2. `allowed-tools: Bash` の許可範囲の十分性
3. 長時間実行時のタイムアウト

### 既知のリスク

1. `allowed-tools` が `Bash` のみのため、エラー発生時にファイル確認が必要な場合は `Read` ツール追加が必要になる可能性
2. `build_merged_text.py` の絶対パスがハードコードされているため、将来的にコマンド化した場合は書き換えが必要

---

## 完了

全タスク完了。ユーザによる実運用時の検証が残る。
