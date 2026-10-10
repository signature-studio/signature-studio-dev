#!/usr/bin/env bash
# 配信後検証: workers.dev の実 URL に対し (1) 無認証は Access にリダイレクト (2) service token でヘッダ検査
# (3) tools/e2e の同一スイートを agent-browser で実行。URL は deploy/work/<WORKER_NAME>.url (20-worker.mjs が書く) か VERIFY_URL。
#   bash deploy/scripts/90-verify.sh [--no-e2e] [e2e の追加引数...]
# 追加の isolation 実測 (SAB / AudioWorklet / OPFS / 分割 wasm) は tools/e2e の suite 側 (他担当) か probe.sh を参照。
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
WORKER_NAME="${WORKER_NAME:-signature-studio}"
URL="${VERIFY_URL:-$(cat "$DEPLOY_DIR/work/$WORKER_NAME.url" 2>/dev/null || true)}"
[[ -n "$URL" ]] || { echo "URL 不明: 20-worker.mjs --phase open を先に実行するか VERIFY_URL を指定" >&2; exit 2; }
NO_E2E=0; [[ "${1:-}" == "--no-e2e" ]] && { NO_E2E=1; shift; }

SECRET="$DEPLOY_DIR/work/secrets/${ACCESS_SERVICE_TOKEN_NAME:-$WORKER_NAME-e2e}.json"
if [[ -z "${E2E_ACCESS_CLIENT_ID:-}" && -f "$SECRET" ]]; then
  E2E_ACCESS_CLIENT_ID="$(node -e 'console.log(JSON.parse(require("fs").readFileSync(process.argv[1],"utf8")).client_id)' "$SECRET")"
  E2E_ACCESS_CLIENT_SECRET="$(node -e 'console.log(JSON.parse(require("fs").readFileSync(process.argv[1],"utf8")).client_secret)' "$SECRET")"
  export E2E_ACCESS_CLIENT_ID E2E_ACCESS_CLIENT_SECRET
fi

step "無認証アクセス -> Access ログインへ 302 (反映遅延: 最大 90 秒ポーリング)"
code=000
for _ in $(seq 1 30); do
  code="$(curl -s -o /dev/null -w '%{http_code}' "$URL/")"
  [[ "$code" == 302 ]] && break
  sleep 3
done
echo "  GET $URL/ (token 無し) -> $code $(curl -s -o /dev/null -w '%{redirect_url}' "$URL/" | cut -c1-80)"
[[ "$code" == 302 ]] || { echo "NG: Access が掛かっていない (公開物が無保護)" >&2; exit 1; }
vp="$(curl -s -o /dev/null -w '%{http_code}' "https://deadbeef-${URL#https://}/")"
echo "  version preview URL 形式 -> $vp (302/404 が期待。200 は NG)"
[[ "$vp" != 200 ]] || { echo "NG: preview が素通し" >&2; exit 1; }

HDR=()
[[ -n "${E2E_ACCESS_CLIENT_ID:-}" ]] && HDR=(-H "CF-Access-Client-Id: $E2E_ACCESS_CLIENT_ID" -H "CF-Access-Client-Secret: $E2E_ACCESS_CLIENT_SECRET")

# release 直後は新 version の asset がエッジに行き渡るまで 404 / 旧 placeholder が混ざる (実測)。release.json の buildId が一致するまで待つ
WANT="$(node -e 'console.log(JSON.parse(require("fs").readFileSync(process.argv[1],"utf8")).buildId)' "$DEPLOY_DIR/work/site/release.json" 2>/dev/null || true)"
if [[ -n "$WANT" ]]; then
  step "release 反映待ち (buildId=$WANT, 最大 180 秒)"
  t0=$SECONDS; got=""
  for _ in $(seq 1 90); do
    got="$(curl -s "${HDR[@]}" "$URL/release.json" | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{console.log(JSON.parse(s).buildId)}catch{console.log("")}})')"
    [[ "$got" == "$WANT" ]] && break
    sleep 2
  done
  echo "  release.json buildId=$got ($((SECONDS-t0))s)"
  [[ "$got" == "$WANT" ]] || { echo "NG: 新 version が反映されない" >&2; exit 1; }
fi

step "ヘッダ確認 (service token) $URL/"
# _headers の反映は 30〜60 秒かかる (実測) -> COEP が付くまでポーリング
for _ in $(seq 1 40); do
  curl -sSI "${HDR[@]}" "$URL/" | grep -qi '^cross-origin-embedder-policy: require-corp' && break
  sleep 3
done
curl -sSI "${HDR[@]}" "$URL/" | grep -iE "^(HTTP|cross-origin|cache-control|content-type|content-encoding|cf-cache-status)" | tee "$DEPLOY_DIR/work/verify-headers.txt"
for h in cross-origin-opener-policy cross-origin-embedder-policy cross-origin-resource-policy; do
  grep -qi "^$h:" "$DEPLOY_DIR/work/verify-headers.txt" || { echo "NG: $h が無い" >&2; exit 1; }
done

[[ "$NO_E2E" == 1 ]] && { echo "ヘッダ検査 OK (E2E は省略)"; exit 0; }
step "E2E (agent-browser, 実 URL)"
exec bash "$REPO_ROOT/tools/e2e/run.sh" --url "$URL" "$@"
