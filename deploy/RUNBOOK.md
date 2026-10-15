# RUNBOOK — CAB-35 実デプロイ (Workers Static Assets + Access worker 型)

**ユーザ承認後にのみ実行**。本チケット (CAB-61) では本番名 `signature-studio` を作成していない (probe は `signature-studio-deploy-probe-*` で作成→削除済み、REPORT.md)。

## 0. 前提 (ユーザ確認が要る項目)
1. Access の人間ポリシー — **ユーザ決定 (2026-10-10)**: `ACCESS_ALLOW_EMAILS` は**未指定のまま** = `include: Everyone` (ログイン必須・この Zero Trust 組織のユーザならログイン可)。後日メール許可リストに絞る/追加する手順は §4。
2. Worker 名 (既定 `signature-studio` -> `https://signature-studio.<account>.workers.dev`。このアカウントの workers.dev サブドメインは probe 時 `pycabbage`)。
3. 配備物 `<dist>` と (あれば) `tools/assets` の manifest。配備物は **ダミーでなく実アプリ**を `vite build` した dist (`E2E` の `tools/e2e/work/dist` でも可)。
4. 既存資産は変更しない: R2 4 バケット (cloudflareos-workshop-blueprint-content / nksf-parser-fixtures / scriba-session-archive / scriba-tfstate)、zone cabbagelettuce.com、既存 Access app 28 件、service token `default-1yr`。本構成はこれらに一切触れない (Worker + Access app + service token 各 1 つを追加するだけ)。

## 1. 手順
```sh
本リポジトリのルート (worktree または main のクローン) に cd し:
export PATH=$HOME/.local/share/pnpm/bin:$HOME/.bun/bin:$PATH
cp deploy/env.example deploy/.env && $EDITOR deploy/.env     # WORKER_NAME 既定 signature-studio。ACCESS_ALLOW_EMAILS は未指定可 (= Everyone、§4)

# (a) ビルド (未作成なら)。tools/e2e/work/dist を使う場合は E2E 担当の検収終了後に
node_modules/.bin/vite build --outDir deploy/work/app-dist --emptyOutDir

# (b) DRY-RUN: 読取 API と wrangler --dry-run、stage 検査のみ (Cloudflare は無変更)
bash deploy/scripts/deploy.sh --src deploy/work/app-dist [--manifest tools/assets/manifest.json]

# (c) 実行
APPLY=1 bash deploy/scripts/deploy.sh --src deploy/work/app-dist [--manifest ...]
#   00 preflight -> 05 stage -> 20 closed(placeholder) -> 40 access --apply -> 20 open(無認証302待ち) -> 20 release(本物の asset) -> 90 verify(buildId待ち+ヘッダ検査+E2E)
```
個別実行: `node deploy/scripts/05-stage.mjs --src …` / `node deploy/scripts/20-worker.mjs --phase closed|open|release` / `node deploy/scripts/40-access.mjs --apply` / `bash deploy/scripts/90-verify.sh`。

## 2. 成功の確認項目
- stage 出力: `headers: ok`、`deployedFiles` ≤ 20,000、`chunked` に >24MiB のファイルが列挙されている (元ファイルは配備されない)。
- `90-verify.sh`: 無認証 `GET /` = **302** (Access)、`<ver>-<name>.<sub>.workers.dev` 形式 = 非 200、service token で `Cross-Origin-{Opener,Embedder,Resource}-Policy` が付く。
- `bash tools/e2e/run.sh --url https://signature-studio.<sub>.workers.dev` (90-verify が最後に実行。token は `deploy/work/secrets/<name>-e2e.json` を自動使用)。`tools/e2e` の `edge-policy` は `/index.html` の `307 -> /` を正しい挙動として PASS にする (#3526・EDGE-SIM.md §B)。`node deploy/probe/policy-check.mjs <url> <token.json>` は同等検査を 307 許容で行うので、必要なら併用して判定する。
- ブラウザ手動: Access ログイン後 `crossOriginIsolated === true`。

## 3. 失敗時・巻き戻し
- stage が `immutable 配下にハッシュ無し` で中止: ファイル名に内容ハッシュを付ける (1 年 immutable のため)。
- Access 作成前に `open` へ進めない設計 (deploy.sh の順序)。`open` は 180 秒待っても 302 にならなければ失敗終了する (その場合 `release` しない。placeholder のみ公開状態なので影響は無い。Access app を確認)。
- 再実行は冪等 (Worker は差分 asset のみ、Access app/token は upsert。service token の secret は初回のみ `deploy/work/secrets/` に保存。紛失時は token を削除して再作成)。
- 取り消し (本番名のため手動・要確認): `bunx wrangler delete --name signature-studio` / Access app `signature-studio` / service token `signature-studio-e2e` を cf で削除。`probe-cleanup.sh` は probe 名にしか効かない (本番名は REFUSE)。

## 4. 運用
### メール許可リストの追加 / 絞り込み (Everyone から後日限定する)
現行ポリシーは人間 allow = `include: [{everyone:{}}]` (ログイン必須・この Zero Trust 組織のユーザならログイン可) + service token `non_identity`。絞り込む/追加する手順:

1. `deploy/.env` に許可対象を設定:
   - `ACCESS_ALLOW_EMAILS=a@x.com,b@y.com` (カンマ区切り) または `ACCESS_ALLOW_EMAIL_DOMAIN=example.com` (ドメイン単位)
   - `ACCESS_ALLOW_EVERYONE=1` を併記すると「組織ユーザ (Everyone) + 指定メール」の両方を残せる (未指定時は email 指定に Everyone を置き換え)
2. `node deploy/scripts/40-access.mjs --apply` を再実行 (冪等 upsert。Worker / asset / service token は無変更、人間ポリシーのみ更新)
3. 確認: `cf zero-trust access applications list` の `signature-studio` の `policies[0].include`、および無認証 `GET /` が引き続き 302 (Access ログイン) であること

- 更新: 同じコマンドを再実行。`_headers` 反映に 30–60 秒。part / immutable 資産は内容アドレスなので古いクライアントも壊れない。
- 自前ドメイン: README「自前ドメインへの移行」。
- 次チケット案: edge-sim の Static Assets 追従 (EDGE-SIM.md)、`/c/` `/m/` `/latest.json` の edge-policy 正本取込み、E のローダを `chunked.mjs` 方式に結線。
