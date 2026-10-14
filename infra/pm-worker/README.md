# signature-studio-pm-worker (部分実装: 純関数の核のみ)

PM の launch / watchdog を Cloudflare Worker で駆動する計画 (#1751) の、この PR の範囲。
**まだデプロイ・GitHub への書き込み・webhook 受信は実装していない。**

## 現状

- `src/hmac.ts`: `X-Hub-Signature-256` の HMAC-SHA256 検証 (定数時間比較・長さ違いは比較前に弾く)。
- `src/launch.ts`: `tools/pm/launch_issues.py` の移植。素材 allowlist・固定 `/oc` テンプレート・
  並び順・選定式 (room = TARGET − active, BATCH)。
- テスト: `npm test` (Node の `--test`。依存パッケージなし)。

## 未実装 (子 issue)

- 分類 (classify) の TS 版と Python 版の突き合わせ
- Cron Trigger / Durable Object alarm による dispatch と reconcile
- GitHub App manifest flow (`/setup`) と暗号化保管
- webhook 受信 (`POST /webhook`)・`GET /status`・dry-run デプロイ手順

## 依頼者の操作 (デプロイ後に 1 回)

ブラウザで `/setup` を開き、「Create GitHub App」と「Install」を押す。
(デプロイ手順と Cloudflare token の権限は子 issue で追記する。)
