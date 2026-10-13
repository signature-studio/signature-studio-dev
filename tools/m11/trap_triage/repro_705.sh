#!/usr/bin/env bash
# #944: function_413060 (D4) の OFF 実害測定の再現。OFF (lift 版) と ON (M11_OV_413060=1, C 転記版) の survey を直列・単発で 1 回ずつ実行し,
# 各回の所要時間・load・集計 (ok/noproc/miss/trap/clobber)・function_413060 の到達計数 (unit 数・呼出し数) を出す。
# 加えて感度確認 (受入条件 3・#1149): dest 値の指紋 (dest_obs_hash) で OFF の決定性 (OFF 再実行で一致) とネガコン
# (M11_NEG_413060=1: dest に p+0x40 を書く既知変更) が OFF と差を作ることを示す。ON と OFF の dest 指紋差も出す。
# 判定: build / survey の rc≠0、unit ラベルの OFF/ON 差分あり、計数の不一致、OFF 再実行で指紋不一致、ネガコンの指紋が OFF と同一 のいずれかで FAIL (exit 1)。
# 前提: work/ が m11_e2e.sh 相当で生成済み (work/boot_final.ll・work/ir_conditions.json)、FL_WIN64_DIR 設定済み。
# 計測 build (M11_INSTR_413060=1) の値は同一 build 内の比較専用。既定 build (計測なし) の基準は REPORT_944 §0 (main と同一の 869/25)。
# 使い方: bash tools/m11/trap_triage/repro_705.sh
set -u
cd "$(dirname "$0")/.."   # tools/m11 へ
export FL_WIN64_DIR="${FL_WIN64_DIR:-}"
OUT=work/repro_705; mkdir -p "$OUT"
FAIL=0
run_one() {  # run_one <label> <M11_OV_413060 値> <M11_NEG_413060 値>
  local label="$1" gate="$2" neg="$3" t0 t1 rc
  if ! M11_INSTR_413060=1 M11_OV_413060="$gate" M11_NEG_413060="$neg" timeout 300 bash m11_build.sh > "$OUT/build_$label.log" 2>&1; then
    echo "[repro_705] build $label FAILED"; FAIL=1; return 1
  fi
  t0=$(date +%s%N)
  M11_INSTR_413060=1 M11_SURVEY_UNITS="$OUT/units_$label.json" timeout 300 node m11_survey.mjs > "$OUT/survey_$label.out" 2>/dev/null; rc=$?
  t1=$(date +%s%N)
  echo "[repro_705] $label: rc=$rc elapsed=$(awk -v a="$t0" -v b="$t1" 'BEGIN{printf "%.3f", (b-a)/1e9}') s load=$(cut -d' ' -f1 /proc/loadavg)"
  if [ "$rc" -ne 0 ]; then echo "[repro_705] survey $label FAILED (rc=$rc)"; FAIL=1; fi
  python3 - "$OUT/survey_$label.out" <<'PYS' || FAIL=1
import json, sys
line = next((l for l in open(sys.argv[1]) if l.startswith('M11_SURVEY ')), None)
if line is None:
    print('[repro_705] M11_SURVEY 行が無い'); sys.exit(1)
d = json.loads(line[len('M11_SURVEY '):])
keys = ['ok', 'noproc', 'miss', 'trap', 'clobber', 'f413060_calls', 'dest_obs_n', 'dest_obs_hash']
print('[repro_705] ' + ' '.join(f'{k}={d.get(k)}' for k in keys) + f" f413060_units={len(d.get('f413060_units', []))}")
PYS
}
run_one off 0 0
run_one on 1 0
run_one off2 0 0
run_one neg 0 1
python3 - "$OUT" <<'PYD' || FAIL=1
import json, sys
d = sys.argv[1]
def units(k): return json.load(open(f'{d}/units_{k}.json'))
def summary(k):
    line = next(l for l in open(f'{d}/survey_{k}.out') if l.startswith('M11_SURVEY '))
    return json.loads(line[len('M11_SURVEY '):])
keys = ['ok', 'noproc', 'miss', 'trap', 'clobber', 'f413060_calls']
o, n = units('off'), units('on')
if len(o) != len(n):
    print(f'[repro_705] unit 数不一致: OFF {len(o)} / ON {len(n)}'); sys.exit(1)
diff = [i for i in range(len(o)) if o[i] != n[i]]
print(f'[repro_705] unit ラベルの OFF/ON 差分: {len(diff)} unit {diff[:20]}')
so, sn = summary('off'), summary('on')
mism = [k for k in keys if so.get(k) != sn.get(k)]
print(f'[repro_705] 計数の OFF/ON 不一致: {mism if mism else "なし"}')
fail = bool(diff or mism)
# 決定性: OFF を 2 回 (off, off2) 実行して dest 指紋が一致すること
det_ok = summary('off')['dest_obs_hash'] == summary('off2')['dest_obs_hash'] and summary('off')['dest_obs_n'] == summary('off2')['dest_obs_n']
print(f'[repro_705] dest 指紋の OFF 決定性 (off == off2): {"一致" if det_ok else "不一致"} ({so["dest_obs_hash"]} / {summary("off2")["dest_obs_hash"]})')
fail = fail or not det_ok
# ネガコン: dest +0x40 の既知変更が OFF と指紋差を作る
sg = summary('neg')
neg_diff = sg['dest_obs_hash'] != so['dest_obs_hash']
print(f'[repro_705] ネガコン (neg) の dest 指紋 {sg["dest_obs_hash"]} vs OFF {so["dest_obs_hash"]}: {"差あり (感度あり)" if neg_diff else "差なし (感度なし)"}')
fail = fail or not neg_diff
print(f'[repro_705] dest 指紋の OFF/ON 差: {"なし" if so["dest_obs_hash"] == sn["dest_obs_hash"] else "あり (" + sn["dest_obs_hash"] + ")"}')
sys.exit(1 if fail else 0)
PYD
if [ "$FAIL" -ne 0 ]; then echo "[repro_705] FAIL"; exit 1; fi
echo "[repro_705] PASS"
