#!/usr/bin/env bash
# ci.sh (週次 workflow の本体) のネガティブコントロール。期待と違う exit があれば exit 1。Web 4 文書の取得でネットワークが要る。
#   bash tools/legal/terms-watch/negative_control_ci.sh
set -uo pipefail
ROOT="$(git rev-parse --show-toplevel)"
CI="$ROOT/tools/legal/terms-watch/ci.sh"
T="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/tw-negci.XXXXXX")"
trap 'rm -rf "$T"' EXIT
fail=0
case_() { # case_ <name> <expected-exit> <env...> -- <ci.sh args...>
  local name="$1" want="$2"; shift 2
  local envs=(); while [ "${1:-}" != "--" ]; do envs+=("$1"); shift; done; shift
  env "${envs[@]}" TW_OUT="$T/out_$RANDOM" bash "$CI" "$@" >"$T/log" 2>&1; local got=$?
  printf '%-52s expected=%s actual=%s\n' "$name" "$want" "$got"
  [ "$got" = "$want" ] || { fail=1; tail -n 8 "$T/log"; }
}

case_ "無改変 (4 件 UNCHANGED)" 0 X=1 --
for id in fl-tou-web kilohearts-eula slate-audiotonix-terms ni-eula; do
  case_ "台帳ハッシュ 1 文字改変: $id" 1 X=1 -- --tamper "$id"
done

# 取得失敗 (接続不能 URL) → 3
sed 's#https://www.native-instruments.com/pages/end-user-license-agreement#http://127.0.0.1:9/x#' "$ROOT/tools/legal/terms-watch/sources.json" > "$T/sources_dead.json"
case_ "接続不能 URL (ni-eula)" 3 TW_SOURCES="$T/sources_dead.json" --

# exit 0 でも UNCHANGED でない: 台帳から 1 文書を除く → cli は NEW (exit 0) → ci.sh が 4 で落とす
node -e '
  const fs = require("fs"); const l = JSON.parse(fs.readFileSync(process.argv[1], "utf8")); delete l.docs["ni-eula"];
  fs.writeFileSync(process.argv[2], JSON.stringify(l));
' "$ROOT/docs/LEGAL_TERMS_LEDGER.json" "$T/ledger_missing.json"
case_ "台帳に無い文書 (NEW で exit 0 → 4 で落とす)" 4 TW_LEDGER="$T/ledger_missing.json" --

case_ "引数不正" 2 X=1 -- --bogus
exit $fail
