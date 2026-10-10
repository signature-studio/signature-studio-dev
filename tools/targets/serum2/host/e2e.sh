#!/usr/bin/env bash
# CAB-68 [SR-1] 1 コマンド E2E — native (wine) 最小 host で Serum2 実 DLL を駆動
#
# 行うこと:
#   1. host build (mingw-w64)
#   2. authstub 適用 DLL 生成 (CAB-237 mpatch.py, work/ 参照) + CAB-237 合成 state
#   3. seed run (plugin 自身の既定 state 保存 → payload 抽出源)
#   4. case 生成 (licensed / demo — make_cases.py v2)
#   5. 2×2 matrix: (patched|unpatched) × (licensed|demo)
#      + unpatched process-only (DSP sanity の認可非依存確認)
#   6. 判定サマリ出力 (work/e2e_result.txt)
#
# 成果物はすべて tools/targets/serum2/host/work/ (gitignore)
set -uo pipefail
cd "$(dirname "$0")"
S2=..  # tools/targets/serum2
HOSTDIR=$PWD
W=$HOSTDIR/work
mkdir -p "$W"

WINEPREFIX=${WINEPREFIX:-$W/wineprefix}
export WINEPREFIX WINEDEBUG=-all
CONTENT='Z:\home\ubuntu\work\webstudio\tools\targets\serum2\work\exe_extract'
DLL_ORIG='Z:\home\ubuntu\work\webstudio\tools\targets\serum2\work\Serum2_win64.vst3'
DLL_PATCH='Z:\home\ubuntu\work\webstudio\tools\targets\serum2\host\work\Serum2_win64.authstub.vst3'

echo "== [1/6] host build =="
bash build.sh || exit 1

echo "== [2/6] authstub DLL + 合成 state =="
if [ ! -f "$W/Serum2_win64.authstub.vst3" ]; then
  (cd "$S2" && python3 license/authstub/mpatch.py work/Serum2_win64.vst3 host/work/Serum2_win64.authstub.vst3) || exit 1
fi
if [ ! -f "$W/state/host/processor_state.json" ]; then
  (cd "$S2" && python3 license/authstub/synth_state.py host/work/state) || exit 1
fi

echo "== [3/6] seed run (既定 state 取得) =="
wine64 "$HOSTDIR/work/build/vst3host.exe" "$DLL_PATCH" - 'Z:\home\ubuntu\work\webstudio\tools\targets\serum2\host\work\out_seed' 4 "$CONTENT" > /dev/null 2>&1
[ -f "$W/out_seed/saved_processor_state.bin" ] || { echo "seed run 失敗"; exit 1; }

echo "== [4/6] case 生成 =="
(cd "$S2" && python3 host/make_cases.py host/work/state host/work/out_seed host/work/cases) || exit 1

echo "== [5/6] 2x2 matrix + process-only =="
run() { # $1=dll $2=case $3=out(Z:パス) $4=blocks — console は work/<outdir名>.console に
  local tag
  tag="${3##*\\}"
  wine64 "$HOSTDIR/work/build/vst3host.exe" "$1" "$2" "$3" "$4" "$CONTENT" > "$HOSTDIR/work/$tag.console" 2>&1
  echo "  exit=$? -> $3"
}
CASES_LIC='Z:\home\ubuntu\work\webstudio\tools\targets\serum2\host\work\cases\licensed'
CASES_DEMO='Z:\home\ubuntu\work\webstudio\tools\targets\serum2\host\work\cases\demo'
OUTB='Z:\home\ubuntu\work\webstudio\tools\targets\serum2\host\work'
mkdir -p "$W/out_p_lic2" "$W/out_p_demo" "$W/out_u_lic" "$W/out_u_demo" "$W/out_u_proc"
run "$DLL_PATCH" "$CASES_LIC" "$OUTB\\out_p_lic2" 64
run "$DLL_PATCH" "$CASES_DEMO" "$OUTB\\out_p_demo" 64
run "$DLL_ORIG"  "$CASES_LIC" "$OUTB\\out_u_lic"  64
run "$DLL_ORIG"  "$CASES_DEMO" "$OUTB\\out_u_demo" 64
run "$DLL_ORIG"  "-"           "$OUTB\\out_u_proc" 64

# corrupt payload run (payload が setState 内で実処理されることの実証)
python3 - <<'PYEOF'
import os
w = os.path.join(os.path.dirname(os.path.abspath("e2e.sh")), "work")
os.makedirs(os.path.join(w, "cases_corrupt"), exist_ok=True)
for side in ("processor", "controller"):
    d = bytearray(open(os.path.join(w, "cases", "licensed", f"{side}_state.json"), "rb").read())
    jl = int.from_bytes(d[9:17], "little")
    d[jl + 8 + 40] ^= 0xFF
    open(os.path.join(w, "cases_corrupt", f"{side}_state.json"), "wb").write(bytes(d))
print("  corrupt case 生成 ok")
PYEOF
run "$DLL_ORIG" 'Z:\home\ubuntu\work\webstudio\tools\targets\serum2\host\work\cases_corrupt' "$OUTB\\out_u_corrupt" 16

echo "== [6/6] 判定 =="
python3 summarize.py "$W" | tee "$W/e2e_result.txt"
