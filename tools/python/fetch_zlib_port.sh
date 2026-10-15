#!/usr/bin/env bash
# emcc の -sUSE_ZLIB port (zlib 1.3.2) を emsdk の port キャッシュへ用意する (PY-298, #4082)。
# emcc は https://github.com/madler/zlib/archive/refs/tags/v1.3.2.tar.gz を取りに行くが、この URL が 404 になると
# build_flpy.sh が止まる。ここでは同じ tarball を次の順で取り、emsdk の pin (sha512) と照合してから
# emcc と同じ形 (cache/ports/zlib.tar.gz + cache/ports/zlib/ + .emscripten_url marker) に展開する。
#   1) 公式 tag URL  2) codeload.github.com の同一 tarball (tag 版・同じ内容)
# 不一致・全失敗は非 0 で止まる (手作業のキャッシュ配置はしない)。
# 使い方: EMSDK_DIR=/opt/emsdk bash tools/python/fetch_zlib_port.sh   (build_flpy.sh から source される)
# 環境変数: EM_CACHE (既定 $EMSDK_DIR/upstream/emscripten/cache) / ZLIB_TAG_URL (テスト用の上書き)
set -euo pipefail
EMSDK_DIR="${EMSDK_DIR:-/opt/emsdk}"
EM_CACHE="${EM_CACHE:-$EMSDK_DIR/upstream/emscripten/cache}"
ZLIB_VER=1.3.2
ZLIB_SHA512="${ZLIB_SHA512:-16fea4df307a68cf0035858abe2fd550250618a97590e202037acd18a666f57afc10f8836cbbd472d54a0e76539d0e558cb26f059d53de52ff90634bbf4f47d4}"
TAG_URL="${ZLIB_TAG_URL:-https://github.com/madler/zlib/archive/refs/tags/v${ZLIB_VER}.tar.gz}"
CODELOAD_URL="${ZLIB_CODELOAD_URL:-https://codeload.github.com/madler/zlib/tar.gz/refs/tags/v${ZLIB_VER}}"
PORTS="$EM_CACHE/ports"
DEST="$PORTS/zlib"
TARBALL="$PORTS/zlib.tar.gz"
MARKER_URL="$TAG_URL"

if [ -f "$DEST/.emscripten_url" ] && [ "$(tr -d '\n' < "$DEST/.emscripten_url")" = "$MARKER_URL" ]; then
  echo "fetch_zlib_port: キャッシュ済み ($DEST)"
  exit 0
fi

mkdir -p "$PORTS"
TMP="$(mktemp -d "$PORTS/zlib-fetch.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

fetched=""
for url in "$TAG_URL" "$CODELOAD_URL"; do
  if curl -sSfL --retry 2 -o "$TMP/zlib.tar.gz" "$url" 2>"$TMP/curl.err"; then
    fetched="$url"; break
  fi
  echo "fetch_zlib_port: 取得失敗 ($url): $(tail -1 "$TMP/curl.err")" >&2
done
[ -n "$fetched" ] || { echo "fetch_zlib_port: ERROR: zlib $ZLIB_VER を取得できない" >&2; exit 1; }

actual="$(sha512sum "$TMP/zlib.tar.gz" | cut -d' ' -f1)"
if [ "$actual" != "$ZLIB_SHA512" ]; then
  echo "fetch_zlib_port: ERROR: sha512 不一致 (取得元 $fetched): $actual" >&2
  exit 1
fi
echo "fetch_zlib_port: sha512 一致 (取得元 $fetched)"

mv "$TMP/zlib.tar.gz" "$TARBALL"
UNPACK="$DEST.tmp"
rm -rf "$UNPACK"; mkdir -p "$UNPACK"
tar -xzf "$TARBALL" -C "$UNPACK"
printf '%s\n' "$MARKER_URL" > "$UNPACK/.emscripten_url"
rm -rf "$DEST"
mv "$UNPACK" "$DEST"
echo "fetch_zlib_port: 展開済み ($DEST)"
