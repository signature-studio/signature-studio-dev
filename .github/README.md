# OpenCode GitHub Actions

Signature Studio の Issue/PR 駆動エージェント実行基盤。**この内容はコミット前にユーザーレビュー待ち。**

## 構成

| ファイル | 役割 |
|---|---|
| `workflows/opencode.yaml` | 起動トリガ (issue_comment `/oc` / `opencode`、pull_request opened、workflow_dispatch) と2ジョブ (implement / review) |
| `actions/agent-setup/action.yml` | ツールチェイン (uv/pnpm/node26/bun/opencode) + **GitHub App トークン自動リフレッシュ** + **R2 からの素材ダウンロード** |
| `actions/opencode/action.yml` | `opencode auth import` (Console 認証) + `opencode run --format json` 実行 + sessionID から `opencode api` で最後の assistant text を `$GITHUB_STEP_SUMMARY` へ |
| `scripts/mint-token.sh` | App 秘密鍵から installation token を再発行して `$RUNNER_TEMP/gh_token` に書く |
| `systemd/token-refresh.service` | `mint-token.sh` を 1 回実行する oneshot unit |
| `systemd/token-refresh.timer` | 50 分ごとに service を起こす timer (App token の有効期限は 1 時間) |
| `scripts/assemble-prompt.sh` | イベント文脈 (コメント本文・issue/PR 番号・権限) をプロンプトテンプレートに流し込む |
| `prompts/implementer.md` | 実装エージェントの行動規範 (スコープ・commit 規約・e2e 実測必須・PR 作成) |
| `prompts/reviewer.md` | レビュワーエージェントの役割 (approve/deny・**Auto Merge が使えない場合はレビュワーがマージまで担当**) |

設計方針: **ロジックはファイルに、YAML には数行だけ**。インライン bash の heredoc・ループ・python は置かず、必要な処理は `scripts/`・`systemd/` のファイルをコミットして `cp` + `systemctl --user` で配置する。

## フロー

1. Issue に `/oc <instruction>` をコメント (`oc_actions_allow_write` を含めると書き込み可)
   → **implement ジョブ**: App トークン取得 → checkout → 素材 DL → プロンプト組み立て → OpenCode 実装 → コミット/push/PR 作成・Auto Merge 有効化
2. PR が open → **review ジョブ**: PR diff を取得 → レビュワーエージェントが検証 → approve/request-changes → 必要なら `gh pr merge --squash --delete-branch`
3. PR に `/oc <instruction>` → コンフリクト解決などの追加作業

## トークン期限対策

`actions/create-github-app-token` のトークンは 1 時間。エージェントが長時間動作すると push/gh が失敗する。
対策: agent-setup が `scripts/mint-token.sh` と `systemd/` の unit を `~/.local/bin`・`~/.config/systemd/user` に配置し、
**user service** の timer (`token-refresh.timer`) で 50 分ごとにトークンを再発行して `$RUNNER_TEMP/gh_token` を更新する。
git は credential helper がこのファイルを都度読むので、実行中プロセスの push でも新しいトークンが使われる (sudo 不要)。

`systemctl --user` が使えない runner では警告を出してタイマー起動を諦める (ジョブは継続)。

## R2 素材

バケット `signature-studio-artifacts` (2026-10-11 作成)。`artifacts/` 配下:

```
aws s3 cp s3://signature-studio-artifacts/artifacts/<prefix> "$HOME/artifacts" \
  --recursive --endpoint-url "https://$CF_ACCOUNT_ID.r2.cloudflarestorage.com"
```

`.tar.zst` のまま置く (展開はエージェントが必要に応じて `tar --zstd -xf`)。認証情報は repository secrets から (未設定なら notice を出してスキップ)。

## 設定 (要ユーザー)

**Variables** (作成済み): `OC_APP_CLIENT_ID`
**Secrets** (要追加):
- `OC_APP_PRIVATE_KEY` — 登録済み
- `OC_AUTH_EXPORT` — `opencode auth export` の出力 (OpenCode Console エントリのみを残した JSON)
- `CF_ACCOUNT_ID` / `CF_R2_ACCESS_KEY_ID` / `CF_R2_SECRET_ACCESS_KEY` — R2 読み取り用

**任意**: `OC_REVIEW_APP_CLIENT_ID` + `OC_REVIEW_APP_PRIVATE_KEY` (レビュワー用の第 2 App)。
設定がない場合、レビュワーは実装 App と同一 identity になり **自分自身の PR を approve できない**。
(comment + 直接 merge にフォールバック)

`workflow_dispatch` の入力は `prompt` のみ。dispatch は write 権限を持つ人手による起動なので、常に書き込み可として扱う。

## 検証手順 (コミット後)

```
gh workflow run opencode.yaml --ref feat/add-opencode -f prompt="..."
# Issue コメント / PR open での自動起動も確認
```
