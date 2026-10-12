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
# 対策:
#   1. バージョンを pin する。インストーラに `--version` を渡すと上の metadata API を
#      呼ばない分岐 (`if [ -z "$requested_version" ]`) を通るので、500 の影響を受けない。
#      バージョンは env (workflow_dispatch 入力 / vars.OPENCODE_VERSION) で上書きできる。
#   2. バックオフ付きリトライ (5s/15s/30s)。
#   3. フォールバック: npm registry の tarball を直接取得して bin/opencode を配置する。
#      公式インストーラが使うのと同じ npm 配布物なので、信頼できる経路は増えない。
#   4. 最後に `opencode --version` の実測で pin 一致を確認し、満たさなければ exit 1。
#
# 注意: 「sleep による 10 秒以上の待機禁止」は opencode エージェント (opencode run)
# 向けの規約で、CI のセットアップ step には適用されない。ここでは待避を優先する。
set -euo pipefail

DEFAULT_OPENCODE_VERSION="2.0.26"
VERSION="${OPENCODE_VERSION:-${OPENCODE_CLI_VERSION:-$DEFAULT_OPENCODE_VERSION}}"
VERSION="${VERSION#v}"

INSTALL_DIR="${OPENCODE_INSTALL_DIR:-$HOME/.opencode/bin}"
ATTEMPTS="${OPENCODE_INSTALL_ATTEMPTS:-3}"

# 公式インストーラは INSTALL_DIR を $HOME/.opencode/bin でハードコードしていて、
# 渡された値を無視する。フォールバック経路と事後検証だけがこの変数を読むので、
# CI では既定値 (インストーラと同じパス) のまま使うのが前提。

log() { printf '%s\n' "$*"; }
warn() { printf '::warning::%s\n' "$*"; }
err() { printf '::error::%s\n' "$*"; }

# --- OS/arch → opencode の配布ターゲット名 ----------------------------------
# 公式インストーラの判定_logic に揃える (musl / AVX2 非対応は -musl / -baseline)。
# ここをずらすと npm に無いパッケージ名を引いてフォールバックも失敗する。
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

  # x64 かつ AVX2 未対応(rc=1 でも「非対応とみなす」)なら baseline ビルドを要求する
  if [ "$arch" = x64 ]; then
    if [ "$os" = linux ]; then
      grep -qwi avx2 /proc/cpuinfo 2>/dev/null || needs_baseline=true
    fi
  fi

  local target="$os-$arch"
  [ "$needs_baseline" = false ] || target="$target-baseline"
  [ "$is_musl" = false ] || target="$target-musl"
  printf '%s' "$target"
}

TARGET="${OPENCODE_TARGET:-}"
if [ -z "$TARGET" ]; then
  TARGET="$(detect_target)" || exit 1
fi

mkdir -p "$INSTALL_DIR"

# インストーラ本体と同じ解析手順を使う: `opencode --version` は "<何か> <version>" 形式。
installed_version() {
  "$INSTALL_DIR/opencode" --version 2>/dev/null | awk '{print $NF}' | sed 's/^v//'
}
matches_pin() { [ "$(installed_version || true)" = "$VERSION" ]; }

# --- 経路 1: 公式インストーラ (--version 明示で metadata API を回避) ----------
install_via_official_installer() {
  curl -fsSL --retry 3 --retry-delay 3 --max-time 300 https://opencode.ai/v2/install \
    | bash -s -- --no-modify-path --version "$VERSION"
}

# --- 経路 2: npm registry の tarball を直接取得 -----------------------------
# @opencode/cli-<target> は package.json に bin フィールドが無いため npm i -g では
# PATH に乗らない。tarball を展開して package/bin/opencode を配置する。
# 公式インストーラ一樣の 404 → 旧スコープ @opencode-ai へのフォールバックを持つ。
install_via_npm_tarball() {
  local scope pkg url tmpdir
  command -v tar >/dev/null 2>&1 || { err "tar is required"; return 1; }

  for scope in @opencode @opencode-ai; do
    pkg="$scope/cli-$TARGET"
    # 公式インストーラと同じ URL 形 (dist.tarball と一致)。
    # パッケージ名 (スコープ込み) を URL パスに載せる。スコープだけエンコードして
    # /-/ 以降を書くと 404 になるので、dist.tarball と同じ形を使う。
    url="https://registry.npmjs.org/$pkg/-/cli-$TARGET-$VERSION.tgz"
    log "trying $url"
    tmpdir="$(mktemp -d)"
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

installed=false
attempt=1
while [ "$attempt" -le "$ATTEMPTS" ]; do
  if install_via_official_installer && matches_pin; then
    log "opencode $VERSION installed via the official installer"
    installed=true
    break
  fi
  warn "official installer attempt $attempt/$ATTEMPTS failed for target $TARGET"
  if [ "$attempt" -lt "$ATTEMPTS" ]; then
    sleep $((5 * attempt))
  fi
  attempt=$((attempt + 1))
done

if [ "$installed" = false ]; then
  warn "falling back to the npm registry tarball for @opencode/cli-$TARGET@$VERSION"
  if install_via_npm_tarball && matches_pin; then
    log "opencode $VERSION installed from the npm registry tarball"
    installed=true
  fi
fi

if [ "$installed" = false ]; then
  err "could not install opencode $VERSION for $TARGET (target may need -musl / -baseline)"
  exit 1
fi

# $GITHUB_PATH は後続 step にしか効かないので、同 step 内の検証はフルパスで行う。
if [ -n "${GITHUB_PATH:-}" ] && ! grep -qxF "$INSTALL_DIR" "$GITHUB_PATH" 2>/dev/null; then
  printf '%s\n' "$INSTALL_DIR" >> "$GITHUB_PATH"
fi

log "opencode ready: $("$INSTALL_DIR/opencode" --version 2>&1) ($INSTALL_DIR/opencode)"