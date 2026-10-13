#!/usr/bin/env bash
# ls737_liftdiff.sh — #737 (LD-15) 1 コマンド再現。LSF 脱落修復 66e080・806740・666a60 の修復前後を
#   liftdiff (native PE vs wasm) で比較し、各 3 回 (n=3) の判定を work/ 配下に出す。
#   修復前 IR = work-m11 の boot_final2.ll (ldfx 名 0 件) の上に、修復後 IR (boot_final3.ll) の
#   3 関数だけを boot_final2 の本体で差し替えたもの。他の関数は修復後と同一。
# 素材: oc_artifacts: fl-win64 toolchain-emsdk work-m11 work-liftdiff + python (numpy capstone pefile)
#   FL_WIN64_DIR = fl-win64 の展開先 (中に extracted/block00031_PE.bin)。EMSDK は /opt/emsdk。
# 使い方: FL_WIN64_DIR=<展開先> bash tools/m11/ldfix/ls737_liftdiff.sh
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../../.." && pwd)"
LD="$REPO/tools/liftdiff"
M11="$REPO/tools/m11/work"
: "${FL_WIN64_DIR:?FL_WIN64_DIR を設定する (fl-win64 の展開先)}"
export FL_WIN64_DIR
test -f "$FL_WIN64_DIR/extracted/block00031_PE.bin"
test -f "$M11/boot_final2.ll" -a -f "$M11/boot_final3.ll"
test -f "$LD/work/m11/boot_state.json"

cd "$LD"
printf '0x66e080\n0x806740\n0x666a60\n' > work/ls737_vas.txt

python3 - "$M11/boot_final2.ll" "$M11/boot_final3.ll" work/ls737_pre.ll <<'PY'
import re, sys
def fns(t):
    return {m.group(1): m.group(0) for m in re.finditer(r'^define [^\n]*@(function_[0-9a-f]+)\(.*?\n}\n', t, re.M | re.S)}
pre = fns(open(sys.argv[1], errors='replace').read())
post = open(sys.argv[2], errors='replace').read()
for k in ['function_66e080', 'function_806740', 'function_666a60']:
    cur = re.search(r'^define [^\n]*@' + k + r'\(.*?\n}\n', post, re.M | re.S).group(0)
    post = post.replace(cur, pre[k], 1)
open(sys.argv[3], 'w').write(post)
PY

python3 - <<'PY'
import json
t = json.load(open('targets/m11.json'))
t['name'] = 'm11_ls737pre'
t['ir'] = 'tools/liftdiff/work/ls737_pre.ll'
t['desc'] = 'LD-15 #737 before-repair baseline (3 fns from boot_final2)'
json.dump(t, open('work/ls737_pre_target.json', 'w'), indent=1, ensure_ascii=False)
PY

ST="$LD/work/m11/boot_state.json"
python3 liftdiff.py build targets/m11.json >/dev/null
python3 liftdiff.py build work/ls737_pre_target.json >/dev/null

for n in 1 2 3; do
  for side in post pre; do
    if [ "$side" = post ]; then T=targets/m11.json; else T=work/ls737_pre_target.json; fi
    s=$(date +%s%N)
    python3 liftdiff.py batch "$T" --set file:work/ls737_vas.txt --shards 3 --nobuild --state "$ST" \
      --out "work/m11/ls737_${side}_r$n.jsonl" > "work/m11/ls737_${side}_r$n.log" 2>&1
    e=$(date +%s%N)
    echo "[ls737] $side r$n $(( (e - s) / 1000000 )) ms  load1=$(cut -d' ' -f1 /proc/loadavg)"
  done
done

python3 - <<'PY'
import json, collections
for side in ['pre', 'post']:
    for n in [1, 2, 3]:
        for l in open(f'work/m11/ls737_{side}_r{n}.jsonl'):
            r = json.loads(l)
            oc = dict(collections.Counter(c['outcome'] for c in r['cases']))
            tags = [t['tag'] for t in r.get('tags', [])]
            print(f"[ls737] {side} r{n} {r['function']['name']} verdict={r['verdict']} reason={r.get('unexec_reason')} cases={oc} tags={tags}")
PY
echo "LS737_LIFTDIFF DONE"
