# STATUS — 技術進捗の正本

本ファイルが**技術進捗**に関する唯一の正本である (チケット状態の正本は Project V2 の Status
フィールド + issue の open/closed。`docs/WORKFLOW.md` §3)。
旧 `tools/docs/MILESTONES.md`・`tools/ipp/STATUS.md`・`tools/m11/STATUS.md` は本ファイルに統合し削除した。

- 更新責任: merge の事実を反映する更新は agent も PR で行ってよい (自動更新は #2361)。方針の変更・MS の定義の改訂は PM。
- 測定値・実測数値は書かない。各リンク先 (`tools/<area>/REPORT.md`) が単一の正本。
- 引き継ぎ情報は `docs/HANDOFF/2026-10-12.md`。

---

## 1. M 番号の再定義 (命名衝突の解消)

過去、`M1`〜`M11` が **2 つの独立した系譜** で使われて衝突していた。

| 系譜 | 意味 | 所在 |
|---|---|---|
| **MS** (milestone stage) | 戦略上の到達段階。M1〜M11 + M12 | `docs/REFERENCES.md` `[STRATEGY]` §4。本ファイル §2 |
| **m#** (tool directory) | 作業用ツリー `tools/m1`〜`tools/m11`。**M# とは無関係** | `tools/m1/README.md` 等 |

**衝突の例 (過去の混乱)**: 旧 MILESTONES の M7=GUI / M8=Audio / M10=性能 / M11=E2E統合 に対し、
`tools/m7`=M6 E2E 化 / `tools/m8`=value-flow / `tools/m10`=OTT band / `tools/m11`=FLEngine 起動 だった。

**新しい規約**:

- 戦略上の到達段階は **`MS1`〜`MS12`** と表記する。
- 作業用ツリーは **`m1`〜`m11`** (小文字・ディレクトリ名) のままで、**MS 番号とは対応させない**。
- **定義元**: `MS1`〜`MS11` は `[STRATEGY]` §4 (`docs/REFERENCES.md`) が定義元。**`MS12` は本ファイルで定義**
  (repo 外の `[STRATEGY]` §4 には M1〜M11 の 11 段のみ)。
- **歴史表記**: 過去のコミット・既存 `REPORT.md` に残る `M7` / `M8` / `M10` / `M11` は
  **milestone 意味の歴史的な表記**で、`tools/m7`・`tools/m8`・`tools/m10`・`tools/m11` という
  ディレクトリ名を指すものではない。過去の記述は書き換えない (判断は文脈の `MS`/`m` 表記で行う)。

## 2. MS (戦略上の到達段階) の状態

| MS | 名称 | 状態 |
|---|---|---|
| MS1 | 極小 PE→wasm PoC (toolchain 実証) | **完了** |
| MS2 | FLEngine 解析の機械化 | **完了** |
| MS3 | 中規模 lifting → wasm | **部分達成** |
| MS4 | Win32 shim コア | **完了** |
| MS5 | FLEngine 部分的 wasm 起動 (オーディオなし) | **部分達成** |
| MS6 | プラグイン路線 PoC — OTT bit-exact | **実現** (`tools/ott/REPORT.md`) |
| MS7 | GUI フレーム転送 → 操作可能 HUD | 設計・PoC あり (`tools/gui/`) |
| MS8 | オーディオパス (AudioWorklet + SAB ring) | 設計・PoC あり (`tools/audio/`) |
| MS9 | プロジェクト入出力 + FL 純正プラグイン in-process | 部分 (`tools/flp`, `tools/plugins/`) |
| MS10 | 性能・安定性チューニング | 計測基盤あり (`tools/perf/`) |
| MS11 | E2E 統合 + FL 追従 + EULA/非再配布運用固定化 | 未達。FL 新版取り込み手順は素材ありで `pnpm terms-watch` (FL 同梱 2 文書 + Xfer) を呼ぶこと (週次 workflow `terms-watch.yaml` は Web 4 文書のみ・配置済み。`tools/legal/terms-watch/REPORT.md`) |
| MS12 | ホストデプロイ + `agent-browser` E2E 検証 | **部分達成** (デプロイ実績あり・FLEngine 起動は未達) |

状態の判断基準: 「完了」= 各段の検証条件が満たされたこと。「部分達成」= 一部の検証項目のみクリア。

## 3. サブシステム 1 行ステータス

測定値は各 REPORT.md を参照。ここには到達点と状態のみ書く。

| サブシステム | 状態 | 正本 |
|---|---|---|
| `m1` ツールチェイン | 完了 (Pin 済・1 コマンド E2E) | `tools/m1/README.md` |
| `m2` FLEngine 解析機械化 | 完了 | `tools/m2/REPORT.md` |
| `m3` 中規模 lift→wasm | 部分達成 | `tools/m3/REPORT.md` |
| `m5` Delphi Mini-PoC | 部分達成 | `tools/m5/REPORT.md` |
| `m6`〜`m10` OTT (RetDec 路線) | 旧路線 (歴史的記録として保持。新規 lift は x64c / flelift / liftlib) | 各 `REPORT.md` |
| `ott` OTT bit-exact 参照 | **完走路検証済** | `tools/ott/REPORT.md` |
| `m11` FLEngine 部分起動 | 部分達成 (到達 stage は REPORT 参照) | `tools/m11/REPORT.md` |
| `m11/alloca` | 修復実装済 | `tools/m11/alloca/REPORT.md` |
| `m11/ldfix` | 修復実装済 (常設化) | `tools/m11/ldfix/REPORT.md` |
| `m11/shimx_link` | 接続実装済 | `tools/m11/shimx_link/REPORT.md` |
| `flelift` | x64c FLEngine 汎用化 | `tools/flelift/REPORT.md` |
| `flelift/boot` | boot 連鎖 lift | `tools/flelift/boot/REPORT.md` |
| `liftlib` | 共通 lift 修復基盤・統合 | `tools/liftlib/REPORT.md` |
| `liftdiff` | flelift 全数採点 | `tools/liftdiff/REPORT.md` |
| `icall` | 間接 call 落ち監査・修復 | `tools/icall/REPORT.md` |
| `icall/disp_size` | capstone disp_size 監査 | `tools/icall/disp_size/REPORT.md` |
| `icall/landing` | unwind landing pad lift | `tools/icall/landing/REPORT.md` |
| `shim` | コア完了 | `tools/shim/README.md` |
| `shimx` | 拡張中 | `tools/shimx/REPORT.md`・`tools/shimx/BACKLOG.md` |
| `shimx/pathreg` | パス写像/レジストリ接続 | `tools/shimx/pathreg/REPORT.md` |
| `startup` | 起動シーケンス設計+stub 計画 | `tools/startup/REPORT.md` |
| `startup/{glue,keyfix,pump,vreg,winstubs}` | 各実装済 | 各 `REPORT.md` |
| `startup/helpviewer` | Help viewer 実装済 (エンジン結線は未) | `tools/startup/helpviewer/REPORT.md` |
| `startup/loadpaths` | 言語 .moe/スキン/Help のロード経路を静的解析で確定・VFS 配置 group 定義 (実トレース確定は未了) | `tools/startup/loadpaths/REPORT.md` |
| `runtime` | 設計・基盤 | `tools/runtime/REPORT.md` |
| `hostbridge` | 設計+mini VST2 host PoC | `tools/hostbridge/REPORT.md` |
| `hostbridge/{cb,h2,lowbase,nfo}` | 各実装済 | 各 `REPORT.md` |
| `hostbridge/h10` | Wrapper chunk reader 静的解析済 (実行検証は #267) | `tools/hostbridge/h10/REPORT.md` |
| `gui` | 設計+PoC。e2e は agent-browser / puppeteer 駆動が main 入り。FL の窓種別に依存する部分は未達 | `tools/gui/REPORT.md` |
| `audio` | 設計+PoC。DirectSound shim・Web MIDI shim・FlAudioShim の本体適用が main 入り。dev 経路の断続 FAIL の再現・切り分け (AU-15) は未了。ソークは AU-10 で一部達成 (残件は REPORT) | `tools/audio/REPORT.md`・`tools/audio/asio/REPORT.md` |
| `audio/asio` | COM アダプタ+soak | `tools/audio/asio/REPORT.md` |
| `assets` | chunk ローダ+二段キャッシュ | `tools/assets/REPORT.md` |
| `assets/wvfs` | 書込可能 VFS | `tools/assets/wvfs/REPORT.md` |
| `python` | CPython wasm+ブリッジ。flapi provider の静的リンクと per-module state が main 入り。FLEngine 実機上の動作は未達 | `tools/python/REPORT.md` |
| `flp` | FLP/FST パーサ設計 | `tools/flp/REPORT.md` |
| `plugins` | 141 種マップ (カウントの正本: `tools/plugins/REPORT.md`) | `tools/plugins/REPORT.md` |
| `plugins/framework` | TFruityHost shim。fw stage-2 は runner で再構築可能 (PLG-P0a)。framework smoke PASS・hs_e2e Phase B は未達 (memory access out of bounds。#985) | `tools/plugins/framework/REPORT.md` |
| `plugins/p0c` | kernel 表検証+f80 | `tools/plugins/p0c/REPORT.md` |
| `shared` | 分類+OSS 再ビルド+プロプラ lift PoC | `tools/shared/REPORT.md` |
| `ipp` | 評価・PoC・優先 stub 充填まで完了 | `tools/ipp/REPORT.md` |
| `ipp/shim` | ローダ+署名 thunk | `tools/ipp/shim/REPORT.md` |
| `ipp/shim/fft` | pffft 差替え | `tools/ipp/shim/fft/REPORT.md` |
| `targets/serum2` | 事前解析+lift 可否評価 | `tools/targets/serum2/REPORT.md` |
| `targets/serum2/license` | 呼出点マップ+stub | `tools/targets/serum2/license/REPORT.md` |
| `targets/massivex` | 事前解析+呼出点マップ | `tools/targets/massivex/REPORT.md` |
| `targets/massivex/dsp` | DSP closure lift 計画 | `tools/targets/massivex/dsp/REPORT.md` |
| `targets/kilohearts` | インストーラ解析+snap-in lift 可否 | `tools/targets/kilohearts/REPORT.md` |
| `targets/kilohearts/license` | ライセンス層 (KH-9/10/11) | `tools/targets/kilohearts/license/REPORT.md` |
| `targets/kilohearts/snapins` | KH 共通基盤 lift+harness | `tools/targets/kilohearts/snapins/REPORT.md` |
| `targets/freshair` | 事前解析+lift 可否 | `tools/targets/freshair/REPORT.md` |
| `targets/freshair/lift2` | lift2 実装 | `tools/targets/freshair/lift2/REPORT.md` |
| `e2e` | ハーネス+PASS 実績 | `tools/e2e/REPORT.md` |
| `hosting` | 配信構成 (案 S) | `tools/hosting/REPORT.md` |
| `legal/notices` | THIRD_PARTY_NOTICES 自動生成+記録なし OSS の検出 (LGL-3) | `tools/legal/notices/REPORT.md` |
| `deploy` | デプロイ構成・実績 | `deploy/README.md`・`deploy/REPORT.md` |
| `perf` | 性能計測 | `tools/perf/REPORT.md`・`tools/perf/PERF.md` |

## 4. 次の一手

順序は PM が issue で管理する。ここには現在の優先順だけ置く。

1. **FLEngine 本体の起動突破** — MS5/MS6 の中核。`m11` の残 trap 削減 → `flelift/boot` の起動連鎖完成。
2. **lift 品質ハーネス** — 関数単位の native 実行 (wine/unicorn) と wasm の比較で誤 lift を機械検出 (`m11/REPORT.md` §5-1)。
3. **audio / gui の FLEngine 接続** — MS7/MS8。`tools/audio`・`tools/gui` の設計を runtime へ実装。
4. **OpenCode Actions 基盤 (GitHub Actions)** — 2026-10-12 main 稼働開始 (PR #282, merge `bec32da`)。残 follow-ups は [CI-1] #284 で管理。
5. **Issue/PR の整理** — `[AREA-n]` prefix 統一・`state:*` ラベル不使用 (PM 担当)。


更新 2026-10-14T11:53Z (基準 commit `9ea012b6` / origin/main)。対象期間 2026-10-13T06:13Z 以降の merge PR 1015 件 (REST `pulls?state=closed&base=main` の `merged_at`)。
