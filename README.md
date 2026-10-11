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
| 基盤 | `m1`,`m2`,`m3`,`m5` | `tools/m1/README.md`・各 `REPORT.md` |
| 基盤 | `flelift`,`liftlib`,`liftdiff` | 各 `REPORT.md`・`tools/liftlib/README.md` |
| OTT | `m6`〜`m10`,`ott` | `tools/ott/REPORT.md` |
| 起動 | `m11` (+`alloca`,`ldfix`,`shimx_link`) | `tools/m11/REPORT.md` |
| 解析 | `icall` (+`disp_size`,`landing`) | `tools/icall/REPORT.md` |
| shim | `shim`,`shimx` (+`pathreg`) | `tools/shim/README.md`・`tools/shimx/README.md` |
| 起動 | `startup` (+`glue`,`keyfix`,`pump`,`vreg`,`winstubs`) | `tools/startup/REPORT.md`・`STARTUP.md`・`GATES.md` |
| 実行基盤 | `runtime` | `tools/runtime/REPORT.md`・`DESIGN.md` |
| ホスト | `hostbridge` (+`cb`,`h2`,`lowbase`,`nfo`) | `tools/hostbridge/REPORT.md`・`HOSTBRIDGE.md` |
| GUI | `gui` | `tools/gui/REPORT.md` |
| オーディオ | `audio` (+`asio`) | `tools/audio/REPORT.md` |
| 資産 | `assets` (+`wvfs`,`bootset`) | `tools/assets/REPORT.md`・`MANIFEST.md` |
| スクリプト | `python`,`flp` | `tools/python/REPORT.md`・`tools/flp/REPORT.md` |
| プラグイン | `plugins` (+`framework`,`p0c`) | `tools/plugins/REPORT.md`・`ABI.md` |
| 共通 | `shared`,`ipp` (+`shim`,`shim/fft`) | `tools/shared/REPORT.md`・`tools/ipp/REPORT.md` |
| ターゲット | `targets/serum2` (+`host`,`license`) | `tools/targets/serum2/REPORT.md` |
| ターゲット | `targets/massivex` (+`dsp`) | `tools/targets/massivex/REPORT.md` |
| ターゲット | `targets/kilohearts` (+`license`,`snapins`) | `tools/targets/kilohearts/REPORT.md` |
| ターゲット | `targets/freshair` (+`lift2`) | `tools/targets/freshair/REPORT.md` |
| 検証 | `e2e`,`hosting`,`perf` | `tools/e2e/REPORT.md`・`tools/hosting/REPORT.md`・`tools/perf/REPORT.md` |

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
