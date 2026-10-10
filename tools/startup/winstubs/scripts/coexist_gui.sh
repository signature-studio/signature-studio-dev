#!/usr/bin/env bash
# tools/gui (CAB-8) の shim 一式 (読取専用) と winstubs の weak 定義が共存できるか (強定義が勝つか) を検査する。
#   gui の .o は work/ にビルド (tools/gui 内は無改変)。duplicate symbol が winstubs 由来 (FindWindowW 等) なら FAIL。
#   shimx × gui の既存重複 (WTSRegisterSessionNotification) は記録のみ。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"
WORK="${1:-$HERE/../work/winstubs}"
G="$HERE/../../gui"
. "$HERE/scripts/env.sh"
if [ ! -f "$G/build/gui_adapt_w32.c" ]; then echo "[coexist_gui] SKIP: tools/gui/build/gui_adapt_w32.c が無い"; exit 0; fi
source "$HERE/../../shimx/flags.sh"
mkdir -p "$WORK/gui_obj"
CF=(-O1 -fwrapv -w -fno-strict-aliasing -pthread -I "$G/include" -I "$G/src" -I "$G/build")
for f in "$G/src/gui_core.c" "$G/src/gui_gdi.c" "$G/build/gui_stubs.c"; do
    emcc -c "${CF[@]}" -DGUI_NO_K32 -include "$G/build/gui_rename.h" "$f" -o "$WORK/gui_obj/$(basename "$f" .c).o"
done
for f in "$G/src/gui_platform.c" "$G/src/gui_reach.c" "$G/build/gui_reach_tab.c" "$G/build/gui_adapt_w32.c"; do
    emcc -c "${CF[@]}" "$f" -o "$WORK/gui_obj/$(basename "$f" .c).o"
done
WR=(); while read -r s; do [ -z "$s" ] || WR+=("-Wl,--wrap=$s"); done < <(grep -v '^#' "$HERE/wrap_list.txt")
LINK=(emcc -O1 -w -pthread "${SHIMX_EMCC_MT[@]}" "${WR[@]}" -Wl,--error-limit=0 "$WORK/probe.c" "$WORK"/obj_MT/shimx/*.o "$WORK"/obj_MT/ws/*.o "$WORK"/gui_obj/*.o)
DUP="$("${LINK[@]}" -o "$WORK/probe_gui.js" 2>&1 | grep -o 'duplicate symbol: [A-Za-z0-9_]*' | sed 's/duplicate symbol: //' | sort -u || true)"
echo "[coexist_gui] shimx × gui の重複シンボル: ${DUP:-なし}"
BAD="$(echo "$DUP" | grep -v '^WTSRegisterSessionNotification$' | grep -v '^$' || true)"
[ -z "$BAD" ] || { echo "[coexist_gui] FAIL: winstubs 由来の重複: $BAD"; exit 1; }
"${LINK[@]}" -Wl,--allow-multiple-definition -o "$WORK/probe_gui.js" >/dev/null 2>&1
mv "$WORK/probe_gui.js" "$WORK/probe_gui.cjs"
NOTSAME=$(node "$WORK/probe_gui.cjs" | grep -v 'same=1' | grep -vc 'gpa=-' || true)
STRONG=0; for s in FindWindowW FindWindowExW GetSystemMetrics SystemParametersInfoW BufferedPaintInit LoadIconW PeekMessageW GetMessageW; do
    llvm-nm --defined-only -g "$WORK/gui_obj/gui_adapt_w32.o" | grep -q " T $s$" && STRONG=$((STRONG+1)) || true; done
echo "[coexist_gui] weak 定義と衝突せず gui 強定義が優先: gui 側が強定義する対象 $STRONG/8、probe の GetProcAddress 不整合 = $NOTSAME"
[ "$NOTSAME" -eq 0 ] || exit 1
