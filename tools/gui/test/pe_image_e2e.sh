#!/usr/bin/env bash
# GUI-12 (#566): RetDec C 経路の `__pe_image` が m11_data_gen と同じ .reloc DIR64 規則で実体化されることの回帰テスト。
#   mingw PE (イメージ内ポインタ有り) → RetDec → gui_lift_post.py → gcc → 実行 → host gcc 直ビルドの戻り値と一致
#   ネガティブコントロール: --no-pe-reloc (補正を出さない) の lift は host と一致してはならない (一致したらテストが無力 → FAIL)
# 終了コード: 0 = 全 PASS / 1 = FAIL (判定が不合格なら必ず非 0) / 2 = 前提欠如
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/.."; OUT="${PE_IMAGE_OUT:-$ROOT/build/pe_image}"; mkdir -p "$OUT"
command -v x86_64-w64-mingw32-gcc >/dev/null || { echo "[pe_image] 前提欠如: x86_64-w64-mingw32-gcc" >&2; exit 2; }
RETC="${RETDEC_DECOMPILER:-/opt/retdec/bin/retdec-decompiler}"; [ -x "$RETC" ] || { echo "[pe_image] 前提欠如: retdec ($RETC)" >&2; exit 2; }
rc=0; P() { echo "[pe_image] PASS $*"; }; F() { echo "[pe_image] FAIL $*"; rc=1; }
SRC="$HERE/pe_image_app.c"
printf '#include <stdio.h>\nint entry(void);\nint main(void){printf("%%d\\n",entry());return 0;}\n' > "$OUT/host_main.c"
printf '#include <stdio.h>\n#include <stdint.h>\nextern int64_t gui_lift_entry(void);\nint main(void){printf("%%d\\n",(int)gui_lift_entry());return 0;}\n' > "$OUT/lift_main.c"
gcc -w "$SRC" "$OUT/host_main.c" -o "$OUT/host" || { echo "[pe_image] host build 失敗" >&2; exit 2; }
EXPECT="$("$OUT/host")"
x86_64-w64-mingw32-gcc -O0 -ffreestanding -fno-builtin -nostartfiles -nostdlib -mwindows -Wl,-e,entry -Wl,--dynamicbase "$SRC" -o "$OUT/app.exe" -lkernel32 || exit 2
"$RETC" "$OUT/app.exe" -o "$OUT/retdec.c" >/dev/null 2>&1 || exit 2
INC=(-I "$ROOT/include" -I "$ROOT/src" -I "$ROOT/build")
python3 "$ROOT/gen_api.py" >/dev/null 2>&1 || true
run_variant() { # run_variant <tag> [post args...] -> stdout: "<post-summary>|<result or CRASH rc=N>"
  local tag="$1"; shift
  local sum; sum="$(python3 "$ROOT/lift/gui_lift_post.py" "$OUT/retdec.c" "$OUT/app.exe" "$OUT/lifted_$tag.c" "$@" 2>&1 | grep -F '[post] globals')"
  gcc -w -O1 "${INC[@]}" -c "$OUT/lifted_$tag.c" -o "$OUT/lifted_$tag.o" 2> "$OUT/cc_$tag.log" || { echo "$sum|COMPILE-FAIL"; return; }
  gcc -w "$OUT/lifted_$tag.o" "$OUT/lift_main.c" -o "$OUT/lift_$tag" 2>> "$OUT/cc_$tag.log" || { echo "$sum|LINK-FAIL"; return; }
  local r; r="$("$OUT/lift_$tag" 2>/dev/null)"; local c=$?
  [ $c = 0 ] && echo "$sum|$r" || echo "$sum|CRASH rc=$c"
}
echo "[pe_image] host (直ビルド) の戻り値 = $EXPECT"
OK="$(run_variant ok)"; echo "[pe_image] lift (補正あり): $OK"
NC="$(run_variant noreloc --no-pe-reloc)"; echo "[pe_image] lift (補正なし = ネガコン): $NC"
[ "${OK##*|}" = "$EXPECT" ] && P "P1 lift の戻り値が host と一致 ($EXPECT)" || F "P1 lift の戻り値 '${OK##*|}' != host '$EXPECT'"
reb="$(echo "$OK" | sed -n 's/.*rebased=\([0-9]*\).*/\1/p')"
[ "${reb:-0}" -ge 5 ] && P "P2 補正スロット数 $reb >= 5 (文字列表 3 + pa 2 + node 2 の下限)" || F "P2 補正スロット数 '${reb:-?}' < 5 (DIR64 検出が空)"
[ "${NC##*|}" != "$EXPECT" ] && P "N1 補正なしは host と一致しない (${NC##*|}) = テストは補正の欠落を検出できる" || F "N1 補正なしでも host と一致した → テストが補正の有無を区別できない"
# N2: 補正を 1 スロットだけ壊す (オフセットを 8 ずらした表) → 一致してはならない
python3 - "$OUT/lifted_ok.c" "$OUT/lifted_bad1.c" <<'PY'
import re, sys
s = open(sys.argv[1]).read()
m = re.search(r"__pe_image_relocs\[\] = \{(0x[0-9a-f]+)", s)
first = int(m.group(1), 16)
s = s.replace("__pe_image_relocs[] = {0x%x" % first, "__pe_image_relocs[] = {0x%x" % (first + 8), 1)
open(sys.argv[2], "w").write(s)
PY
gcc -w -O1 "${INC[@]}" -c "$OUT/lifted_bad1.c" -o "$OUT/lifted_bad1.o" && gcc -w "$OUT/lifted_bad1.o" "$OUT/lift_main.c" -o "$OUT/lift_bad1" && R1="$("$OUT/lift_bad1" 2>/dev/null)"; c1=$?
if [ $c1 = 0 ] && [ "$R1" = "$EXPECT" ]; then F "N2 補正表を 1 件ずらしても host と一致 → 個別スロットを検査できていない"; else P "N2 補正表 1 件ずらしで不一致/クラッシュ (rc=$c1 out='$R1')"; fi
python3 "$ROOT/lift/pe_image.py" "$OUT/app.exe" | sed 's/^/[pe_image] /'
echo "[pe_image] done → exit $rc"; exit $rc
