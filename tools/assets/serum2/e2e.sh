#!/usr/bin/env bash
# Serum 2 コンテンツ配信 (#70) 1 コマンド e2e (pass 1 本 + ネガコン 3 本)。不合格は exit 1。
#   SERUM2_INSTALLER=<Install_Xfer_Serum2_2.1.5.exe> EMSDK_ENV=<emsdk_env.sh> bash tools/assets/serum2/e2e.sh
#   (展開済みなら SERUM2_EXTRACTED=<7z x の出力 dir>)
# 手順: 7z 展開 -> inventory (期待値と不一致なら exit 2) -> pack -> libFLAC wasm ビルド -> libsndfile 参照 -> e2e (pass 1 + neg 3)
# ネガコン判定: pass は exit 0 かつ failures=0。neg-* は exit 1 かつ failures が下表の値ちょうど (0 件や過大も不合格)。
set -euo pipefail
cd "$(dirname "$0")"
A="$(pwd)/.."
W="$(pwd)/work"; mkdir -p "$W"
export TMPDIR="${TMPDIR:-${RUNNER_TEMP:-$W}}"
BASE="${SERUM2_WORK:-$W/run}"; mkdir -p "$BASE"
EX="${SERUM2_EXTRACTED:-}"
if [[ -z "$EX" ]]; then
  : "${SERUM2_INSTALLER:?SERUM2_INSTALLER か SERUM2_EXTRACTED を指定}"
  EX="$BASE/x"
  [[ -d "$EX/Multisamples" ]] || { rm -rf "$EX"; 7z x -y -o"$EX" "$SERUM2_INSTALLER" >"$BASE/7z.log" 2>&1; grep -q 'Everything is Ok' "$BASE/7z.log"; }
fi
PY="${SERUM2_PY:-$BASE/venv/bin/python}"
if [[ ! -x "$PY" ]]; then uv venv -q "$BASE/venv"; uv pip install -q --python "$BASE/venv/bin/python" soundfile numpy; fi

t=$(date +%s)
node make-inventory.mjs "$EX" "$BASE/inv"
rm -rf "$BASE/pkg"
node "$A/pack/pack.ts" --inv "$BASE/inv/inv.jsonl" --tiers "$BASE/inv/tiers.json" --out "$BASE/pkg" --name serum2-2.1.5-content --quality 9 --concurrency 4 | tail -1
[[ -f "$W/flacdec.wasm" ]] || bash flac/build.sh
[[ -f "$BASE/ref-flac.json" ]] || "$PY" ref-flac.py "$EX" "$BASE/ref-flac.json" --jobs 4
echo "[prep] $(( $(date +%s) - t )) s  load $(cut -d' ' -f1-3 /proc/loadavg)"

run() { # mode -> exit code
  local rc=0
  node serum2-e2e.ts --pkg "$BASE/pkg" --src "$EX" --ref "$BASE/ref-flac.json" --wasm "$W/flacdec.wasm" --mode "$1" --out "$BASE/result-$1.json" >"$BASE/e2e-$1.log" 2>&1 || rc=$?
  echo "$rc"
}
fails() { node -e "console.log(JSON.parse(require('fs').readFileSync('$BASE/result-$1.json','utf8')).failures)"; }
bad=0
# mode:期待 failures
for spec in pass:0 neg-flac:1 neg-ref:1 neg-chunk:1; do
  m=${spec%%:*}; want=${spec##*:}
  t=$(date +%s); rc=$(run "$m"); dt=$(( $(date +%s) - t ))
  got=$(fails "$m" 2>/dev/null || echo NA)
  if [[ "$m" == pass ]]; then okc=$([[ $rc == 0 && $got == 0 ]] && echo 1 || echo 0); else okc=$([[ $rc == 1 && $got == "$want" ]] && echo 1 || echo 0); fi
  echo "[$m] exit=$rc failures=$got (期待 exit=$([[ $m == pass ]] && echo 0 || echo 1) failures=$want) ${dt}s load $(cut -d' ' -f1-3 /proc/loadavg) => $([[ $okc == 1 ]] && echo OK || echo NG)"
  [[ $okc == 1 ]] || { bad=1; tail -15 "$BASE/e2e-$m.log"; }
done
[[ $bad == 0 ]] && echo "SERUM2 E2E OK" || { echo "SERUM2 E2E NG"; exit 1; }
