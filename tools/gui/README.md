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
