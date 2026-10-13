# helpviewer の環境定義 (e2e.sh が source する)。FL_WIN64_DIR は tools/shared/env.sh の既定を使い、未設定なら上書きする。
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$HERE/../../shared/env.sh"
export FL_WIN64_DIR
