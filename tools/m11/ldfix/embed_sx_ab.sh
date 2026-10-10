#!/usr/bin/env bash
# embed_sx_ab.sh — CAB-131: alloca 適用状態 (CAB-129 検収と同じ足場) での mainline + shimx_link 純リンク A/B。
#
#   bash tools/m11/ldfix/embed_sx_ab.sh
#
# base = gen_ir2 素出力 (ldfix 無し) / fix = gen_ir2+ldfix 出力。それぞれに m11_alloca.py を適用してから
#   (1) mainline: m11_post → work/boot_final3.ll 差替え → m11_build.sh → m11_run / m11_survey / m11_judge
#   (2) shimx_link 純リンク (--soft): build.sh --soft → run_trace (起動 unit 数) + survey_trace (942 unit 隔離)
# 注意: work/boot_final{,3}.ll と work/obj を差し替える (他 agent の同時 build と競合しうる; 実行は単発で)。
#       終了後 work/boot_final.ll は fix+alloca 状態になる (CAB-129 受入状態 + 本チケット変更の合成 = 新たな正)。
#       tools/m11/shimx_link は読取のみ (CAB-177 が build.sh を改変中でも A/B は同一 harness 状態で base/fix 比較)。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
M11="$(cd -- "$HERE/.." && pwd)"
REPO="$(cd -- "$M11/../.." && pwd)"
cd "$REPO"
export PATH="$HOME/.local/share/pnpm/bin:$PATH"
BASE_IR="$HERE/work/ir_base_noldfix.ll"
FIX_IR="$HERE/work/ir_fix_embedded.ll"

step() { echo "[embed_sx_ab] $(date +%H:%M:%S) $*"; }
mark() { touch "$HERE/work/sxab_$1.done"; }
done_p() { [ -f "$HERE/work/sxab_$1.done" ]; }

for V in base fix; do
  if done_p "$V"; then step "$V: done マーカーあり skip"; continue; fi
  IR="$BASE_IR"; [ $V = fix ] && IR="$FIX_IR"
  step "[$V] IR 設置 + alloca 適用 (in-place)"
  cp "$IR" "$M11/work/boot_final.ll"
  python3 "$M11/alloca/m11_alloca.py" "$M11/work/boot_final.ll" "$M11/work/boot_final.ll" \
    --report "$HERE/work/alloca_report_$V.json" > /dev/null || { step "FAILED: alloca/$V"; exit 1; }
  step "[$V] m11_build.sh"
  (cd "$M11" && bash m11_build.sh) > "$HERE/work/sxab_build_$V.log" 2>&1 || { step "FAILED: build/$V"; tail -5 "$HERE/work/sxab_build_$V.log"; exit 1; }
  grep -o "signature mismatch: [0-9]*, undefined symbol: [0-9]*" "$HERE/work/sxab_build_$V.log" | tail -1
  step "[$V] mainline run + survey + judge"
  (cd "$M11" && timeout 300 node m11_run.mjs > "$HERE/work/sxab_full_$V.out" 2>&1) || true
  (cd "$M11" && timeout 600 node m11_survey.mjs > "$HERE/work/sxab_survey_$V.out" 2>&1) || true
  # m11_judge.py は work/e2e_*.out の固定 path を読むため、実測出力をそこへ置いてから判定する
  cp "$HERE/work/sxab_full_$V.out" "$M11/work/e2e_full.out"
  cp "$HERE/work/sxab_survey_$V.out" "$M11/work/e2e_survey.out"
  (cd "$M11" && python3 m11_judge.py > "$HERE/work/sxab_judge_$V.out" 2>&1) || true
  grep -E "reached_stage|units:|survey ok=|trap kinds" "$HERE/work/sxab_judge_$V.out" | head -6
  step "[$V] shimx_link 純リンク (--soft) build + run_trace + survey_trace"
  (cd "$M11/shimx_link" && bash build.sh --soft) > "$HERE/work/sxab_sxbuild_$V.log" 2>&1 || { step "FAILED: sxbuild/$V"; tail -5 "$HERE/work/sxab_sxbuild_$V.log"; exit 1; }
  tail -1 "$HERE/work/sxab_sxbuild_$V.log"
  node "$M11/shimx_link/run_trace.mjs" "$M11/work/shimx_link/m11_sx_plain_soft.cjs" > "$HERE/work/sxab_sx_$V.out" 2>&1 || true
  grep SXL_RESULT "$HERE/work/sxab_sx_$V.out" | cut -c1-300 || true
  node "$M11/shimx_link/survey_trace.mjs" "$M11/work/shimx_link/m11_sx_plain_soft.cjs" --out "$HERE/work/sxsurvey_$V" > "$HERE/work/sxab_sxsurvey_$V.out" 2>&1 || true
  grep SXL_SURVEY "$HERE/work/sxab_sxsurvey_$V.out" | cut -c1-260 || true
  mark "$V"
done

# 集計
python3 - "$HERE/work" <<'PYEOF'
import json, re, sys, os
W = sys.argv[1]
def jline(p, tag):
    try:
        t = open(p, errors='replace').read()
        m = re.search(r'^%s (\{.*\})\s*$' % tag, t, re.M)
        return json.loads(m.group(1)) if m else {}
    except OSError: return {}
def sxrun(v):
    d = jline(os.path.join(W, 'sxab_sx_%s.out' % v), 'SXL_RESULT')
    return d
def sxsurvey(v):
    p = os.path.join(W, 'sxsurvey_%s' % v, 'm11_sx_plain_soft.survey.json')
    try:
        d = json.load(open(p)); return d.get('summary', {}).get('kinds', {}), d.get('summary', {})
    except Exception: return {}, {}
def judge(v):
    t = open(os.path.join(W, 'sxab_judge_%s.out' % v), errors='replace').read()
    def rx(p):
        m = re.search(p, t); return m.group(1) if m else None
    return {'stage': rx(r'reached_stage: (\d)/6'), 'units': rx(r'units: run=(\d+) / total=(\d+)'),
            'init': rx(r'init_count\(prologue\)=(\d+)'), 'ok': rx(r'survey ok=(\d+)'), 'trap': rx(r'trap=(\d+)')}
print('SXAB_SUMMARY (base -> fix):')
jb, jf = judge('base'), judge('fix')
for k in jb:
    print('  judge %-8s %s -> %s %s' % (k, jb[k], jf[k], '' if jb[k] == jf[k] else '  <-- CHANGED'))
for v in ('base', 'fix'):
    d = sxrun(v)
    print('  sx_run[%s] units_run=%s init_count_var=%s dllmain_done=%s' % (
        v, d.get('units_run'), d.get('init_count_var'), d.get('dllmain_done')))
kb, sb = sxsurvey('base'); kf, sf = sxsurvey('fix')
print('  sx_survey kinds base: %s' % json.dumps(kb, ensure_ascii=False))
print('  sx_survey kinds fix : %s' % json.dumps(kf, ensure_ascii=False))
PYEOF
step "done"
exit 0
