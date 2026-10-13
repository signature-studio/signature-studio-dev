#!/usr/bin/env bash
# wbench.sh — GUI-5 (#181) shim 全体 (gui_gdi.c の API: BitBlt/StretchBlt/StretchDIBits/AlphaBlend + clip/xmap/pull/push) の
# wasm (emcc + node, 1920x1080) API 単位 frame time を SIMD128 / scalar (-DGUI_NO_SIMD) で比較する。usage: wbench.sh [N=5]
#   - 同一ソース (test/bench.c) を 2 ビルドし、交互に N 回ずつ実行して min–max を出す (順序偏り・熱の影響を避ける)
#   - 取り違え防止: wasm 全体の v128 系命令数で「SIMD ビルド > 0 かつ scalar ビルド < SIMD ビルド」を確認。違えば exit 1 (画素一致は本 bench の対象外)
#   - gui_now_ms は 1 ms 粒度 (30 反復/行 → 約 0.033 ms/frame 刻み)。画素の SIMD == scalar 一致は simd_e2e.sh / selftest が担う (本 bench は時間のみ)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; R="$HERE/.."; N="${1:-5}"; B="$R/build/wbench"; mkdir -p "$B"
set +u; . "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1 || true; set -u
command -v emcc >/dev/null || { echo "emcc not found" >&2; exit 2; }
command -v x86_64-w64-mingw32-gcc >/dev/null || { echo "x86_64-w64-mingw32-gcc not found (apt: gcc-mingw-w64-x86-64)" >&2; exit 2; }
python3 "$R/gen_api.py" >/dev/null
SRC=("$R"/src/gui_platform.c "$R"/src/gui_reach.c "$R"/build/gui_reach_tab.c "$R"/src/gui_core.c "$R"/src/gui_gdi.c "$R"/src/gui_headless.c "$R"/build/gui_stubs.c "$HERE/bench.c" "$HERE/wbench_shim.c")
for m in scalar simd; do
  F=(-msimd128); [ "$m" = scalar ] && F=(-DGUI_NO_SIMD)
  emcc -O2 -w -fwrapv -fno-strict-aliasing -pthread "${F[@]}" -DBENCH_BPP -I "$R/include" -I "$R/src" -I "$R/build" "${SRC[@]}" -o "$B/b_$m.cjs" \
    -sGLOBAL_BASE=1048576 -sENVIRONMENT=node -sEXIT_RUNTIME=1 -sINITIAL_MEMORY=268435456 -sSTACK_SIZE=1048576 -sPTHREAD_POOL_SIZE=4 -sPROXY_TO_PTHREAD=1
done
OBJD=/opt/emsdk/upstream/bin/llvm-objdump; [ -x "$OBJD" ] || OBJD=llvm-objdump
v() { "$OBJD" -d "$B/b_$1.wasm" 2>/dev/null | grep -cE 'v128\.|i32x4\.|i16x8\.|i8x16\.' || true; }
vs=$(v simd); vn=$(v scalar)
echo "[wbench] v128 系命令数 (最終 wasm 全体): simd=$vs scalar=$vn"
[ "$vs" -gt 0 ] && [ "$vn" -lt "$vs" ] || { echo "[wbench] FAIL: SIMD ビルドと scalar ビルドの v128 命令数が期待と違う (ビルド取り違え)"; exit 1; }
echo "[wbench] node $(node --version), $(nproc) CPU, load(1m) $(cut -d' ' -f1 /proc/loadavg), $N runs x 2 (交互)"
for m in scalar simd; do : > "$B/w_$m.txt"; done
for i in $(seq 1 "$N"); do for m in scalar simd; do timeout 120 node "$B/b_$m.cjs" | grep '^\[bench\]' >> "$B/w_$m.txt"; done; done
echo "[wbench] load(1m) after: $(cut -d' ' -f1 /proc/loadavg)"
python3 - "$B/w_scalar.txt" "$B/w_simd.txt" "$N" <<'PY'
import re, sys
N = int(sys.argv[3])
def load(p):
    d = {}
    for l in open(p):
        m = re.match(r"\[bench\] (.+?)\s+\d+x\d+\s+[0-9.]+ Mpx/s\s+\(([0-9.]+) ms/frame", l)
        d.setdefault(m.group(1).strip(), []).append(float(m.group(2)))
    return d
sc, si = load(sys.argv[1]), load(sys.argv[2])
bad = [k for k in list(sc) + list(si) if len(sc.get(k, [])) != N or len(si.get(k, [])) != N]
if bad: print("[wbench] FAIL: 実行回数が不足", bad); sys.exit(1)
print("| API (1920x1080, wasm/node) | scalar ms/frame (min-max, n=%d) | simd128 ms/frame (min-max, n=%d) | min 比 |" % (N, N))
print("|---|---|---|---|")
for k in sc:
    print("| %s | %.2f-%.2f | %.2f-%.2f | %.2fx |" % (k, min(sc[k]), max(sc[k]), min(si[k]), max(si[k]), min(sc[k]) / min(si[k])))
PY
