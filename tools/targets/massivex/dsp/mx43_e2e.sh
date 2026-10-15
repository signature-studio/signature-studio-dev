#!/usr/bin/env bash
# MX-43 (#3838) U4e 受入 1 の 1 コマンド再現: flow 未到達の FH3 funclet を x64c の追加 root にして lift し、件数を出す
# 前提: mx39_e2e.sh を先に実行済み (MX39_WORK の reach.json)。PE は MX_PE で指定。出力は repo 外 (MX43_WORK)。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../.." && pwd)"
PE="${MX_PE:-$REPO/tools/targets/massivex/work/extracted/VST3/Massive X.vst3}"
[ -f "$PE" ] || { echo "FATAL: PE not found: $PE" >&2; exit 2; }
W="${MX43_WORK:-${RUNNER_TEMP:-${TMPDIR:-/tmp}}/massivex-mx43}"
REACH="${MX39_WORK:-${RUNNER_TEMP:-${TMPDIR:-/tmp}}/massivex-mx39}/reach.json"
[ -f "$REACH" ] || { echo "FATAL: reach.json not found (run mx39_e2e.sh first): $REACH" >&2; exit 2; }
mkdir -p "$W"
T0=$(date +%s)

echo "== 1/2 root 一覧 (flow 未到達の FH3 funclet・.text 内)"
python3 "$HERE/scripts/mx43_funclet_roots.py" "$PE" "$REACH" "$W/roots.json"

echo "== 2/2 x64c lift (追加 root・closure 0)"
rm -rf "$W/lift"
python3 "$REPO/tools/flelift/x64c.py" --pe "$PE" --entries "$W/roots.json" --out "$W/lift" \
  --closure 0 --img 0x180000000 --shift 0 --img-size 0x6616000 > "$W/lift.stdout" 2>&1
tail -1 "$W/lift.stdout" | cut -c1-200
python3 - "$W/lift" <<'PY'
import json, os, re, sys
d = sys.argv[1]
m = json.load(open(os.path.join(d, 'lift_meta.json')))
txt = open(os.path.join(d, 'fle_lifted.c'), encoding='utf-8', errors='replace').read()
blocks = [b for b in re.split(r'\n(?=void f_[0-9a-f]+\(void\) \{)', txt) if b.startswith('void f_')]
clean = sum(1 for b in blocks if 'ott_unsup(' not in b)
print('   lifted functions=%d (blocks=%d) clean(ott_unsup なし)=%d with_unsup=%d unsup_sites=%d insns=%d' % (
    len(m['functions']), len(blocks), clean, len(blocks) - clean, len(m['unsup_sites']), m['ninsn']))
PY
echo "== 3/3 .text 外候補 211 件の由来・棄却内訳・U4f〜U4i (mx47_origin.py)"
python3 "$HERE/scripts/mx47_origin.py" "$PE" "$REACH" "$W/origin.json" > "$W/origin.stdout"
python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print('   .text 外候補=%d (由来: 値が image 外 %s / .data %s) 棄却=%d (per FuncInfo)' % (d['out_of_text_candidates'], d['out_where'].get('value in outside_image'), d['out_where'].get('value in .data'), d['fh3_funcinfo_rejected_total']))" "$W/origin.json"
T1=$(date +%s)
echo "OK  elapsed=$((T1-T0))s"
