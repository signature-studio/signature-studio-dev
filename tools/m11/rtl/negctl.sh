#!/usr/bin/env bash
# rtl_compare.py のネガティブコントロール (#129): x64c batch の 1 関数の verdict を書き換えて集計が動くことを確認する。
# usage: negctl.sh <rtl_units.json> <m11_batch.jsonl> <flelift_batch.jsonl> [VA(既定 0x4133f0 = _UStrAsg)]
set -eu
U=$1; M=$2; X=$3; VA=${4:-0x4133f0}
D=$(dirname "$0")
T=$(mktemp -d)
python3 "$D/rtl_compare.py" "$U" "$M" "$X" --tsv "$T/base.tsv" > "$T/base.txt"
python3 - "$X" "$VA" "$T/broken.jsonl" <<'EOF'
import json, sys
src, va, dst = sys.argv[1:4]
n = 0
with open(dst, 'w') as fo:
    for l in open(src):
        r = json.loads(l)
        if (r.get('function') or {}).get('va') == va:
            print('before: %s -> after: mismatch' % r['verdict'])
            r['verdict'] = 'mismatch'
            n += 1
        fo.write(json.dumps(r) + '\n')
assert n == 1, 'VA が 1 行ちょうどで見つからない: %d' % n
EOF
python3 "$D/rtl_compare.py" "$U" "$M" "$T/broken.jsonl" --tsv "$T/broken.tsv" > "$T/broken.txt"
echo '--- base 計 / 遷移'; grep -E '^\| \*\*計|^遷移' "$T/base.txt"
echo '--- broken 計 / 遷移'; grep -E '^\| \*\*計|^遷移' "$T/broken.txt"
echo '--- tsv diff (変化行数)'; diff "$T/base.tsv" "$T/broken.tsv" | grep -c '^>' || true
diff "$T/base.tsv" "$T/broken.tsv" || true
rm -rf "$T"
