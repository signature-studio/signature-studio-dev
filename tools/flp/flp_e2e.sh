#!/usr/bin/env bash
# One-command verification for tools/flp: typecheck -> unit/corpus tests -> corpus round trip (level 0+1)
# -> manifests/census/plugin ranking -> win-vs-mac check -> PyFLP cross-check (if its venv exists).
# env: FL_ROOT (default mac .app Resources/FL), WIN_ROOT (default analysis/win64), SETUP_PYFLP=1 builds the py3.10 venv for the cross-check,
#      E2E_FLP_WIN_DIR=<fl-win64.tar.zst の extracted/> (or FL_ROOT) enables the browser e2e (tools/e2e suite flp); BROWSER_E2E=0 disables it,
#      REGEN_IDS=1 re-derives engine_event_ids.json from FLEngine_x64.dll (needs pefile) and src/id_sets.ts (needs the PyFLP venv).
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.local/share/pnpm/bin:$PATH"
command -v node >/dev/null || { echo "node not found"; exit 2; }
mkdir -p corpus work
fail=0
step() { echo; echo "== $*"; }

step "typecheck"; ../../node_modules/.bin/tsc -p tsconfig.json
step "browser-safety (src/ must not import node: modules)"
if grep -rn "from 'node:" src/; then echo "FAIL: node import in src/"; fail=1; else echo "ok"; fi
step "browser-safety (web/ harness must not import node: modules)"
if grep -rn "from 'node:" web/; then echo "FAIL: node import in web/"; fail=1; else echo "ok"; fi
step "unit + corpus tests"; node --test test/ 2>&1 | grep -E "^ℹ (tests|pass|fail)"
step "round trip (level 0 container, level 1 typed)"; node cli/roundtrip.ts corpus/roundtrip.json | head -12
step "manifest / census / plugins"; node cli/corpus.ts 2>/dev/null
step "win installer vs mac corpus"; node cli/winmac.ts corpus/winmac.json
if [ "${SETUP_PYFLP:-0}" = 1 ] && [ ! -x work/venv310/bin/python ]; then
  command -v uv >/dev/null && uv venv --python 3.10 work/venv310 && uv pip install --python work/venv310/bin/python pyflp
fi
if [ -x work/venv310/bin/python ]; then
  step "PyFLP 2.2.1 cross-check (py3.10)"; work/venv310/bin/python scripts/crosscheck_pyflp.py
else echo "(skip PyFLP cross-check: run with SETUP_PYFLP=1)"; fi
if [ "${REGEN_IDS:-0}" = 1 ]; then
  step "regenerate id sets"; python3 scripts/engine_event_ids.py
  [ -x work/venv310/bin/python ] && work/venv310/bin/python scripts/gen_id_sets.py
fi
if [ "${BROWSER_E2E:-1}" = 1 ]; then
  if [ -n "${E2E_FLP_WIN_DIR:-}" ] || [ -n "${FL_ROOT:-}" ]; then
    step "browser e2e (agent-browser: parse/dump/round trip in Chrome via file input + drop)"
    E2E_REQUIRE_FLP=1 bash ../e2e/run.sh --suite flp || fail=1
  else echo "(skip browser e2e: set E2E_FLP_WIN_DIR=<fl-win64 extracted/> or FL_ROOT)"; fi
fi
node -e '
const r=JSON.parse(require("fs").readFileSync("corpus/roundtrip.json","utf8"));
console.log("\nSUMMARY level0",r.level0.ok+"/"+r.total,"level1",r.level1.ok+"/"+r.total,"events",r.totalEvents);
if(r.level0.ok!==r.total||r.level1.ok!==r.total) process.exit(1);
'
exit $fail
