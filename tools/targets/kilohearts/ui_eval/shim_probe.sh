#!/usr/bin/env bash
# KH-7 (#59): HeartCore の画面転送呼び出しを M7 GUI shim (tools/gui) へ投入するプローブ。native ビルド (gcc + headless host)。
# gen_api.py (mingw 必須) を使わず、shim 本体 4 ファイルだけをビルドする。tools/gui は読み取りのみ (ビルド物は work/ = gitignore)。
# exit: 0 = 全ケース一致 / 2 = HeartCore 形の不一致が残る (gap) / 1 = ハーネス異常
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
GUI="${KH_GUI_DIR:-$HERE/../../../gui}"   # 既定は repo の tools/gui。修正案の事前検証では修正済みコピーを指定する
WORK="${KH_UI_WORK:-$HERE/work}"; mkdir -p "$WORK"
cat > "$WORK/reach_tab_stub.c" <<'EOT'
#include <stdint.h>
typedef struct { const char *name; uint8_t stub; int8_t prio; } GuiReachEnt;
const GuiReachEnt gui_reach_tab[] = { { "", 0, 0 } };
const int gui_reach_n = 0;
EOT
gcc -O1 -g -w -fsanitize=address,undefined -fno-sanitize-recover=undefined -pthread -I "$GUI/include" -I "$GUI/src" \
  "$GUI"/src/gui_platform.c "$GUI"/src/gui_reach.c "$WORK/reach_tab_stub.c" "$GUI"/src/gui_core.c "$GUI"/src/gui_gdi.c "$GUI"/src/gui_headless.c \
  "$HERE/shim_probe.c" -o "$WORK/shim_probe" -lm
set +e
"$WORK/shim_probe"
rc=$?
set -e
exit $rc
