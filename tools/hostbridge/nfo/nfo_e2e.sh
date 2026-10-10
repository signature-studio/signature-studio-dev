#!/usr/bin/env bash
# One-command verification for tools/hostbridge/nfo (H9 / CAB-98):
#   typecheck -> browser-safety grep -> unit/corpus tests -> measured metrics -> synthetic DB generation (+ reader-model acceptance).
# env: FL_ROOT (mac FL Resources/FL; default analysis/mac extract), REGEN_EVIDENCE=1 (re-run Ghidra extraction; ~1 min, needs tools/m2/work/ghidra_dll)
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.local/share/pnpm/bin:$HOME/.bun/bin:$PATH"
command -v node >/dev/null || { echo "node not found"; exit 2; }
mkdir -p work
fail=0
step() { echo; echo "== $*"; }

step "typecheck"; ../../../node_modules/.bin/tsc -p tsconfig.json
step "browser-safety (src/ must not import node: modules)"
if grep -rn "from 'node:" src/; then echo "FAIL: node import in src/"; fail=1; else echo "ok"; fi
step "unit + corpus tests"; node --test test/ 2>&1 | grep -E "^ℹ (tests|pass|fail|skipped)|^✖" || true
node --test test/ >/dev/null 2>&1 || { echo "FAIL: tests"; fail=1; }
step "metrics (shipped corpus + generator)"; node cli/metrics.ts work/metrics.json | grep -E '"(nfoFilesTotal|nfoRoundTripExact|nativePluginNfo|fst1155Files|fst1155ReproducedExact|generatedEntries|generatedFiles|readerAccepted)"'
step "generate synthetic DB for the wasm plugin set"
KH=../../targets/kilohearts/work/macpkg/product_index.json
rm -rf work/gen_out
node cli/gen.ts specs/wasm_plugins.json work/gen_out ${KH:+--kilohearts "$KH"}
echo "-- Installed/Effects/VST/OTT.nfo"; cat work/gen_out/Installed/Effects/VST/OTT.nfo
if [ "${REGEN_EVIDENCE:-0}" = 1 ]; then step "regenerate evidence"; bash analysis/reproduce.sh; fi
node -e '
const m=JSON.parse(require("fs").readFileSync("work/metrics.json","utf8"));
const ok=(!m.haveFl)||(m.nfoRoundTripExact===m.nfoFilesTotal-m.nfoNonAscii&&m.fst1155ReproducedExact===m.fst1155Files);
console.log("\nSUMMARY nfo round-trip",m.nfoRoundTripExact+"/"+m.nfoFilesTotal,"| fst(11.5.5) rebuilt byte-exact",m.fst1155ReproducedExact+"/"+m.fst1155Files,"| generated entries",m.generatedEntries,"accepted by reader model",m.readerAccepted);
if(!ok||m.readerAccepted!==m.generatedEntries) process.exit(1);
'
exit $fail
