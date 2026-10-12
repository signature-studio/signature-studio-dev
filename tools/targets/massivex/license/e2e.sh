#!/bin/bash
# MX-2 E2E: PE 修復 → RetDec lift → 中性化 IR pass (+check) → merge → wasm ハーネス → 対比検証。
# 再現: bash tools/targets/massivex/license/e2e.sh
# (lift キャッシュ work/lift/*.ll あり時 約 20 秒 / 無し時 +約 60 秒)
set -e
cd "$(dirname "$0")"
source ../../../shared/env.sh
W=work
PE_IN='../work/extracted/VST3/Massive X.vst3'
PE=$W/mx_fixed.vst3

echo "== [1] PE 修復 (ヘッダ clamp + .text 2B 修復, work copy のみ) =="
python3 scripts/mx_pefix.py "$PE_IN" "$PE"

echo "== [2] RetDec lift (select-decode-only, TMPDIR=work/tmp) =="
mkdir -p $W/lift $W/tmp
if [ ! -f $W/lift/lic.drc.ll ]; then
  (cd $W/lift && TMPDIR=../tmp /opt/retdec/bin/retdec-decompiler ../mx_fixed.vst3 -o lic.drc.c \
    --select-ranges "0x18115de60-0x18115ee55" --select-decode-only --timeout 600 > lic.log 2>&1)
  rm -f $W/lift/lic.drc.dsm $W/lift/lic.drc.bc $W/lift/lic.drc.c $W/lift/lic.drc.config.json
fi
if [ ! -f $W/lift/eng.drc.ll ]; then
  (cd $W/lift && TMPDIR=../tmp /opt/retdec/bin/retdec-decompiler ../mx_fixed.vst3 -o eng.drc.c \
    --select-ranges "0x1805b3510-0x1805b38ae,0x1805b3ad0-0x1805b3ea2" --select-decode-only --timeout 600 > eng.log 2>&1)
  rm -f $W/lift/eng.drc.dsm $W/lift/eng.drc.bc $W/lift/eng.drc.c $W/lift/eng.drc.config.json
fi
[ -f $W/lift/lic.drc.ll ] && [ -f $W/lift/eng.drc.ll ] || { echo "lift 失敗"; exit 1; }

echo "== [3] 中性化 IR pass (N1-N3) + 到達性 check =="
python3 scripts/mx_lic_stub.py $W/lift/lic.drc.ll $W/lic_patched.ll --report $W/irpatch_lic.json --check
python3 scripts/mx_lic_stub.py $W/lift/eng.drc.ll $W/eng_patched.ll --report $W/irpatch_eng.json --check

echo "== [4] base 修復 (liftlib ライブラリ利用, 無改変) — patched / raw の両方 =="
python3 - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1] + '/tools/liftlib')
from liftlib.passes import base as B
for src, dst in (('work/lic_patched.ll', 'work/lic_patched_base.ll'),
                 ('work/lift/lic.drc.ll', 'work/lic_raw_base.ll'),
                 ('work/eng_patched.ll', 'work/eng_patched_base.ll'),
                 ('work/lift/eng.drc.ll', 'work/eng_raw_base.ll')):
    text = open(src).read()
    out, rep = B.run_base(text, B.make_args(infile=src, outfile=dst))
    open(dst, 'w').write(out)
    print(dst, {k: v for k, v in rep.items() if k in ('b1_fixed', 's1_stores', 'a9_residual_constexpr')})
EOF

echo "== [5] harness 用 liftfix + merge (patched / pre 両方) =="
python3 scripts/mx_lic_stub.py work/lic_patched_base.ll work/lic_patched_hf.ll --harness-fix --no-rules
python3 scripts/mx_lic_stub.py work/lic_raw_base.ll work/lic_pre_hf.ll --harness-fix --no-rules
python3 scripts/mkrun_merge.py $W/run_all.ll \
  $W/eng_patched_base.ll:1805b3510 \
  $W/eng_patched_base.ll:1805b3ad0 \
  $W/eng_raw_base.ll:1805b3510:function_1805b3510_pre \
  $W/eng_raw_base.ll:1805b3ad0:function_1805b3ad0_pre \
  $W/lic_patched_hf.ll:18115de60 \
  $W/lic_pre_hf.ll:18115de60:function_18115de60_pre

echo "== [6] 同名異型 declare の整理 (18396fb60: 5引数版を _5 へ) =="
python3 - <<'EOF'
import re
p = 'work/run_all.ll'
t = open(p).read()
t = t.replace('declare i64 @function_18396fb60(i64, i64, i64, i64, i64)',
              'declare i64 @function_18396fb60_5(i64, i64, i64, i64, i64)')
t = re.sub(r'call i64 @function_18396fb60\((i64 [^)]*), (i64 [^)]*), (i64 [^)]*), (i64 [^)]*), (i64 [^)]*)\)',
           r'call i64 @function_18396fb60_5(\1, \2, \3, \4, \5)', t)
# uselistorder は merge 後 use 数と不一致になるため除去 (clang が再生成)
t = '\n'.join(l for l in t.split('\n') if not l.strip().startswith('uselistorder'))
# RetDec (x86-64) の datalayout/triple は wasm と非互換 → liftlib DATALAYOUT_WASM と同じ形へ差し替え
t = re.sub(r'^target datalayout = .*$',
           'target datalayout = "e-m:e-p:32:32-p10:8:8-p20:8:8-i64:64-i128:128-f128:64-n32:64-S128-ni:1:10:20"',
           t, flags=re.M)
t = re.sub(r'^target triple = .*$', 'target triple = "wasm32-unknown-emscripten"', t, flags=re.M)
# RetDec の numeric 名 global (@0, clang が __unnamed_N に改名して未解決になる) を定義へ変更
t = t.replace('@0 = external global i32', '@0 = global i32 0')
# RetDec は movups (非アライメント許容) を align 8 の i128 load でモデル化するため
# SSO バッファの中途半端なオフセット (+16/+26 等) で wasm のアライメント違反になる。
# load/store の align を一律 1 へ (atomic 系は行に含まれないので無影響)。
fixed = 0
out = []
for l in t.split('\n'):
    if (' load ' in l or ' store ' in l) and ', align ' in l and 'atomic' not in l:
        l2 = re.sub(r', align \d+', ', align 1', l)
        if l2 != l:
            fixed += 1
        l = l2
    out.append(l)
t = '\n'.join(out)
print('align->1:', fixed, 'lines')
open(p, 'w').write(t)
print('18396fb60_5 rename + uselistorder strip done')
EOF

echo "== [7] mock 生成 (declare から wasm シグネチャ一致) + emcc → wasm → node ハーネス =="
python3 scripts/mx_mocks_gen.py work/run_all.ll work/mocks_gen.c
export EMSDK=/opt/emsdk
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
# opt レベルは MX_OPT で切替可。既定は -O0。
#   背景 (MX-2 検収・実測): -O1/-O2/-Os では T7-T11 (evaluateRAS2) が
#   "memory access out of bounds" で TRAP し 6/11 PASS。-O0 では 11/11 PASS。
#   原因: RetDec raw IR は ① reg2mem alloca を store 前に load する
#   (%stack_var_-824.0.reload 等・未初期化) ② 0x180724c60 への interior call
#   (DEFECTS.md D11: 0x180724c60 = pdata 関数 0x180724b70 の offset 208 内部) を
#   string-builder と推定し mock を return 0 だけにして out-param (SSO バッファ) を未初期化。
#   MSVC の std::string は "add -8; load" (ヒープブロック先頭のサイズ) を読むため、
#   -O1 以上では LLVM がその load をガード (icmp ult 16) の前に hoist し、
#   未初期化ポインタを deref して TRAP。-O0 は hoist せず・フレームが 0 初期化のため 11/11 PASS。
#   TF: MX_OPT=-O1 で 6/11 を再現できる (ネガティブコントロール代わり)。
EMCC_OPT="${MX_OPT:--O0}"
emcc -w $EMCC_OPT -sENVIRONMENT=node -sMODULARIZE=1 -sALLOW_MEMORY_GROWTH=1 \
  -sERROR_ON_UNDEFINED_SYMBOLS=0 \
  -sEXPORTED_FUNCTIONS=_mx_run_tests,_mx_get_result,_mx_get_detail,_mx_run_one,_mx_get_detail_1,_mx_get_detail_2,_mx_get_detail_3,_mx_get_detail_4,_mx_get_detail_5,_mx_get_detail_6,_mx_get_detail_7,_mx_get_detail_8,_mx_get_detail_9,_mx_get_detail_10,_mx_get_detail_11,_malloc \
  -o $W/h_all.cjs work/run_all.ll harness/mocks_extra.ll work/mocks_gen.c harness/mx_harness.c
node harness/run.mjs $W/h_all.cjs --report $W/harness_report.json
