#!/bin/bash
# install-opencode.sh — opencode CLI をインストールする。
# installer は内部でバージョン解決のため opencode.ai の metadata API を呼ぶが、
# これが transient に 500 を返すことがあるので、pip 全体をリトライする。
set -euo pipefail

for attempt in 1 2 3; do
  if curl -fsSL --retry 3 --retry-delay 3 https://opencode.ai/v2/install | bash; then
    echo "$HOME/.opencode/bin" >> "${GITHUB_PATH:-/dev/null}"
    echo "opencode: $(command -v opencode) $(opencode --version 2>/dev/null || true)"
    exit 0
  fi
  echo "::warning::opencode install failed (attempt $attempt); retrying"
done

echo "::error::could not install opencode after 3 attempts"
exit 1
