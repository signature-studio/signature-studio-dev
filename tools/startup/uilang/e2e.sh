#!/usr/bin/env bash
# uilang 1 コマンド検証 (ST-T19 / #591):
#   bash tools/startup/uilang/e2e.sh
# 前提: FL_WIN64_DIR (fl-win64 展開先。直下に extracted/)、emsdk (/opt/emsdk)、node、python3。
# [1] verify_uilang.py: FLEngine_x64.dll の静的根拠 (A〜E) を機械照合 + ネガコン (DLL/spec を壊して FAIL を確認)
# [2] probe: shimx の GetUserPreferredUILanguages を FL と同じ呼び方 (flags=8 / 2 段階) で実測し、期待表と照合 + ネガコン
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
# shellcheck source=/dev/null
source "$HERE/../../shared/env.sh"
DLL="$FL_WIN64_DIR/extracted/block00031_PE.bin"
[ -f "$DLL" ] || { echo "FAIL: $DLL が無い (fl-win64 未展開)" >&2; exit 1; }
WORK="$HERE/work"; mkdir -p "$WORK"
T0=$(date +%s.%N)
echo "[uilang] load average (開始): $(cut -d' ' -f1-3 /proc/loadavg)"

echo "[1/2] verify_uilang.py"
python3 "$HERE/verify_uilang.py" "$DLL" --fonts-json "$WORK/fonts.json" | tee "$WORK/verify.log"
grep -q '"fail": 0' "$WORK/verify.log" || { echo "FAIL: verify_uilang.py" >&2; exit 1; }

expect_fail() {  # $1=ラベル $2=期待する FAIL 行の ID (例 C4) $3...=verify_uilang.py の引数
    local label="$1" id="$2"; shift 2
    if python3 "$HERE/verify_uilang.py" "$@" > "$WORK/nc.log" 2>&1; then echo "FAIL: ネガコン($label) が通った" >&2; exit 1; fi
    grep -q "^FAIL $id " "$WORK/nc.log" || { echo "FAIL: ネガコン($label) が $id で落ちていない" >&2; cat "$WORK/nc.log" >&2; exit 1; }
    echo "  NC($label): $(grep -c '^FAIL' "$WORK/nc.log") 件検出 ($id を含む)"
}
patch_dll() {  # $1=出力 $2=VA $3=旧 hex $4=新 hex  (VA→file offset は PE のセクション表から)
    python3 - "$DLL" "$1" "$2" "$3" "$4" <<'PY'
import struct, sys
src, dst, va, old, new = sys.argv[1], sys.argv[2], int(sys.argv[3], 16), bytes.fromhex(sys.argv[4]), bytes.fromhex(sys.argv[5])
d = bytearray(open(src, 'rb').read())
pe = struct.unpack_from('<I', d, 0x3C)[0]
n = struct.unpack_from('<H', d, pe + 6)[0]; o = struct.unpack_from('<H', d, pe + 20)[0]
base = struct.unpack_from('<Q', d, pe + 24 + 24)[0]; rva = va - base
for i in range(n):
    s = struct.unpack_from('<8sIIIIIIHHI', d, pe + 24 + o + 40 * i)
    if s[2] <= rva < s[2] + max(s[1], s[3]):
        off = s[4] + rva - s[2]; break
assert d[off:off + len(old)] == old, f'旧バイト不一致 {d[off:off+len(old)].hex()}'
d[off:off + len(new)] = new
open(dst, 'wb').write(d)
PY
}
# NC1: 'Program Language' 既定値の符号化文字列 ('zh' = ac00 9a00) の 1 byte を壊す → C4
patch_dll "$WORK/nc1.dll" 0x9deca8 ac009a00 ad009a00
expect_fail "zh 符号化 1byte 反転" C4 "$WORK/nc1.dll"
# NC2: 0x9deb8c の `jne 0x9debab` (75 1d) を `je` (74 1d) に反転 → C5
patch_dll "$WORK/nc2.dll" 0x9deb8c 751d 741d
expect_fail "zh 比較後の分岐反転" C5 "$WORK/nc2.dll"
# NC3: 0x9df190 の 1 回目 `mov ecx, 8` を `mov ecx, 4` → B2
patch_dll "$WORK/nc3.dll" 0x9df1b0 b908000000 b904000000
expect_fail "MUI flags 8→4" B2 "$WORK/nc3.dll"
# NC4: spec の呼出元期待値を壊す → A3
python3 - "$HERE/uilang.json" "$WORK/spec_nc.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); d['gupl_callers'] = ['0x9df190', '0x9deaa0']; json.dump(d, open(sys.argv[2], 'w'))
PY
expect_fail "spec 呼出元" A3 "$DLL" --spec "$WORK/spec_nc.json"
# NC5: FlagBtnPaint のコードポインタ (published 表) の指す先を 1 byte ずらす → D5 (0xdcf270 を指すポインタが 0 件)
patch_dll "$WORK/nc5.dll" 0xdc7cb0 70f2dc00 71f2dc00
expect_fail "published 表ポインタ破壊" D5 "$WORK/nc5.dll"
rm -f "$WORK"/nc?.dll

echo "[2/2] shimx probe (GetUserPreferredUILanguages を FL と同じ呼び方で実測)"
set +u; . /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; set -u
# shellcheck source=/dev/null
source "$HERE/../../shimx/flags.sh"
S="$HERE/../../shimx"
emcc "${SHIMX_CLANG_FLAGS[@]}" "${SHIMX_EMCC_ST[@]}" -I"$S/src" "$S"/src/*.c "$HERE/probe.c" -o "$WORK/probe.js"
mv "$WORK/probe.js" "$WORK/probe.cjs"
: > "$WORK/probe.out"
for m in "default" "lcid 0409" "lcid 0411" "lcid 0804" "lcid 0407" "lcid 040c" "lcid 0c0a" "lcid 0412" "lcid 042a" "lcid 1234"; do
    node "$WORK/probe.cjs" $m >> "$WORK/probe.out"
done
cat "$WORK/probe.out" | sed 's/^/  /'
python3 - "$WORK/probe.out" <<'PY'
import re, sys
exp = {  # mode/lcid -> (full, lang, fl_writes_program_language)。表に無い LCID (ko 0412 / vi 042a / 1234) は en-US に落ちる
    ('default', 0x0000): ('en-US', 'en', 0), ('lcid', 0x0409): ('en-US', 'en', 0), ('lcid', 0x0411): ('ja-JP', 'ja', 0),
    ('lcid', 0x0804): ('zh-CN', 'zh', 1), ('lcid', 0x0407): ('de-DE', 'de', 0), ('lcid', 0x040c): ('fr-FR', 'fr', 0),
    ('lcid', 0x0c0a): ('es-ES', 'es', 0), ('lcid', 0x0412): ('en-US', 'en', 0), ('lcid', 0x042a): ('en-US', 'en', 0), ('lcid', 0x1234): ('en-US', 'en', 0),
}
got = {}
for ln in open(sys.argv[1]):
    kv = dict(re.findall(r'(\w+)=(\S+)', ln))
    assert kv['r1'] == '1' and kv['r2'] == '1' and kv['num'] == '1' and kv['cch1'] == '7' and kv['cch2'] == '7' and kv['tail_nul2'] == '1', ln
    got[(kv['mode'], int(kv['lcid'], 16))] = (kv['full'], kv['lang'], int(kv['fl_writes_program_language']))
bad = {k: (got.get(k), v) for k, v in exp.items() if got.get(k) != v}
assert not bad and len(got) == len(exp), f'probe 不一致: {bad}'
assert [k for k, v in got.items() if v[2]] == [('lcid', 0x0804)], 'Program language を書くのは zh だけのはず'
print(f'  probe {len(got)} 件 = 期待表と一致 / Program language 自動書込みになるのは zh-CN (0x0804) のみ')
# NC: 期待表を 1 件壊すと検出できること (検査器自体の健全性)
exp[('default', 0)] = ('en-US', 'en', 1)
assert {k for k, v in exp.items() if got.get(k) != v} == {('default', 0)}
print('  NC(期待表 1 件反転): 1 件検出')
PY

T1=$(date +%s.%N)
echo "[uilang] e2e PASS 所要 $(printf '%.2f' "$(echo "$T1 - $T0" | bc)") 秒 / load average (終了): $(cut -d' ' -f1-3 /proc/loadavg)"
