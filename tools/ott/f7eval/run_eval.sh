#!/usr/bin/env bash
# run_eval.sh — CAB-238 site 別評価を 1 コマンドで実行 (1 tag = 1 process で並列)。
#
#   bash tools/ott/f7eval/run_eval.sh [tag ...]      # 既定 = 全 variant (14 + P1 site 単体 19)
#   LIFTLIB_PKG=<別 checkout の tools/liftlib> を指定するとそこを使う (既定 = tools/liftlib)
#
# 各 tag の結果: tools/ott/work/cab238/<tag>/{result.json,auto_repair.log} と <tag>.run.log
# 集約表: tools/ott/work/cab238/summary.md
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
OTT="$(dirname "$HERE")"
OUT="$OTT/work/cab238"
mkdir -p "$OUT"
# 既定 = 全 variant (14) + P1 site 単体 (p1_one_*: 脱落分岐 site の個別評価 / 無限ルーブ切り分け)
P1ONE="$(python3 -c "
import sys; sys.path.insert(0, '$HERE')
import cab238_eval as E
print(' '.join(sorted(t for t in E.VARIANTS if t.startswith('p1_one_'))))
")"
TAGS="${*:-f7_only f7_ex_18011ef10 f7_ex_18011f00e f7_ex_18011f9aa f7_ex_180120632 f7_ex_180120e6a f7_ex_1801adda1 f7_ex_1801c6b5b p1_env p1_tail p1_resume p1_cvt p1_tanpoly p1_only $P1ONE}"
PIDS=""
for t in $TAGS; do
  ( python3 "$HERE/cab238_eval.py" "$t" > "$OUT/$t.run.log" 2>&1 ) & PIDS="$PIDS $!"
done
RC=0
for p in $PIDS; do wait "$p" || RC=1; done
python3 - "$OUT" <<'PYEOF' || RC=1
import json, os, sys
out = sys.argv[1]
rows = []
for d in sorted(os.listdir(out)):
    p = os.path.join(out, d, "result.json")
    if not os.path.isfile(p):
        continue
    r = json.load(open(p))
    c0, c1 = r.get("census0") or {}, r.get("census1") or {}
    bc = r.get("bitcmp_vs_x64c") or {}
    if r.get("error"):
        rows.append("| %s | ERROR | | | | %s |" % (d, (r["error"][:60]).replace("|", "/")))
        continue
    rows.append("| %s | %s/%s | %s/%s/%s/%s | %s/%s/%s/%s | %s |" % (
        d, r.get("checks"), r.get("broken"),
        c0.get("zero"), c0.get("normal"), c0.get("junkHi"), c0.get("junkTiny"),
        c1.get("zero"), c1.get("normal"), c1.get("junkHi"), c1.get("junkTiny"),
        bc.get("equal") if bc else "-"))
print("| tag | checks | [0]=zero/normal/junkHi/junkTiny | [1]=zero/normal/junkHi/junkTiny | bit-equal/x64c |")
print("|---|---|---|---|---|")
for r in rows:
    print(r)
open(os.path.join(out, "summary.md"), "w").write("\n".join(rows) + "\n")
PYEOF
[ "$RC" = 0 ] && echo "[run_eval] ALL OK" || echo "[run_eval] FAIL (一部 tag 失敗)"
exit $RC
