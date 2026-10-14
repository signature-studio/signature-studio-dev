#!/usr/bin/env bash
# SR-5 (#73): 実 DLL・実 wine64 なしで ref_render.sh / ref_harness.sh の制御経路だけを確かめる補助確認。
# 偽 wine64 が決定的な合成 WAV を書く。実 DLL の測定ではない (再測定の代わりにならない)。
# usage: bash ref_stub_check.sh   期待: render rc 伝播 OK・harness は ref_manifest.json 照合のみ NG (NG=1)
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
FLP="$(cd "$HERE/../../../flp" && pwd)"
T="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/sr5stub.XXXXXX")"
trap 'rm -rf "$T"' EXIT
S="$T/tools/targets/serum2"
mkdir -p "$T/bin" "$S/work" "$S/host/work/build"
cp "$HERE"/ref_render.sh "$HERE"/ref_harness.sh "$HERE"/ref_manifest.json "$S/host/"
ln -s "$FLP" "$T/tools/flp"
: > "$S/host/work/build/vst3host.exe"
: > "$S/work/Serum2_win64.vst3"
cat > "$T/bin/wine64" <<'PY'
#!/usr/bin/env python3
import math, os, struct, sys
out = sys.argv[4]
d = out[2:].replace("\\", "/")
os.makedirs(d, exist_ok=True)
f = 440.0 * 2 ** ((int(os.environ.get("S2HOST_PITCH", "60")) - 69) / 12)
n = 128 * 64
data = b"".join(struct.pack("<ff", *(0.5 * math.sin(2 * math.pi * f * i / 48000) * (1 - i / n),) * 2) for i in range(n))
hdr = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE" + b"fmt " + struct.pack("<IHHIIHH", 16, 3, 2, 48000, 48000 * 8, 8, 32) + b"data" + struct.pack("<I", len(data))
open(d + "/render_f32.wav", "wb").write(hdr + data)
sys.exit(int(os.environ.get("STUB_RC", "0")))
PY
chmod +x "$T/bin/wine64"
export PATH="$T/bin:$PATH"
FAIL=0
chk() { if [ "$2" = "$3" ]; then echo "  [OK] $1 (=$3)"; else echo "  [NG] $1 (期待 $3, 実際 $2)"; FAIL=$((FAIL+1)); fi; }

echo "== render: wine が rc=3 を返したとき =="
out="$(STUB_RC=3 bash "$S/host/ref_render.sh" "$T/o3" 60 2>&1)"; rc=$?
chk "ref_render.sh の exit" "$rc" 3
printf '%s' "$out" | grep -q '^wine exit=3 ' && echo "  [OK] 'wine exit=3' を表示" || { echo "  [NG] 'wine exit=' が表示されない"; FAIL=$((FAIL+1)); }
out="$(STUB_RC=0 bash "$S/host/ref_render.sh" "$T/o0" 60 2>&1)"; rc=$?
chk "rc=0 のとき exit" "$rc" 0

echo "== content dir (S2REF_CONTENT) =="
printf '%s' "$out" | grep -q '^content=.*/work/ref_content tables=no$' && echo "  [OK] 既定は専用の空 dir (tables=no)" || { echo "  [NG] 既定の content 表示が不正"; FAIL=$((FAIL+1)); }
mkdir -p "$T/full/Tables"
out="$(S2REF_CONTENT="$T/full" bash "$S/host/ref_render.sh" "$T/ofull" 60 2>&1)"; rc=$?
chk "S2REF_CONTENT=<Tables あり dir> の exit" "$rc" 0
printf '%s' "$out" | grep -q "^content=$T/full tables=yes$" && echo "  [OK] 指定 dir と tables=yes を表示" || { echo "  [NG] 指定 dir / tables=yes が表示されない"; FAIL=$((FAIL+1)); }
S2REF_CONTENT="$T/none" bash "$S/host/ref_render.sh" "$T/onone" 60 >/dev/null 2>&1; chk "存在しない S2REF_CONTENT の exit" "$?" 1

echo "== harness 全体 (stub WAV。ref_manifest.json 照合のみ NG が正) =="
hout="$(bash "$S/host/ref_harness.sh" 2>&1)"; hrc=$?
printf '%s\n' "$hout" | sed 's/^/  | /' | cut -c1-120
chk "ref_harness.sh の exit (pin 不一致の NG=1)" "$hrc" 1
printf '%s' "$hout" | grep -q '結果: NG=1 ' && echo "  [OK] NG=1" || { echo "  [NG] NG 数が 1 でない"; FAIL=$((FAIL+1)); }
printf '%s' "$hout" | grep -q '\[NG\] 参照 sha256 が ref_manifest.json (main) と不一致' && echo "  [OK] NG は manifest 照合のみ" || { echo "  [NG] manifest 照合の NG が出ていない"; FAIL=$((FAIL+1)); }

echo "== 結果: FAIL=$FAIL =="
[ "$FAIL" -eq 0 ]
