#!/usr/bin/env bash
# M11 IR 生成 (再現用): boot0..4.lift.ll → merge → numfix → asmfix → passes → genstubs → dotfix → fnclex0 rename
#   boot4 = tail-call/間接 call 表 seed の追加分 (m11_tail.py 出力)
#   boot6 = WNDCLASS 静的実体の WNDPROC (+閉包) の追加分 (m11_wndclass_scan.py --ranges-out → m11_lift.sh ... boot6; #565)
#           boot5 は #132 の間接 call fallback (m11_extra_ranges5.txt) が使うため、名前を分けている
set -euo pipefail
cd "$(dirname "$0")"
source ../shared/env.sh   # FL_WIN64_DIR (環境変数で指定)
PE="${M11_PE:-${PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}}"
python3 m11_cond.py --reset ldfix=pending qstore=not-applied ld108=not-applied ld115=not-applied r8b=not-applied pe="$PE"   # #680: IR 生成条件を記録 (work/ir_conditions.json)
CH="work/boot0.lift.ll work/boot1.lift.ll work/boot2.lift.ll work/boot3.lift.ll"
[ -f work/boot4.lift.ll ] && CH="$CH work/boot4.lift.ll"
# boot5 = 間接 call 先の fallback 実装 (m11_extra_ranges5.txt; #132 unit #23)
[ -f work/boot5.lift.ll ] && CH="$CH work/boot5.lift.ll"
[ -f work/boot6.lift.ll ] && CH="$CH work/boot6.lift.ll"   # boot6 = WNDCLASS 静的実体の WNDPROC 閉包 (m11_wndclass_scan.py, #565)
[ -f work/boot7.lift.ll ] && CH="$CH work/boot7.lift.ll"   # boot7 = CreateFruityInstance (0x1375990) の閉包のうち現 closure に無い分 (gf_seed_closure.py, #2715)
python3 m11_merge.py $CH -o work/boot_all.ll
python3 - <<'PYnum'
import re
d = 'work/boot_all.ll'
s = open(d).read()
names = sorted(set(int(x) for x in re.findall(r'^@(\d+) = ', s, re.M)))
s2 = re.sub(r'(?<![\w$.])@(\d+)\b', lambda m: '@m11num_%s' % m.group(1), s)
open(d, 'w').write(s2)
print('[numfix] numeric globals:', len(names))
PYnum
python3 m11_asmfix.py work/boot_all.ll work/boot_allfx.ll
python3 m11_passes.py work/boot_allfx.ll work/boot_final.ll --report work/ir_report.json --init-list work/inits_text.txt
python3 m11_genstubs.py work/boot_final.ll work
python3 - <<'PY2'
import re
d = 'work/boot_final.ll'
s = open(d).read()
s = re.sub(r'@([A-Za-z_][\w]*)\.\d+\b', lambda m: '@%s_D%s' % (m.group(1), m.group(0).split('.')[-1]), s)
# argless fnclex: 同一シンボル(i64)共存回避 (m11_rt.c が __asm_fnclex0 を C 実装)
s = s.replace('@__asm_fnclex__112', '@__asm_fnclex0')
open(d, 'w').write(s)
print('[dotfix+fnclex0] done')
PY2
# ldfix (CAB-231/CAB-131): load 取り違え (値↔アドレス / 1 段 deref 脱落) 修復 pass を常設適用する。
#   capstone による実機械語 (.pdata 区間) との突合付き。詳細は ldfix/REPORT.md / ldfix/REPORT_CAB131.md。
#   適用位置は m11_post (weak 化/sigfix) 前 = ここ (ldfix REPORT §6-2 の推奨)。
#   skip は失敗扱い (#680 fail-closed): 警告のみで IR を作ると測定基準が環境で変わるため。
#   M11_LDFIX=0 は ldfix 適用前の IR を明示的に取る検証用 (ldfix/audit_lsf_e2e.sh)。ir_conditions.json に ldfix=disabled を残し、build は拒否する。
if [ "${M11_LDFIX:-1}" = 0 ]; then
  python3 m11_cond.py ldfix=disabled
  echo "[gen_ir2] M11_LDFIX=0: ldfix を適用しない (ir_conditions.json ldfix=disabled; この IR は build できない)" >&2
elif [ -f "$PE" ] && python3 -c 'import capstone, pefile' 2>/dev/null; then
  python3 ldfix/ldfix.py work/boot_final.ll work/boot_final.ldfix.ll --pe "$PE" --report work/ldfix_report.json ${LDFIX_ARGS:-}
  mv work/boot_final.ldfix.ll work/boot_final.ll
  python3 m11_cond.py ldfix=applied
  # #2556 (CI-104): function_450560 の 2 段 deref 復元 (#2502)。ldfix 直後に常設する。機械語 26 命令と突合して fail-closed。
  #   M11_FIX_450560=0 は適用前の IR を明示的に取る A/B 検証用 (ir_conditions.json 450560=disabled。build は M11_ALLOW_450560_DISABLED=1 でしか通さない)。
  if [ "${M11_FIX_450560:-1}" = 0 ]; then
    python3 m11_cond.py 450560=disabled
    echo "[gen_ir2] M11_FIX_450560=0: fix_450560 を適用しない (ir_conditions.json 450560=disabled; build は M11_ALLOW_450560_DISABLED=1 が要る)" >&2
  else
    python3 ldfix/fix_450560.py work/boot_final.ll work/boot_final.450560.ll --pe "$PE"
    mv work/boot_final.450560.ll work/boot_final.ll
    python3 m11_cond.py 450560=applied
  fi
  # ld108 (#2316/#2402, D20): 41a670 の head 解除 store (機械語 `mov rax,[rax]` = [arg1+0]) を lift 段の [arg1+8] の load から直す。
  #   1 関数だけを書き換え、想定と違う IR (仮引数の型・store 行・二重適用) は assert で止める (set -e で fail-closed)。
  #   M11_FIX_LD108=0 は適用前の IR を明示的に取る A/B 検証用 (ldfix/ld108_e2e.sh)。ir_conditions.json に ld108=disabled を残し、build は M11_ALLOW_LD108_DISABLED=1 でしか通さない。
  if [ "${M11_FIX_LD108:-1}" = 0 ]; then
    python3 m11_cond.py ld108=disabled
    echo "[gen_ir2] M11_FIX_LD108=0: fix_ld108 を適用しない (ir_conditions.json ld108=disabled; build は M11_ALLOW_LD108_DISABLED=1 が要る)" >&2
  else
    python3 ldfix/fix_ld108.py work/boot_final.ll work/boot_final.ld108.ll
    mv work/boot_final.ld108.ll work/boot_final.ll
    python3 m11_cond.py ld108=applied
  fi
  # ld115 (#2447, D20 の 666a60 への延長): 回数の初期値 (機械語 666ada) とループ内 store (機械語 666b13) を直す。fix_ld108 の後に掛ける (ld115_e2e.sh と同じ順序)。
  #   1 関数だけを書き換え、想定と違う IR は assert で止める (set -e で fail-closed)。
  #   M11_FIX_LD115=0 は適用前の IR を明示的に取る A/B 検証用 (ld115_e2e.sh)。ir_conditions.json に ld115=disabled を残し、build は M11_ALLOW_LD115_DISABLED=1 でしか通さない。
  if [ "${M11_FIX_LD115:-1}" = 0 ]; then
    python3 m11_cond.py ld115=disabled
    echo "[gen_ir2] M11_FIX_LD115=0: fix_ld115 を適用しない (ir_conditions.json ld115=disabled; build は M11_ALLOW_LD115_DISABLED=1 が要る)" >&2
  else
    python3 ldfix/fix_ld115.py work/boot_final.ll work/boot_final.ld115.ll
    mv work/boot_final.ld115.ll work/boot_final.ll
    python3 m11_cond.py ld115=applied
  fi
  # #4675 (LD-236): function_1046a30 の上流 X (cell→C→[C]) の 1 段不足。既定 OFF (本番 IR は変えない・unit 結果は未測定)。
  #   M11_FIX_LD236=1 のときだけ適用する (ir_conditions.json ld236=applied)。想定外の入力は assert で止まる。
  if [ "${M11_FIX_LD236:-0}" = 1 ]; then
    python3 ldfix/fix_ld236.py work/boot_final.ll work/boot_final.ld236.ll
    mv work/boot_final.ld236.ll work/boot_final.ll
    python3 m11_cond.py ld236=applied
  else
    python3 m11_cond.py ld236=not-applied
  fi
  # #5693 (CI-235): function_439f90 を機械語どおりの IR に組み直す (fix_439f90.py)。既定 OFF (wasm unit 結果は未測定。tools/m11/ldfix/REPORT_5693.md)。
  #   M11_FIX_439F90=1 のときだけ適用する (ir_conditions.json 439f90=applied)。想定外の入力は assert で止まる。
  if [ "${M11_FIX_439F90:-0}" = 1 ]; then
    python3 ldfix/fix_439f90.py work/boot_final.ll work/boot_final.439f90.ll
    mv work/boot_final.439f90.ll work/boot_final.ll
    python3 m11_cond.py 439f90=applied
  else
    python3 m11_cond.py 439f90=not-applied
  fi
  # #3296: function_412770 の rep movsq 源 (機械語 mov rsi,[rax] の load が lift で脱落し ptr null)。想定外の入力は assert で止まる (fail-closed)。
  python3 ldfix/fix_src412770.py work/boot_final.ll work/boot_final.src412770.ll
  mv work/boot_final.src412770.ll work/boot_final.ll
  # #5358 (FLE-44): function_409c80 の 0x409d2d `jae 0x409c40` は tail jump。lift の call+fall-through を tail call に直す (想定外の入力は assert で止まる)。
  python3 ldfix/fix_tail409c80.py work/boot_final.ll work/boot_final.tail409c80.ll
  mv work/boot_final.tail409c80.ll work/boot_final.ll
  # #1448 (#683 §8.1): function_815050 の 6cefb0 第 3 引数は機械語 `mov r8b,1` の即値 1 (RetDec 段で alloca アドレスになる)。
  #   M11_FIX_R8B=0 は適用前の IR を明示的に取る A/B 検証用 (ir_conditions.json r8b=disabled。build は M11_ALLOW_R8B_DISABLED=1 でしか通さない)。
  if [ "${M11_FIX_R8B:-1}" = 0 ]; then
    python3 m11_cond.py r8b=disabled
    echo "[gen_ir2] M11_FIX_R8B=0: fix_r8b815050 を適用しない (ir_conditions.json r8b=disabled; build は M11_ALLOW_R8B_DISABLED=1 が要る)" >&2
  else
    python3 ldfix/fix_r8b815050.py work/boot_final.ll work/boot_final.r8b.ll --pe "$PE"
    mv work/boot_final.r8b.ll work/boot_final.ll
    python3 m11_cond.py r8b=applied
  fi
  # #5999 (CI-249): function_f552a0 のループ内呼出し第 1 引数を機械語 [rbx] (= %arg1) に戻し、rcx.0/rcx.1 の loop-carry を外す (#5995)。
  #   既定 OFF (e2e 期待値ゲートが 101→114 / 873→875 で落ちたため。ldfix/REPORT_5999.md)。M11_FIX_F552A0=1 のときだけ適用する (ir_conditions.json f552a0=applied)。想定外の入力は assert で止まる (fail-closed)。
  if [ "${M11_FIX_F552A0:-0}" = 1 ]; then
    python3 ldfix/fix_f552a0.py work/boot_final.ll work/boot_final.f552a0.ll
    mv work/boot_final.f552a0.ll work/boot_final.ll
    python3 ldfix/judge_arg1_5999.py work/boot_final.ll
    python3 m11_cond.py f552a0=applied
  else
    python3 m11_cond.py f552a0=not-applied
  fi
  # #3234 (SHX-T40, D23) 実験用: M11_FIX_SHX_T40=1 のときだけ function_448490 の親 object を callee の view に合わせる。
  #   既定 OFF (実測で修復 ON は unit 18 で hang・+0x70 のみでは OOB。tools/m11/REPORT_SHX-T40.md)。既定の IR は変えない。
  if [ "${M11_FIX_SHX_T40:-0}" = 1 ]; then
    python3 ldfix/fix_shx_t40.py work/boot_final.ll work/boot_final.shx40.ll
    mv work/boot_final.shx40.ll work/boot_final.ll
    python3 m11_cond.py shx_t40=applied
  elif [ "${M11_FIX_SHX_T40:-0}" = 70 ]; then
    # #4121 (SHX-T42) ネガコン: +0x70 の書込みだけ (+0x4c の初期 store を外す)。
    python3 ldfix/fix_shx_t40.py work/boot_final.ll work/boot_final.shx40.ll --only-70
    mv work/boot_final.shx40.ll work/boot_final.ll
    python3 m11_cond.py shx_t40=applied-70only
  else
    python3 m11_cond.py shx_t40=not-applied
  fi
  # #5203 (SHX-T46, D23 段 1) 実験用: M11_FIX_SHX_T46=1 のときだけ function_448490 の count (-32) の 6 スロットを object +0x48 のメモリに統合する。
  #   既定 OFF (既定の IR は変えない)。想定外の入力は assert で止まる (fail-closed)。ldfix/fix_shx_t46.py。
  if [ "${M11_FIX_SHX_T46:-0}" = 1 ]; then
    #   M11_FIX_SHX_T46_LEN=1 は entry の +0x70 (arg1) と +0x4c (length) の初期化も入れる (機械語 0x4484b3・0x4484e4)。
    SHX46_ARGS=""
    if [ "${M11_FIX_SHX_T46_LEN:-0}" = 1 ]; then SHX46_ARGS="--length"; fi
    python3 ldfix/fix_shx_t46.py $SHX46_ARGS work/boot_final.ll work/boot_final.shx46.ll
    mv work/boot_final.shx46.ll work/boot_final.ll
    python3 m11_cond.py shx_t46=applied${SHX46_ARGS:+-length}
  else
    python3 m11_cond.py shx_t46=not-applied
  fi
  # #5855 (SHX-T61) 計装用: M11_FIX_SHX_T61=1 のときだけ callee function_4483f0 の入口に呼出し計数と this+0x4c / +0x48 の出力を入れる (既定 OFF)。
  if [ "${M11_FIX_SHX_T61:-0}" = 1 ]; then
    python3 ldfix/fix_shx_t61.py work/boot_final.ll work/boot_final.shx61.ll
    mv work/boot_final.shx61.ll work/boot_final.ll
    python3 m11_cond.py shx_t61=applied
  else
    python3 m11_cond.py shx_t61=not-applied
  fi
  # #5855 (SHX-T61 次段) 計装用: M11_FIX_SHX_T61B=1 のときだけ親 function_448490 の外側 loop 入口に通過回数と上限・添字を記録する (既定 OFF)。
  if [ "${M11_FIX_SHX_T61B:-0}" = 1 ]; then
    python3 ldfix/fix_shx_t61b.py work/boot_final.ll work/boot_final.shx61b.ll
    mv work/boot_final.shx61b.ll work/boot_final.ll
    python3 m11_cond.py shx_t61b=applied
  else
    python3 m11_cond.py shx_t61b=not-applied
  fi
else
  python3 m11_cond.py ldfix=skipped
  echo "[gen_ir2] ERROR: ldfix skip (PE 無し: $PE / capstone・pefile 無し) — fail-closed で失敗" >&2
  exit 1
fi
python3 m11_cond.py --bind work/boot_final.ll   # IR の指紋を記録 (m11_build.sh はこれと一致する IR だけを build する)
echo "[gen_ir2] OK: work/boot_final.ll ($(wc -l < work/boot_final.ll) 行)"
