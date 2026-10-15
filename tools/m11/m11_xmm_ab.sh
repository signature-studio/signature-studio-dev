#!/usr/bin/env bash
# #1479 (M11-2): xmm 引数の callee 署名復元 (fix_xmm_args.py, M11_XMM_ARGS=1, #954) の unit 別 A/B.
# 同一 IR・同一 PE で既定 (M11_XMM_ARGS=0) と opt-in (=1) の survey を取り、unit 別 (942 本) に ok→非 ok の退行を判定する。
# 判定: ok 喪失 (ok→非 ok) が 1 件以上、または unit 838/882/885 が ok でなければ終了 1。negative control で判定器自体を検査する。
# 両 arm の boot_final3.ll が同一 (opt-in が IR を変えていない) なら A/B は空振りとして終了 2。
# 前提: work/boot_final.ll と work/ir_conditions.json (m11_build.sh と同じ)、FL_WIN64_DIR、emsdk ([EMSDK]・docs/REFERENCES.md)、node。出力は work/xmm_ab/ (gitignore)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$HERE"
OUT=work/xmm_ab
mkdir -p "$OUT"
for x in 0 1; do
  M11_XMM_ARGS=$x bash m11_build.sh > "$OUT/build_$x.log" 2>&1
  sha256sum work/boot_final3.ll > "$OUT/ir_sha256_$x.txt"
  M11_SURVEY_UNITS="$OUT/survey_$x.json" node m11_survey.mjs > "$OUT/survey_$x.out" 2>&1
  sha256sum "$OUT/survey_$x.json" > "$OUT/survey_sha256_$x.txt"
done
cat "$OUT"/ir_sha256_0.txt "$OUT"/ir_sha256_1.txt "$OUT"/survey_sha256_0.txt "$OUT"/survey_sha256_1.txt
if cmp -s "$OUT/ir_sha256_0.txt" "$OUT/ir_sha256_1.txt"; then
  echo "[ab] IR 不変: 両 arm の boot_final3.ll が同一 (opt-in が IR を変えていない)。A/B は空振り" >&2
  exit 2
fi
if [ -f work/xmm_args_report.json ]; then
  python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); print("[xmm] fixed=%d skipped=%d callsite_zero_args=%d" % (len(r["fixed"]), len(r["skipped"]), r["callsite_zero_args"]))' work/xmm_args_report.json
fi
python3 - "$OUT/survey_0.json" "$OUT/survey_1.json" <<'PYEOF'
import json, sys
from collections import Counter

WATCH = (838, 882, 885)

def judge(base, after):
    assert len(base) == len(after) == 942, (len(base), len(after))
    diff = [i for i in range(942) if base[i] != after[i]]
    loss = [i for i in range(942) if base[i] == 'ok' and after[i] != 'ok']
    gain = [i for i in range(942) if base[i] != 'ok' and after[i] == 'ok']
    watch_bad = [i for i in WATCH if after[i] != 'ok']
    return diff, loss, gain, watch_bad

base = json.load(open(sys.argv[1]))
after = json.load(open(sys.argv[2]))
for name, lab in (('base(0)', base), ('xmm(1)', after)):
    c = Counter(lab)
    print('[%s] ok %d / trap %d / miss %d / noproc %d / oom %d / clobber %d' % (name, c['ok'], c['trap'], c['miss'], c['noproc'], c['oom'], c['clobber']))
diff, loss, gain, watch_bad = judge(base, after)
print('[ab] unit 別 差 %d 件 (942 本): %s' % (len(diff), ' '.join('%d:%s->%s' % (i, base[i], after[i]) for i in diff) or '0'))
print('[ab] ok 喪失 (ok->非ok) %d 件: %s' % (len(loss), loss or '0'))
print('[ab] ok 獲得 (非ok->ok) %d 件: %s' % (len(gain), gain or '0'))
print('[ab] watch unit %s の非ok: %s' % (WATCH, watch_bad or '0'))
rc = 1 if (loss or watch_bad) else 0
print('[ab] verdict: %s' % ('REGRESSION' if rc else 'OK (退行 0)'))

# negative control: 判定器が退行を検出できること (unit 838 を ok→trap に改変した写しで FAIL を確認)
neg = list(after); neg[838] = 'trap'
_, nloss, _, nwatch = judge(base, neg)
assert nloss or nwatch, 'negctl: 退行を検出できない'
print('[negctl] 改変写し (unit 838 ok->trap) で検出: loss %s / watch %s' % (nloss, nwatch))
sys.exit(rc)
PYEOF
