#!/usr/bin/env bash
# fw_stage2.sh — P0a (CAB-194) framework lift stage 2: 修復 pass → wasm → headless smoke。
#   bash fw_stage2.sh            # 増分 (既存成果物をスキップ)
#   bash fw_stage2.sh --fresh    # stage-2 生成物を全部作り直し (stage-1 の RetDec lift は再利用)
# 前提: stage-1 (fw_lift.sh) 済み = work/fw/{fw_icall.dll,fw_map.json,fw[0-7].restored.ll}
# 経路: merge (無名番号衝突 Fix + fn-ptr 戻り型正規化) → decode 漏れ round2/3 → fnptr → f80
#       → liftlib base.normalize → cleanup → cefix (事前 hoist) → ir5_patch (8 way 並列)
#       → cefix (残留型補完) → sigfix → entry_fix → cab129 → flatten → rep/cpuid/ymm/fldenv 正規化
#       → liftlib simd gen (TAG 拡張) → ovpass → fw_table (dispatch 表 + override) → emcc → smoke
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
T=/home/ubuntu/work/webstudio
W="$HERE/../work/fw"
PE="$W/fw_icall.dll"
FRESH=0
for a in "$@"; do case "$a" in --fresh) FRESH=1 ;; esac; done
cd "$W"
mkdir -p tmp
export TMPDIR="$W/tmp"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1

# ---- 1. 8 chunk merge (無名番号衝突 Fix + fn-ptr 戻り define 取り込み) ----
if [ $FRESH = 1 ] || [ ! -f fw_all8.ll ]; then
  python3 "$HERE/fw_merge.py" fw[0-7].restored.ll -o fw_all8.ll
fi
if [ $FRESH = 1 ] || [ ! -f fw_all.restored.ll ]; then
  # fn-ptr 戻り型正規化
  python3 "$HERE/fw_fnptr.py" fw_all8.ll fw_all8n.ll
  python3 "$HERE/fw_merge.py" fw_all8n.ll r2.restored.ll r3.restored.ll -o fw_all.restored.ll
fi

# ---- 2. decode 漏れ関数の第二/三ラウンド ----
if [ $FRESH = 1 ] || [ ! -f r2.restored.ll ]; then
  python3 "$HERE/fw_round2.py" --ir fw_all8.ll --map fw_map.json --ranges-out r2.ranges
  /opt/retdec/bin/retdec-decompiler "$PE" -o r2.drc.c --select-ranges "$(cat r2.ranges)" --select-decode-only --timeout 1800 > r2.retdec.log 2>&1
  python3 "$T/tools/icall/ir_icall_restore.py" --ir r2.drc.ll --map fw_map.json --out r2.restored.ll --report r2.restore.json
fi
if [ $FRESH = 1 ] || [ ! -f r3.restored.ll ]; then
  python3 "$HERE/fw_merge.py" fw_all8.ll r2.restored.ll -o fw_all2.ll
  python3 "$HERE/fw_round2.py" --ir fw_all2.ll --map fw_map.json --ranges-out r3.ranges
  /opt/retdec/bin/retdec-decompiler "$PE" -o r3.drc.c --select-ranges "$(cat r3.ranges)" --select-decode-only --timeout 1200 > r3.retdec.log 2>&1
  python3 "$T/tools/icall/ir_icall_restore.py" --ir r3.drc.ll --map fw_map.json --out r3.restored.ll --report r3.restore.json
fi
if [ $FRESH = 1 ] || [ ! -f fw_all.restored.ll ]; then
  python3 "$HERE/fw_fnptr.py" fw_all8.ll fw_all8n.ll
  python3 "$HERE/fw_merge.py" fw_all8n.ll r2.restored.ll r3.restored.ll -o fw_all.restored.ll
fi

# ---- 3. f80 → f64 ----
[ -f fw_f80.ll ] || python3 "$HERE/fw_f80.py" fw_all.restored.ll fw_f80.ll --report fw_f80.json

# ---- 4. liftlib base normalize ----
if [ ! -f fw_norm.ll ]; then
  python3 - <<'PY'
import sys
sys.path.insert(0, '/home/ubuntu/work/webstudio/tools/liftlib')
from liftlib.passes import base
text = open('fw_f80.ll', errors='replace').read()
open('fw_norm.ll', 'w').write(base.normalize(text))
PY
fi

# ---- 5. cleanup ----
[ -f fw_clean.ll ] || python3 "$HERE/fw_cleanup.py" fw_norm.ll fw_clean.ll

# ---- 6. 事前 hoist ----
[ -f fw_clean2.ll ] || python3 "$HERE/fw_cefix.py" fw_clean.ll fw_clean2.ll

# ---- 7. ir5_patch (8 way 並列) ----
if [ ! -f fw_lift.ll ]; then
  rm -rf slice && mkdir -p slice
  python3 - <<'PY'
lines = open('fw_clean2.ll', errors='replace').read().split('\n')
starts = [i for i, l in enumerate(lines) if l.startswith('define ')]
first = starts[0]
header = [l for l in lines[:first] if not l.startswith('declare ')]
declares = [l for l in lines[:first] if l.startswith('declare ')]
blocks = []
for si, s in enumerate(starts):
    e = starts[si + 1] if si + 1 < len(starts) else len(lines)
    blocks.append('\n'.join(lines[s:e]).rstrip() + '\n')
for k in range(8):
    part = blocks[k::8]
    open('slice/fw_slice%d.ll' % k, 'w').write('\n'.join(header) + '\n' + '\n'.join(part) + '\n' + '\n'.join(declares) + '\n')
print('[slice] %d defines -> 8' % len(blocks))
PY
  pids=()
  for k in 0 1 2 3 4 5 6 7; do
    ( python3 "$T/tools/m5/ir5_patch.py" slice/fw_slice$k.ll slice/fw_slice$k.lift.ll --keep-all > slice/ir5_$k.log 2>&1 ) &
    pids+=($!)
  done
  fail=0
  for p in "${pids[@]}"; do wait "$p" || fail=1; done
  [ $fail = 0 ] || { echo "[s2] ir5 slice 失敗: slice/ir5_*.log を確認" >&2; exit 1; }
  python3 "$HERE/fw_merge.py" slice/fw_slice0.lift.ll slice/fw_slice1.lift.ll slice/fw_slice2.lift.ll slice/fw_slice3.lift.ll \
    slice/fw_slice4.lift.ll slice/fw_slice5.lift.ll slice/fw_slice6.lift.ll slice/fw_slice7.lift.ll -o fw_lift.ll
fi

# ---- 8. A9L 残留の型補完 ----
[ -f fw_lift2.ll ] || python3 "$HERE/fw_cefix.py" fw_lift.ll fw_lift2.ll

# ---- 9. sigfix (cross-chunk 署名整合) ----
[ -f fw_lift3.ll ] || python3 "$HERE/fw_sigfix.py" fw_lift2.ll fw_lift3.ll --report sigfix.json

# ---- 10. entry spill 修復 ----
[ -f fw_lift4.ll ] || python3 "$HERE/fw_entry_fix.py" fw_lift3.ll fw_lift4.ll --report entry_fix.json

# ---- 11. alloca 縮退修復 (CAB-129) ----
[ -f fw_lift5.ll ] || python3 "$HERE/fw_cab129.py" fw_lift4.ll fw_lift5.ll --report cab129_fix.json

# ---- 12. flatten ----
[ -f fw_flat.ll ] || python3 "$T/tools/icall/ir_flatten.py" fw_lift5.ll fw_flat.ll \
  --base 0x400000 --newbase 0x400000 --limit 0xd02000

# ---- 13. rep/cpuid/ymm/fldenv 正規化 ----
[ -f fw_flat2.ll ] || python3 "$HERE/fw_rep.py" fw_flat.ll fw_flat2.ll
[ -f fw_flat3.ll ] || python3 "$HERE/fw_cpuid.py" fw_flat2.ll fw_flat3.ll

# ---- 14. ymm store 正規化 + simd gen + table + ovpass ----
cp -f "$HERE/fw_rt.h" "$HERE/fw_rt.c" . 2>/dev/null || true
if [ ! -f fw_flat4_canon2.ll ]; then
  # ymm store 形を IR store に正規化 + i256 helper を IR identity define 化
  python3 - <<'PY'
import re
lines = open('fw_flat3.ll').read().split('\n')
out = []
CALL_RE = re.compile(r'^(\s*)call void @(__asm_vmovups__3)\(i256 ([^,]+), i256 (%[\w.-]+)\)\s*$')
LOAD_RE = re.compile(r'^\s*(%[\w.-]+) = load i256, (?:ptr|[^ ]+\*) (%[\w.-]+)')
def find_load_ptr(buf, old, idx, depth=160):
    for k in range(idx - 1, max(-1, idx - depth), -1):
        m = LOAD_RE.match(buf[k])
        if m and m.group(1) == old:
            return m.group(2), k
    return None, None
for idx, l in enumerate(lines):
    m = CALL_RE.match(l)
    if m:
        ptr, load_at = find_load_ptr(lines, m.group(3), idx)
        if ptr:
            out.append('%sstore i256 %s, ptr %s, align 1' % (m.group(1), m.group(4), ptr))
            continue
    out.append(l)
# i256 declare → IR identity define
t = '\n'.join(out)
decls = re.findall(r'^declare (i256) @(__asm_[\w]+)\((i256)\) local_unnamed_addr$', t, re.M)
for ret, nm, args in decls:
    t = t.replace('declare %s @%s(%s) local_unnamed_addr\n' % (ret, nm, args), '')
    d = 'define i256 @%s(i256 %%v) {\n  ret i256 %%v\n}' % nm
    idx = t.index('\ndefine ')
    t = t[:idx] + '\n' + d + '\n' + t[idx:]
# fldenv (i224) → ptr
t = t.replace('call void @__asm_fldenv__v?(i224 %7)', 'call void @fw_fldenv(ptr %6)')
t = t.replace('declare void @__asm_fldenv__v?(i224) local_unnamed_addr\n', '')
open('fw_flat4.ll', 'w').write(t)
print('[ymm] done')
PY
fi
if [ ! -f fw_flat4_canon2.ll ]; then
  cp -f "$HERE/fw_rt.h" . 2>/dev/null || true
  # ymm store (残り) → IR store
  python3 - <<'PY'
import re
t = open('fw_flat4.ll').read().split('\n')
out = []
n = 0
CALL_RE = re.compile(r'^(\s*)call void @(__asm_vmovups__3)\(i256 ([^,]+), i256 (%[\w.-]+)\)\s*$')
LOAD_RE = re.compile(r'^\s*(%[\w.-]+) = load i256, (?:ptr|[^ ]+\*) (%[\w.-]+)')
for idx, l in enumerate(t):
    m = CALL_RE.match(l)
    if m:
        ptr = None
        for k in range(idx - 1, max(-1, idx - 160), -1):
            mm = LOAD_RE.match(t[k])
            if mm and mm.group(1) == m.group(3).strip():
                ptr = mm.group(2); break
        if ptr is None:
            for k in range(idx + 1, min(len(t), idx + 14)):
                mm = LOAD_RE.match(t[k])
                if mm: ptr = mm.group(2); break
        if ptr:
            out.append('%sstore i256 %s, ptr %s, align 1' % (m.group(1), m.group(4), ptr)); n += 1
            continue
    out.append(l)
# ymm store の dominance 修正 (chain clone)
lines = out
uid = [0]
fixed = 0
starts2 = [i for i, l in enumerate(lines) if l.startswith('define ')]
starts2.append(len(lines))
for si in range(len(starts2) - 1):
    lo, hi = starts2[si], starts2[si + 1]
    defs = {}
    for j in range(lo, hi):
        m2 = re.match(r'\s*(%[\w.-]+) = ', lines[j])
        if m2 and m2.group(1) not in defs: defs[m2.group(1)] = j
    i2 = lo
    while i2 < hi:
        m2 = re.match(r'^(\s*)store i256 (%[\w.-]+), ptr (%[\w.-]+), align 1\s*$', lines[i2])
        if not m2: i2 += 1; continue
        ptrname = m2.group(3)
        dj = defs.get(ptrname)
        if dj is None or dj < i2: i2 += 1; continue
        dm = re.match(r'\s*%[\w.-]+ = inttoptr i64 (%[\w.-]+) to ptr', lines[dj])
        if not dm: i2 += 1; continue
        chain = []; seen = set(); stack = [dm.group(1)]
        while stack:
            nm = stack.pop()
            if nm in seen: continue
            seen.add(nm)
            dj2 = defs.get(nm)
            if dj2 is None: continue
            dl = lines[dj2].lstrip()
            mm2 = re.match(r'%[\w.-]+ = (inttoptr i64 |ptrtoint ptr |add i64 )(.*)$', dl)
            if not mm2: continue
            chain.append((nm, dl.split(' = ', 1)[1]))
            for d in re.findall(r'%[\w.-]+', mm2.group(2)): stack.append(d)
        pre = []; ren = {}
        for nm, rhs in reversed(chain):
            uid[0] += 1; nn = '%%ceclone%d' % uid[0]
            for old, new in reversed(list(ren.items())):
                rhs = rhs.replace(old + ' ', new + ' ').replace(', ' + old, ', ' + new).replace(' ' + old + ',', ' ' + new + ',')
            ren[nm] = nn; pre.append('  %s = %s' % (nn, rhs))
        top = ren.get(dm.group(1))
        top_i = '%%ceclone%d' % (uid[0] + 1); uid[0] += 1
        pre.append('  %s = inttoptr i64 %s to ptr' % (top_i, top))
        lines[i2] = '  store i256 %s, ptr %s, align 1' % (m2.group(2), top_i)
        for k2, pl in enumerate(pre): lines.insert(i2 + k2, pl)
        i2 += len(pre) + 1; fixed += 1
# fldenv → ptr
t2 = '\n'.join(lines)
t2 = t2.replace('call void @__asm_fldenv__v?(i224 %7)', 'call void @fw_fldenv(ptr %6)')
t2 = t2.replace('declare void @__asm_fldenv__v?(i224) local_unnamed_addr\n', '')
# fn-ptr 戻り型正規化 (simd gen 対応)
t2 = re.sub(r'\b(?:i\d+|void|ptr|float|double) \(\)\* ', 'ptr ', t2)
# BLENDFUNCTION/tagPOINT 構造体引数 → i64
t2 = t2.replace('%_BLENDFUNCTION %', 'i64 %').replace('%_BLENDFUNCTION)', 'i64)').replace('%_BLENDFUNCTION,', 'i64,')
t2 = t2.replace('%tagPOINT %', 'i64 %').replace('%tagPOINT)', 'i64)').replace('%tagPOINT,', 'i64,')
open('fw_flat4.ll', 'w').write(t2)
print('[ymm2] dominance fixed: %d' % fixed)
PY
fi
if [ ! -f fw_simd.c ]; then
  # liftlib simd gen (TAG 拡張)
  cp -f "$HERE/fw_rt.h" . 2>/dev/null || true
  python3 - <<'PY'
import sys, re
sys.path.insert(0, '/home/ubuntu/work/webstudio/tools/liftlib')
from liftlib.simd import gen as G
class DynTag(dict):
    def get(self, k, d=None):
        if k in self: return dict.__getitem__(self, k)
        m = re.match(r'^i(\d+)$', k)
        if m: return 'g%s' % m.group(1)
        return d or '?'
G.TAG = DynTag({'i128':'x','i64':'q','i32':'d','i16':'w','i8':'b','i256':'y','void':'v','ptr':'p','float':'f','double':'F'})
G.CT.update({'p':'void*','f':'float','F':'double'})
sys.argv = ['gen', 'fw_flat4.ll', '-o', 'fw_simd.c', '--canon', 'fw_flat4_canon.ll']
G.main(sys.argv[1:])
PY
fi
if [ ! -f fw_flat4_canon2.ll ]; then
  # canon → ymm 残り store → fnptr/BLENDFUNCTION/tagPOINT 正規化
  python3 - <<'PY'
import re
t = open('fw_flat4_canon.ll').read()
# ymm store 残り
lines = t.split('\n')
out = []
CALL_RE = re.compile(r'^(\s*)call void @(__asm_vmovups__3)\(i256 ([^,]+), i256 (%[\w.-]+)\)\s*$')
LOAD_RE = re.compile(r'^\s*(%[\w.-]+) = load i256, (?:ptr|[^ ]+\*) (%[\w.-]+)')
uid = [0]
for idx, l in enumerate(lines):
    m = CALL_RE.match(l)
    if m:
        ptr = None
        for k in range(idx - 1, max(-1, idx - 160), -1):
            mm = LOAD_RE.match(t.split('\n')[k])
            if mm and mm.group(1) == m.group(3).strip(): ptr = mm.group(2); break
        if ptr is None:
            for k in range(idx + 1, min(len(lines), idx + 14)):
                mm = LOAD_RE.match(lines[k])
                if mm: ptr = mm.group(2); break
        if ptr:
            out.append('%sstore i256 %s, ptr %s, align 1' % (m.group(1), m.group(4), ptr)); continue
    out.append(l)
# dominance fix + fnptr + struct 引数
lines = out
uid[0] = 0
starts2 = [i for i, l in enumerate(lines) if l.startswith('define ')]
starts2.append(len(lines))
for si in range(len(starts2) - 1):
    lo, hi = starts2[si], starts2[si + 1]
    defs = {}
    for j in range(lo, hi):
        m2 = re.match(r'\s*(%[\w.-]+) = ', lines[j])
        if m2 and m2.group(1) not in defs: defs[m2.group(1)] = j
    i2 = lo
    while i2 < hi:
        m2 = re.match(r'^(\s*)store i256 (%[\w.-]+), ptr (%[\w.-]+), align 1\s*$', lines[i2])
        if not m2: i2 += 1; continue
        ptrname = m2.group(3)
        dj = defs.get(ptrname)
        if dj is None or dj < i2: i2 += 1; continue
        dm = re.match(r'\s*%[\w.-]+ = inttoptr i64 (%[\w.-]+) to ptr', lines[dj])
        if not dm: i2 += 1; continue
        chain = []; seen = set(); stack = [dm.group(1)]
        while stack:
            nm = stack.pop()
            if nm in seen: continue
            seen.add(nm)
            dj2 = defs.get(nm)
            if dj2 is None: continue
            dl = lines[dj2].lstrip()
            mm2 = re.match(r'%[\w.-]+ = (inttoptr i64 |ptrtoint ptr |add i64 )(.*)$', dl)
            if not mm2: continue
            chain.append((nm, dl.split(' = ', 1)[1]))
            for d in re.findall(r'%[\w.-]+', mm2.group(2)): stack.append(d)
        pre = []; ren = {}
        for nm, rhs in reversed(chain):
            uid[0] += 1; nn = '%%ceclone%d' % uid[0]
            for old, new in reversed(list(ren.items())):
                rhs = rhs.replace(old + ' ', new + ' ').replace(', ' + old, ', ' + new).replace(' ' + old + ',', ' ' + new + ',')
            ren[nm] = nn; pre.append('  %s = %s' % (nn, rhs))
        top = ren.get(dm.group(1))
        top_i = '%%ceclone%d' % (uid[0] + 1); uid[0] += 1
        pre.append('  %s = inttoptr i64 %s to ptr' % (top_i, top))
        lines[i2] = '  store i256 %s, ptr %s, align 1' % (m2.group(2), top_i)
        for k2, pl in enumerate(pre): lines.insert(i2 + k2, pl)
        i2 += len(pre) + 1; fixed = fixed + 1 if 'fixed' in dir() else 1
t2 = '\n'.join(lines)
t2 = re.sub(r'\b(?:i\d+|void|ptr|float|double) \(\)\* ', 'ptr ', t2)
t2 = t2.replace('%_BLENDFUNCTION %', 'i64 %').replace('%_BLENDFUNCTION)', 'i64)').replace('%_BLENDFUNCTION,', 'i64,')
t2 = t2.replace('%tagPOINT %', 'i64 %').replace('%tagPOINT)', 'i64)').replace('%tagPOINT,', 'i64,')
# fldenv
t2 = t2.replace('call void @__asm_fldenv__vg224(i224 %7)', 'call void @fw_fldenv(ptr %6)')
t2 = t2.replace('declare void @__asm_fldenv__vg224(i224) local_unnamed_addr\n', '')
open('fw_flat4_canon2.ll', 'w').write(t2)
print('[canon2] done')
PY
fi

# ---- 15. ovpass (_StartLib/_InitLib/RestoreContext override) ----
if [ ! -f fw_flat4_canon3.ll ]; then
  python3 "$HERE/fw_ovpass.py" fw_flat4_canon2.ll fw_flat4_canon3.ll
  python3 - <<'PY'
t = open('fw_flat4_canon3.ll').read().split('\n')
seen = set(); out = []
for l in t:
    if l.startswith('declare ') and 'fw_ov_' in l:
        if l in seen: continue
        seen.add(l)
    out.append(l)
open('fw_flat4_canon3.ll','w').write('\n'.join(out))
PY
fi

# ---- 16. dispatch 表 ----
[ -f fw_image.bin ] || python3 "$HERE/fw_image.py" --pe "$PE" --map fw_map.json --out fw_image.bin --imports fw_imports.json
[ -f fw_table.c ] || python3 "$HERE/fw_table.py" --ir fw_flat4_canon3.ll --imports fw_imports.json --out fw_table.c --blk 0x8A1000

# ---- 16.5 plugin 連鎖用の IR 修復は hostshim/hs_e2e.sh に分離 (CAB-195) ----
# 本 stage-2 の成果物 (canon3) は CAB-194 の headless smoke と同一挙動を保つ。
# CreatePlugInstance 連鎖の検証 (hs_irfix → fw_retw → fw_hostfix → emcc → e2e) は
# hostshim/hs_e2e.sh が canon3 から派生ビルドを作って実施する (framework build に
# 戻り値 store / mosaic override を混入させると unit init #16 経路の分岐が変わり
# smoke が OOB trap する — 実測のため分離)。

# ---- 17. emcc ----
if [ ! -f fw_route.cjs ]; then
  emcc fw_flat4_canon3.ll fw_simd.c fw_table.c fw_rt.c fw_boot.c "$HERE/hostshim/hostshim.c" \
    -I. -I"$HERE/hostshim" -I"$T/tools/liftlib/liftlib/simd" \
    -w -O0 -g -ffp-contract=off -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB \
    -sGLOBAL_BASE=$((0x10000000)) -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule \
    -sEXIT_RUNTIME=1 -sERROR_ON_UNDEFINED_SYMBOLS=0 \
    -sEXPORTED_FUNCTIONS=_function_6c13a0,_function_4189c0,_function_6bdde0,_fw_dispatch_count,_fw_last_site,_fw_last_target,_fw_ff_count,_fw_ff_msg,_fw_va_calls,_fw_va_used,_fw_alloc_count,_fw_alloc_bytes,_fw_call_cur,_fw_hs_host,_fw_hs_host_va,_fw_hs_install,_fw_hs_fold_cell,_fw_hs_trace,_fw_hs_reset,_fw_hs_count,_fw_hs_records,_fw_hs_installed,_fw_hs_fle_impl \
    -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64,wasmExports \
    -Wl,--initial-memory=$((0x14000000)) -Wl,--max-memory=$((0x80000000)) \
    -o fw_route.cjs 2> emcc.log || { grep -v 'warning\|>>>\|^$' emcc.log | head -20; exit 1; }
fi
ls -la fw_route.cjs

# ---- 18. smoke ----
node "$HERE/fw_run.mjs" "$W/fw_image.bin" "$W/fw_route.cjs"
