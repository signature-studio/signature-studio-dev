#!/bin/bash
# SR-21 one-command e2e: classify the non-.pdata code blocks (20,467), run the independent check and the RTTI vtable check (SR-21b).
# Requires: work/Serum2_win64.vst3 + work/index.npz (made by sr3_run.sh), python with pefile capstone numpy.
# usage: bash scripts/sr21_run.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"; cd "$HERE"
PY="${PY:-python3}"; V=work/Serum2_win64.vst3; O=out
[ -f "$V" ] && [ -f work/index.npz ] || { echo "missing $V or work/index.npz: run scripts/sr3_run.sh first" >&2; exit 1; }
echo "sha256 $(sha256sum "$V" | cut -d' ' -f1)"
$PY scripts/sr21_classify.py "$V" work/index.npz $O/sr3_gap_blocks.tsv $O/sr3_cut_table.tsv $O > /dev/null
cat $O/sr21_summary.txt
echo "## independent check (no capstone)"
$PY scripts/sr21_verify.py "$V" $O/sr21_classify.tsv $O/sr3_cut_table.tsv | tee $O/sr21_verify.txt
echo "## RTTI vtable check (SR-21b)"
$PY scripts/sr21_vtable.py "$V" work/index.npz $O/sr21_classify.tsv $O > /dev/null
cat $O/sr21_vtable_summary.txt
echo "sr21_run OK"
