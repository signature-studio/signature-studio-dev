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
# wine の Z: ドライブは / を指す。リポジトリ位置から導出する (旧: /home/ubuntu/work/webstudio 固定)
export PATH="/usr/lib/wine:$PATH"
S2ABS=$(cd "$S2" && pwd)
ZS2='Z:'"${S2ABS//\//\\}"
CONTENT="$ZS2\\work\\exe_extract"
DLL_ORIG="$ZS2\\work\\Serum2_win64.vst3"
DLL_PATCH="$ZS2\\host\\work\\Serum2_win64.authstub.vst3"

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
wine64 "$HOSTDIR/work/build/vst3host.exe" "$DLL_PATCH" - "$ZS2\\host\\work\\out_seed" 4 "$CONTENT" > /dev/null 2>&1
[ -f "$W/out_seed/saved_processor_state.bin" ] || { echo "seed run 失敗"; exit 1; }

echo "== [4/6] case 生成 =="
(cd "$S2" && python3 host/make_cases.py host/work/state host/work/out_seed host/work/cases) || exit 1

echo "== [5/6] 2x2 matrix + process-only + payload 注入 A/B =="
run() { # $1=dll $2=case $3=out(Z:パス) $4=blocks — console は work/<outdir名>.console に
  local tag
  tag="${3##*\\}"
  wine64 "$HOSTDIR/work/build/vst3host.exe" "$1" "$2" "$3" "$4" "$CONTENT" > "$HOSTDIR/work/$tag.console" 2>&1
  echo "  exit=$? -> $3"
}
CASES_LIC="$ZS2\\host\\work\\cases\\licensed"
CASES_DEMO="$ZS2\\host\\work\\cases\\demo"
OUTB="$ZS2\\host\\work"
mkdir -p "$W/out_p_lic2" "$W/out_p_demo" "$W/out_u_lic" "$W/out_u_demo" "$W/out_u_proc"
run "$DLL_PATCH" "$CASES_LIC" "$OUTB\\out_p_lic2" 64
run "$DLL_PATCH" "$CASES_DEMO" "$OUTB\\out_p_demo" 64
run "$DLL_ORIG"  "$CASES_LIC" "$OUTB\\out_u_lic"  64
run "$DLL_ORIG"  "$CASES_DEMO" "$OUTB\\out_u_demo" 64
run "$DLL_ORIG"  "-"           "$OUTB\\out_u_proc" 64

# payload 注入 A/B (#255): sentinel 対照 (lic_sent) と demo payload (demo_payload) × (patched|unpatched)
CASES_LS="$ZS2\\host\\work\\cases\\lic_sent"
CASES_DP="$ZS2\\host\\work\\cases\\demo_payload"
mkdir -p "$W/out_p_lsent" "$W/out_u_lsent" "$W/out_p_dpl" "$W/out_u_dpl"
run "$DLL_PATCH" "$CASES_LS" "$OUTB\\out_p_lsent" 16
run "$DLL_ORIG"  "$CASES_LS" "$OUTB\\out_u_lsent" 16
run "$DLL_PATCH" "$CASES_DP" "$OUTB\\out_p_dpl" 16
run "$DLL_ORIG"  "$CASES_DP" "$OUTB\\out_u_dpl" 16

# payload 側 productVersion 下げ A/B (#341): lowver (payload productVersion=2.0.19) × (patched|unpatched)
CASES_LV="$ZS2\\host\\work\\cases\\lowver"
mkdir -p "$W/out_p_lowver" "$W/out_u_lowver"
run "$DLL_PATCH" "$CASES_LV" "$OUTB\\out_p_lowver" 16
run "$DLL_ORIG"  "$CASES_LV" "$OUTB\\out_u_lowver" 16

# 強制ゲート A/B (#341): controller +0xdc は headless で 2 のまま (§3-3) → 0x1800c2cd7 の `cmp [this+0xdc],1` で
# productVersion 比較に到達しない。S2HOST_FORCE_GATE=1 で +0xdc を ctrl setState 直前に 1 へ書換えて比較へ到達させる。
# {patched,unpatched} × {lic_sent (payload pv=2.1.5), lowver (2.0.19), demo_payload (ctrl マーカ false)}
for c in lic_sent lowver demo_payload; do
  for d in p u; do
    [ $d = p ] && DLLX="$DLL_PATCH" || DLLX="$DLL_ORIG"
    mkdir -p "$W/out_${d}_g1_${c}"
    S2HOST_FORCE_GATE=1 run "$DLLX" "$ZS2\\host\\work\\cases\\$c" "$OUTB\\out_${d}_g1_${c}" 16
  done
done

# #1360: 既定 host の gate==2 の原因 (0x180037600 の wrapper QI 2 件が kNoInterface) を、
# S2HOST_WRAPPER_QI=1 で IVst3ToAUWrapper/IVst3ToAAXWrapper に kResultOk を返して外す。
# gate は 1 になり 0x800010 が出る (既定 host では出ない)。既定 run は上の 50 件を変えない。
# {patched,unpatched} × {lic_sent, lowver, demo_payload} (ゲート強制無し)
for c in lic_sent lowver demo_payload; do
  for d in p u; do
    [ $d = p ] && DLLX="$DLL_PATCH" || DLLX="$DLL_ORIG"
    mkdir -p "$W/out_${d}_wq_${c}"
    S2HOST_WRAPPER_QI=1 run "$DLLX" "$ZS2\\host\\work\\cases\\$c" "$OUTB\\out_${d}_wq_${c}" 16
  done
done

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
run "$DLL_ORIG" "$ZS2\\host\\work\\cases_corrupt" "$OUTB\\out_u_corrupt" 16

echo "== [6/6] 判定 =="
python3 summarize.py "$W" | tee "$W/e2e_result.txt"
RC=${PIPESTATUS[0]}

# ネガティブコントロール (#341): 判定が壊れた入力で必ず FAIL することの確認。
#   NC1: unpatched+g1+lowver の summary を lic_sent のもの (pv>=2.0.20 = bit 0) に差し替え → 契約チェックが NG になること
#   NC2: out_u_lowver (gate==2) の summary を g1+lowver のもの (bit 1) に差し替え → 「gate==2 では無影響」が NG になること
NCW="$W/nc"
rm -rf "$NCW"; mkdir -p "$NCW"
for d in "$W"/out_*; do [ -d "$d" ] && { mkdir -p "$NCW/$(basename "$d")"; cp "$d"/summary.json "$d"/saved_*_state.bin "$NCW/$(basename "$d")/" 2>/dev/null; }; done
cp "$W/out_u_g1_lic_sent/summary.json" "$NCW/out_u_g1_lowver/summary.json"
python3 summarize.py "$NCW" > "$NCW/nc1.txt"; NC1=$?
NC1_NG=$(grep -c "\[NG\]" "$NCW/nc1.txt")
for d in "$W"/out_*; do [ -d "$d" ] && cp "$d"/summary.json "$NCW/$(basename "$d")/" 2>/dev/null; done
cp "$W/out_u_g1_lowver/summary.json" "$NCW/out_u_lowver/summary.json"
python3 summarize.py "$NCW" > "$NCW/nc2.txt"; NC2=$?
NC2_NG=$(grep -c "\[NG\]" "$NCW/nc2.txt")
echo "== ネガティブコントロール =="
echo "  NC1 (契約チェックを壊す): summarize exit=$NC1, NG=$NC1_NG (期待: exit!=0 かつ NG>=1)" | tee -a "$W/e2e_result.txt"
echo "  NC2 (gate==2 無影響チェックを壊す): summarize exit=$NC2, NG=$NC2_NG (期待: exit!=0 かつ NG>=1)" | tee -a "$W/e2e_result.txt"
if [ "$NC1" -eq 0 ] || [ "$NC1_NG" -lt 1 ] || [ "$NC2" -eq 0 ] || [ "$NC2_NG" -lt 1 ]; then
  echo "NEGATIVE CONTROL FAILED: 判定が壊れた入力で FAIL しない" >&2
  exit 3
fi
exit "$RC"
