# WebStudio

FL Studio 26.1.7 をブラウザ (wasm) 上で完全に動作させるプロジェクト。
実物バイナリを lift して最小変更で wasm 化し、ネイティブ依存は shim 層でブラウザ API に吸収する。

## 現状

詳細は **[`docs/STATUS.md`](docs/STATUS.md)** が状態の唯一の正本。要点:

- **完走路**: OTT (Xfer) DSP が native 実機械語と bit-exact (`tools/ott/REPORT.md`)
- **本命**: FLEngine 本体起動 (`tools/flelift/boot/REPORT.md`)・lift 品質 (`tools/liftlib/REPORT.md`)
- **未達**: FLEngine 全体の wasm 起動・E2E 統合・MS11/M12 の残項目

## ドキュメント地図

| ファイル | 内容 |
|---|---|
| [`AGENTS.md`](AGENTS.md) | エージェント規約・ドキュメント責務マップ・命名規則 |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | パイプライン全体像 |
| [`docs/STATUS.md`](docs/STATUS.md) | **状態の唯一の正本** (MS 番号・サブシステム 1 行ステータス) |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | 方式決定と理由 (ADR) |
| [`docs/WORKFLOW.md`](docs/WORKFLOW.md) | subagent 運用・PR・レビュー・検収 |
| [`docs/REFERENCES.md`](docs/REFERENCES.md) | 外部ソース・素材・ツール・vendored 台帳 |
| [`docs/DOC_MAP.md`](docs/DOC_MAP.md) | REPORT.md 索引・行数上限ルール |
| [`docs/DEFECTS.md`](docs/DEFECTS.md) | lift silent miscompile 類型 |
| [`docs/LEGAL.md`](docs/LEGAL.md) | ライセンス/規約上の運用制約 |
| [`docs/HANDOFF/`](docs/HANDOFF/) | 日付付き引継ぎ (最新のみ) |

## tools 索引 (37 サブシステム)

測定値・実測は各 `REPORT.md` が単一の正本。索引は [`docs/DOC_MAP.md`](docs/DOC_MAP.md)。

| 系統 | ディレクトリ | 正本 |
|---|---|---|
| 基盤 | `m1`,`m2`,`m3`,`m5`・`flelift`(+`boot`)・`liftlib`・`liftdiff` | `tools/m1/README.md`・各 `REPORT.md` |
| OTT | `m6`〜`m10`,`ott` | `tools/ott/REPORT.md` |
| 起動 | `m11`(+`alloca`,`ldfix`,`shimx_link`)・`startup`(+`glue`,`keyfix`,`pump`,`vreg`,`winstubs`) | `tools/m11/REPORT.md`・`tools/startup/STARTUP.md` |
| 解析 | `icall` (+`disp_size`,`landing`) | `tools/icall/REPORT.md` |
| shim | `shim`,`shimx` (+`pathreg`) | `tools/shim/README.md`・`tools/shimx/README.md` |
| 実行 | `runtime`・`hostbridge`(+`cb`,`h2`,`lowbase`,`nfo`)・`gui`・`audio`(+`asio`)・`assets`(+`wvfs`,`bootset`) | 各 `REPORT.md`・`tools/runtime/DESIGN.md` |
| 共通 | `python`,`flp`,`shared`,`ipp`(+`shim`,`shim/fft`)・`plugins`(+`framework`,`p0c`) | 各 `REPORT.md`・`tools/plugins/ABI.md` |
| ターゲット | `targets/{serum2,massivex,kilohearts,freshair}` とその下位 dir | 各 `targets/*/REPORT.md` |
| 検証/配信 | `e2e`,`hosting`,`deploy`,`perf` | `tools/e2e/REPORT.md`・`deploy/README.md` |

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

ブランチ → worktree → 実装 subagent → レビュー subagent → PM がマージ。`master`/`main` には変更を加えない。
詳細は [`AGENTS.md`](AGENTS.md)・[`docs/WORKFLOW.md`](docs/WORKFLOW.md)。
