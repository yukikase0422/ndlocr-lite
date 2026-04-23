# Sub-C: Claude Codeカスタムスラッシュコマンド調査

## 担当範囲
Claude Codeのカスタムスラッシュコマンドが**スキル一覧に載らない**ように実装する方法の調査

## 目的
NDLOCR関連の文字起こし生成手順をスラッシュコマンド化したいが、スキル一覧（常時コンテキストにロードされる）には載せたくない。スキル一覧への登録を回避しつつ、スラッシュコマンドとして機能させる方法を調査する。

## ToDoリスト

### 詳細検索スキルの手順に従った調査

- [x] 1. 検索計画の作成
- [x] 2. 検索の実行
- [x] 3. 検索結果の評価
- [x] 4. 情報収集状況の検証
- [x] 5. 追加検索の判断と実行（不要と判断）
- [x] 6. 回答の生成（調査結果の整理）→ Issue #2 にコメント投稿完了

### 調査すべき具体事項

- [x] 1-1. Claude Codeのカスタムスラッシュコマンドとは何か
  - [x] 公式ドキュメント上の位置付け
  - [x] 配置場所（`~/.claude/commands/` / `.claude/commands/`）
  - [x] ファイル形式（Markdown? YAML frontmatter? スクリプト?）

- [x] 1-2. スラッシュコマンドとスキルの違い
  - [x] Skillとの構造上の差異
  - [x] descriptionの常時ロード有無
  - [x] 実行の仕組み

- [x] 1-3. スキル一覧にロードされないスラッシュコマンドの作り方
  - [x] `commands/` ディレクトリの挙動
  - [x] 何らかのフラグの有無
  - [x] 既存プラグイン実装例の確認

- [x] 1-4. ユーザ環境のローカル情報の確認
  - [x] `C:/Users/yukik/.claude/commands/` の確認
  - [x] Claude Codeバージョン・環境変数の確認

- [x] 1-5. NDLOCR文字起こし生成用コマンドの設計提案

## 作業記録

### 開始時刻
2026-04-23

### 進捗状況

#### ステップ1: 検索計画の作成 [completed]

**検索計画**:

| # | 検索目的 | 検索手段 |
|---|---------|---------|
| A | Claude Codeの公式ドキュメントでカスタムコマンド/スラッシュコマンドの仕様を確認 | WebSearch + WebFetch (docs.anthropic.com) |
| B | Claude Codeのカスタムコマンドとスキルの違いを公式ドキュメントで確認 | WebSearch + WebFetch |
| C | ユーザ環境の既存commands/ディレクトリの確認 | ローカルファイル読み取り (Glob + Read) |
| D | ユーザ環境の既存skills/ディレクトリの確認（比較用） | ローカルファイル読み取り |
| E | ユーザ環境のsettings.jsonでコマンド関連設定の確認 | Read |
| F | 既存プラグインの実装例確認（commit-commands, superpowers等） | ローカルファイル読み取り |
| G | GitHubでClaude Codeカスタムコマンド実装例の検索 | gh search |

#### ステップ2: 検索の実行 [completed]

**実行済み検索**:

- [x] A: 公式ドキュメント https://code.claude.com/docs/en/slash-commands を取得
- [x] B: 上記ドキュメントにcommands/とskills/の違いが記載されていた
- [x] C: `C:/Users/yukik/.claude/commands/` に6件の既存コマンドを確認
- [x] D: `C:/Users/yukik/.claude/skills/` に4件の既存スキルを確認
- [x] E: `C:/Users/yukik/.claude/settings.json` を確認
- [x] F: `commit-commands:commit`、`feature-dev:feature-dev` の実装を確認

#### ステップ3: 検索結果の評価 [completed]

**核心的な発見**:

公式ドキュメント（https://code.claude.com/docs/en/slash-commands）より、以下が確認できた:

1. **commands/とskills/は統合された**: 
   > "Custom commands have been merged into skills. A file at `.claude/commands/deploy.md` and a skill at `.claude/skills/deploy/SKILL.md` both create `/deploy` and work the same way."

2. **`disable-model-invocation: true` フラグの効果**:
   > "Set to `true` to prevent Claude from automatically loading this skill. Use for workflows you want to trigger manually with `/name`. Also prevents the skill from being preloaded into subagents. Default: `false`."
   
   これが**スキル一覧から除外する方法**である。

3. **descriptionの常時ロードの仕組み**:
   - `description` はスキル一覧としてコンテキストにロードされる（1,536文字制限）
   - `disable-model-invocation: true` を設定すると、descriptionもコンテキストに入らない

4. **commands/ディレクトリは引き続き動作**:
   > "Your existing `.claude/commands/` files keep working. Skills add optional features: a directory for supporting files, frontmatter..."

#### ステップ4: 情報収集状況の検証 [completed]

**回答に十分な情報が得られた**。追加検索は不要。

#### ステップ5-6: 回答の生成 [completed]

Issue #2 に調査結果コメントを投稿完了: https://github.com/yukikase0422/ndlocr-lite/issues/2#issuecomment-4302620117

---

## 完了報告

**全タスク完了**。Issue #2 に `[Sub-C]` プレフィックス付きで調査結果を投稿した。
