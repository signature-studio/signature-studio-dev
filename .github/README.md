# OpenCode GitHub Actions

Signature Studio の Issue/PR 駆動エージェント実行基盤。**この内容はコミット前にユーザーレビュー待ち。**

## 構成

| ファイル | 役割 |
|---|---|
| `workflows/opencode.yaml` | 起動トリガ (issue_comment `/oc` / `opencode`、pull_request opened、workflow_dispatch) と2ジョブ (implement / review) |
| `actions/agent-setup/action.yml` | ツールチェイン (uv/pnpm/node26/bun/zstd/opencode) + **GitHub App トークン自動リフレッシュ** (1h 期限対策) + **R2 からの素材ダウンロード** |
| `actions/opencode/action.yml` | `opencode auth import` (Console 認証) + `opencode run --format json` 実行 + **末尾 text イベントの抽出を $GITHUB_STEP_SUMMARY へ** |
| `scripts/assemble-prompt.sh` | イベント文脈 (コメント本文・issue/PR 番号・権限) をプロンプトテンプレートに流し込む |
| `prompts/implementer.md` | 実装エージェントの行動規範 (スコープ・commit 規約・e2e 実測必須・PR 作成) |
| `prompts/reviewer.md` | レビュワーエージェントの役割 (approve/deny・**Auto Merge が使えない場合はレビュワーがマージまで担当**) |

## フロー

1. Issue に `/oc <instruction>` をコメント (`oc_actions_allow_write` を含めると書き込み可)
   → **implement ジョブ**: App トークン取得 → checkout → 素材 DL → プロンプト組み立て → OpenCode 実装 → コミット/push/PR 作成・Auto Merge 有効化
2. PR が open → **review ジョブ**: PR diff を取得 → レビュワーエージェントが検証 → approve/request-changes → 必要なら `gh pr merge --squash --delete-branch`
3. PR に `/oc <instruction>` → コンフリクト解消などの追加作業

## トークン期限対策 (未検証→本 workflow で検証)

`actions/create-github-app-token` のトークンは 1 時間。エージェントが長時間動作すると push/gh が失敗する。
対策: agent-setup が App 秘密鍵から **JWT を自ミントして installation token を再発行するループ** (50 分間隔・最大 6 時間) を回し、
`gh` ラッパーと git credential helper が `$RUNNER_TEMP/gh_token` を都度読む (実行中プロセスでも新しいトークンが有効)。

## R2 素材

バケット `signature-studio-artifacts` (2026-10-11 作成)。`artifacts/` 配下に zstd tarball を配置:

| オブジェクト | サイズ | 内容 |
|---|---|---|
| `fl-win64.tar.zst` | 2.22 GiB | FL Studio win64 インストーラ + analysis/win64/extracted |
| `plugins-ott.tar.zst` | 165 MiB | OTT (DLL + インストーラ exe/dmg) |
| `plugins-serum2.tar.zst` | 2.46 GiB | Serum 2 インストーラ (exe + pkg) |
| `plugins-freshair.tar.zst` | 68 MiB | Fresh Air (zip + pkg) |
| `plugins-massivex.tar.zst` | 1.75 GiB | Massive X インストーラ (exe) |
| `plugins-kilohearts.tar.zst` | 3.55 GiB | Kilohearts offline installer (zip) |
| `manifest.json` | — | sha256・サイズ一覧 |

ダウンロードは `x-amz-content-sha256: UNSIGNED-PAYLOAD` + SigV4 の curl。runner では `$HOME/ダウンロード`・`$HOME/work/analysis` に展開。

## 設定 (要ユーザー)

**Variables** (作成済み): `OC_APP_CLIENT_ID`
**Secrets** (要追加):
- `OC_APP_PRIVATE_KEY` — 登録済み
- `OC_AUTH_EXPORT` — `opencode auth export` の出力 (OpenCode Console エントリのみを残した JSON)
- `CF_ACCOUNT_ID` / `CF_R2_ACCESS_KEY_ID` / `CF_R2_SECRET_ACCESS_KEY` — R2 読み取り用

**任意**: `OC_REVIEW_APP_CLIENT_ID` + `OC_REVIEW_APP_PRIVATE_KEY` (レビュワー用の第 2 App)。
設定がない場合、レビュワーは実装 App と同一 identity になり **自分自身の PR を approve できない**。
(comment + 直接 merge にフォールバック)

## 検証手順 (コミット後)

```
gh workflow run opencode.yaml --ref feat/add-opencode -f prompt="..."
# Issue コメント / PR open での自動起動も確認
```
