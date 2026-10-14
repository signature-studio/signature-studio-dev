# WebStudio

FL Studio 26.1.7 をブラウザ (wasm) 上で完全に動作させるプロジェクト。
実物バイナリを lift して最小変更で wasm 化し、ネイティブ依存は shim 層でブラウザ API に吸収する。

## 現状

詳細は **[`docs/STATUS.md`](docs/STATUS.md)** が状態の唯一の正本。要点:

- **完走路**: OTT (Xfer) DSP が native 実機械語と bit-exact (`tools/ott/REPORT.md`)
- **本命**: FLEngine 本体起動 (`tools/flelift/boot/REPORT.md`)・lift 品質 (`tools/liftlib/REPORT.md`)
- **未達**: FLEngine 全体の wasm 起動・E2E 統合・MS11/M12 の残項目

## ドキュメント地図

docs 索引・各ファイルの責務・行数上限ルールは **[`docs/DOC_MAP.md`](docs/DOC_MAP.md) が正本**。
正史は `docs/` に集約している (`ARCHITECTURE` / `STATUS` / `DECISIONS` / `WORKFLOW` /
`REFERENCES` / `DOC_MAP` / `DEFECTS` / `LEGAL` / `pm/` / `HANDOFF/`)。エージェント規約は
[`AGENTS.md`](AGENTS.md) (要約) と [`docs/WORKFLOW.md`](docs/WORKFLOW.md) (運用の詳細)。

## tools 索引

tools 直下は **33 dir** (下表は下位 dir を含め 60 名を列挙)。測定値・実測は各 `REPORT.md` が単一の正本。
索引は [`docs/DOC_MAP.md`](docs/DOC_MAP.md)。

| 系統 | ディレクトリ | 正本 |
|---|---|---|
| 基盤 | `m1`,`m2`,`m3`,`m5`・`flelift`(+`boot`)・`liftlib`・`liftdiff` | `tools/m1/README.md`・各 `REPORT.md` |
| OTT | `m6`〜`m10`,`ott` | `tools/ott/REPORT.md` |
| 起動 | `startup`(+`glue`,`keyfix`,`loadpaths`,`pump`,`vreg`,`winstubs`)・RetDec 路線・旧の `m11`(+`alloca`,`ldfix`,`shimx_link`) | `tools/flelift/boot/REPORT.md`・`tools/startup/STARTUP.md`・`tools/m11/REPORT.md` (旧路線) |
| 解析 | `icall` (+`disp_size`,`landing`) | `tools/icall/REPORT.md` |
| shim | `shim`,`shimx` (+`pathreg`) | `tools/shim/README.md`・`tools/shimx/README.md` |
| 実行 | `runtime`・`hostbridge`(+`cb`,`h2`,`lowbase`,`nfo`)・`gui`・`audio`(+`asio`)・`assets`(+`wvfs`,`bootset`) | 各 `REPORT.md`・`tools/runtime/DESIGN.md` |
| 共通 | `python`,`flp`,`shared`,`ipp`(+`shim`,`shim/fft`)・`plugins`(+`framework`,`p0c`) | 各 `REPORT.md`・`tools/plugins/ABI.md` |
| ターゲット | `targets/{serum2,massivex,kilohearts,freshair}` とその下位 dir | 各 `targets/*/REPORT.md` |
| 検証/配信 | `e2e`,`hosting`,`deploy`,`perf` | `tools/e2e/REPORT.md`・`deploy/README.md` |

`tools/misc/` (`loader_smoke.mjs` のみ・ドキュメント無し) は**索引対象外**。

## 開発

```sh
pnpm install
pnpm dev              # vite dev server
pnpm typecheck        # tsc --noEmit
pnpm build            # tsc --noEmit && vite build
pnpm runtime:stage    # wasm を public/ にステージ
pnpm runtime:e2e      # ローカル E2E (node + headless chrome)
pnpm runtime:e2e:prod # 本番 (デプロイ済 URL) E2E
```

## デプロイ

Worker コード無しの **Workers Static Assets (案 S)** + `_headers` で COOP/COEP/CORP 一括付与、
Cloudflare Access は `worker` 型。R2 / zone Transform Rules は不要 (旧構成は `deploy/legacy-r2/`)。
詳細は [`deploy/README.md`](deploy/README.md)・[`docs/DECISIONS.md`](docs/DECISIONS.md) D1。

## 運用

ブランチ → worktree → 実装 subagent → レビュー subagent (検収) が approve 後にマージ。既定ブランチ `main`
(旧 `master` は凍結) には変更を加えない。詳細は [`AGENTS.md`](AGENTS.md)・
[`docs/WORKFLOW.md`](docs/WORKFLOW.md)。
