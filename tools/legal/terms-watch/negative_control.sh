#!/usr/bin/env bash
# ネガティブコントロール (実 FL 素材): 同梱 EULA.html / ToU(RTF) を 1 語だけ改変した複製で terms-watch が FAIL (exit 1) すること、
# 空白だけの改変では PASS (exit 0)、素材 dir 無しは exit 3 であることを確認する。台帳は書き換えない (--no-write)。
#   FL_WIN64_DIR=<fl-win64 展開先> bash tools/legal/terms-watch/negative_control.sh
set -uo pipefail
source "$(git rev-parse --show-toplevel)/tools/shared/env.sh"
CLI="$REPO_ROOT/tools/legal/terms-watch/cli.mjs"
SRC="$FL_WIN64_DIR/extracted"
T="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/tw-neg.XXXXXX")"
trap 'rm -rf "$T"' EXIT
fail=0

mk() { # mk <name> <python-expr on bytes d for EULA> <python-expr for RTF>
  mkdir -p "$T/$1/extracted"
  python3 - "$SRC" "$T/$1/extracted" "$2" "$3" <<'PY'
import sys, pathlib, re
src, dst, fe, fr = map(pathlib.Path, sys.argv[1:5])
e = (src / "block24719_DATA.bin").read_bytes(); r = (src / "block00029_DATA.bin").read_bytes()
for name, d, expr in (("block24719_DATA.bin", e, str(fe)), ("block00029_DATA.bin", r, str(fr))):
    out = eval(expr, {"d": d, "re": re})
    assert expr == "d" or out != d, f"改変が空振り: {name}"
    (dst / name).write_bytes(out)
PY
}
run() { # run <case> <expected-exit> <fl-dir>
  out="$(node "$CLI" check --fl-dir "$3" --only fl-eula-html,fl-tou-rtf --no-write --snapshots "$T/snap" 2>&1)"; code=$?
  printf '%-34s expected=%s actual=%s\n' "$1" "$2" "$code"
  [ "$code" = "$2" ] || { fail=1; echo "$out"; }
  echo "$out" | grep -E '^(CHANGED|UNCHANGED|SKIP|ERROR|PENDING)' | cut -c1-90 | sed 's/^/    /'
}

run "baseline (無改変)" 0 "$FL_WIN64_DIR"
mk word 'd.replace(b"decompile, disassemble", b"decompiles, disassemble", 1)' 'd.replace(b"Cracked", b"Cracker", 1)'
run "1 語改変 (EULA/RTF とも)" 1 "$T/word"
mk eula_only 'd.replace(b"decompile, disassemble", b"decompiles, disassemble", 1)' 'd'
run "EULA.html のみ 1 語改変" 1 "$T/eula_only"
mk rtf_only 'd' 'd.replace(b"Cracked", b"Cracker", 1)'
run "RTF のみ 1 語改変" 1 "$T/rtf_only"
mk space 'd.replace(b"reverse \r\nengineer", b"reverse\n\n\t  engineer", 1)' 'd.replace(b" Applicability", b"   Applicability", 1)'
run "空白だけ改変 (偽陽性にならない)" 0 "$T/space"
run "素材 dir 無し (検証不能)" 3 "$T/nonexistent"

# Web 文書: 台帳側のハッシュを 1 文字だけ壊す (= 取得した本文が台帳と食い違う状況の再現)。ネットワークが要る (NC_WEB=0 で省略)
if [ "${NC_WEB:-1}" = 1 ]; then
  LEDGER="$REPO_ROOT/docs/LEGAL_TERMS_LEDGER.json"
  for id in fl-tou-web kilohearts-eula slate-audiotonix-terms ni-eula; do
    python3 - "$LEDGER" "$T/tampered_$id.json" "$id" <<'PY'
import json, sys
l = json.load(open(sys.argv[1])); c = l["docs"][sys.argv[3]]["current"]
c["sha256"] = ("0" if c["sha256"][0] != "0" else "1") + c["sha256"][1:]
json.dump(l, open(sys.argv[2], "w"))
PY
    out="$(node "$CLI" check --only "$id" --ledger "$T/tampered_$id.json" --md "$T/x.md" --no-write --snapshots "$T/snap" 2>&1)"; code=$?
    printf '%-34s expected=1 actual=%s\n' "台帳ハッシュ改変 $id" "$code"
    [ "$code" = 1 ] || { fail=1; echo "$out"; }
  done
  out="$(node "$CLI" check --only ni-eula --sources <(sed 's#https://www.native-instruments.com/pages/end-user-license-agreement#http://127.0.0.1:9/x#' "$REPO_ROOT/tools/legal/terms-watch/sources.json") --ledger "$LEDGER" --no-write 2>&1)"; code=$?
  printf '%-34s expected=3 actual=%s\n' "接続不能 (ni-eula)" "$code"
  [ "$code" = 3 ] || { fail=1; echo "$out"; }
fi
exit $fail
