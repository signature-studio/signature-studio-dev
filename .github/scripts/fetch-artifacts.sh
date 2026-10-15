#!/bin/bash
# fetch-artifacts.sh <artifacts_dir> — R2 の素材 s3://$R2_BUCKET/artifacts/<name>.tar.zst を取得する (#3976)。
#   - 1 素材あたり最大 3 回まで取得する。失敗・サイズ不一致のときは部分ファイルを消し、指数バックオフで再試行する。
#   - 取得の前に head-object で R2 側のサイズを得て、取得後のファイルサイズと突合する (終了コード 0 でも不一致なら失敗扱い)。
#   - head-object が 404 のときだけ「本当に無い」として missing に積み、再試行しない。
#   - 1 つでも取得できなければ exit 1。取得を続けるかどうかは呼び出し側 (agent-setup) が artifacts-required で決める。
# 入力 (環境変数): R2_BUCKET / CF_ACCOUNT_ID / R2_ARTIFACTS (空白区切りの prefix)。AWS_* は aws CLI が読む。
# FETCH_RETRY_BASE_SEC: 再試行の待ちの基準秒 (既定 5 → 5 秒・10 秒。テストでは 0)。
# 実行: bash .github/scripts/fetch-artifacts.sh <artifacts_dir>
set -uo pipefail

artifacts_dir="${1:?usage: fetch-artifacts.sh <artifacts_dir>}"
endpoint="https://${CF_ACCOUNT_ID:-}.r2.cloudflarestorage.com"
max_attempts=3
base_sec="${FETCH_RETRY_BASE_SEC:-5}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
missing=""
failed=0

# fetch_one <key> <dest>: 0 = 取得成功 / 1 = R2 に無い (404, 再試行なし) / 2 = 再試行を使い切った
fetch_one() {
  local key="$1" dest="$2" attempt=1 expected actual wait_s last_err=""
  local err="$work/err"
  while [ "$attempt" -le "$max_attempts" ]; do
    if expected="$(aws s3api head-object --bucket "$R2_BUCKET" --key "$key" --endpoint-url "$endpoint" \
      --query ContentLength --output text 2>"$err")"; then
      rm -f "$dest"
      if aws s3 cp "s3://${R2_BUCKET}/$key" "$dest" --endpoint-url "$endpoint" --only-show-errors 2>"$err"; then
        actual="$(stat -c %s "$dest" 2>/dev/null || echo 0)"
        if [ "$actual" = "$expected" ]; then
          [ "$attempt" -gt 1 ] && echo "::notice::fetched $key after $attempt attempts"
          return 0
        fi
        last_err="size mismatch: got $actual bytes, R2 has $expected bytes"
      else
        last_err="$(tail -n 1 "$err")"
      fi
    else
      if grep -qE '\(404\)|Not Found|NoSuchKey' "$err"; then
        return 1
      fi
      last_err="$(tail -n 1 "$err")"
    fi
    rm -f "$dest"
    if [ "$attempt" -lt "$max_attempts" ]; then
      wait_s=$((base_sec * (1 << (attempt - 1))))
      echo "retry $attempt/$max_attempts for $key in ${wait_s}s: $last_err"
      sleep "$wait_s"
    fi
    attempt=$((attempt + 1))
  done
  echo "::error::download failed after $max_attempts attempts: $key (${last_err:-unknown error})"
  return 2
}

mkdir -p "$artifacts_dir"
# 命名は <prefix>.tar.zst で固定。--recursive の prefix 指定だと fl-win64 が
# fl-win64-anything.tar.zst も拾うため、オブジェクトを明示して取得する。
for name in ${R2_ARTIFACTS:-}; do
  # apt-* は R2 の素材ではない (後段で apt から入れる)
  case "$name" in apt-*) continue ;; esac
  key="artifacts/${name}.tar.zst"
  fetch_one "$key" "$artifacts_dir/${name}.tar.zst"
  case $? in
    0) echo "fetched $key" ;;
    1) missing="$missing $key" ;;
    *) failed=1 ;;
  esac
done

if [ -n "$missing" ]; then
  # 何がバケットに実在するかを一緒に出して、認証エラーと「空/命名違い」を
  # 切り分けられるようにする。
  echo "::error::missing R2 object(s) in s3://${R2_BUCKET}:$missing"
  echo "::error::objects actually present under artifacts/ (first 20):"
  aws s3 ls "s3://${R2_BUCKET}/artifacts/" --endpoint-url "$endpoint" 2>&1 | head -20 || true
  failed=1
fi
exit "$failed"
