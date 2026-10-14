# OpenCode GitHub Actions

Signature Studio の Issue/PR 駆動エージェント実行基盤。

このリポジトリの Issue / PR は作成が Collaborators のみに制限されている。
ただし public repo では第三者も既存 Issue にコメントできるため、
issue_comment での `/oc` 起動は `author_association` COLLABORATOR / MEMBER /
OWNER に限定している。アクセス制御はそのうえで、コメント本文に
`oc_actions_allow_write` を含めるかどうかで行っている。

### PM 用 GitHub App (bot) の `/oc`

PM Worker など **PM 用 GitHub App** が投稿した `/oc` も implement を起動する (#1949)。条件は repo 変数
`OC_PM_BOT_LOGIN` (App のログイン名。例 `oc-pm-for-signature-studio[bot]`) との**完全一致**と `user.type == 'Bot'`:

```
github.event.comment.user.type == 'Bot' && github.event.comment.user.login == vars.OC_PM_BOT_LOGIN
```

- **偽装できない**: App のログイン (`<slug>[bot]`) は GitHub が App に付与する。第三者は同じログインのコメントを
  作れない (`[bot]` 付きの名前は通常のユーザーに使えない)。`user.type == 'Bot'` も併せて見る。`author_association`
  による人の判定は変えていない。
- **未設定 (空) なら何も許可しない**: workflow の `if:` は `vars.OC_PM_BOT_LOGIN != ''` を併せて見る (未設定の変数は空文字になり、
  空の login との `==` が真になるのを防ぐ)。`prepare-event-context.sh` が同じ判定を二重に行い (確定判定。
  テストは `tests/test-dispatch-context.sh`)、空なら bot を通さない。
- 実装 App (`opencode-for-signature-studio[bot]`) と reviewer App は、変数に設定されても許可しない (agent 自身の
  コメントに `/oc` が含まれると自己起動のループになるため。設定の誤りを fail-closed にする)。
- `/oc` 本文の検査 (行頭アンカーの `COMMAND_RE`) は変わらない。
- **設定 (PM が行う。PR には含まれない)**: `gh variable set OC_PM_BOT_LOGIN --repo <R> --body 'oc-pm-for-signature-studio[bot]'`

`/oc` / `/opencode` は**行頭に 1 コマンドだけ**書いた行で発火する (箇条書き行や
文中の `/oc`・URL 内の `/oc/` では発火しない)。指示は同じ行か続く行に書くこと。

## 構成

| ファイル | 役割 |
|---|---|
| `workflows/opencode.yaml` | 起動トリガ (issue_comment `/oc`・pull_request・pull_request_review・workflow_dispatch) と 2 ジョブ (implement / review) |
| `actions/agent-setup/action.yml` | ツールチェイン (uv/pnpm/node26/bun/opencode) と R2 からの素材ダウンロード |
| `actions/opencode/action.yml` | `opencode auth import` → `opencode run --format json` (JSONL をファイルへ) → `Dump OpenCode events` が allowlist の投影 (text 全文・tool 名/状態/所要 ms/入力の先頭 200 文字・cost/tokens。tool の出力と生 JSONL はログに出さない) を job ログへ → `Write step summary` が text ブロックを全て順に + steps/cost を `$GITHUB_STEP_SUMMARY` とログへ |
| `scripts/install-opencode.sh` | opencode CLI のインストール (pin・指数バックオフ・フォールバック) |
| `scripts/prepare-event-context.sh` | untrusted なイベント値をファイルに隔離し、制御変数を `$GITHUB_ENV` へ 1 行ずつ書く |
| `scripts/assemble-prompt.sh` | イベント文脈を実装エージェント用プロンプトに流し込む |
| `scripts/assemble-reviewer-prompt.sh` | 同じ方式でレビュワー用プロンプトを組み立てる |
| `scripts/record-run-outcome.sh` / `review-recover.sh` | implement が PR を出さずに終わった issue への `oc:no-pr` ラベルと `<!-- oc-run-outcome: ... -->` マーカー、review の runner 打ち切りの即時再起動 (上限は review-retry 3 回。#1950)。詳細は `docs/WORKFLOW.md` §11 |
| `scripts/fix-progress.sh` / `verify-review-verdict.sh` / `reopen-pr.sh` | 差し戻し後の fix の進捗判定・往復の上限、verdict の検証、close -> reopen による review の再起動 (reopen は 3 回まで再試行。merge 済み・close 済みの PR は何もせず成功) |
| `prompts/implementer.md` | 実装エージェントの行動規範 (スコープ・commit 規約・実測必須・マージ方法・規約への導線) |
| `prompts/reviewer.md` | レビュワーエージェントの役割 (approve/request-changes・マージ) |

設計方針: **ロジックはファイルに、YAML には数行だけ**。プロンプトとイベント文脈は
`$RUNNER_TEMP` のファイルとして扱い、`$GITHUB_OUTPUT` / `$GITHUB_ENV` には
1 行のスカラー値だけを書き込む (heredoc のデリミタは入力で閉じられるため使わない)。

## フロー

1. Issue に `/oc <instruction>` をコメント (`oc_actions_allow_write` を含めると書き込み可)
   → **implement ジョブ**: イベント文脈の隔離 → App トークン取得 → checkout →
   素材 DL → プロンプト組み立て → OpenCode 実装 → コミット/push/PR 作成・Auto Merge 有効化
2. PR が open / synchronize / reopen → **review ジョブ**: 差分取得 →
   レビュワーエージェントが検証 → approve/request-changes → 必要なら `gh pr merge --merge --delete-branch`
3. PR に `/oc <instruction>` → コンフリクト解決などの追加作業

`pull_request` の `synchronize` (PR が更新されるたび) でも review ジョブが起動する。
同時実行は `concurrency.group` (PR/issue 単位) で直列化し、
`cancel-in-progress: false` なので、小さい push でも reviewer が 1 回ずつ走る。

fork からの PR は review ジョブの対象外 (`head.repo.full_name == github.repository`)。
`pull_request` イベントでは fork PR に secrets が渡らないため、App トークンの生成が
必ず失敗する。fork PR のレビューは人手で行う。

## opencode のインストール

インストールは **pin したバージョンを取得して `opencode --version` で実測確認する**。
`opencode.ai` の metadata API には依存しない。

取得元は次の順 (auto の場合):

1. **npm registry の tarball** (`@opencode/cli-<target>`)
2. **GitHub Releases の tarball** (`anomalyco/opencode` の `opencode-<target>.tar.gz` / `.zip`)
3. **公式インストーラ** (`--version` を渡すので metadata API を経由しない)

> なぜ npm が先か: `anomalyco/opencode` には tag `v2.0.26` / `v2.0.27` が
> 存在するが、`releases/download/v2.0.26/opencode-<target>.tar.gz` は 404 で、
> 2.x の release 資産は publish されていない (2026-10-12 時点)。
> `releases/latest` も `v1.19.0` のままで、**Releases 経路では 2.x を取れない**。
> 既定は「今の CLI」である 2.x に固定したいので、Releases (1.x の別 pin) は
> フォールバックに回す。

> `anomalyco/opencode-beta` は取得元にできない。2026-10-12 時点で公開済 release の
> 資産は `opencode-desktop-*` と electron-updater のメタデータのみで、CLI の tarball を
> 持たない (最新 tag は `v0.0.0-beta-19723` で、CLI 版より古い)。

Releases 系統と npm 系統はバージョントラックが異なる (Releases は 1.x、npm は 2.x)。
そのため pin も 2 本ある。既定値:

| 変数 | 既定 | 対象 |
|---|---|---|
| `OPENCODE_VERSION` | `2.0.26` | npm の `@opencode/cli-<target>` (第一経路) |
| `OPENCODE_RELEASE_VERSION` | `v1.19.0` | Releases の tag (フォールバック) |
| `OPENCODE_INSTALL_SOURCE` | `auto` | `auto` = npm → Releases → 公式 / `releases` / `npm` |
| `OPENCODE_RELEASE_SHA256` | (空) | 指定すると tarball の SHA-256 を検証する |

上書きは `workflow_dispatch` の入力、または repository variable
(`OPENCODE_VERSION` / `OPENCODE_RELEASE_VERSION` / `OPENCODE_INSTALL_SOURCE`) で行う。

## トークン

`actions/create-github-app-token` が返す installation token は 1 時間有効。
**runner 上で再発行する仕組みは無い。** GitHub-hosted runner には systemd の user
session が無いため、user timer による自動更新は動作しない。旧実装の
`mint-token.sh` + `systemd/token-refresh.*` は削除済み (更新されたトークンを
git / `gh` のどちらにも反映できない経路だった)。

そのため `actions/checkout` は `persist-credentials: false` とし、認証は
App トークンを明示的に渡す経路だけに統一している。ジョブは `timeout-minutes: 60`
で 1 時間以内に収まるようにしてある。

## R2 素材

バケット `signature-studio-artifacts`、オブジェクトは `artifacts/<prefix>.tar.zst`
という命名 (`.tar.zst` のまま置き、エージェントが必要に応じて `tar --zstd -xf` で展開)。

```
aws s3 cp s3://signature-studio-artifacts/artifacts/<prefix>.tar.zst "$HOME/artifacts" \
  --endpoint-url "https://$CF_ACCOUNT_ID.r2.cloudflarestorage.com"
```

**2026-10-12 時点でバケットは空** (全実行 404)。agent-setup は素材が欠けているとき
ジョブを落とすが、`artifacts-required: false` を渡せば警告付きで続行する。
その場合エージェントは素材なしで動くので、`$ARTIFACTS_DIR` を `ls` で確認し、
空なら「素材なしで e2e は実行できない」と報告して停止する。

## 設定

**Variables**: `OC_APP_CLIENT_ID` (必須)、`OC_REVIEW_APP_CLIENT_ID` (任意)、`OC_PM_BOT_LOGIN` (任意。PM 用 App の `/oc` を許可する。未設定なら許可しない)、
`OPENCODE_VERSION` / `OPENCODE_RELEASE_VERSION` / `OPENCODE_INSTALL_SOURCE` (任意)

**Secrets**: `OC_APP_PRIVATE_KEY`、`OC_AUTH_EXPORT`、
`CF_ACCOUNT_ID` / `CF_R2_ACCESS_KEY_ID` / `CF_R2_SECRET_ACCESS_KEY`

**任意**: `OC_REVIEW_APP_PRIVATE_KEY`。設定がない場合、レビュワーは実装 App と同一
identity になり **自分自身の PR を approve できない** (comment + 直接 merge に
フォールバック)。設定していても installation が `contents:write` /
`pull-requests:write` を grant していない場合は同じフォールバックになる。

`workflow_dispatch` の入力は `prompt` と opencode の pin 3 つ。dispatch は write
権限を持つ人手による起動なので、常に書き込み可として扱う。

## マージ戦略

このリポジトリは merge commit のみ許可されている:

```
allow_merge_commit: true
allow_squash_merge: false
allow_rebase_merge: false
```

`gh pr merge --squash` は必ず失敗する。プロンプトも `gh pr merge --auto --merge` /
`gh pr merge --merge --delete-branch` を使う。

## 規約

エージェントが従う規約の正本はリポジトリ内にある。
`AGENTS.md` (要約) と `docs/WORKFLOW.md` (詳細) を参照すること。
プロンプトには導線のみを記載し、規約本文は複製していない。

## 検証手順 (コミット後)

```
gh workflow run opencode.yaml --ref <branch> -f prompt="..."
# Issue コメント / PR open での自動起動も確認
```

ローカルで静的検査:

```
bash -n .github/scripts/*.sh
shellcheck .github/scripts/*.sh
actionlint .github/workflows/*.yaml
```