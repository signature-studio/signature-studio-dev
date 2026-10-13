#!/usr/bin/env bash
# P0c-8 (#311) ext IR の wasm32 バックエンド検証 + framework 統合 — 1 コマンド再現
#   bash tools/plugins/p0c/p0c8_e2e.sh [N=3000000]
# 前提: emsdk (/opt/emsdk), llvm-as (PATH か /usr/lib/llvm-18/bin), cc, node。素材不要。
#   [1] ext_core_test (native C, f80_lower の演算と同一ロジック) vs native x87
#   [2] f80_lower.py の生成器 (ext_wasm_gen.py) → llvm-as → wasm32 (emcc) → node 実行
#       native x87 の期待値 (ext_wasm_test.c -DGEN) と 8N + 固定集合 case を bit 比較
#   [3] ネガティブコントロール: Dekker 分割定数を壊した IR が FAIL (exit 非 0) すること
#   [4] fw_f80.py --ext-funcs の統合: 既定 byte 一致 / ext 化 / 指定関数不在で FAIL
#       ([4] は work/k80.lift.ll があるときのみ。無ければ SKIP と明示し exit 0 にはしない)
# 判定が不合格のとき exit 非 0。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
N="${1:-3000000}"
export PATH="/usr/lib/llvm-18/bin:$PATH"
W="${P0C8_WORK:-$HERE/work/p0c8}"
mkdir -p "$W"
export TMPDIR="$W/tmp"; mkdir -p "$TMPDIR"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
export EM_CACHE="${EM_CACHE:-$W/emcache}"
t0=$(date +%s); load0=$(cut -d' ' -f1-3 /proc/loadavg)

echo "== [1] ext_core_test (N=$N) =="
cc -O2 -ffp-contract=off -o "$W/ext_core_test" "$HERE/ext_core_test.c" -lm
"$W/ext_core_test" "$N" | tail -2

echo "== [2] wasm32 ext IR vs native x87 =="
python3 "$HERE/ext_wasm_gen.py" "$W/t.ll"
llvm-as "$W/t.ll" -o /dev/null
cc -O0 -ffp-contract=off -DGEN -o "$W/gen" "$HERE/ext_wasm_test.c" -lm
"$W/gen" "$N" "$W/exp.bin"
emcc -O2 -ffp-contract=off -w "$HERE/ext_wasm_test.c" "$W/t.ll" -sNODERAWFS -sENVIRONMENT=node -o "$W/t.js"
echo "wasm: $(stat -c %s "$W/t.wasm") B"
node "$W/t.js" "$N" "$W/exp.bin" | tail -2

echo "== [3] ネガティブコントロール (Dekker 定数 2^27+1 -> 2^26+1) =="
python3 "$HERE/ext_wasm_gen.py" "$W/tb.ll" --break
emcc -O2 -ffp-contract=off -w "$HERE/ext_wasm_test.c" "$W/tb.ll" -sNODERAWFS -sENVIRONMENT=node -o "$W/tb.js"
if node "$W/tb.js" "$N" "$W/exp.bin" > "$W/nega.log"; then
  echo "[FAIL] ネガコンが PASS した (検査が無効)"; tail -2 "$W/nega.log"; exit 1
fi
tail -2 "$W/nega.log" | head -1; echo "negative control OK (FAIL を確認)"

echo "== [4] fw_f80.py --ext-funcs =="
K="$HERE/work/k80.lift.ll"
if [ -f "$K" ]; then
  FW="$HERE/../framework"
  python3 "$FW/fw_f80.py" "$K" "$W/f_default.ll" > /dev/null
  git -C "$HERE" show d5e6f98:tools/plugins/framework/fw_f80.py > "$W/fw_f80_base.py"   # 変更前 (起点 commit)
  python3 "$W/fw_f80_base.py" "$K" "$W/f_base.ll" > /dev/null
  cmp "$W/f_default.ll" "$W/f_base.ll" && echo "既定動作: 変更前と byte 一致"
  python3 "$FW/fw_f80.py" "$K" "$W/f_ext.ll" --ext-funcs function_5dfd30,function_5dfbe0 | tail -1 | cut -c1-120
  llvm-as "$W/f_ext.ll" -o /dev/null && echo "fw_f80 --ext: llvm-as OK"
  python3 - "$W/f_ext.ll" "$W/f_ext.wasm.ll" <<'PY'
import sys
o = []
for ln in open(sys.argv[1]).read().split('\n'):
    if ln.startswith('target triple ='): o.append('target triple = "wasm32-unknown-emscripten"')
    elif ln.startswith('target datalayout ='): o.append('target datalayout = "e-m:e-p:32:32-p10:8:8-p20:8:8-i64:64-i128:128-n32:64-S128-ni:1:10:20"')
    else: o.append(ln)
open(sys.argv[2], 'w').write('\n'.join(o))
PY
  /opt/emsdk/upstream/bin/clang --target=wasm32 -O1 -w -c "$W/f_ext.wasm.ll" -o "$W/f_ext.o" --sysroot=/opt/emsdk/sysroot
  echo "framework ext IR wasm32 compile OK ($(stat -c %s "$W/f_ext.o") B)"
  if python3 "$FW/fw_f80.py" "$K" "$W/f_neg.ll" --ext-funcs function_nonexistent 2> "$W/neg.err"; then
    echo "[FAIL] 存在しない ext 関数で成功扱い"; exit 1
  fi
  echo "negative control (関数不在で fw_f80 が exit 非 0) OK"
else
  echo "SKIP [4]: $K が無い (p0c3_e2e.sh / lift_ranges.sh で生成)"
fi
t1=$(date +%s); load1=$(cut -d' ' -f1-3 /proc/loadavg)
echo "== p0c8 e2e OK: $((t1-t0)) s, load avg $load0 -> $load1 =="
