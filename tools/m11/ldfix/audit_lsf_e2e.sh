#!/usr/bin/env bash
# audit_lsf_e2e.sh — #484 (LD-8) 1 コマンド再現。PE (fl-win64) 無しで、work-m11 の
#   work/{boot*.lift.ll, boot*.drc.config.json, m11_image.bin, boot_final3.ll, ldfix_report.json} だけで走る。
#   1/4 ldfix を PE 無し (ldmach_img) で再実行し、PE 版の ldfix_report.json と全 32 キーが一致するか検証 (shim の妥当性)
#   2/4 5c0270 に対する fix_f3c の門 (G1〜G5) を表示 (ldfix が検出できなかった理由)
#   3/4 audit_lsf.py (別算法) を修復前 IR / boot_final3.ll の両方に実行
#   4/4 ネガティブコントロール (negctl_484.sh)
# 使い方: bash tools/m11/ldfix/audit_lsf_e2e.sh      環境変数: M11_WORK (既定 tools/m11/work) / PY (capstone+pefile 入り python)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../../.." && pwd)"
W="${M11_WORK:-$REPO/tools/m11/work}"
OUT="${RUNNER_TEMP:-/tmp}/audit_lsf_e2e"; mkdir -p "$OUT"
if [ -z "${PY:-}" ]; then
  if python3 -c 'import capstone, pefile' 2>/dev/null; then PY=python3
  else uv venv "$OUT/venv" -q && uv pip install -q --python "$OUT/venv/bin/python" capstone pefile && PY="$OUT/venv/bin/python"; fi
fi
CFG="$W/boot*.drc.config.json"; IMG="$W/m11_image.bin"
step() { echo "[audit_lsf_e2e] $*"; }

step "1/4 修復前 IR を再生成 (tools/m11 を $OUT/gen にコピーして m11_gen_ir2.sh を実行。PE 無しなので ldfix は skip される) → ldfix_img.py で ldfix を再実行"
rm -rf "$OUT/gen"; mkdir -p "$OUT/gen/tools"; cp -r "$REPO/tools/m11" "$OUT/gen/tools/"; rm -rf "$OUT/gen/tools/m11/work"
mkdir -p "$OUT/gen/tools/m11/work"
for f in boot0 boot1 boot2 boot3 boot4; do cp "$W/$f.lift.ll" "$OUT/gen/tools/m11/work/"; done
find "$W" -maxdepth 1 -type f -size -3M -exec cp {} "$OUT/gen/tools/m11/work/" \;
( cd "$OUT/gen/tools/m11" && bash m11_gen_ir2.sh > "$OUT/gen_ir2.log" 2>&1 ) || { echo "gen_ir2 失敗: $OUT/gen_ir2.log"; exit 1; }
PRE="$OUT/gen/tools/m11/work/boot_final.ll"
"$PY" "$HERE/ldfix_img.py" "$PRE" "$OUT/ldfix_img_out.ll" "$IMG" "$CFG" --report "$OUT/ldfix_img_report.json" 2>&1 | tail -1
"$PY" - "$W/ldfix_report.json" "$OUT/ldfix_img_report.json" <<'EOF'
import json, sys
a, b = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
d = [k for k in a if a[k] != b.get(k)]
print('[equiv] PE 版 ldfix_report.json vs PE 無し版: キー %d / %d, 不一致 %d %s' % (len(a), len(b), len(d), d))
EOF

step "2/4 fix_f3c の門 (5c0270 / 41a670; 入力 = 修復前 IR)"
"$PY" "$HERE/f3c_gate_probe.py" "$PRE" 5c0270,41a670 "$IMG" "$CFG" | grep -v -E 'IR の dec_label|IR 全体|^     \['

step "3/4 audit_lsf.py (修復前 IR / boot_final3.ll)"
"$PY" "$HERE/audit_lsf.py" "$PRE" "$IMG" "$CFG" --json "$OUT/audit_pre.json" | sed 's/^/[pre ] /'
"$PY" "$HERE/audit_lsf.py" "$W/boot_final3.ll" "$IMG" "$CFG" --json "$OUT/audit_post.json" | sed 's/^/[post] /'

step "4/4 ネガティブコントロール"
M11_WORK="$W" PY="$PY" bash "$HERE/negctl_484.sh"
