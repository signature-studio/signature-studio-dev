#!/usr/bin/env bash
# lift IR (tools/m11 の boot_final2.ll) が declare している API のうち api_matrix.tsv に載るものについて、
# IR 側の wasm 署名と winstubs/shimx の定義側署名が一致するか (wasm-ld の "function signature mismatch" 0 件) を検査する。
# 20MB の IR 全体はリンクせず、declare 行だけを抜いて各 API を 1 回ずつ呼ぶ最小 .ll を生成してリンクする。
#   使い方: verify_sig_ir.sh <work dir> [ir.ll ...]      IR が無ければ SKIP (exit 0)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"
WORK="${1:-$HERE/../work/winstubs}"; shift || true
IRS=("$@"); [ ${#IRS[@]} -eq 0 ] && IRS=("$HERE/../../m11/work/boot_final2.ll")
. "$HERE/scripts/env.sh"
SHIMX="$HERE/../../shimx"
fail=0
for IR in "${IRS[@]}"; do
    if [ ! -f "$IR" ]; then echo "[verify_sig_ir] SKIP: $IR が無い"; continue; fi
    tag="$(basename "$IR" .ll)"
    python3 "$HERE/scripts/gen_sigprobe.py" "$IR" "$WORK/sigprobe_$tag.ll" > "$WORK/sigprobe_$tag.info"
    cat "$WORK/sigprobe_$tag.info" | sed 's/^/    /'
    OBJS=("$WORK"/obj_ST/shimx/*.o "$WORK"/obj_ST/ws/*.o)
    WR=(); while read -r s; do [ -z "$s" ] || WR+=("-Wl,--wrap=$s"); done < <(grep -v '^#' "$HERE/wrap_list.txt")
    LOG="$WORK/sigprobe_$tag.log"
    emcc "$WORK/sigprobe_$tag.ll" "${OBJS[@]}" "${WR[@]}" -o "$WORK/sigprobe_$tag.js" -w -O0 -sALLOW_MEMORY_GROWTH=1 -sENVIRONMENT=node \
        -sERROR_ON_UNDEFINED_SYMBOLS=0 --no-entry -sGLOBAL_BASE=268435456 -Wl,--error-limit=0 -Wl,--no-gc-sections > "$LOG" 2>&1 || { tail -5 "$LOG"; echo "[verify_sig_ir] $tag: リンク失敗"; fail=1; continue; }
    N=$(grep -ci "function signature mismatch" "$LOG" || true)
    U=$(grep -c "undefined symbol" "$LOG" || true)
    echo "[verify_sig_ir] $tag: signature mismatch = $N / undefined symbol = $U"
    [ "$N" -eq 0 ] || { grep -A2 -i "function signature mismatch" "$LOG" | head -30; fail=1; }
    [ "$U" -eq 0 ] || { grep "undefined symbol" "$LOG" | head; fail=1; }
done

# 検出器の健全性 (陰性対照): 故意に i64 署名で declare した GetSystemMetrics が mismatch として検出されること
cat > "$WORK/sigprobe_neg.ll" <<'LL'
target triple = "wasm32-unknown-emscripten"
declare i64 @GetSystemMetrics(i64)
define void @sigprobe_main() {
  call i64 @GetSystemMetrics(i64 0)
  ret void
}
LL
emcc "$WORK/sigprobe_neg.ll" "$WORK"/obj_ST/shimx/*.o "$WORK"/obj_ST/ws/*.o -o "$WORK/sigprobe_neg.js" -w -O0 -sALLOW_MEMORY_GROWTH=1 -sENVIRONMENT=node \
    -sERROR_ON_UNDEFINED_SYMBOLS=0 --no-entry -sGLOBAL_BASE=268435456 -Wl,--no-gc-sections > "$WORK/sigprobe_neg.log" 2>&1 || true
NN=$(grep -ci "function signature mismatch" "$WORK/sigprobe_neg.log" || true)
echo "[verify_sig_ir] 陰性対照 (故意の i64 署名): mismatch 検出 = $NN (期待 1)"
[ "$NN" -eq 1 ] || fail=1
exit $fail
