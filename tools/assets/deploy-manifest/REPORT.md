# deploy-manifest — 配備 manifest の生産側 (#63 / E2E-1)

検証起点 commit `2847625` (main)。既知類型との関係: 該当なし (lift/逆アセ/IR pass 系ではない)。

## 1. 結論

- `deploy/scripts/05-stage.mjs --manifest` が消費する `{version:1, files:[{path,src,contentType}]}` の**生産側**を `make-manifest.mjs` として実装した。
  immutable 配下 (`/assets /wasm /data`) の非ハッシュ名は `<stem>.<sha256 先頭 12 hex>.<ext>` に改名、既にハッシュ名のもの (`tools/runtime/stage_wasm.mjs` 出力) は不変 (冪等)。
- **受入の達成範囲 (部分)**: 05-stage 通過・release.json 突合・`tools/e2e/run.sh --url` の wasm-load (MIME `application/wasm`) は PASS。
  **`deploy.sh --manifest` の DRY-RUN 完走は未確認** — runner に `cf` CLI/認証が無く 00-preflight で停止する (§4)。よって PR は `Refs #63`。
- 前提の変化 (issue 本文は古い): 消費側は `20-upload.mjs` (R2、`deploy/legacy-r2/` へ移動済) ではなく Workers Static Assets の `05-stage.mjs`。
  `release.json` は 05-stage が全 file/part の sha256 から生成する (buildId = 内容ハッシュ 12 桁)。ローダ側の解決は既存 (`src/runtime/boot.ts: loadManifest("/wasm/manifest.json")` → ブート manifest の `entries[].file`)。

## 2. 構成

| ファイル | 役割 |
|---|---|
| `make-manifest.mjs` | `--add <dest>=<file\|dir>` を走査 → 改名 → `--out` に hardlink 配置 + `deploy-manifest.json` (`size`/`sha256` は参考情報として付与。05-stage は無視する) |
| `verify-release.mjs` | manifest の sha256/size/contentType と 05-stage の `release.json` を突合 (make-manifest が先に計算した値 vs stage が配備物から再計算した値) |
| `serve-check.mjs` | 05-stage 出力を edge-policy 準拠 (`applyResponseHeaders`) で配信し、全 path を fetch (sha256・Content-Type・immutable Cache-Control・`.wasm` は `instantiateStreaming`)。`--serve` で `run.sh --url` 用に配信のみ |
| `make-manifest.test.mjs` | node:test 7 件 |
| `e2e.sh` | 上記 + vite build + 05-stage + `tools/e2e/run.sh --url` を 1 コマンドで実行 |

`/wasm/manifest.json` (ブート manifest) が入力に含まれる場合、`entries[].file`/`glue` が配備集合に存在し `sha256`/`bytes` が実体と一致することを突合する (不一致は exit 2)。

規則: 予約名 (`_headers` `_redirects` `release.json`)・`..` 等の不正 path・内容が異なる path 衝突・拡張子無しの immutable ファイルは中止。contentType は edge-policy `contentTypes` から明示 (未登録は `defaultContentType`)。

## 3. 実測 (`bash tools/assets/deploy-manifest/e2e.sh`)

入力は合成のみ (add.wasm 41B + `deploy/probe/make-wasm.mjs` の 1MiB wasm + 乱数 4KiB bin + ブート manifest 付き既ハッシュ名 wasm)。FL/プラグイン由来バイトは使わない (05-stage は `--skip-release-guard`: deny-list が runner に無いため)。

| 項目 | 結果 |
|---|---|
| unit | 7/7 PASS |
| make-manifest | files 5 / renamed 3 / totalBytes 1,052,926 / bootManifestChecked true |
| 05-stage | exit 0 / deployedFiles 12 / headers ok / buildId は内容依存 |
| verify-release | 5 files OK |
| serve-check | 5 files fetched, wasm instantiateStreaming OK 3 (MIME application/wasm) |
| `run.sh --url` (agent-browser, Chrome) | PASS=8 FAIL=0 SKIP=1 (fl-boot)。wasm-load: `instantiateStreaming OK (ct=application/wasm)` |
| 所要 (n=3, 連続実行, clean HEAD でなく作業ツリー; 下記注) | 6.30s / 3.34s / 3.30s。load average 0.42–0.46 (開始時), 並列数 1 |

ネガティブコントロール (数値):
- 非ハッシュ名 `wasm/big.wasm` を手書き manifest で渡す → 05-stage **exit 2** (`immutable 配下にハッシュ無しのファイル名`)。make-manifest 経由では同ファイルが `big.<hash12>.wasm` になり通る。
- manifest の sha256 先頭 1 文字を改変 → verify-release **exit 2** (1 件検出)。
- ブート manifest の sha256 改変 / glue 欠落 → unit test で検出 (`sha256 不一致` / `glue`)。
- 初回の `run.sh --url` は私の簡易サーバが `/` を index.html に解決せず PASS=1 FAIL=7 になった (サーバ側の不備を修正し 8/0)。Static Assets は `/` を解決するため実機差ではない。

検証範囲: ローカルの policy 準拠サーバ (edge-sim 相当) への配信。範囲外: 実 Workers URL (Access 配下)、25MiB 超の part 分割 (05-stage 既存機能・本変更の対象外)、FL 由来の実 wasm (`tools/*/work` 素材なし)。

clean HEAD 検証 (commit `cddfa58`, `git worktree add --detach` で展開): unit 7/7、verify-release 5 files OK、serve-check OK、`run.sh --url` PASS=8 FAIL=0 SKIP=1、**5.93s** (load average 1.09 開始時, 並列 1)。上表 n=3 の所要は作業ツリー (コミット前) での実測。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `deploy.sh --manifest` の DRY-RUN 完走 (00-preflight が `cf` CLI と認証を要求。runner に無い) | 受入条件の 1 項目が未達 → PR は Refs | #63 にコメント。`cf`/wrangler 認証を持つ環境での再実行が必要 (PM 判断) |
| 実 wasm (`tools/runtime/stage_wasm.mjs` 出力) を `--add wasm=tools/runtime/work/wasm` で通す実測 | 冪等性 (既ハッシュ名の維持) は合成入力でのみ確認 | `work-m6-ott work-m11 toolchain-emsdk` 等が必要。#63 にコメント |
| `tools/assets` の chunk 配置 (`c/ m/ latest.json`) と本 manifest の統合 | 本 manifest は個別ファイル配備用。chunk 配置は 05-stage `--src` 側の既存経路 | #22 系 (closed)。必要なら新規 [E2E-n] |
