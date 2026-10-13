#!/usr/bin/env bash
# loadpaths 1 コマンド検証 (ST-T14 / #39):
#   bash tools/startup/loadpaths/e2e.sh
# 前提: FL_WIN64_DIR (= fl-win64 素材の展開先。直下に flstudio_win64_*.exe と extracted/)。未設定なら tools/shared/env.sh の既定。
# 手順: [1] 配置照合 (check.py: 再構成 manifest → パス復元 → group 件数/写像)
#       [2] 静的根拠の機械照合 (verify_refs.py) + ネガコン
#       [3] .moe 復号 + 検査 (moe.py) + 別算法/ネガコン (crosscheck.py)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
# shellcheck source=/dev/null
source "$HERE/../../shared/env.sh"
EXE="$(ls "$FL_WIN64_DIR"/flstudio_win64_*.exe | head -1)"
EXT="$FL_WIN64_DIR/extracted"
WORK="$HERE/work"; mkdir -p "$WORK"
T0=$(date +%s.%N)
echo "[loadpaths] load average (開始): $(cut -d' ' -f1-3 /proc/loadavg)"

echo "[1/3] check.py"
python3 "$HERE/check.py" "$EXE" "$EXT" --work "$WORK" --out "$WORK/result.json" > "$WORK/check.log"
python3 - "$WORK/result.json" "$WORK/win_paths.json" "$WORK/inputs.txt" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
assert r['fail'] == [] and r['map_mismatch'] == 0 and r['map_checked'] == r['grouped_files']
by = {g['id']: g for g in r['groups']}
assert by['lang-moe']['files'] == 7 and by['help-scr']['files'] == 2 and len(r['groups']) == 15, 'group 件数'
print(f"  groups {len(r['groups'])} / grouped_files {r['grouped_files']} / map_mismatch {r['map_mismatch']} / shadowed {r['shadowed']}")
wp = json.load(open(sys.argv[2]))
idx = lambda p: next(k for k, v in wp.items() if k.isdigit() and p in v)
with open(sys.argv[3], 'w') as f:
    f.write('extracted/block%s_PE.bin\n' % idx('$INSTDIR\\FLEngine_x64.dll'))
    for p in r['files']['lang-moe']:
        f.write('extracted/block%s_DATA.bin\n' % idx('$INSTDIR\\' + p.replace('/', '\\')))
PY
DLL="$FL_WIN64_DIR/$(sed -n 1p "$WORK/inputs.txt")"
mapfile -t MOES < <(sed -n '2,$p' "$WORK/inputs.txt" | sed "s#^#$FL_WIN64_DIR/#")

echo "[2/3] verify_refs.py"
python3 "$HERE/verify_refs.py" "$DLL"
python3 - "$HERE/loadpaths.json" "$WORK/spec_nc.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
d['claims'][0]['refs'][0] = '.moeX'                       # 存在しない文字列
d['calls'].append(['0x9de400', '0x9deaa0'])               # 存在しない呼出辺
json.dump(d, open(sys.argv[2], 'w'))
PY
if python3 "$HERE/verify_refs.py" "$DLL" "$WORK/spec_nc.json" > "$WORK/nc.log"; then echo "FAIL: ネガコンが通った" >&2; exit 1; fi
echo "  NC (文字列 1 + 呼出辺 1 を壊す): $(grep -c '^FAIL' "$WORK/nc.log") 件検出 (期待 2)"
[ "$(grep -c '^FAIL' "$WORK/nc.log")" = 2 ]

echo "[3/3] moe.py / crosscheck.py"
python3 "$HERE/moe.py" "$DLL" "${MOES[@]}" --json | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['ok'] and d['distinct_enc_headers'] == 1 and len(d['files']) == 7
for f in d['files']:
    print('  ', {k: f[k] for k in ('entries', 'mo_bytes', 'charset_utf8', 'language')})
"
python3 "$HERE/crosscheck.py" "$DLL" "${MOES[@]}" | tail -6

T1=$(date +%s.%N)
echo "[loadpaths] e2e PASS 所要 $(printf '%.2f' "$(echo "$T1 - $T0" | bc)") 秒 / load average (終了): $(cut -d' ' -f1-3 /proc/loadavg)"
