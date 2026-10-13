#!/usr/bin/env bash
# AU-3 (#188) MIDI shim の 1 コマンド e2e: 型検査 → emcc ビルド → headless Chrome (本番 + ネガコン 2 + Worker 内 Web MIDI 実測)。exit 0 = 全 PASS
#   bash tools/audio/e2e_midi.sh
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(cd -- "$HERE/../.." && pwd)"
command -v node >/dev/null || { echo "node not found" >&2; exit 1; }
"$ROOT/node_modules/.bin/tsc" --noEmit -p "$ROOT/tsconfig.json"
bash "$HERE/build.sh"
node "$HERE/harness/midi_run.mjs" --out "$HERE/results/midi_results.json"
