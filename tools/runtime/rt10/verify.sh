#!/usr/bin/env bash
# verify.sh — RT-10 (#128) 検算 (本計測とは別アルゴリズム) とネガティブコントロール。
#   bash tools/runtime/rt10/verify.sh
# (1) wasm セクションサイズ/関数数を python の独立パーサで再計算 (measure.mjs sizes は node 実装)
# (2) brotli .br の往復 (復号 sha256 == 原本 sha256)。Chrome 側は resource timing の decodedBodySize == 原本バイト数 (results の cold/warm/bw に記録)
# (3) ネガティブコントロール: 末尾を切り詰めた wasm を同じハーネスで流して ok:false (CompileError) になること
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
WEB="$HERE/../../flelift/work/boot/web"
python3 - "$WEB/fleweb.wasm" <<'PY'
import sys
b = open(sys.argv[1], 'rb').read()
def leb(o):
    r = s = 0
    while True:
        x = b[o]; o += 1; r |= (x & 0x7f) << s; s += 7
        if not x & 0x80: return r, o
o = 8; secs = {}
while o < len(b):
    sid = b[o]; o += 1; sz, o = leb(o)
    if sid == 3: nfunc = leb(o)[0]
    secs[sid] = secs.get(sid, 0) + sz; o += sz
print('python: total', len(b), 'code(10)', secs[10], 'data(11)', secs[11], 'defined funcs', nfunc)
PY
node -e '
const fs=require("fs"),z=require("zlib"),c=require("crypto");
const w=fs.readFileSync(process.argv[1]),br=fs.readFileSync(process.argv[1]+".br");
const h=(x)=>c.createHash("sha256").update(x).digest("hex");
const d=z.brotliDecompressSync(br);
console.log("brotli roundtrip sha256 equal:",h(w)===h(d),"orig",w.length,"br",br.length);
if(h(w)!==h(d)) process.exit(1);
' "$WEB/fleweb.wasm"
NEG="$HERE/work/neg"; mkdir -p "$NEG"
cp "$WEB/fleweb.mjs" "$NEG/"; head -c 100000000 "$WEB/fleweb.wasm" > "$NEG/fleweb.wasm"
rm -f "$HERE/results/rt10_cold_neg.jsonl"
node "$HERE/measure.mjs" cold --reps 1 --flags default --enc none --wasm "$NEG" --tag _neg 2>/dev/null || true
grep -o '"ok":[a-z]*,"error":"[^"]\{0,160\}' "$HERE/results/rt10_cold_neg.jsonl" | head -2
