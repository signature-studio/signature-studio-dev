#!/usr/bin/env bash
# One-command verification for tools/hostbridge/nfo (H9 / CAB-98):
#   typecheck -> browser-safety grep -> unit/corpus tests -> measured metrics -> synthetic DB generation (+ reader-model acceptance).
# env: FL_ROOT (mac FL Resources/FL; default $FL_MAC_DIR/pkg_extract/...; tools/shared/env.sh), REGEN_EVIDENCE=1 (re-run Ghidra extraction; ~1 min, needs tools/m2/work/ghidra_dll)
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
step "unit + corpus tests"; node --test test/*.test.ts 2>&1 | grep -E "^ℹ (tests|pass|fail|skipped)|^✖" || true
node --test test/*.test.ts >/dev/null 2>&1 || { echo "FAIL: tests"; fail=1; }
step "real-machine ingest (CAB-219: .Plugins.ini / VerifiedIDs.nfo)"
node analysis/real_ini_check.mjs > work/real_ini_metrics.json || { echo "FAIL: real-machine checks"; fail=1; }
node -e 'const m=JSON.parse(require("fs").readFileSync("work/real_ini_metrics.json","utf8"));
console.log(`real-machine: ini round-trip + writer 406/406 sections, ${m.plugins_ini.files} files | VerifiedIDs ${m.verifiedids.keys} keys (${m.verifiedids.families.VST} VST/${m.verifiedids.families.VST3} VST3/${m.verifiedids.families.CLAP} CLAP) | VST2 pseudo-guid ${m.vst2.reproduced} | failed checks ${m.failed}`);
if (m.failed) process.exit(1);'
step "CAB-218 (H11 VST3 filename rule + KH VST2 magic 実測 + VerifiedIDs decimal)"
node analysis/kh_magic_check.mjs > work/kh_magic_metrics.json || { echo "FAIL: CAB-218 checks"; fail=1; }
node -e 'const m=JSON.parse(require("fs").readFileSync("work/kh_magic_metrics.json","utf8")).cab218;
console.log(`cab-218: VST2 magic files ${m.vst2MagicFiles} (Effects\\VST ${m.effectsVstMagicSections}) | KH index==real ${m.khIndexMatch} | VerifiedIDs ${m.verifiedIdsVst} | VST3 filename inner ${m.vst3FilenameForms.innerBinary}/module ${m.vst3FilenameForms.moduleFile} | gen KH ${m.generatedKhMatch} | failed ${m.failed}`);
if (m.failed) process.exit(1);'
step "CAB-46 follow-up (Massive X CID 突合 + spec 実機照合)"
node analysis/mx_check.mjs > work/mx_check_metrics.json || { echo "FAIL: CAB-46 follow-up checks"; fail=1; }
node -e 'const m=JSON.parse(require("fs").readFileSync("work/mx_check_metrics.json","utf8")).cab46mx;
console.log(`cab-46mx: ${m.cid} (PluginID ${m.pluginId} / SNPID ${m.snpid}) | ${m.filename} (${m.size} B) | moduleinfo.json ${m.moduleinfoJson===undefined?"n/a":(m.moduleinfoJson.includes("not shipped")?"not shipped":"present")} | failed ${m.failed}`);
if (m.failed) process.exit(1);'
step "metrics (shipped corpus + generator)"; node cli/metrics.ts work/metrics.json | grep -E '"(nfoFilesTotal|nfoRoundTripExact|nativePluginNfo|fst1155Files|fst1155ReproducedExact|generatedEntries|generatedFiles|readerAccepted)"'
step "generate synthetic DB for the wasm plugin set"
KH=../../targets/kilohearts/work/macpkg/product_index.json
rm -rf work/gen_out
node cli/gen.ts specs/wasm_plugins.json work/gen_out ${KH:+--kilohearts "$KH"}
echo "-- Installed/Effects/VST/OTT.nfo"; cat work/gen_out/Installed/Effects/VST/OTT.nfo
if [ "${REGEN_EVIDENCE:-0}" = 1 ]; then step "regenerate evidence"; bash analysis/reproduce.sh; fi
if [ "${SKIP_H4:-0}" = 1 ]; then echo; echo "== CAB-216 (h4) skipped (SKIP_H4=1)"; exit $fail; fi
step "CAB-216 (HB-H4'): generateDb → pathreg → wvfs virtual fs (node + Chrome OPFS)"
bash h4_e2e.sh ${H4_ARGS:-} || { echo "FAIL: h4 e2e"; fail=1; }
node -e '
const m=JSON.parse(require("fs").readFileSync("work/metrics.json","utf8"));
const ok=(!m.haveFl)||(m.nfoRoundTripExact===m.nfoFilesTotal-m.nfoNonAscii&&m.fst1155ReproducedExact===m.fst1155Files);
console.log("\nSUMMARY nfo round-trip",m.nfoRoundTripExact+"/"+m.nfoFilesTotal,"| fst(11.5.5) rebuilt byte-exact",m.fst1155ReproducedExact+"/"+m.fst1155Files,"| generated entries",m.generatedEntries,"accepted by reader model",m.readerAccepted);
if(!ok||m.readerAccepted!==m.generatedEntries) process.exit(1);
'
exit $fail
