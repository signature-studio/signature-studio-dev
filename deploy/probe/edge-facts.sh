#!/usr/bin/env bash
# Static Assets の実エッジ挙動を curl で採取 (tools/e2e edge-sim 調整用。docs/EDGE-SIM.md の根拠)。
#   bash deploy/probe/edge-facts.sh <url> [token.json]
set -uo pipefail
URL="${1:?url}"; TOK="${2:-}"
H=()
[[ -n "$TOK" ]] && H=(-H "CF-Access-Client-Id: $(node -e 'console.log(JSON.parse(require("fs").readFileSync(process.argv[1])).client_id)' "$TOK")" -H "CF-Access-Client-Secret: $(node -e 'console.log(JSON.parse(require("fs").readFileSync(process.argv[1])).client_secret)' "$TOK")")
req() { # label, curl args...
  local label="$1"; shift
  printf '%-34s ' "$label"
  curl -s -o /dev/null -D - "${H[@]}" "$@" | tr -d '\r' | awk 'NR==1{printf "%s |",$2} tolower($1) ~ /^(content-type|content-encoding|content-length|cache-control|location|cross-origin-embedder-policy|accept-ranges|content-range|etag):/ {printf " %s", $0} END{print ""}' | cut -c1-260
}
KEY="$(node -e 'const r=JSON.parse(require("fs").readFileSync(process.argv[1]));console.log(Object.keys(r.chunked)[0]??"")' "$(dirname "$0")/../work/site/release.json")"
PART="$(node -e 'const d=JSON.parse(require("fs").readFileSync(process.argv[1]));console.log(d.parts[0].name)' "$(dirname "$0")/../work/site/${KEY}.parts/index.json")"
SMALL="$(cd "$(dirname "$0")/../work/site/wasm" && ls | grep '^probe-small' | head -1)"
req "GET /"                           "$URL/"
req "GET /index.html (307?)"          "$URL/index.html"
req "GET /release.json"               "$URL/release.json"
req "GET small wasm (br/zstd/gzip)"   -H 'Accept-Encoding: br, zstd, gzip' "$URL/wasm/$SMALL"
req "GET small wasm (identity)"       -H 'Accept-Encoding: identity' "$URL/wasm/$SMALL"
req "GET part (Range: bytes=0-99)"    -H 'Range: bytes=0-99' "$URL/${KEY}.parts/${PART}"
req "GET part (no Range)"             "$URL/${KEY}.parts/${PART}"
req "HEAD part"                       -I "$URL/${KEY}.parts/${PART}"
req "GET descriptor index.json"       "$URL/${KEY}.parts/index.json"
req "GET /__probe__/ce/hello.br"      "$URL/__probe__/ce/hello.br"
req "GET hello.br AE=br,zstd,gzip"    -H 'Accept-Encoding: br, zstd, gzip' "$URL/__probe__/ce/hello.br"
req "GET hello.br AE=identity"        -H 'Accept-Encoding: identity' "$URL/__probe__/ce/hello.br"
req "GET ct/a.html (_headers CT)"     "$URL/__probe__/ct/a.html"
req "GET ct/a.js   (_headers CT)"     "$URL/__probe__/ct/a.js"
req "GET ct/a.css  (_headers CT)"     "$URL/__probe__/ct/a.css"
req "GET /__probe__/worker.js (JS)"   -H 'Accept-Encoding: br, zstd, gzip' "$URL/__probe__/worker.js"
req "GET /nope (404)"                 "$URL/nope-$RANDOM"
req "GET If-None-Match (304?)"        -H "If-None-Match: $(curl -s -D - -o /dev/null "${H[@]}" "$URL/release.json" | tr -d '\r' | awk 'tolower($1)=="etag:"{print $2}')" "$URL/release.json"
echo "-- hello.br body (identity): $(curl -s "${H[@]}" -H 'Accept-Encoding: identity' "$URL/__probe__/ce/hello.br" | wc -c) bytes, sha256=$(curl -s "${H[@]}" -H 'Accept-Encoding: identity' "$URL/__probe__/ce/hello.br" | sha256sum | cut -c1-16) / AE=br: $(curl -s "${H[@]}" -H 'Accept-Encoding: br' "$URL/__probe__/ce/hello.br" | wc -c) bytes"
