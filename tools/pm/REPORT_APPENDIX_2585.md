> **正本**: 本書 (`tools/pm/REPORT_APPENDIX_2585.md`) が #2585 (pm-worker の Workers Builds install と Workers Logs) の測定の正本。`infra/pm-worker/README.md` と `wrangler.toml` は結論と不変条件だけを持ち、測定値は本書に置く (`docs/DOC_MAP.md` §4)。`tools/pm/REPORT.md` は 250 行上限のため本体へ追記しない。

# #2585: pm-worker の Workers Builds install と Workers Logs の測定

測定 commit: `6868e0a1` (`infra/pm-worker/` のコードを変えた最後の commit。`minimumReleaseAgeExclude` を外した commit。`origin/main` (`064af0d8`) を取り込んだ merge `be1ee59d` の後)。PR #2586。環境: pnpm 12.10.1 (root `devEngines` と同じ)・Node v22.23.3 (runner)・wrangler 4.151.0。

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

## 4. 検証 (測定 commit `6868e0a1`、既定設定・CLI 上書きなし)

### 4-1. `pnpm install --frozen-lockfile` (exclude 無し)

`CI=true`・`node_modules` を削除してから実行。rc=1。

```
✗ Lockfile failed supply-chain policy check (159 entries in 995ms)
Lockfile is up to date, resolution step is skipped
Error: ERR_PNPM_MINIMUM_RELEASE_AGE_VIOLATION
3 lockfile entries failed verification:
  @cloudflare/vitest-plugin@1.4.2 was published at 2026-10-14T05:53:30.000Z
  miniflare@5.20261012.0-beta was published at 2026-10-14T05:43:25.000Z
  wrangler@4.151.0 was published at 2026-10-14T05:48:57.000Z
  (minimumReleaseAge cutoff: 2026-10-13T16:27:02.904Z)
rc=1
```

- 3 版が 24 時間を過ぎるのは、pnpm の表示で 2026-10-15T05:53:30Z 以降 (vitest-plugin)、npm の `time` で 2026-10-15T05:54:48Z 以降 (§4-5)。05:55Z 以降なら両方を満たす。その時刻以降は既定設定のまま通る見込み (未確認)。
- PM 判断 (2026-10-14) で `minimumReleaseAgeExclude` は採らない。exclude を入れた試行 (`fc4e5915`・`e11ab9a9`・`12aca053`) は rc=0 だったが、採用しない (§4-6)。

### 4-2. テスト

| コマンド | 結果 (測定 commit `6868e0a1`) | rc |
|---|---|---|
| `pnpm test` (依存なし。Node の test runner と Python 3) | tests 251 / pass 251 / fail 0 (12.5 s) | 0 |
| `pnpm run test:unit` | 未実施。`vitest` が入らない (§4-1) | — |
| `pnpm run test:workers` | 未実施。`@cloudflare/vitest-plugin` が入らない (§4-1) | — |

未実施の 2 件は 2026-10-15 05:55Z 以降の既定設定の install で再測定する (PR #2586 の未解決表)。exclude 入りの旧測定の値は §4-6。今の HEAD の値ではない。

### 4-3. dry-run と observability

- `pnpm exec wrangler deploy --dry-run`: 未実施 (wrangler が入らない。§4-1)。exclude 入りの旧測定の値は §4-6。
- `wrangler.toml` の observability を TOML として直接読む (測定 commit `6868e0a1`・依存なし): `{'enabled': True, 'head_sampling_rate': 1}`。`[observability]` の table は main と同一で、本 PR では触っていない。
- `wrangler.toml` の `[vars]` と `[[durable_objects]]` も同じ読み取りで確認: DO binding は `PM` (`PmDO`) の 1 件。`[vars]` は 10 個 (`REPO` `ORG` `TARGET` `BATCH` `BOT_LOGIN` `PM_LOGINS` `LIVE_LAUNCH` `LIVE_DISPATCH` `NO_PR_COOLDOWN_H` `COMMENT_MAX_PAGES`)。

### 4-4. fsevents の darwin 模擬 (Copilot の指摘の確認)

- 方法: `git archive fc4e5915 infra/pm-worker` を一時 dir に展開し、`pnpm-workspace.yaml` に `supportedArchitectures: {os: [darwin], cpu: [arm64]}` を足して `CI=true pnpm install --frozen-lockfile`。Linux runner での模擬で、実機の macOS では確認していない。lockfile は `e11ab9a9` と同一。
- 結果: rc=0。`fsevents@2.3.3` は `node_modules/.pnpm` に入った。`node_modules/.modules.yaml` の `pendingBuilds` は `[]`。
- `fsevents@2.3.3` の tarball (`npm pack`) の `scripts` は `clean`・`build`・`test`・`prepublishOnly` だけで、`install`・`preinstall`・`postinstall` は無い。`fsevents.node` は同梱されている。
- 旧 `package-lock.json` は fsevents に `hasInstallScript: true` を記録していたが、tarball と食い違う。記録の根拠は未確認。`allowBuilds` への追加は不要と判断した。

### 4-5. npm registry の公開時刻 (`npm view <pkg>@<ver> time`)

| 版 | npm の `time` (UTC) | pnpm の表示 (§4-1) |
|---|---|---|
| `miniflare@5.20261012.0-beta` | 2026-10-14T05:43:27.769Z | 05:43:25.000Z |
| `wrangler@4.151.0` | 2026-10-14T05:50:43.466Z | 05:48:57.000Z |
| `@cloudflare/vitest-plugin@1.4.2` | 2026-10-14T05:54:48.543Z | 05:53:30.000Z |

最後の版が 24 時間を過ぎるのは、npm の `time` で 2026-10-15T05:54:48Z 以降、pnpm の表示で 05:53:30Z 以降。README と PR 本文は両方を満たす 05:55Z を目安にする。

### 4-6. 旧測定 (exclude 入り・不採用。今の HEAD の値ではない)

exclude を入れていた時点の測定。PM 判断 (2026-10-14) で採らないため、参考として残す。

- `fc4e5915`: 未キャッシュの policy 検証で `✓ Lockfile passes supply-chain policies (159 entries in 415ms)` → `Packages: +79` → `Done in 1.8s using pnpm v12.10.1`。rc=0。
- `e11ab9a9`: `pnpm test` 201/201 (10 s)・`test:unit` 10/10 (2 s)・`test:workers` 3/3 (4 s)。rc は各 0。`tools/pm` を含めて展開する必要がある (突き合わせテストが `tools/pm/*.py` を読む)。
- `12aca053` (main `58d1183b` 取り込み後): `CI=true pnpm install --frozen-lockfile` は `verified 1m ago` (store のキャッシュ済み検証) → `Done in 66ms` rc=0。`pnpm test` 213/213 (15.5 s)・`test:unit` 10/10 (783 ms)・`test:workers` 3/3 (1.39 s)・`wrangler deploy --dry-run` rc=0 (Total Upload 109.30 KiB / gzip 33.88 KiB・bindings は `PM` と `[vars]` 10 個)・`unstable_readConfig` の observability `{"enabled":true,"head_sampling_rate":1}`。

## 5. 未解決

未解決の一覧 (起票先つき) は PR #2586 の本文の未解決表が正本。本書には数値だけを残す。
