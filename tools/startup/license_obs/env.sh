#!/usr/bin/env bash
# license_obs の環境。`source` して使う。FL_WIN64_DIR は tools/shared/env.sh の規約 (素材 fl-win64 の展開先)。
_lo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$_lo_dir/../../shared/env.sh"
: "${LICENSE_OBS_VENV:=${TMPDIR:-/tmp}/license_obs_venv}"
export LICENSE_OBS_VENV
unset _lo_dir
