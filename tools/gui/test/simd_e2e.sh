#!/usr/bin/env bash
# simd_e2e.sh — GUI-5 (#181) の wasm SIMD128 行カーネル検証 (emcc + node; FL・RetDec・Chrome 不要)。
#   1. SIMD 無効ビルドでは simd_test が exit 2 で拒否する (SIMD 比較が scalar 同士にすり替わって PASS しないこと)
#   2. -msimd128 ビルドで simd_test PASS (scalar 参照と画素完全一致)
#   3. ネガティブコントロール: 故意の欠陥 4 種 (-DGS_FAULT=1..4) を入れた SIMD ビルドは全て FAIL (exit 1 + MISMATCH 出力) すること
#   4. gui_gdi.c を -msimd128 で wasm 化すると v128 命令が入り、-DGUI_NO_SIMD では 0 であること (SIMD 経路が実際にリンクされる証跡)
#   5. 1080p 行カーネル bench (scalar / simd 各 5 回, min–max)。BENCH=0 で省略
# 1 つでも期待外なら exit 1。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/.."; B="$ROOT/build/simd"; mkdir -p "$B"
set +u; . "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1 || true; set -u
command -v emcc >/dev/null || { echo "emcc not found" >&2; exit 2; }
LF=(-sENVIRONMENT=node -sEXIT_RUNTIME=1 -sALLOW_MEMORY_GROWTH=1)
cc() { emcc -O2 -I "$ROOT/src" "$@" "${LF[@]}" 2>&1 | grep -v "^$" | head -5 || true; }
rc() { set +e; node "$1" >"$2" 2>&1; local r=$?; set -e; echo $r; }
fail=0
echo "[simd-e2e] 1/5 SIMD 無効ビルドの simd_test は exit 2 で拒否"
cc "$HERE/simd_test.c" -o "$B/t_scalar.cjs"
r=$(rc "$B/t_scalar.cjs" "$B/t_scalar.out"); [ "$r" = 2 ] && echo "  OK (exit $r)" || { echo "  FAIL: exit $r (期待 2)"; fail=1; }
echo "[simd-e2e] 2/5 -msimd128 simd_test (SIMD == scalar)"
cc -msimd128 "$HERE/simd_test.c" -o "$B/t_simd.cjs"
r=$(rc "$B/t_simd.cjs" "$B/t_simd.out"); tail -1 "$B/t_simd.out"; [ "$r" = 0 ] && echo "  OK" || { echo "  FAIL: exit $r"; fail=1; }
echo "[simd-e2e] 3/5 ネガティブコントロール (故意の欠陥は全て検出されること)"
for f in 1 2 3 4; do
  cc -msimd128 -DGS_FAULT=$f "$HERE/simd_test.c" -o "$B/t_fault$f.cjs"
  r=$(rc "$B/t_fault$f.cjs" "$B/t_fault$f.out"); n=$(grep -c '^MISMATCH' "$B/t_fault$f.out" || true)
  if [ "$r" = 1 ] && [ "$n" -ge 1 ]; then echo "  OK GS_FAULT=$f -> FAIL as expected ($(tail -1 "$B/t_fault$f.out"))"; else echo "  FAIL: GS_FAULT=$f exit $r mismatches=$n (欠陥を検出できていない)"; fail=1; fi
done
echo "[simd-e2e] 4/5 gui_gdi.c の wasm 化で v128 命令が入る (SIMD 有り / 無し)"
CF=(-O2 -w -fwrapv -pthread -I "$ROOT/include" -I "$ROOT/src" -I "$ROOT/build")
python3 "$ROOT/gen_api.py" >/dev/null
emcc -c "${CF[@]}" -msimd128 "$ROOT/src/gui_gdi.c" -o "$B/gdi_simd.o"; emcc -c "${CF[@]}" -DGUI_NO_SIMD "$ROOT/src/gui_gdi.c" -o "$B/gdi_nosimd.o"
OBJD=/opt/emsdk/upstream/bin/llvm-objdump; [ -x "$OBJD" ] || OBJD=llvm-objdump
ns=$("$OBJD" -d "$B/gdi_simd.o" | grep -cE 'v128\.|i32x4\.|i16x8\.|i8x16\.' || true); nn=$("$OBJD" -d "$B/gdi_nosimd.o" | grep -cE 'v128\.|i32x4\.|i16x8\.|i8x16\.' || true)
echo "  v128 系命令数: -msimd128 = $ns / -DGUI_NO_SIMD = $nn"
[ "$ns" -gt 0 ] && [ "$nn" = 0 ] && echo "  OK" || { echo "  FAIL"; fail=1; }
if [ "${BENCH:-1}" = 1 ]; then
  echo "[simd-e2e] 5/5 1080p 行カーネル bench (node $(node --version), load $(cut -d' ' -f1-3 /proc/loadavg), 5 回)"
  cc "$HERE/simd_bench.c" -o "$B/b_scalar.cjs"; cc -msimd128 "$HERE/simd_bench.c" -o "$B/b_simd.cjs"
  for m in scalar simd; do : > "$B/bench_$m.txt"; for i in 1 2 3 4 5; do node "$B/b_$m.cjs" | grep ms/frame >> "$B/bench_$m.txt"; done; done
  python3 - "$B/bench_scalar.txt" "$B/bench_simd.txt" <<'PY'
import re, sys
def load(p):
    d = {}
    for l in open(p):
        m = re.match(r"(.+?)\s+([0-9.]+) ms/frame", l)
        d.setdefault(m.group(1).strip(), []).append(float(m.group(2)))
    return d
sc, si = load(sys.argv[1]), load(sys.argv[2])
print("| kernel (1920x1080) | scalar ms/frame (min-max, n=5) | simd128 ms/frame (min-max, n=5) | min 比 |")
print("|---|---|---|---|")
for k in sc:
    print("| %s | %.3f-%.3f | %.3f-%.3f | %.2fx |" % (k, min(sc[k]), max(sc[k]), min(si[k]), max(si[k]), min(sc[k]) / min(si[k])))
PY
fi
[ "$fail" = 0 ] && echo "[simd-e2e] ALL PASS" || { echo "[simd-e2e] FAILED"; exit 1; }
