# 計画・状況・報告: Sub-B フック・流入文面更新

## 指示概要
`~/.claude/` 側のフック・流入文面を更新する。SKILL.md削除、流入文面を別ファイル化、`ndlocr-post-tool.sh` の正規表現を新命名に合わせて更新。

## 担当範囲
- ユーザ環境設定（fork repoへのcommitなし）
- 変更内容はIssue #2にコメントで全文記録

## ToDoリスト

### 0. 事前調査（必須）
- [x] past-issue-finderで過去のフック作成時の問題を調査
- [x] 調査結果を記録

**調査結果サマリ:**

1. **PostToolUseフックのJSON出力形式**（2025-11-28記録）
   - ブロックでも `exit 0` 必須（exit非0ではJSON無視）
   - additionalContextはJSON形式 `{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "..."}}` で出力
   - Write-Error/Write-Host等では表示されない、JSON出力のみ有効

2. **stdin読み取りのエンコーディング問題**（2025-11-21, 2026-04-19記録、4度再発）
   - `[Console]::In.ReadToEnd()` は使用禁止（CP932扱いで文字化け）
   - 確定パターン: StreamReader + UTF-8
   - 現行の ndlocr-post-tool.sh は bash で python を使用しており、`PYTHONIOENCODING=utf-8` と `PYTHONUTF8=1` を設定済みで問題なし

3. **PowerShell日本語コメント構文エラー**（2026-04-19記録）
   - BOMなしUTF-8 + 日本語コメント多用でパースエラー
   - 今回は bash スクリプトなので直接影響なし

4. **現行スクリプトの落とし穴対応状況**
   - `flock` なし → ファイル存在チェックで代替（対応済み）
   - `python3` → `python` 使用（対応済み）
   - `$USER` 未定義 → `${USER:-}` で対処（対応済み）
   - PYTHONIOENCODING/PYTHONUTF8 設定済み

### 1. SKILL.md の削除
- [x] `~/.claude/skills/ndlocr-search/SKILL.md` を削除
- [x] `~/.claude/skills/ndlocr-search/` ディレクトリも削除

### 2. 流入文面の別配置
- [x] `~/.claude/hooks/ndlocr-context/message.md` を作成
- [x] ユーザ指定の文面を配置

### 3. `ndlocr-post-tool.sh` の正規表現更新
- [x] 検出正規表現を新命名方式に対応
- [x] SKILL_PATH参照を MESSAGE_PATH に書き換え

### 4. 動作検証
- [x] シナリオ1: NDLOCR新命名パターン含むtool_input → additionalContext返却（message.md全文）
- [x] シナリオ2: 同セッション2回目 → noop（{}）
- [x] シナリオ3: NDLOCR新命名パターン含まない入力 → noop（{}）
- [x] シナリオ4: SessionStartフック発火 → フラグ削除確認（成功）
- [x] シナリオ5: クリア後に再度NDLOCR新命名入力 → 再流入成功
- [x] 追加: _NDLOCR/ ディレクトリパターン → 流入成功

### 5. settings.json の確認
- [x] matcherの確認: `Read|Grep|Glob|Bash|Edit|Write` で問題なし
- [x] 変更不要（バックアップ取得不要）

### 6. Issue #2 へのコメント投稿
- [x] `[Sub-B]` プレフィックス付きでコメント投稿
  - URL: https://github.com/yukikase0422/ndlocr-lite/issues/2#issuecomment-4302677047

## 進行状況

### 2026-04-23 作業開始
- completed: Issue #2の最新コメント確認完了
- completed: 既存ファイル読み取り完了
- completed: past-issue-finder調査完了
- completed: SKILL.md削除、ディレクトリ削除
- completed: message.md作成
- completed: ndlocr-post-tool.sh更新（正規表現、パス参照）
- completed: 動作検証（6シナリオすべて成功）
- completed: settings.json確認（変更不要）
- completed: Issue #2コメント投稿

### 2026-04-23 作業完了
全タスク完了
