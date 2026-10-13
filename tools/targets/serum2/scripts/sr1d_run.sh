#!/bin/bash
# SR-1d (#340) one-command e2e: locate + verify nlohmann binary_reader/writer (CBOR) in Serum2 Win64; exit 1 if any check or negative control fails.
# usage: bash scripts/sr1d_run.sh      env: PY (python with pefile capstone numpy), DL (dir holding Install_Xfer_Serum2_2.1.5.exe)
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"; cd "$HERE"
PY="${PY:-python3}"; DL="${DL:-${ARTIFACTS_DIR:-$HOME/artifacts}}"; W=work; O=out
mkdir -p $W/o $O
if [ ! -f $W/Serum2_win64.vst3 ]; then
  EXE="$DL/Install_Xfer_Serum2_2.1.5.exe"
  [ -f "$EXE" ] || { mkdir -p $W/dl && tar --zstd -xf "$DL/plugins-serum2.tar.zst" -C $W/dl Install_Xfer_Serum2_2.1.5.exe && EXE=$W/dl/Install_Xfer_Serum2_2.1.5.exe; }
  7z x -y -o$W/exe_extract "$EXE" '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' >/dev/null
  cp "$W/exe_extract/\$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3" $W/Serum2_win64.vst3
fi
V=$W/Serum2_win64.vst3
SHA=$(sha256sum $V | cut -d' ' -f1); echo "sha256 $SHA"
[ "$SHA" = 501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283 ] || { echo "FAIL: unexpected Serum2_win64.vst3 sha256"; exit 1; }
[ -f $W/index.npz ] || $PY scripts/sr3_index.py $V $W/index.npz
$PY scripts/sr1d_cbor_locate.py $V $W/index.npz > $O/sr1d_locate.tsv
$PY scripts/sr1d_closure.py $W/index.npz $O/sr3_cut_table.tsv > $O/sr1d_closure.txt
$PY scripts/sr1d_verify.py $V $W/index.npz | tee $O/sr1d_verify.txt
