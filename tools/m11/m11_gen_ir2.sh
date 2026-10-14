#!/usr/bin/env bash
# M11 IR 生成 (再現用): boot0..4.lift.ll → merge → numfix → asmfix → passes → genstubs → dotfix → fnclex0 rename
#   boot4 = tail-call/間接 call 表 seed の追加分 (m11_tail.py 出力)
#   boot6 = WNDCLASS 静的実体の WNDPROC (+閉包) の追加分 (m11_wndclass_scan.py --ranges-out → m11_lift.sh ... boot6; #565)
#           boot5 は #132 の間接 call fallback (m11_extra_ranges5.txt) が使うため、名前を分けている
set -euo pipefail
cd "$(dirname "$0")"
source ../shared/env.sh   # FL_WIN64_DIR (環境変数で指定)
PE="${M11_PE:-${PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}}"
python3 m11_cond.py --reset ldfix=pending qstore=not-applied ld108=not-applied pe="$PE"   # #680: IR 生成条件を記録 (work/ir_conditions.json)
CH="work/boot0.lift.ll work/boot1.lift.ll work/boot2.lift.ll work/boot3.lift.ll"
[ -f work/boot4.lift.ll ] && CH="$CH work/boot4.lift.ll"
# boot5 = 間接 call 先の fallback 実装 (m11_extra_ranges5.txt; #132 unit #23)
[ -f work/boot5.lift.ll ] && CH="$CH work/boot5.lift.ll"
[ -f work/boot6.lift.ll ] && CH="$CH work/boot6.lift.ll"   # boot6 = WNDCLASS 静的実体の WNDPROC 閉包 (m11_wndclass_scan.py, #565)
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
else
  python3 m11_cond.py ldfix=skipped
  echo "[gen_ir2] ERROR: ldfix skip (PE 無し: $PE / capstone・pefile 無し) — fail-closed で失敗" >&2
  exit 1
fi
python3 m11_cond.py --bind work/boot_final.ll   # IR の指紋を記録 (m11_build.sh はこれと一致する IR だけを build する)
echo "[gen_ir2] OK: work/boot_final.ll ($(wc -l < work/boot_final.ll) 行)"
