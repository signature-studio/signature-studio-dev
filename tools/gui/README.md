# tools/gui — Win32 GUI shim (user32/gdi32 → OffscreenCanvas + SAB)

FL の GUI (Win32 user32/gdi32 経由のウィンドウ・メッセージループ・BitBlt/DIB) をブラウザへ載せる shim の設計と PoC。

- 設計仕様: [PROTOCOL.md](PROTOCOL.md) / import 優先度: [IMPORTS.md](IMPORTS.md) / 結果: [REPORT.md](REPORT.md)
- 1 コマンド E2E: `bash tools/gui/e2e.sh` (mingw PE → RetDec → emcc → headless Chrome → golden 比較; `SKIP_NATIVE=1` で native 層を省略)
- native 単体テストのみ: `bash tools/gui/test/selftest.sh`
- ブラウザ側 host: `src/runtime/gui.ts` (入力/起動), `gui_worker.ts` (描画), `gui_proto.ts` (プロトコルミラー)
- 中間生成物は `build/` `work/` (gitignore)。node は emsdk 同梱 (`. /opt/emsdk/emsdk_env.sh`) を使用。

使い方 (組込み側): wasm を `-pthread -sPROXY_TO_PTHREAD -sGLOBAL_BASE=1048576 -sEXPORTED_FUNCTIONS=_gui_shared_ptr,...` で作り、
`gui_core.c gui_gdi.c gui_platform.c` + `build/gui_stubs.c` をリンク、lifted C は `#include "gui_api.h"`。
ページ側は `GuiHost.attach({canvas, memory: Module.wasmMemory, base: Module._gui_shared_ptr(), width, height, workerUrl})`。

結合 (実 FLEngine; CAB-173) 向け: [INTEGRATION.md](INTEGRATION.md) (リンク手順・ABI チェックリスト・到達 API ログ) / [integ/INTEGRATION_XCHECK.md](integ/INTEGRATION_XCHECK.md) (m11 IR との署名突合表; `python3 tools/gui/integ/gen_adapt.py`)。
検証: `bash tools/gui/test/reach_test.sh` (到達ログ/adapter/31bit) / `bash tools/gui/integ/sigprobe.sh` (wasm-ld 署名検査) / `bash tools/gui/lift/gui_wasm.sh <lifted.c> <out> reach` (到達ログ付き wasm)。
