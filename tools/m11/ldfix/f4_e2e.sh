#!/usr/bin/env bash
# #564 e2e: ldfix F4 (escape 済み stack_var 内部の read が undef→xor 0,0 になる欠陥の修復) を、実 FLEngine lift に対して
#   pre (--no-f4) / post / noand (--f4-no-consumer) の 3 構成で gen_ir2 → m11_build → gui 結合 build → probe + 起動 + survey まで実測し判定する。
#   bash tools/m11/ldfix/f4_e2e.sh      終了コード: 0 = 全 gate PASS かつ全ネガコンが期待どおり FAIL / 1 = gate FAIL またはネガコン不発 / 2 = 前提欠如
# 前提: tools/m11/work (work-m11) / FL_WIN64_DIR / EMSDK_ENV ([EMSDK] の emsdk_env.sh、必須) / node / capstone+pefile / x86_64-w64-mingw32-gcc (gui の gen_api)。
#   tools/m11/work の boot_final.ll は本スクリプトが再生成して上書きする (最後は post 構成)。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; REPO="$(cd "$HERE/../../.." && pwd)"; M="$REPO/tools/m11"; GF="$REPO/tools/gui/flengine"
R="$HERE/results"; W="${F4_W:-$HERE/work/f4}"; mkdir -p "$R" "$W"
S() { echo "[f4_e2e] $*"; }; rc=0
t0=$(date +%s); S "start load=$(cut -d' ' -f1-3 /proc/loadavg) nproc=$(nproc)"
PE="${FL_WIN64_DIR:-/nonexistent}/extracted/block00031_PE.bin"
[ -f "$PE" ] || { S "前提欠如: FL_WIN64_DIR/extracted/block00031_PE.bin"; exit 2; }
[ -f "$M/work/boot0.lift.ll" ] || { S "前提欠如: tools/m11/work (work-m11 素材)"; exit 2; }
python3 -c 'import capstone, pefile' 2>/dev/null || { S "前提欠如: capstone/pefile"; exit 2; }
[ -n "${EMSDK_ENV:-}" ] && [ -f "$EMSDK_ENV" ] || { S "前提欠如: EMSDK_ENV (docs/REFERENCES.md の [EMSDK] の emsdk_env.sh を指定)"; exit 2; }
set +u; . "$EMSDK_ENV" >/dev/null 2>&1; set -u

variant() { # variant <tag> <LDFIX_ARGS>  → $W/<tag>.json
  local tag="$1" args="$2"
  ( cd "$M" && LDFIX_ARGS="$args" bash m11_gen_ir2.sh > "$W/$tag.gen.log" 2>&1 ) || { S "gen_ir2 失敗 ($tag)"; tail -3 "$W/$tag.gen.log"; exit 2; }
  ( cd "$M" && bash m11_build.sh > "$W/$tag.build.log" 2>&1 ) || { S "m11_build 失敗 ($tag)"; tail -3 "$W/$tag.build.log"; exit 2; }
  bash "$GF/build.sh" --soft > "$W/$tag.gf.log" 2>&1 || { S "gui build 失敗 ($tag)"; tail -3 "$W/$tag.gf.log"; exit 2; }
  ( cd "$GF" && node probe.mjs --wasm "$REPO/tools/gui/work/flengine/m11_gui_soft.cjs" --out "$W/$tag.probe.json" > /dev/null ) || { S "probe 失敗 ($tag)"; exit 2; }
  ( cd "$M" && node m11_run.mjs 2>/dev/null | sed -n 's/^M11_RESULT //p' > "$W/$tag.boot.json" && node m11_survey.mjs 2>/dev/null | sed -n 's/^M11_SURVEY //p' > "$W/$tag.survey.json" )
  python3 - "$tag" "$W" "$M" <<'PY' || exit 2
import json, re, sys
tag, W, M = sys.argv[1:4]
p, b, s = (json.load(open('%s/%s.%s.json' % (W, tag, k))) for k in ('probe', 'boot', 'survey'))
rep = json.load(open(M + '/work/ldfix_report.json'))
ir = open(M + '/work/boot_final.ll').read()
m = re.search(r'^define [^\n]*@function_52a7f0\(.*?^\}', ir, re.S | re.M)
fn = m.group(0)
xm = re.search(r'^  (%[\w.$-]+) = xor i64 0, 0$', fn, re.M)
used = bool(xm) and len(re.findall(re.escape(xm.group(1)) + r'(?![\w.$-])', fn)) > 1
out = dict(tag=tag, f4_fns=rep.get('f4_fns', 0), f4_vas=rep.get('f4_vas', []), f4_sites=rep.get('f4_sites', []), f4_consumer_and=rep.get('f4_consumer_and', []),
           ir_52a7f0_xor_used=used, ir_52a7f0_ldf4=('ldf4_' in fn),
           reg_calls=next((r['calls'] for r in p['reach'] if r['name'] == 'RegisterClassW'), 0), util_ret=p['util_window']['ret'], util_err=p['util_window']['err'],
           classes=[(c['name'], c['atom']) for c in p['classes']],
           units_run=b['units_run'], init_count=b['init_count'], icall_miss=b['icall_miss'], ok=s['ok'], noproc=s['noproc'], miss=s['miss'], trap=s['trap'])
json.dump(out, open('%s/%s.json' % (W, tag), 'w'), indent=1)
print('[f4_e2e] %s: f4_fns=%d RegisterClassW=%d util_ret=%s units_run=%d survey ok/noproc/miss/trap=%d/%d/%d/%d' % (tag, out['f4_fns'], out['reg_calls'], out['util_ret'], out['units_run'], out['ok'], out['noproc'], out['miss'], out['trap']))
PY
}
S "1/5 pre (F4 無し)";                       variant pre   "--no-f4"
S "2/5 noand (F4 の consumer 復元だけ無し)"; variant noand "--f4-no-consumer"
S "3/5 post (F4 全部)";                      variant post  ""
S "4/5 audit (機械語突合の全数走査: boot*.norm0.ll = B1 前)"
python3 "$HERE/audit_undefload.py" "$PE" "$W/audit_full.json" "$M"/work/boot{0,1,2,3,4}.norm0.ll > "$W/audit.txt" || { S "audit 失敗"; exit 2; }; cat "$W/audit.txt"
python3 - "$W" <<'PY' || { S "audit 集約失敗"; exit 2; }
import json, sys
W = sys.argv[1]; d = json.load(open(W + '/audit_full.json'))
slim = dict(sites_total=d['sites_total'], by_class=d['by_class'], fns_by_class=d['fns_by_class'],
            frame_in_escaped_fns=sorted({s['fn'] for s in d['frame_in_escaped']}), frame_not_escaped_fns=sorted({s['fn'] for s in d['frame_not_escaped']}),
            memread_fns=sorted({s['fn'] for s in d['memread']}), ripread_fns=sorted({s['fn'] for s in d['ripread']}))
json.dump(slim, open(W + '/audit.json', 'w'), indent=1)
PY
S "5/5 judge + ネガティブコントロール"
cd "$HERE"
python3 f4_judge.py --dir "$W" | tee "$W/judge.txt"; j=${PIPESTATUS[0]}; [ "$j" = 0 ] || rc=1
nc() { local label="$1" pat="$2"; shift 2
  "$@" > "$W/nc.out" 2>&1; local r=$?
  if [ $r = 0 ]; then S "NC $label: 期待に反して PASS → この検査は壊れても検出できない"; rc=1
  elif ! grep -Eq "$pat" "$W/nc.out"; then S "NC $label: 非 0 (rc=$r) だが期待した FAIL 行 /$pat/ が無い (judge のクラッシュ?)"; tail -3 "$W/nc.out"; rc=1
  else S "NC $label: FAIL を確認 (rc=$r): $(grep -Eo "$pat" "$W/nc.out" | head -1 | cut -c1-110)"; fi; }
cp "$W/pre.json" "$W/post_as_pre.json";   nc "N1 修復を外した (pre) 出力を post として判定" "D1 AllocateHWnd reaches RegisterClassW[^\n]* FAIL|D1 .*FAIL" python3 f4_judge.py --dir "$W" --post post_as_pre.json
cp "$W/noand.json" "$W/post_as_noand.json"; nc "N2 consumer 復元を外した (noand) 出力を post として判定" "D1 .*FAIL" python3 f4_judge.py --dir "$W" --post post_as_noand.json
nc "N3 到達増分を過大に要求 (delta >= 5)" "D1 .*FAIL" python3 f4_judge.py --dir "$W" --min-reg-delta 5
python3 - "$W" <<'PY'
import json, sys
W = sys.argv[1]; d = json.load(open(W + '/post.json')); d['ok'] -= 1; d['trap'] += 1; json.dump(d, open(W + '/post_broken_parity.json', 'w'))
PY
nc "N4 survey の 1 unit を ok→trap に壊す (parity gate)" "P1 boot/survey parity \(no regression\) +FAIL" python3 f4_judge.py --dir "$W" --post post_broken_parity.json
for t in pre noand post; do cp "$W/$t.json" "$R/f4_564_$t.json"; done; cp "$W/audit.json" "$R/audit_undefload_564.json"; cp "$W/audit_full.json" "$R/audit_undefload_564_full.json"
S "done: $(( $(date +%s) - t0 )) s, load=$(cut -d' ' -f1-3 /proc/loadavg) → exit $rc"
exit $rc
