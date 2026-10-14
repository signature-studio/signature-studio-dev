# AGENTS.md — エージェント規約 (AI / 人間共通)

Signature Studio (webstudio) のリポジトリで作業する**全エージェント (AI / 人間)** が従う規約。
本書は**必読 1 枚サマリ**。運用の詳細は `docs/WORKFLOW.md`、ドキュメント索引と責務は
`docs/DOC_MAP.md` が正本。本書はそれらへの導線だけを持ち、**規約本文は複製しない**。

| 読み順 | ファイル | 役割 |
|---|---|---|
| 1 | `README.md` | 何のプロジェクトか・docs/tools の地図と索引・開発コマンド |
| 2 | `docs/ARCHITECTURE.md` | パイプライン全体像 |
| 3 | `docs/STATUS.md` | 技術進捗の正本 (MS 番号・サブシステム 1 行ステータス) |
| 4 | `docs/DECISIONS.md` | 方式決定と理由 (ADR) |
| 5 | `docs/WORKFLOW.md` | subagent 運用・PR・レビュー・検収の**詳細** |
| 6 | `docs/REFERENCES.md` | 外部ソース・素材・ツール・vendored 台帳 |
| 7 | `docs/DOC_MAP.md` | REPORT.md 索引・行数上限ルール・ドキュメント責務の正本 |
| 8 | `docs/DEFECTS.md` | lift の silent miscompile 類型 (D1a〜D23) |
| 9 | `docs/LEGAL.md` | ライセンス/規約上の運用制約 |
| 10 | `docs/HANDOFF/<日付>.md` | 最新の引継ぎ |
| 11 | `docs/pm/DIRECTIVES.md` | ユーザ指示の逐語原文 (依頼の正本) |
| 12 | `docs/pm/PREDECESSOR_ANALYSIS.md` | 前任 PM セッションの分析 (現行規約がこうなった理由) |

---

## 1. 基本フロー

```
ブランチを切る → worktree 作成 → 実装 subagent → レビュー subagent → PM (main) がマージ
```

- **既定ブランチは `main`**。旧 `master` は `main` の祖先で凍結した過去枝。
  `main` への直接 commit・push は禁止 — `docs/WORKFLOW.md` §1-1・§7。
- **全作業は subagent 委任**。1 チケット = 1 subagent、10 tool call 超は必ず委任 —
  `docs/WORKFLOW.md` §7。
- worktree は親 dir の `ws-<N>`。main の共有ワークツリーは触らない — `docs/WORKFLOW.md` §2。
- **検収は独立 subagent**。approve / request changes の 2 値。merge は検収の approve 後に検収 / PM が行い、
  実装者は自分の PR を merge しない (Auto Merge を含む)。自分で完了にしない —
  `docs/WORKFLOW.md` §2・§3・§5。
- PR は `--base main`。body に `Closes #N`・受入条件・検証結果 — `docs/WORKFLOW.md` §7・§9。

## 2. ドキュメント責務 (原則)

- **測定値・実測数値は `tools/<area>/REPORT.md` だけ**。外側は「結論 1 行 + リンク」に縮める。
- **状態は `docs/STATUS.md`・運用は `docs/WORKFLOW.md`・外部資産は `docs/REFERENCES.md`・
  索引は `docs/DOC_MAP.md`**。同じ数値を 2 ファイルに書かない。
- ファイルごとの単一責任・「書いてはいけないもの」の詳細表は **`docs/DOC_MAP.md` §4 が正本**。

## 3. 命名規則

- **Issue タイトル**: `[AREA-n]` prefix + 英語表題。AREA 一覧は **`docs/WORKFLOW.md` §9 が正本**
  (`n` は AREA 内の連番。重複タイトルを作らない)。
- **commit / PR**: conventional commits。scope はサブシステム名。`git add <dir>` +
  `git commit -- <dir>` (`git add -A` / `git add .` 禁止)。誤記は
  `fix(<name>): report corrections` で別コミット — `docs/WORKFLOW.md` §7。
- **branch**: `<N>-<slug>` (N = issue 番号) / **worktree**: `ws-<N>`。
- 破壊的 git 操作 (`reset --hard` / `push --force` / `stash` / 他 branch checkout) は禁止 —
  `docs/WORKFLOW.md` §1。

## 4. 禁止事項 (絶対・詳細は `docs/WORKFLOW.md` §1)

1. repo 外絶対パス (`/home/<user>/...`・`/opt/...`) の羅列 — `docs/REFERENCES.md` のエントリ ID
   (`[WIN64]`・`[EMSDK]` 等) で参照。
2. preflight 読了証跡 (ハッシュ 1 行) の羅列 — 廃止 (`docs/DECISIONS.md` D6)。
3. 同一測定値の二重 (以上) 記載 — 測定値は REPORT だけ。
4. `tools/**/work/`・`tools/**/venv/`・`node_modules/`・`dist/`・`.wrangler/` への作業
   (gitignore 対象・vendored / 検証スナップショット)。
5. `git push --force`・`git reset --hard`・`git stash`・`git checkout .`・`git clean`・
   他 branch checkout。
6. 既定ブランチ (`main`) への直接 commit・push、main worktree での作業。
7. Linear への書き込み (2026-10-12 廃止)・`state:*` ラベルの新規作成・付与。
8. 自動生成ドキュメント (`results/*.md`・inventory 系) の人手編集 — 生成元を直す。
9. REPORT の行を「古いので」と削除して内容を失う — 上限超過は**分割移動** (Git 履歴に残す)。

## 5. 原典・正本を引く順

`docs/DECISIONS.md` (方式決定) → `docs/STATUS.md` (状態) → `docs/WORKFLOW.md` (運用) →
`tools/<area>/REPORT.md` (測定値) → `docs/REFERENCES.md` (外部資産)。
