#!/usr/bin/env bash
# #113 S1 probe: fl-win64 (block 分割) からインストール木を組み立て、wine64 で FL64.exe の起動を 1 回試す。
# 前提: apt の wine64 / xvfb, python3, fl-win64 素材 ($ARTIFACTS_DIR/fl-win64.tar.zst) 展開済み ($FL_WIN64_DIR/extracted)。
# 出力は $RUNNER_TEMP 配下のみ (commit 対象外)。結果の要約は tools/flp/REPORT.md §S1。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ART="${RUNNER_TEMP:-/tmp}"
EXT="$ART/fl-win64/extracted"
INST="$ART/fl-install"
WORK="$ROOT/tools/assets/work"
export WINEPREFIX="$ART/wineprefix" WINEDEBUG="${WINEDEBUG:--all}" WINEARCH=win64
export PATH="/usr/lib/wine:$PATH"

[[ -d "$EXT" ]] || { echo "missing $EXT (fl-win64 を展開すること)" >&2; exit 2; }
EXE="$ART/fl-win64/flstudio_win64_26.1.7.5653.exe"
[[ -f "$EXE" ]] || { echo "missing installer $EXE" >&2; exit 2; }

mkdir -p "$WORK"
python3 "$ROOT/tools/startup/loadpaths/mk_manifest.py" "$EXE" "$WORK/block_offsets.json" >/dev/null
python3 "$ROOT/tools/assets/inventory/mk_inputs.py" "$EXT" "$WORK" "$WORK/block_offsets.json" >/dev/null
python3 "$ROOT/tools/assets/win_paths/recover_paths.py" "$EXE" "$WORK/block_manifest.json" "$WORK/win_paths.json"

python3 - "$EXT" "$INST" "$WORK/win_paths.json" <<'EOF'
import json, os, shutil, sys
ext, inst, wp = sys.argv[1:4]
d = json.load(open(wp))
for idx, paths in d.items():
    src = next((os.path.join(ext, f) for f in os.listdir(ext) if f.startswith('block' + idx + '_')), None)
    if not src or not paths or not paths[0].startswith('$INSTDIR\\'):
        continue
    dst = os.path.join(inst, paths[0][len('$INSTDIR\\'):].replace('\\', '/'))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if not os.path.exists(dst):
        shutil.copyfile(src, dst)
EOF

cd "$INST"
timeout 90 xvfb-run -a wine64 FL64.exe > "$ART/s1_probe.log" 2>&1 || true
grep -iE 'wintrust:WinVerifyTrust|msgbox' "$ART/s1_probe.log" | head -5 || true
