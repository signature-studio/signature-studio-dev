> **正本**: 本書 (`tools/pm/REPORT_APPENDIX_2585.md`) が #2585 (pm-worker の Workers Builds install と Workers Logs) の測定の正本。`infra/pm-worker/README.md` と `wrangler.toml` は結論と不変条件だけを持ち、測定値は本書に置く (`docs/DOC_MAP.md` §4)。`tools/pm/REPORT.md` は 250 行上限のため本体へ追記しない。

# #2585: pm-worker の Workers Builds install と Workers Logs の測定

測定 commit: `fc4e5915` (`infra/pm-worker/` のコードを変えた最後の commit。PR #2586)。検証は同じ commit で既定設定のまま行った。環境: pnpm 12.10.1 (root `devEngines` と同じ)・Node v22.23.3 (runner)・wrangler 4.151.0。

## 0. 取得方法

- Workers Builds: Cloudflare API `GET /accounts/{id}/builds/workers/{script_tag}/builds` と `GET /accounts/{id}/builds/builds/{uuid}/logs`。取得時刻は 2026-10-14 15:25Z 前後。
- Workers Logs: `GET /accounts/{id}/workers/scripts/signature-studio-pm/settings` と、Workers Logs の `telemetry/query` (`$metadata.service = signature-studio-pm`、直近 7 日)。
- watch paths の観測: 取得方法の詳細は記録していない (件数だけ残す)。

## 1. Workers Builds の件数と段

記録された run は 22 件。成功は 0 件。

| 結果 | 件数 | 備考 |
|---|---|---|
| fail | 18 | すべて `installing_tools_and_deps` 段 (依存関係のインストール) で停止。build / deploy 段には進まない |
| skipped | 4 | 実行されなかった。理由は未確認 |
| 成功 | 0 | |

| 期間 (UTC) | 件数 | ログ (要点) |
|---|---|---|
| 13:10Z〜13:56Z (#2454 の前) | 8 | `pnpm install --frozen-lockfile` → `Error: ERR_PNPM_NO_LOCKFILE` |
| 14:01Z〜15:22Z (#2454 の merge 以後) | 10 | `This project is configured to use npm because infra/pm-worker/package.json has a "packageManager" field` → `Failed: error occurred while installing tools or dependencies` |

- 両期間とも `SKIP_DEPENDENCY_INSTALL` は未設定、build command は空。
- ログの `Detected the following tools` に `pnpm@12.10.1` が出る。リポジトリ直下の `package.json` の `packageManager` から選ばれたと推定している (未確認)。
- ローカルの pnpm 12.9.1 で同じ `package.json` を使うと `ERR_PNPM_OTHER_PM_EXPECTED` で再現する。`packageManager` が npm のままでは、lockfile の有無に関わらず pnpm 経路は落ちる。

## 2. Workers Logs (observability) が無効だった経緯の記録

- `infra/pm-worker/wrangler.toml` に `[observability]` が無かった。wrangler 4.151.0 の deploy は、設定に observability が無いと `PATCH .../script-settings` に `observability: { enabled: false }` を送る (wrangler 同梱のソースのコメント: 「設定に無ければ無効にしたいものとみなす」)。
- VM からの deploy 12 回 (version 3〜14、2026-10-14 13:10:42Z〜14:31:09Z) の audit log すべてに `patch_settings` (`observability_enabled: false`) がある。
- 稼働中の Worker `signature-studio-pm` の settings に `observability` は無かった。
- Workers Logs のイベント数 (直近 7 日) は 0。
- Workers Builds が成功し始めても、同じ `wrangler.toml` で deploy するなら同じく無効になる。

## 3. watch paths `infra/pm-worker/*` の観測

- `infra/pm-worker` の差分がある merge 10 件は、すべてビルドが作成された。
- 差分が無い merge 37 件のうち 11 件にも、ビルドが作成された (2026-10-14 の観測)。
- 公式は『push event の変更ファイルが 0 件ならパス判定を飛ばして build する』と書く。原因は未確認。

## 4. 検証 (測定 commit `fc4e5915`、既定設定・CLI 上書きなし)

### 4-1. `pnpm install --frozen-lockfile`

修正前 (merge 後の `01c27a6a`。`minimumReleaseAgeExclude` 無し): rc=1

```
✗ Lockfile failed supply-chain policy check (159 entries in 1s)
Error: ERR_PNPM_MINIMUM_RELEASE_AGE_VIOLATION
3 lockfile entries failed verification: @cloudflare/vitest-plugin@1.4.2, miniflare@5.20261012.0-beta, wrangler@4.151.0
```

修正後 (`fc4e5915`): rc=0

```
✓ Lockfile passes supply-chain policies (159 entries in 415ms)
Lockfile is up to date, resolution step is skipped
Packages: +79
.../node_modules/workerd postinstall$ node install.js
.../esbuild@0.28.2/node_modules/esbuild postinstall$ node install.js
.../esbuild@0.28.2/node_modules/esbuild postinstall: Done
.../node_modules/workerd postinstall: Done
devDependencies:
+ @cloudflare/vitest-plugin 1.4.2
+ vitest 4.1.11
+ wrangler 4.151.0
Done in 1.8s using pnpm v12.10.1
rc=0
```

### 4-2. テスト

| コマンド | 結果 | rc |
|---|---|---|
| `pnpm test` | tests 188 / pass 188 / fail 0 (11 s) | 0 |
| `pnpm run test:unit` | 10/10 (3 s) | 0 |
| `pnpm run test:workers` | 3/3 (5 s) | 0 |

### 4-3. dry-run と observability の読み取り

- `pnpm exec wrangler deploy --dry-run --outdir <一時 dir>`: rc=0。Total Upload 103.45 KiB / gzip 31.98 KiB。bindings は `PM` (PmDO) と `[vars]` 10 個 (`REPO` `ORG` `TARGET=50` `BATCH=25` `BOT_LOGIN` `PM_LOGINS` `LIVE_LAUNCH=1` `LIVE_DISPATCH=1` `NO_PR_COOLDOWN_H=24` `COMMENT_MAX_PAGES=150`)。
- `unstable_readConfig({ config: 'wrangler.toml' })` の `observability`: `{"enabled":true,"head_sampling_rate":1}`。

### 4-4. fsevents の darwin 模擬 (Copilot の指摘の確認)

- 方法: `git archive fc4e5915 infra/pm-worker` を一時 dir に展開し、`pnpm-workspace.yaml` に `supportedArchitectures: {os: [darwin], cpu: [arm64]}` を足して `CI=true pnpm install --frozen-lockfile`。Linux runner での模擬で、実機の macOS では確認していない。
- 結果: rc=0。`fsevents@2.3.3` は `node_modules/.pnpm` に入った。`node_modules/.modules.yaml` の `pendingBuilds` は `[]`。
- `fsevents@2.3.3` の tarball (`npm pack`) の `scripts` は `clean`・`build`・`test`・`prepublishOnly` だけで、`install`・`preinstall`・`postinstall` は無い。`fsevents.node` は同梱されている。
- 旧 `package-lock.json` は fsevents に `hasInstallScript: true` を記録していたが、tarball と食い違う。記録の根拠は未確認。`allowBuilds` への追加は不要と判断した。

### 4-5. npm registry の公開時刻 (`npm view <pkg>@<ver> time`)

| 版 | 公開時刻 (UTC) |
|---|---|
| `miniflare@5.20261012.0-beta` | 2026-10-14T05:43:27.769Z |
| `wrangler@4.151.0` | 2026-10-14T05:50:43.466Z |
| `@cloudflare/vitest-plugin@1.4.2` | 2026-10-14T05:54:48.543Z |

3 版の最後の公開 (05:54:48.543Z) から 24 時間を過ぎるのは 2026-10-15T05:54:48Z 以降。`minimumReleaseAgeExclude` を外すと、それまで frozen lockfile の install が `ERR_PNPM_MINIMUM_RELEASE_AGE_VIOLATION` で落ちる (4-1)。

## 5. 未解決

未解決の一覧 (起票先つき) は PR #2586 の本文の未解決表が正本。本書には数値だけを残す。
