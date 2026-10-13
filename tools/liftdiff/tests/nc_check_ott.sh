#!/usr/bin/env bash
# check_ott.py のネガティブコントロール: work/ott_old/batch.jsonl のコピーから D1〜D6 のタグを 1 系統ずつ除去し、
# check_ott.py が exit 1 (FAIL) になることを確認する。1 つでも exit 0 なら gate が無効 → exit 1。
# 前提: work/ott_old/batch.jsonl (liftdiff.py batch targets/ott_old.json の産物)。work/ は触らず一時 dir のコピーで実行。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
SRC="$HERE/../work/ott_old/batch.jsonl"
[ -e "$SRC" ] || { echo "missing input: $SRC" >&2; exit 2; }
T="$(mktemp -d "${TMPDIR:-/tmp}/nc_check_ott.XXXXXX")"
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/tests" "$T/work/ott_old"
cp "$HERE/check_ott.py" "$T/tests/"
bad=0
run() { # name, python filter expression body (r -> r)
  python3 - "$SRC" "$T/work/ott_old/batch.jsonl" "$2" <<'PY'
import json, sys
src, dst, drop = sys.argv[1], sys.argv[2], set(sys.argv[3].split(','))
with open(dst, 'w') as o:
    for l in open(src):
        r = json.loads(l)
        r['tags'] = [t for t in r.get('tags', []) if t['tag'] not in drop]
        o.write(json.dumps(r) + '\n')
PY
  set +e; python3 "$T/tests/check_ott.py" >/dev/null; rc=$?; set -e
  if [ "$rc" = 1 ]; then echo "PASS NC[$1]: タグ除去 → check_ott.py exit 1"; else echo "FAIL NC[$1]: check_ott.py exit $rc (期待 1)"; bad=1; fi
}
cp "$SRC" "$T/work/ott_old/batch.jsonl"
set +e; python3 "$T/tests/check_ott.py" >/dev/null; rc=$?; set -e
if [ "$rc" = 0 ]; then echo "PASS positive: 無加工 batch → exit 0"; else echo "FAIL positive: 無加工 batch で exit $rc"; bad=1; fi
run D1 icall_drop
run D2 short_global
run D3 callsite_arg_drop,arg_drop
run D6 xmm_arg_drop,zero_init_drop,fp_flag_unreflected,spill_slot_deref
exit $bad
