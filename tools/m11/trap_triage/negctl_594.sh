#!/usr/bin/env bash
# #594 再現 + gate: 8cc190 系 OOB (unit 56, 58-63) の原因 = 417b70 の `Q(a)` が上位 4B 未初期化 (D17 型). 本 script は main の既定構成 (qstore 有り) の gate を判定する.
#   usage: FL_WIN64_DIR=<fl-win64 の展開先> bash trap_triage/negctl_594.sh   (work/ に work-m11 の展開が必要)
#   前提 (fail-closed: 1 つでも欠ければ数値を出さずに exit 1): $FL_WIN64_DIR/extracted/block00031_PE.bin と
#     python3 での capstone・pefile の import。qstore (m11_build.sh 既定 M11_QSTORE=1) はこの 2 つが揃って初めて効くため,
#     無い環境では既定構成の数値が変わる (PE 無しで qstore が skip される) → 止める。
#   IR の出どころ: 毎回 m11_gen_ir2.sh で作り直した直後の IR を work/boot_final.pristine.ll に複製する (ldfix=applied・qstore=not-applied・
#     指紋記録済み)。detect で qstore 対象 site > 0 を確認する。m11_build.sh は boot_final.ll を qstore/alloca で書き換えるので, 構成の前に複製から戻す。
#     PE は $FL_WIN64_DIR/extracted/block00031_PE.bin を gen_ir2 と ldfix (--pe) が同じ値で読む。/home/ubuntu は env.sh の既定値でしかない。
#   構成 (m11_ov.c を python で加工して work/obj/ov.o に差し替え → m11_build.sh → survey_units.mjs):
#     base      qstore 無し (M11_QSTORE=0 = #552 前の base) の現行 m11_ov.c (無加工). 遷移の info 行の基準にのみ使う (gate に使わない)
#     qbase     現行 m11_ov.c + qstore (M11_QSTORE=1 = main の既定). qstore の適用 site 数 = 前提の検出数
#     qprobe    probe (8cc190 に M11_TRACE probe) + qstore: probe の透過性 (qbase と kind 完全一致)
#   gate (#1041 PM 判断 (b): 前提 (qstore 無し base で 58–63 が oob) が main で成立しない G1〜G10 を廃止。廃止理由と復活条件は REPORT_594.md §7):
#     G11 qstore 適用 site 数 = 前提の検出数 / G12 probe 透過 (qprobe と qbase の kind 完全一致) / G13 58–63 が ok
#   gate: 条件を満たさなければ exit 1 (FAIL を出して続行しない).  終了時に work/obj/ov.o を現行 m11_ov.c から再生成する.
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1
OUT=work/negctl_594; mkdir -p "$OUT"
PE="${PE:-${FL_WIN64_DIR:-}/extracted/block00031_PE.bin}"; export PE FL_WIN64_DIR
pre() { echo "FAIL: 前提 $1" >&2; exit 1; }
[ -n "${FL_WIN64_DIR:-}" ] && [ -f "$PE" ] || pre "PE 無し ($PE)。FL_WIN64_DIR に fl-win64 を展開すること"
python3 -c 'import capstone, pefile' 2>/dev/null || pre "capstone/pefile を import できない (python3 -m pip install capstone pefile)"
[ -f work/boot_final.ll ] || pre "work/boot_final.ll 無し (work-m11 を展開すること)"
# pristine は m11_gen_ir2.sh の直後の IR (ldfix=applied・qstore=not-applied・指紋記録済み) から作る。
# 旧 snapshot の boot_final.ll は qstore 適用済みの場合があるため複製元にしない (#594 前 run の FAIL 原因)
bash m11_gen_ir2.sh > "$OUT/gen_ir2.log" 2>&1 || pre "m11_gen_ir2.sh 失敗 ($OUT/gen_ir2.log)"
cp work/boot_final.ll work/boot_final.pristine.ll
cp work/ir_conditions.json work/ir_conditions.pristine.json
python3 qstore/m11_qstore.py work/boot_final.pristine.ll work/qstore_pre.tmp.ll --pe "$PE" --detect-only \
  --report "$OUT/pristine_detect.json" --sites "$OUT/pristine_sites.tsv" > "$OUT/pristine_detect.log" 2>&1
rm -f work/qstore_pre.tmp.ll
PRE_N=$(grep -o 'fixed_stores=[0-9]*' "$OUT/pristine_detect.log" | head -1 | cut -d= -f2)
[ "${PRE_N:-0}" -gt 0 ] || pre "pristine IR に qstore 対象 site が無い (PRE_N=${PRE_N:-none})。複製元が qstore 適用済みの疑い"
echo "[negctl_594] 前提 OK: PE=$PE, qstore 検出 (pristine) = $PRE_N site"
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=${M11_LB_BASE:-0} -I."
[ -f work/obj/boot.o ] || bash m11_build.sh > /dev/null
# prep は IR と指紋 (ir_conditions.json) を対で戻す。m11_build.sh は後処理 (alloca 等) の結果を指紋に記録するため、片方だけ戻すと --check で拒否される
prep() { cp work/boot_final.pristine.ll work/boot_final.ll; cp work/ir_conditions.pristine.json work/ir_conditions.json; }
restore() { rm -f work/ov_ablate.c; touch m11_ov.c; bash m11_build.sh > /dev/null 2>&1; echo "ov.o を現行 m11_ov.c から再生成した (既定 M11_QSTORE=1)"; }
trap restore EXIT

gen() { # gen <構成> → work/ov_ablate.c
  python3 - "$1" <<'PY'
import sys
c = sys.argv[1]
s = open('m11_ov.c').read()
def rep(old, new):
    global s
    assert s.count(old) == 1, 'anchor not unique: ' + old
    s = s.replace(old, new)
if c == 'base':
    pass
elif c == 'probe':
    rep('u64 function_8cc190(u64 self, u64 key, u64 val) {\n',
        'u64 function_8cc190(u64 self, u64 key, u64 val) {\n'
        '    M11_TRACE("[p8cc190] self=%llx key=%llx cnt=%llx cap=%llx items=%llx cmp=%llx\\n", self, key, Q(self+0x10), Q(self+0x20), Q(self+8), Q(self+0x18));\n')
else:
    sys.exit('unknown config ' + c)
open('work/ov_ablate.c', 'w').write(s)
PY
}
run() { # run <出力名> <構成 (gen)> <M11_QSTORE 0|1>
  local c="$1" g="$2" q="$3"
  gen "$g" || exit 1
  emcc -c work/ov_ablate.c -o work/obj/ov.o $CF || { echo "FAIL: $c ov compile"; exit 1; }
  touch work/obj/ov.o
  M11_QSTORE=$q bash m11_build.sh > work/negctl_build.log 2>&1 || { echo "FAIL: $c link"; tail -3 work/negctl_build.log; exit 1; }
  [ "$q" = 1 ] && cp work/qstore.log "$OUT/$c.qstore.log"
  local s e; s=$(date +%s.%N)
  env SV_TRACE_AT=99999 node trap_triage/survey_units.mjs "$OUT/$c.json" > "$OUT/$c.out" 2> "$OUT/$c.err"
  e=$(date +%s.%N)
  printf '%-8s %5.1fs  %s  load=%s\n' "$c" "$(echo "$e - $s" | bc)" "$(grep -a SURVEY_UNITS "$OUT/$c.out" | head -1)" "$(cut -d' ' -f1 /proc/loadavg)"
}
# qstore 無し: 遷移の info 行の基準. 構成の前に IR を pristine へ戻す (qstore は M11_QSTORE=0 で止まる)
prep
run base base 0
# qstore あり (main の既定): 構成ごとに IR を pristine へ戻してから m11_build.sh が qstore を適用する
prep; run qbase base 1
prep; run qprobe probe 1

python3 - "$OUT" "$PRE_N" <<'PY'
import json, sys, re
O, PRE_N = sys.argv[1], int(sys.argv[2])
def load(n): return {r['unit']: r for r in json.load(open('%s/%s.json' % (O, n)))}
kinds = lambda d: {u: r['kind'] for u, r in d.items()}
base, Q, QP = (load(n) for n in ('base', 'qbase', 'qprobe'))
fails = []
def gate(name, ok, detail):
    print('%s %-60s %s' % ('PASS' if ok else 'FAIL', name, detail))
    if not ok: fails.append(name)
def info(name, detail):
    print('info %-59s %s' % (name, detail))
# 8cc190 系 OOB = 最上位 frame を問わず frames に function_8cc190 と function_8c7a10 を含む oob unit
def fam(d): return sorted(u for u, r in d.items() if r['kind'] == 'oob' and 'function_8cc190' in r.get('frames', []) and 'function_8c7a10' in r.get('frames', []))
# qstore あり (main の既定)
qlog = open(O + '/qbase.qstore.log', errors='replace').read()
QN = re.search(r'fixed_stores=(\d+)', qlog)
QN = int(QN.group(1)) if QN else -1
gate('G11 [qstore あり] qstore 適用 site 数 = 前提の検出数 (pristine)', QN == PRE_N and QN > 0, 'applied=%d detect=%d' % (QN, PRE_N))
gate('G12 [qstore あり] probe と base の kind 差 0 (probe 透過)', kinds(QP) == kinds(Q), 'diff=%d %s' % (
    sum(1 for u in Q if Q[u]['kind'] != QP[u]['kind']),
    sorted((u, Q[u]['kind'], QP[u]['kind']) for u in Q if Q[u]['kind'] != QP[u]['kind'])))
gate('G13 [qstore あり] 58..63 が ok (#552 の修復が既定構成で効く)', all(Q[u]['kind'] == 'ok' for u in range(58, 64)), [Q[u]['kind'] for u in range(58, 64)])
info('[qstore あり] 8cc190←8c7a10 系 OOB', 'n=%d %s' % (len(fam(Q)), fam(Q)))
info('[qstore 無し→あり] kind 遷移 (oob→ok / oob→halt0 / halt0→ok / ok 退行)',
     'oob→ok=%d oob→halt0=%d halt0→ok=%d ok 退行=%d' % (
         sum(1 for u in base if base[u]['kind'] == 'oob' and Q[u]['kind'] == 'ok'),
         sum(1 for u in base if base[u]['kind'] == 'oob' and Q[u]['kind'] == 'halt0'),
         sum(1 for u in base if base[u]['kind'] == 'halt0' and Q[u]['kind'] == 'ok'),
         sum(1 for u in base if base[u]['kind'] == 'ok' and Q[u]['kind'] != 'ok')))
print('SUMMARY %s' % ('FAIL: ' + ', '.join(fails) if fails else 'ALL PASS'))
sys.exit(1 if fails else 0)
PY
rc=$?
exit $rc
