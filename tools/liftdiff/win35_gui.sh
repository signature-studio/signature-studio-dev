#!/usr/bin/env bash
# WIN-35 (#3618): native の RegisterClassW・CreateWindowExW を tools/gui の headless host へ向けた spike の再現。
# 既定 (LD_GUI_HL 無し) と GUI 経路 (LD_GUI_HL=1) の spike を 1 回ずつ実行し、窓 surface の統計を出す。
# 統計関数 (gui_hl_stats) の陽性対照として、1 画素だけ描いた合成 surface を数えて sha256 を独立計算と照合する。
# 使い方: FL_WIN64_DIR=<fl-win64 展開先> bash tools/liftdiff/win35_gui.sh   (出力は work/flelift/win35/)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; cd "$HERE"
OUT="$HERE/work/flelift/win35"; mkdir -p "$OUT"

rm -f "$OUT/gui.txt"
LD_GUI_HL=1 LD_GUI_OUT="$OUT/gui.txt" python3 spike_cfi.py targets/flelift.json > "$OUT/spike_gui.log" 2>&1
cp work/flelift/spike_cfi.json "$OUT/spike_gui.json"

env -u LD_GUI_HL python3 spike_cfi.py targets/flelift.json > "$OUT/spike_default.log" 2>&1
cp work/flelift/spike_cfi.json "$OUT/spike_default.json"

python3 - "$OUT" <<'PY'
import json, sys
out = sys.argv[1]
for tag in ("default", "gui"):
    d = json.load(open(f"{out}/spike_{tag}.json"))
    p = d.get("post") or d
    c = p["cfi"]
    names = [x.get("n") for x in c["calls_full"]]
    win = [(x.get("n"), x.get("r")) for x in c["calls_full"] if x.get("n") in ("GetClassInfoW", "RegisterClassW", "CreateWindowExW", "DefWindowProcW", "SetWindowLongPtrW")]
    print(f"{tag}: units_run={p['boot']['units_run']}/{p['boot']['units_total']} first_fail={p['boot']['first_fail']} "
          f"cfi={c['status']} {c['detail'][:24]} imports={c['calls_n']} window={win}")
PY
echo "gui 統計の行数 (全 case): $(wc -l < "$OUT/gui.txt")・うち case=cfi: $(grep -c 'case=cfi' "$OUT/gui.txt" || true)"
grep 'case=cfi' "$OUT/gui.txt" || true

cat > "$OUT/stats_control.c" <<'C'
#include <stdio.h>
#include <stdint.h>
#include "gui_headless.h"
int main(void) {
  uint32_t px[2] = { 0xFF000000u, 0xFF112233u };   /* 2×1: 背景 + 1 画素だけ描いた */
  GuiHlStats st; gui_hl_stats(px, 2, 1, 0xFF000000u, &st);
  printf("control: w=%u h=%u nonbg=%llu colors=%u sha256=", st.w, st.h, (unsigned long long)st.nonbg, st.colors);
  for (int k = 0; k < 32; k++) printf("%02x", st.sha256[k]);
  printf("\n");
  return 0;
}
C
gcc -O1 -w -I../gui/include -I../gui/src -o "$OUT/stats_control" "$OUT/stats_control.c" ../gui/src/gui_hl_stats.c
"$OUT/stats_control"
printf '\x00\x00\x00\x11\x22\x33' | sha256sum | sed 's/^/independent sha256 (RGB 6 bytes): /'
