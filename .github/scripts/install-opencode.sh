#!/bin/bash
# install-opencode.sh — opencode CLI を pin したバージョンでインストールする。
#
# なぜ作り直したか:
#   旧実装は `curl -fsSL https://opencode.ai/v2/install | bash` を 3 回回すだけだった。
#   公式インストーラはバージョン未指定だと
#     https://opencode.ai/update/api/latest/cli/npm
#   を叩いてバージョンを解決するが、この metadata API が transient に 500 を返すと
#   「Failed to fetch version information」で即死する。外側の curl --retry は
#   インストーラ内部のこの 1 リクエストに効かない。さらに旧ループの待ち時間は 0 秒
#   だったので 3 回の試行が 1.28 秒で潰え、workflow は一度も完走していない。
#
# 取得元 (第一候補 = GitHub Releases の tarball 直接取得):
#   anomalyco/opencode の release asset を直接ダウンロードする。metadata API を
#   一切経由しないので、500 の影響を受けない。
#
#   なお `anomalyco/opencode-beta` は Releases に CLI 資産を持たない
#   (2026-10-12 時点、公開済 release はすべて opencode-desktop-* と
#   electron-updater のメタデータのみ・最新 tag は v0.0.0-beta-19723 で CLI 版より
#   古い)。そのため beta リポジトリは取得元として使わない。
#
#   注意: Releases 系統と npm 系統はバージョントラックが異なる。
#     Releases: v1.19.0 まで (1.x 系)
#     npm:      2.0.26 (2.x 系 / @opencode/cli-<target>)
#   よって pin は 2 本持つ (OPENCODE_RELEASE_VERSION / OPENCODE_VERSION)。
#
# 検証は、最後に `opencode --version` を実際に実行して
# 「 whichever 経路が勝ったかに応じた期待値」と一致することを確認してから exit 0。
#
# 注意: 「sleep による 10 秒以上の待機禁止」は opencode エージェント (opencode run)
# 向けの規約で、CI のセットアップ step には適用されない。ここでは待避を優先する。
set -euo pipefail

# デフォルトの pin (2026-10-12 実測)。
# - Releases tag v1.19.0 / asset opencode-linux-x64.tar.gz の SHA-256
# - npm @opencode/cli-linux-x64@2.0.26
DEFAULT_RELEASE_VERSION="v1.19.0"
DEFAULT_NPM_VERSION="2.0.26"

RELEASE_REPO="${OPENCODE_RELEASE_REPO:-anomalyco/opencode}"
RELEASE_VERSION="${OPENCODE_RELEASE_VERSION:-$DEFAULT_RELEASE_VERSION}"
NPM_VERSION="${OPENCODE_VERSION:-${OPENCODE_CLI_VERSION:-$DEFAULT_NPM_VERSION}}"
SOURCE="${OPENCODE_INSTALL_SOURCE:-auto}" # auto | releases | npm
INSTALL_DIR="${OPENCODE_INSTALL_DIR:-$HOME/.opencode/bin}"
ATTEMPTS="${OPENCODE_INSTALL_ATTEMPTS:-3}"
# 空なら SHA-256 検証を省略する。設定すると改ざん検出になるが、release 資産を
# 再アップロードすると壊れるので既定は空。埋める場合は releases API の digest 欄の値。
RELEASE_SHA256="${OPENCODE_RELEASE_SHA256:-}"

RELEASE_VERSION="${RELEASE_VERSION#v}"

log() { printf '%s\n' "$*"; }
warn() { printf '::warning::%s\n' "$*"; }
err() { printf '::error::%s\n' "$*"; }

# 一時ディレクトリは RUNNER_TEMP (runner 上の作業領域) に作る。
# /tmp は小さい・共有され得る الحجمなので、200MB 弱の tarball 展開には使わない。
SCRATCH="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
new_tmpdir() { mktemp -d "$SCRATCH/oc-install.XXXXXXXX"; }

# --- OS/arch → opencode の配布ターゲット名 ----------------------------------
# 公式インストーラの判定に揃える (musl / AVX2 非対応は -musl / -baseline)。
# ここをずらすと存在しないパッケージ名を引いて取得に失敗する。
detect_target() {
  local os arch is_musl=false needs_baseline=false
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  case "$os" in
    linux) ;;
    darwin) ;;
    *) err "unsupported OS: $(uname -s)"; return 1 ;;
  esac
  arch="$(uname -m)"
  case "$arch" in
    x86_64 | amd64) arch="x64" ;;
    aarch64 | arm64) arch="arm64" ;;
    *) err "unsupported architecture: $(uname -m)"; return 1 ;;
  esac

  if [ "$os" = linux ]; then
    [ -f /etc/alpine-release ] && is_musl=true
    if command -v ldd >/dev/null 2>&1 && ldd --version 2>&1 | grep -qi musl; then
      is_musl=true
    fi
  fi

  # x64 かつ AVX2 非対応 (grep 失敗も「非対応」とみなす) なら baseline ビルドを要求する
  if [ "$arch" = x64 ]; then
    if [ "$os" = linux ]; then
      grep -qwi avx2 /proc/cpuinfo 2>/dev/null || needs_baseline=true
    fi
  fi

  local suffix=""
  [ "$needs_baseline" = false ] || suffix="baseline"
  [ "$is_musl" = false ] || suffix="${suffix:+$suffix-}musl"

  # arm64 には baseline ビルドが存在しない
  if [ -n "$suffix" ] && [ "$arch" = arm64 ]; then
    suffix="${suffix%-baseline}"
  fi
  printf '%s-%s%s' "$os" "$arch" "$suffix"
}

TARGET="${OPENCODE_TARGET:-}"
if [ -z "$TARGET" ]; then
  TARGET="$(detect_target)" || exit 1
fi

mkdir -p "$INSTALL_DIR"

# `opencode --version` は取得元により書式が不同 (Releases は "1.19.0"、
# npm は "opencode v2.0.26")。末尾フィールドを取り、先頭の v を落として正規化する。
installed_version() {
  "$INSTALL_DIR/opencode" --version 2>/dev/null | awk '{print $NF}' | sed 's/^v//'
}
matches() { [ "$(installed_version || true)" = "$1" ]; }

verify_sha256() {
  local file="$1" expected="$2" actual
  [ -n "$expected" ] || return 0
  actual="$(sha256sum "$file" | cut -d' ' -f1)"
  if [ "$actual" != "$expected" ]; then
    err "sha256 mismatch for $file: expected $expected, got $actual"
    return 1
  fi
  log "sha256 verified: $actual"
}

# --- 経路 1: GitHub Releases の tarball を直接取得 --------------------------
# 第一候補。metadata API を経由しないので transient 500 の影響を受けない。
install_via_github_release() {
  local url tmpdir ext="tar.gz" src
  case "$TARGET" in
    darwin-*) ext="zip" ;;
  esac
  url="https://github.com/$RELEASE_REPO/releases/download/v$RELEASE_VERSION/opencode-$TARGET.$ext"

  tmpdir="$(new_tmpdir)"
  if ! curl -fsSL --retry 3 --retry-delay 3 --max-time 900 -o "$tmpdir/oc.$ext" "$url"; then
    rm -rf "$tmpdir"
    return 1
  fi
  if ! verify_sha256 "$tmpdir/oc.$ext" "$RELEASE_SHA256"; then
    rm -rf "$tmpdir"
    return 1
  fi

  if [ "$ext" = zip ]; then
    command -v unzip >/dev/null 2>&1 || { err "unzip is required for $TARGET"; rm -rf "$tmpdir"; return 1; }
    mkdir -p "$tmpdir/out"
    unzip -qo "$tmpdir/oc.$ext" -d "$tmpdir/out" || { rm -rf "$tmpdir"; return 1; }
    src="$tmpdir/out/opencode"
  else
    # tarball のルートには opencode バイナリ 1 個だけが入る。
    tar -xzf "$tmpdir/oc.$ext" -C "$tmpdir" || { rm -rf "$tmpdir"; return 1; }
    src="$tmpdir/opencode"
  fi

  cp "$src" "$INSTALL_DIR/opencode" || { rm -rf "$tmpdir"; return 1; }
  chmod +x "$INSTALL_DIR/opencode"
  rm -rf "$tmpdir"
}

# --- 経路 2: npm registry の tarball を直接取得 ------------------------------
# 経路 1 が使えないときのフォールバック。公式インストーラが使うのと同じ配布物。
# @opencode/cli-<target> は package.json に bin フィールドが無いため npm i -g では
# PATH に乗らない。tarball を展開して package/bin/opencode を配置する。
install_via_npm_tarball() {
  local scope pkg url tmpdir
  command -v tar >/dev/null 2>&1 || { err "tar is required"; return 1; }

  # 旧スコープ @opencode-ai へのフォールバック (公式インストーラと同じ扱い)。
  for scope in @opencode @opencode-ai; do
    pkg="$scope/cli-$TARGET"
    # スコープ込みのパッケージ名を URL パスに載せる。スコープだけをエンコードして
    # /-/ を書くと 404 になるので、dist.tarball と同じ形を使う。
    url="https://registry.npmjs.org/$pkg/-/cli-$TARGET-$NPM_VERSION.tgz"
    log "trying $url"
    tmpdir="$(new_tmpdir)"
    if curl -fsSL --retry 3 --retry-delay 3 --max-time 900 -o "$tmpdir/cli.tgz" "$url" \
      && tar -xzf "$tmpdir/cli.tgz" -C "$tmpdir" \
      && cp "$tmpdir/package/bin/opencode" "$INSTALL_DIR/opencode"; then
      chmod +x "$INSTALL_DIR/opencode"
      rm -rf "$tmpdir"
      return 0
    fi
    rm -rf "$tmpdir"
  done
  return 1
}

# --- 経路 3: 公式インストーラ (--version 明示で metadata API を回避) ---------
install_via_official_installer() {
  curl -fsSL --retry 3 --retry-delay 3 --max-time 300 https://opencode.ai/v2/install \
    | bash -s -- --no-modify-path --version "$NPM_VERSION"
}

# --- 指数バックオフ付き試行 --------------------------------------------------
# attempt ごとに 2 倍로増える待ち時間を入れる (上限 60s)。
try_with_backoff() {
  local label="$1" expect="$2"
  shift 2
  local attempt=1 wait_s=5
  while [ "$attempt" -le "$ATTEMPTS" ]; do
    log "$label: attempt $attempt/$ATTEMPTS (expected version $expect)"
    if "$@" && matches "$expect"; then
      log "$label succeeded: opencode $expect"
      return 0
    fi
    warn "$label attempt $attempt/$ATTEMPTS failed"
    if [ "$attempt" -lt "$ATTEMPTS" ]; then
      log "waiting ${wait_s}s before retrying"
      sleep "$wait_s"
      wait_s=$((wait_s * 2))
      [ "$wait_s" -le 60 ] || wait_s=60
    fi
    attempt=$((attempt + 1))
  done
  return 1
}

source_releases=false
source_npm=false
case "$SOURCE" in
  releases) source_releases=true ;;
  npm) source_npm=true ;;
  auto)
    source_releases=true
    source_npm=true
    ;;
  *)
    err "OPENCODE_INSTALL_SOURCE must be auto, releases or npm (got \"$SOURCE\")"
    exit 1
    ;;
esac

installed=false
installed_from=""

# 公式インストーラは INSTALL_DIR を $HOME/.opencode/bin でハードコードしていて、
# 渡された値を無視する。経路 2/3 と事後検証だけがこの変数を読むので、
# CI では既定値 (インストーラと同じパス) のまま使うのが前提。

if [ "$source_releases" = true ]; then
  if try_with_backoff "github release v$RELEASE_VERSION" "$RELEASE_VERSION" install_via_github_release; then
    installed=true
    installed_from="github release anomalyco/opencode v$RELEASE_VERSION"
  fi
fi

if [ "$installed" = false ] && [ "$source_npm" = true ]; then
  if try_with_backoff "npm @opencode/cli-$TARGET@$NPM_VERSION" "$NPM_VERSION" install_via_npm_tarball; then
    installed=true
    installed_from="npm @opencode/cli-$TARGET@$NPM_VERSION"
  fi
fi

if [ "$installed" = false ] && [ "$SOURCE" = auto ]; then
  warn "falling back to the official installer (it is pinned too, so the metadata API is skipped)"
  if try_with_backoff "official installer $NPM_VERSION" "$NPM_VERSION" install_via_official_installer; then
    installed=true
    installed_from="official installer (opencode.ai/v2/install) $NPM_VERSION"
  fi
fi

if [ "$installed" = false ]; then
  err "could not install opencode (target=$TARGET, releases=v$RELEASE_VERSION, npm=$NPM_VERSION)"
  exit 1
fi

# $GITHUB_PATH は後続 step にしか効かないので、同 step 内の検証はフルパスで行う。
if [ -n "${GITHUB_PATH:-}" ] && ! grep -qxF "$INSTALL_DIR" "$GITHUB_PATH" 2>/dev/null; then
  printf '%s\n' "$INSTALL_DIR" >> "$GITHUB_PATH"
fi

log "opencode ready: $("$INSTALL_DIR/opencode" --version 2>&1) (source: $installed_from)"