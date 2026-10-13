# tools/gui — Win32 GUI shim (user32/gdi32 → OffscreenCanvas + SAB)

FL の GUI (Win32 user32/gdi32 経由のウィンドウ・メッセージループ・BitBlt/DIB) をブラウザへ載せる shim の設計と PoC。

- 設計仕様: [PROTOCOL.md](PROTOCOL.md) / import 優先度: [IMPORTS.md](IMPORTS.md) / 結果: [REPORT.md](REPORT.md)
- 1 コマンド E2E: `bash tools/gui/e2e.sh` (mingw PE → RetDec → emcc → headless Chrome → golden 比較; `SKIP_NATIVE=1` で native 層を省略)
- native 単体テストのみ: `bash tools/gui/test/selftest.sh`
- ブラウザ側 host: `src/runtime/gui.ts` (入力/起動), `gui_worker.ts` (描画ワーカ; 描画本体は `gui_renderer.ts`、RT-3 で fl-runtime Worker 共用に切り出し), `gui_proto.ts` (プロトコルミラー)
- 中間生成物は `build/` `work/` (gitignore)。node は emsdk 同梱 (`[EMSDK]` の `emsdk_env.sh` を source) を使用。

使い方 (組込み側): wasm を `-pthread -sPROXY_TO_PTHREAD -sGLOBAL_BASE=1048576 -sEXPORTED_FUNCTIONS=_gui_shared_ptr,...` で作り、
`gui_core.c gui_gdi.c gui_platform.c` + `build/gui_stubs.c` をリンク、lifted C は `#include "gui_api.h"`。
ページ側は `GuiHost.attach({canvas, memory: Module.wasmMemory, base: Module._gui_shared_ptr(), width, height, workerUrl})`。

実 FLEngine 結合 (GUI-3 #174): `bash tools/gui/flengine/e2e.sh` (m11 closure + 本 shim を `-pthread` でリンクし、到達 API を集計・判定。結果は [flengine/REPORT.md](flengine/REPORT.md))。
結合 (実 FLEngine; CAB-173) 向け: [INTEGRATION.md](INTEGRATION.md) (リンク手順・ABI チェックリスト・到達 API ログ) / [integ/INTEGRATION_XCHECK.md](integ/INTEGRATION_XCHECK.md) (m11 IR との署名突合表; `python3 tools/gui/integ/gen_adapt.py`)。
検証: `bash tools/gui/test/reach_test.sh` (到達ログ/adapter/31bit) / `bash tools/gui/integ/sigprobe.sh` (wasm-ld 署名検査) / `bash tools/gui/lift/gui_wasm.sh <lifted.c> <out> reach` (到達ログ付き wasm)。
P1 50 名 (CAB-159) の意味論: [PROTOCOL.md §11](PROTOCOL.md)。unit テスト `test/selftest_p1.inc` (selftest 314 assertion) と `python3 tools/gui/integ/check_p1_tests.py` (実装+テスト呼出の機械検査)。

shimx 共存 (#172 SHX-T5): `bash tools/gui/shimx_coexist/coexist.sh` (weak/強定義の共存リンク + ShellExecute→`window.open` / GetOpen・SaveFileName→File System Access / Drag&Drop の host 呼出路。結果は [shimx_coexist/REPORT.md](shimx_coexist/REPORT.md))。
GUI-4 (#180) present (WebGL2 / dirty 複数矩形 / rAF 同期 / seqlock): `bash tools/gui/present/e2e.sh` (FL・lift・wasm 不要の模擬 guest で golden 画素一致・tearing・bench; 結果は REPORT_APPENDIX §9)。方式は `GuiPresentOptions` (`src/runtime/gui_renderer.ts`)、仕様は [PROTOCOL.md §4](PROTOCOL.md)。
GUI-5 (#181) 各 bpp DIB/DDB・wasm SIMD128 行カーネル: `bash tools/gui/test/bpp_golden.sh` (独立 Python オラクル `golden/gen_golden_bpp.py` と画素完全一致 + ネガコン) / `bash tools/gui/test/simd_e2e.sh` (emcc + node: SIMD == scalar・故意欠陥の検出・1080p 行カーネル bench) / `bash tools/gui/test/bench.sh` (native API bench)。結果は REPORT_APPENDIX §10、仕様は [PROTOCOL.md §8](PROTOCOL.md)。
