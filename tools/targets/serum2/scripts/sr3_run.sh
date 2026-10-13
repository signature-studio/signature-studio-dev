#!/bin/bash
# SR-3 one-command e2e: Serum2 Win64 OSS boundary signature DB + cut table.
# usage: bash scripts/sr3_run.sh            (needs work/Serum2_win64.vst3; else extracts it from $DL/Install_Xfer_Serum2_2.1.5.exe)
# env  : PY (python with pefile capstone numpy), DL (installer dir), UPSTREAM=1 (fetch sqlite 3.19.3 / muparser tarballs for verify)
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"; cd "$HERE"
PY="${PY:-python3}"; DL="${DL:-${ARTIFACTS_DIR:-$HOME/artifacts}}"; W=work; O=out
mkdir -p $W/o $W/upstream $O
if [ ! -f $W/Serum2_win64.vst3 ]; then
  EXE="$DL/Install_Xfer_Serum2_2.1.5.exe"; [ -f "$EXE" ] || EXE="${RUNNER_TEMP:-/tmp}/serum2/Install_Xfer_Serum2_2.1.5.exe"
  7z x -y -o$W/exe_extract "$EXE" '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' >/dev/null
  cp "$W/exe_extract/\$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3" $W/Serum2_win64.vst3
fi
V=$W/Serum2_win64.vst3
echo "sha256 $(sha256sum $V | cut -d' ' -f1)"
$PY scripts/sr3_index.py $V $W/index.npz
$PY scripts/sr3_anchors.py $V $W/index.npz $W/anchors.json > $O/sr3_anchors.txt
$PY scripts/sr3_cut.py $V $W/index.npz $W/anchors.json $O > /dev/null
$PY scripts/sr3_gaps.py $V $W/index.npz $O/sr3_cut_table.tsv $O/sr3_gap_blocks.tsv | tee $O/sr3_gaps_summary.txt
cp $W/anchors.json $O/sr3_anchors.json
# upstream string cross-check (independent evidence class)
if [ ! -f $W/upstream/sqlite3.c ]; then
  curl -sL -o $W/upstream/s.zip https://sqlite.org/2017/sqlite-amalgamation-3190300.zip
  ( cd $W/upstream && unzip -qo s.zip && cp sqlite-amalgamation-3190300/sqlite3.c sqlite3.c )
fi
if [ ! -f $W/upstream/muparser_2.3.2.cpp ]; then
  for f in muParserBase muParserError muParser muParserTokenReader muParserCallback; do
    curl -sL https://raw.githubusercontent.com/beltoforion/muparser/v2.3.2/src/$f.cpp
  done > $W/upstream/muparser_2.3.2.cpp
fi
{
  echo "## sqlite 3.19.3 amalgamation vs sqlite window"
  $PY scripts/sr3_verify_strings.py $V $W/index.npz $O/sr3_cut_table.tsv sqlite $W/upstream/sqlite3.c
  echo; echo "## negative control: sqlite literals vs zstd window (expect 0 in window)"
  $PY scripts/sr3_verify_strings.py $V $W/index.npz $O/sr3_cut_table.tsv zstd $W/upstream/sqlite3.c | sed -n 2,3p
  echo; echo "## muparser v2.3.2 vs muparser window"
  $PY scripts/sr3_verify_strings.py $V $W/index.npz $O/sr3_cut_table.tsv muparser $W/upstream/muparser_2.3.2.cpp --minlen 4
} > $O/sr3_verify.txt
python3 - <<'EOF'
import json
d = json.load(open('out/sr3_signature_db.json'))
t = d['_total']
print("TOTAL cut_funcs=%d cut_bytes=%d lift_funcs %d -> %d, lift_bytes %d -> %d" % (t['cut_funcs'], t['cut_bytes'], t['lift_funcs_before'], t['lift_funcs_after'], t['lift_bytes_before'], t['lift_bytes_after']))
for k, v in sorted(d.items()):
    if k != '_total': print(f"{k:<14} cut_funcs={v['cut_funcs']:<5} cut_bytes={v['cut_bytes']:<8} tags={v['by_tag']}")
EOF
echo "sr3_run OK"
