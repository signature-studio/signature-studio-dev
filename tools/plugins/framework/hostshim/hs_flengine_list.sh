#!/usr/bin/env bash
# hs_flengine_list.sh — fl-win64 素材から FLEngine 実体 (PE) の一覧を作る (#5923)。
#   ARTIFACTS_DIR=<素材 dir> bash hs_flengine_list.sh
# 入力: $ARTIFACTS_DIR/fl-win64.tar.zst (展開先は $RUNNER_TEMP/flw)
# 出力: work/flengine/pe_list.tsv (全 PE block の一覧、gitignore 対象)
#       stdout に FLEngine_x64.dll の確定行。
# 展開は tar --zstd -xf (zstd 必須)。素材の installer 本体は `flstudio_win64_26.1.7.5653.exe`、
# NSIS payload は `extracted/block<NNNNN>_<KIND>.bin` (installer 解析側 [WIN64] で切り出し済み)。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
SRC="${FL_WIN64_TAR:-${ARTIFACTS_DIR:?ARTIFACTS_DIR を設定する}/fl-win64.tar.zst}"
TMP="${RUNNER_TEMP:-/tmp/opencode}/flw"
OUT="$ROOT/tools/plugins/framework/hostshim/work/flengine"

[ -f "$SRC" ] || { echo "hs_flengine_list: 素材が無い: $SRC" >&2; exit 2; }
mkdir -p "$TMP" "$OUT"
if [ ! -d "$TMP/extracted" ]; then
  (cd "$TMP" && tar --zstd -xf "$SRC")
fi

python3 - "$TMP/extracted" "$OUT/pe_list.tsv" <<'EOF'
import sys, os, struct, hashlib, glob
src, out = sys.argv[1], sys.argv[2]

def exports(d):
    pe = struct.unpack_from('<I', d, 0x3c)[0]
    if d[pe:pe+4] != b'PE\0\0':
        return None, []
    nsec = struct.unpack_from('<H', d, pe+6)[0]
    optsz = struct.unpack_from('<H', d, pe+20)[0]
    opt = pe + 24
    magic = struct.unpack_from('<H', d, opt)[0]
    dd = opt + (112 if magic == 0x20b else 96)
    exp_rva = struct.unpack_from('<I', d, dd)[0]
    secs = []
    so = opt + optsz
    for i in range(nsec):
        _, vs, va, rs, rp = struct.unpack_from('<8sIIII', d, so + 40*i)
        secs.append((va, max(vs, rs), rp))
    def r2o(r):
        for va, sz, rp in secs:
            if va <= r < va + sz:
                return r - va + rp
        return None
    if not exp_rva:
        return None, []
    eo = r2o(exp_rva)
    if eo is None:
        return None, []
    def cstr(off):
        return d[off:d.index(b'\0', off)].decode('latin1')
    mod = cstr(r2o(struct.unpack_from('<I', d, eo+12)[0]))
    n = struct.unpack_from('<I', d, eo+24)[0]
    names_rva = struct.unpack_from('<I', d, eo+32)[0]
    no = r2o(names_rva)
    names = []
    for i in range(n):
        names.append(cstr(r2o(struct.unpack_from('<I', d, no + 4*i)[0])))
    return mod, names

rows = []
for p in sorted(glob.glob(os.path.join(src, 'block*_PE.bin'))):
    d = open(p, 'rb').read()
    mod, names = exports(d)
    rows.append((os.path.basename(p), len(d), hashlib.sha256(d).hexdigest(), mod or '-', ','.join(names) or '-'))

os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, 'w') as f:
    f.write('block\tsize\tsha256\tmodule\texports\n')
    for r in rows:
        f.write('\t'.join(map(str, r)) + '\n')
print('PE blocks:', len(rows))
for r in rows:
    if r[3] == 'FLEngine_x64.dll':
        print('FLEngine_x64.dll:', r[0], r[1], r[2], r[4])
EOF
echo "一覧: $OUT/pe_list.tsv"
