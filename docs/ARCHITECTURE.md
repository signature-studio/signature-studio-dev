# ARCHITECTURE — パイプライン全体像

正本: 本ファイルが**パイプライン構造**の唯一の正本。
測定値・実測数値は書かない (それらは `tools/<area>/REPORT.md` が単一の正本)。
背景にある元戦略文書は `docs/REFERENCES.md` `[STRATEGY]`。

---

## 1. 全体像

```
[素材] FL Studio 26.1.7 (win64 FLEngine_x64.dll / mac FLEngine_x64.dylib) + プロプライエタリ plugin
   │
   ▼
① 解析 (tools/m2)         関数境界・Delphi 品質・shim 照合・インベントリ生成 (機械化)
   │
   ▼
② lift (x64c / flelift)   capstone ベースの自作 x86-64 → C lifter (`x64c.py`)。
   │                      FLEngine 向け汎用化は `tools/flelift`、OTT 向けの本家は
   │                      `tools/ott/lift/x64c.py` (vendored fork の元)。
   │                      ネイティブ依存 (DirectSound/ASIO/Win32 FS/registry/window) は
   │                      shim 層でブラウザ API に吸収。FL 側コードは極力変更しない。
   │                      旧路線 RetDec は構造欠陥が多く主役を退いた (DECISIONS D5)
   ▼
③ IR pass (liftlib)       共通 lift 修復基盤。load 取り違え / 2 段 deref / 引数脱落 /
   │                      value-flow / 間接 call 復元 / alloca 縮退 / global 窓 等
   ▼
④ wasm (emcc)              C → LLVM IR → wasm。CRT 数学は DLL 自身の機械語を lift して
   │                      bit-exact を維持
   ▼
⑤ shim / runtime (tools/shim, shimx, runtime)
   │                      Win32/CRT 互換層、パス写像・仮想レジストリ、起動シーケンス stub
   ▼
⑥ host (hostbridge / gui / audio / assets)
   │                      VST2 ホスト、GUI フレーム転送 (SAB→OffscreenCanvas)、
   │                      AudioWorklet + SAB リング、巨大 wasm の chunk ローダ + 二段キャッシュ
   ▼
⑦ deploy (deploy/)        Workers Static Assets (案 S) + Cloudflare Access。_headers で COOP/COEP/CORP
```

## 2. 各段の責務と正本

| 段 | ディレクトリ | 技術レポート (測定値の正本) | 設計/仕様 |
|---|---|---|---|
| 素材・解析 | `analysis/` (repo 外) | `docs/REFERENCES.md` `[WIN64]` / `[MAC]` | — |
| ① 解析機械化 | `tools/m2` | `tools/m2/REPORT.md` | `tools/m2/delphi_inventory.md`・`SHIM_INVENTORY.md` |
| ② lift | `tools/flelift`, `tools/ott/lift` (`x64c.py`), `tools/liftlib` | `tools/flelift/REPORT.md`・`tools/ott/REPORT.md`・`tools/liftlib/REPORT.md` | `tools/liftlib/README.md` |
| ②' OTT 路線 (歴史) | `tools/m5`〜`tools/m10`, `tools/ott` | 各 `REPORT.md`・`tools/ott/REPORT.md` | — |
| ③ IR pass | `tools/liftlib/liftlib/passes/` | `tools/liftlib/REPORT.md` | — |
| ③' 修復 pass 群 | `tools/m11/{alloca,ldfix}` (RetDec 路線・旧), `tools/icall/*`, `tools/startup/{glue,keyfix,pump,vreg}` | 各 `REPORT.md` | — |
| ④ wasm | `tools/m1` (定型フラグ), `tools/m3`/`tools/m5` | `tools/m1/README.md`・`tools/m3/REPORT.md` | `tools/m1/flags.sh` |
| ⑤ shim | `tools/shim`, `tools/shimx` (+`pathreg`) | 各 `REPORT.md` | `tools/shim/README.md`・`tools/shimx/README.md` |
| ⑤' 起動 | `tools/startup`, `tools/m11` (RetDec 路線・旧) | 各 `REPORT.md` | `tools/startup/STARTUP.md`・`GATES.md` |
| ⑥ runtime | `tools/runtime` | `tools/runtime/REPORT.md` | `tools/runtime/DESIGN.md` |
| ⑥ host | `tools/hostbridge` (+`cb`,`h2`,`lowbase`,`nfo`) | 各 `REPORT.md` | `tools/hostbridge/HOSTBRIDGE.md`・`nfo/FORMAT.md` |
| ⑥ gui | `tools/gui` | `tools/gui/REPORT.md` | `tools/gui/PROTOCOL.md`・`INTEGRATION.md` |
| ⑥ audio | `tools/audio` (+`asio`) | 各 `REPORT.md` | `tools/audio/docs/PROTOCOL.md` |
| ⑥ asset | `tools/assets` (+`wvfs`, `bootset`) | 各 `REPORT.md` | `tools/assets/MANIFEST.md` |
| ⑥ python | `tools/python` | `tools/python/REPORT.md` | `tools/python/BRIDGE.md` |
| ⑥ flp | `tools/flp` | `tools/flp/REPORT.md` | `tools/flp/ORACLE.md` |
| ⑥ plugins | `tools/plugins` (+`framework`,`p0c`) | 各 `REPORT.md` | `tools/plugins/ABI.md`・`batch_plan.md`・`PLUGIN_MATRIX.md` |
| ⑦ deploy | `deploy/` | `deploy/REPORT.md` | `deploy/README.md`・`RUNBOOK.md` |
| ⑦ e2e | `tools/e2e` | `tools/e2e/REPORT.md` | — |
| ⑦ hosting | `tools/hosting` | `tools/hosting/REPORT.md` | — |
| 品質 | `tools/liftdiff`, `tools/perf` | 各 `REPORT.md` | `tools/liftdiff/docs/FORMAT.md`・`tools/perf/PERF.md` |

## 3. サブシステム一覧 (ナビゲーション)

`tools/` 配下のサブシステムは下表のとおり。詳細は `README.md` の索引と `docs/DOC_MAP.md`。

| サブシステム | 責務 |
|---|---|
| `m1`,`m2`,`m3`,`m5` | ツールチェイン PoC・FLEngine 解析機械化・中規模/ Delphi lift → wasm |
| `m6`〜`m10`, `ott` | OTT (Xfer) VST2 DSP の lift → wasm 完走路 ( RetDec 路線 ) |
| `m11` (+`alloca`,`ldfix`,`shimx_link`) | RetDec 路線・旧: FLEngine_x64.dll 部分起動 PoC (DllMain → InitUnits → FastMM) |
| `flelift`, `liftlib` | x64c の FLEngine 汎用化・共通 lift 修復基盤 |
| `icall` (+`disp_size`,`landing`) | 間接 call/jmp 落ち監査・修復・Delphi unwind landing pad |
| `shim`, `shimx` (+`pathreg`) | Win32/CRT shim コア・拡張・パス写像/レジストリ永続化 |
| `startup` (+`glue`,`keyfix`,`pump`,`vreg`,`winstubs`) | FL 起動シーケンス・子プロセス・ゲート・仮想レジストリ・stub |
| `runtime` | ブラウザ実行基盤 (wasm ローダ・worker・SAB) |
| `hostbridge` (+`cb`,`h2`,`lowbase`,`nfo`) | VST2 ロード経路・Plugin database `.nfo`/`.fst` |
| `gui` | Win32 user32/gdi32 → OffscreenCanvas + 入力キュー |
| `audio` (+`asio`) | ASIO/WASAPI/DirectSound → AudioWorklet + SAB リング |
| `assets` (+`wvfs`,`bootset`) | 巨大 wasm の chunk ローダ・二段キャッシュ・書込可能 VFS |
| `python` | CPython wasm + flapi/MCP ブリッジ |
| `flp` | FLP/FST パーサ・ライタ・往復コーパス |
| `plugins` (+`framework`,`p0c`) | Fruity プラグイン 141 種 wasm 化 (カウントの正本: `tools/plugins/REPORT.md`)・TFruityHost shim・ABI 推定 |
| `shared` | FL Shared ライブラリ (IPP 実測・OSS wasm 再ビルド・プロプラ lift PoC) |
| `targets/*` | Serum 2 / Massive X / Kilohearts / Fresh Air / OTT の個別解析と lift |
| `e2e`, `hosting`, `deploy` | ブラウザ E2E ハーネス・配信構成・デプロイ手順 |
| `liftdiff`, `perf` | lift 品質の全数採点・wasm 実時間性能 |

## 4. 横断的な原則

1. **外部絶対パスは `docs/REFERENCES.md` だけ**。repo 内の他 `.md` に書かない。
2. **外部通信機能 (Gopher AI / FL Cloud / 認証・ログイン系) は対象外** (`docs/DECISIONS.md` D3)。
3. **スクラッチ再実装は不採用**。実物バイナリの lift → wasm が第一目標 (`docs/DECISIONS.md` D5)。
4. **ライセンス機構の無力化方針**は `docs/LEGAL.md` §6.0 が正本。
