#!/usr/bin/env bash
# x64c_fle_probe.sh — R の自作 lifter (tools/ott/lift/x64c.py) を FLEngine_x64.dll (Delphi, ImageBase 0x400000) に当てた時の対応度を実測する.
#   x64c.py は tools/ott 配下で読取専用なので、定数 3 行 (IMG/SHIFT/IMG_SIZE) + 例外耐性 1 行だけ変えたコピーを work/x64c に作る (差分: integration/x64c_fle.patch)
#   出力: lift 関数数 / 命令数 / 未対応命令 site 数と内訳, UStrAsg(0x4133f0) 単体実行
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; T="$HERE/.."; W="$HERE/work/x64c"; mkdir -p "$W/out_all"
source "$T/shared/env.sh"
PE="$FL_WIN64_DIR/extracted/block00031_PE.bin"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
cp "$T/ott/lift/x64c.py" "$W/x64c_fle.py" && patch -s "$W/x64c_fle.py" "$HERE/integration/x64c_fle.patch"
python3 -c "
import json; F=[int(x,16) for x in open('$HERE/work/fle_F.txt').read().split()]
json.dump({'roots':F,'calltgt':[]},open('$W/e_all.json','w'))"
( time python3 "$W/x64c_fle.py" --pe "$PE" --entries "$W/e_all.json" --out "$W/out_all" --closure 0 ) 2>&1 | tail -4 | cut -c1-200
python3 - "$W/out_all/lift_meta.json" <<'PY'
import json, sys, collections
m = json.load(open(sys.argv[1]))
print('x64c on FLEngine: lifted functions %d / instructions %d / unsupported sites %d (%.2f%%) / kinds %d' % (len(m['functions']), m['ninsn'], sum(m['unsup'].values()), 100.0 * sum(m['unsup'].values()) / m['ninsn'], len(m['unsup'])))
c = collections.Counter()
for k, v in m['unsup'].items(): c[k.split(':')[0]] += v
print('  top:', c.most_common(12))
PY
