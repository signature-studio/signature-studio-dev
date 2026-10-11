# AGENTS.md — エージェント規約 (AI / 人間共通)

Signature Studio (webstudio) のリポジトリで作業する**全エージェント (AI / 人間)** が従う規約。
運用の詳細は `docs/WORKFLOW.md` が正本。本書は**他ファイルと重複しない規約** (フロー・責務マップ・命名・禁止) を扱う。

| 読み順 | ファイル | 役割 |
|---|---|---|
| 1 | `README.md` | 何のプロジェクトか・docs/tools の地図と索引・開発コマンド |
| 2 | `docs/ARCHITECTURE.md` | パイプライン全体像 |
| 3 | `docs/STATUS.md` | 状態の唯一の正本 (MS 番号・サブシステム 1 行ステータス) |
| 4 | `docs/DECISIONS.md` | 方式決定と理由 (ADR) |
| 5 | `docs/WORKFLOW.md` | subagent 運用・PR・レビュー・検収 |
| 6 | `docs/REFERENCES.md` | 外部ソース・素材・ツール・vendored 台帳 |
| 7 | `docs/DOC_MAP.md` | REPORT.md 索引・行数上限ルール |
| 8 | `docs/DEFECTS.md` | lift の silent miscompile 類型 (D1a〜D16) |
| 9 | `docs/LEGAL.md` | ライセンス/規約上の運用制約 |
| 10 | `docs/HANDOFF/<日付>.md` | 最新の引継ぎ |

---

## 1. 基本フロー (破壊的ブレークスルーを先導する)

```
ブランチを切る → worktree 作成 → 実装 subagent → レビュー subagent → PM (main) がマージ
```

- **`master` / `main` には変更を加えない** (直接 commit・`git push origin master` 禁止)。
- **全作業は subagent 委任**。**1 チケット = 1 subagent**。チケット化されていない作業も subagent で行う。
  10 回以上の tool call が必要になる作業は必ず subagent に委任する。
- worktree の場所は `/home/ubuntu/work/ws-<N>` (N = issue 番号)。
  共有ワークツリー `/home/ubuntu/work/webstudio` は main のもの。**絶対に触らない。**
- 詳細: `docs/WORKFLOW.md` §1〜§2。

## 2. ドキュメント責務マップ (最も重要なセクション)

**「何をどこに書くか」の単一責任の割り当て。** 重複を作らないこと。

| ファイル | 単一責任 | **書いてはいけないもの** |
|---|---|---|
| `README.md` | 何のプロジェクトか (1〜2 行) / **docs・tools の地図と索引** / 開発コマンド / デプロイ 3 行要約 | 測定値・実測数値・repo 外絶対パス・進捗の詳細 |
| `AGENTS.md` (本書) | エージェント規約・フロー・責務マップ・命名規則・禁止事項 | 測定値・技術的な手順・状態の詳細 |
| `docs/ARCHITECTURE.md` | パイプライン全体像 (x64c → liftlib → wasm → shim → runtime → deploy) | 測定値・個別バグ・issue 個別の経緯 |
| `docs/STATUS.md` | **状態の唯一の正本** (MS 番号・サブシステム 1 行ステータス・次の一手) | 測定値・数値の詳細 (REPORT へのリンクにする) |
| `docs/DECISIONS.md` | ADR: 方式決定・理由・日付 | 測定値・検証手順 |
| `docs/WORKFLOW.md` | subagent 運用・PR・レビュー・検収・自己点検 | 技術的な実装手順・測定値 |
| `docs/REFERENCES.md` | 外部ソース・素材・ツール・**vendored 台帳**。**repo 外絶対パスはここだけ** | repo 内パス・技術内容 |
| `docs/LEGAL.md` | ライセンス/規約上の運用制約と事実整理 | 技術実装・数値実測 |
| `docs/DOC_MAP.md` | REPORT.md 索引・行数上限ルール・自動生成一覧 | 技術内容・測定値 |
| `docs/DEFECTS.md` | lift silent miscompile 類型 D1a〜D16 (横断正本) | 個別ケースの詳細 (report 側) |
| `docs/HANDOFF/<日付>.md` | 引継ぎ要約 (方針・ブロッカー・次の一手)。最新のみ保持 | 状態の正本 (STATUS.md へ)・数値の羅列 |
| `tools/<area>/REPORT.md` | **測定値・実測数値・検証結果の単一の正本** | なし (ここが正本) |
| `tools/<area>/README.md` | **ナビゲーションのみ** (何をする dir か・E2E コマンド・関連ファイル) | 測定値・状態表 |
| `tools/<area>/{PROTOCOL,FORMAT,ABI,MANIFEST,STARTUP,GATES,BACKLOG,inventory}.md` | 仕様・台帳 (現状は良い設計・維持) | 測定値 |
| `tools/<area>/results/*.md`・inventory 系 | **自動生成**。先頭 1 行に `自動生成: <cmd>` | **人手編集禁止** |
| `deploy/` | デプロイ単独 (README からは 3 行 + リンクだけ残す) | 測定値 |

**鉄則**: 同じ数値を 2 ファイルに書かない。外側は「結論 1 行 + リンク」に縮める。

## 3. 命名規則

### Issue タイトル

- **`[AREA-n]` prefix + 英語の conventional 書式** (PM が策定)。
- `AREA` はサブシステム識別子。過去の採番は尊重する:

  | AREA | 対象 | 例 |
  |---|---|---|
  | `KH` | Kilohearts | `[KH-2b]` |
  | `PLG` / `P0c` | plugins / 継続番号 | `[PLG-P0c]` |
  | `SHX` / `T-SH` | shimx / shim | `[SHX-T3]` |
  | `AU` | audio | — |
  | `HB` | hostbridge | `[HB-H2]` |
  | `IPP` | Intel IPP | `[IPP-7]` |
  | `LIFTLIB` / `L` | liftlib | — |
  | `RT` | runtime | — |
  | `GUI` | gui | — |
  | `SR` | serum2 | — |
  | `MX` | massivex | — |
  | `FA` | freshair | — |
  | `OTT` | ott | — |
  | `E2E` | e2e | — |
  | `LGL` | legal | — |
  | `ST` | startup | — |
  | `PY` | python | — |
  | `PERF` | perf | — |
  | `LD` / `ICALL` | liftdiff / icall | — |
  | `M11` | flelift 起動系 | — |

- **作ってはいけない表記**: `[HB-H4']`・`[HB-H4'']`・`[ユーザ依頼]` のような記号付き・日本語 prefix。
  prefix と `needs-user-input` ラベルの二重表現もしない。
- 起票前に `gh issue list --search "<kw>"` で重複確認。**重複タイトルを作らない。**

### コミット

- **conventional commits**。観察された既存書式に準拠:
  - `fix(ipp): ...`
  - `feat(flelift): ... (CAB-252)`
  - `docs(plugins): p0c report issue/pr refs (CAB-253)`
  - `docs(liftlib): LIFTLIB-4 report (CAB-272)`
  - `fix(shimx): report corrections (CAB-271)`
- scope はサブシステム名 (`ipp`, `flelift`, `liftlib`, `shimx`, `plugins`, `docs`, `agents`, `kh`, `massivex`…)。
- 過去の `CAB-xxx` 採番を末尾に括弧で参照してよい。commit はスコープ付き
  (`git add <dir>` + `git commit -- <dir>`)、`git add -A` / `git add .` 禁止。
- 誤記は `fix(<name>): report corrections` で別コミット (検収任せにしない)。

### PR

- タイトルは commit と同じ conventional commits 書式。
- body: `Closes #N` / 受入条件 / 検証結果 (実測・数え方の定義)。
- `--base master` を基本。

### ブランチ / worktree

- branch: `<N>-<slug>` (N = issue 番号。例 `254-arg-pass-abi`)。
- worktree: `/home/ubuntu/work/ws-<N>`。
- 破壊的 git 操作 (`reset --hard` / `push --force` / `stash` / 他 branch checkout) は禁止。

## 4. レビュー規約

- **全 PR は独立した検収 subagent の review を通過してから merge** (PM がマージ)。
- 検収は e2e 独立再実行 + **別アルゴリズム**の検算 + ネガティブコントロールを実施
  (`docs/WORKFLOW.md` §5)。
- 誤記・誇張は PR branch に `fix(<name>): report corrections` を追加して push。
- 判定は **approve / request changes** の 2 値。条件付きは In review 維持 + 所見コメント。
- 自分で自分を検収しない。自分のチケットを Done にしない (実装は In review で報告)。

## 5. CI 期待事項

- `.github/workflows/opencode.yaml` (OpenCode セットアップ・検証) が PR で緑であること。
- マージ前にローカルで少なくとも `pnpm typecheck`・`pnpm build` を実行し結果を REPORT に書く。
  (`pnpm runtime:e2e` は任意。長時間 e2e は数十分かかるため報告に実測秒を添える。)
- `feat/add-opencode` への GitHub Actions 移行が進行中 (優先度高・他作業と並行可能)。
- **20 MiB 超 blob の commit 禁止** (GitHub hard limit)。commit 前に
  `find <dir> -type f -size +20M -not -path '*/work/*'` を確認。

## 6. 禁止事項 (絶対)

1. **repo 外絶対パス (`/home/ubuntu/work/...`, `/opt/...`) の羅列を repo 内 .md に書く** —
   外部パスは `docs/REFERENCES.md` のエントリ ID (`[WIN64]`・`[EMSDK]` 等) で参照する。
2. **preflight 読了証跡 (ハッシュ 1 行) の羅列** — 廃止 (`docs/DECISIONS.md` D6・`docs/WORKFLOW.md` 冒頭参照)。
   検証手順は `docs/WORKFLOW.md` §6 に一本化。
3. **同一測定値の二重 (以上) 記載** — 測定値は `tools/<area>/REPORT.md` だけに書く。
4. **`tools/**/work/` と `tools/**/venv/` への作業** — vendored / 検証スナップショット。
   gitignore 対象・絶対に触らない・commit しない。
5. **`node_modules/`・`dist/`・`.wrangler/` への作業** (gitignore 対象)。
6. **`git push --force` / `--force-with-lease` (他人 branch)**・`git reset --hard`・
   `git stash`・`git checkout -- <他人のfile>`・`git checkout .`・`git clean`。
7. **他ブランチへの checkout / main worktree (`/home/ubuntu/work/webstudio`) への作業。**
8. **旧 `master` / `main` への直接 commit・push。**
9. **Linear への書き込み** — 2026-10-12 廃止・読み取り専用の歴史データ。
10. **`state:*` ラベルの新規作成・付与** (全削除済み)。
11. **自動生成ドキュメント (`results/*.md`・inventory 系) の人手編集** — 生成元を直す。
12. **REPORT の行を「古いので」と削除して内容を失う** — 上限超過は**分割移動** (Git 履歴に残す)。

## 7. 原典・正本の対応

曖昧なときはこの順で正本を引く:

1. `docs/DECISIONS.md` (方式決定) → 2. `docs/STATUS.md` (状態) → 3. `docs/WORKFLOW.md` (運用) →
4. `tools/<area>/REPORT.md` (測定値) → 5. `docs/REFERENCES.md` (外部資産の所在)。

