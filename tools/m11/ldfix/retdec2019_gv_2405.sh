#!/usr/bin/env bash
# #2405 (LD-113): RetDec 2019-03 版 (avast/retdec 6edcaaea) で constants.cpp の gv 分岐 (L163〜168) が
# 41a6a0 などで発火するかを、一時ログ付きビルドで実測する。結果と解釈は REPORT_2405.md。
#
# 2019-03-03 の share (retdec-support) は入手できない (REPORT_2405.md §1)。このため [RETDEC] (v5.0) の share を
# 土台にし、2019 版が読む旧レイアウト (x86/ords・arm/ords) と version.txt (2019-03-03) だけ合わせた代用 share を使う。
#
# 使い方: bash tools/m11/ldfix/retdec2019_gv_2405.sh {build|install|ranges|all}
#   build   : retdec を取得 → 6edcaaea → 一時ログのパッチ適用 → cmake → make (所要を time で出す)
#   install : 代用 share を置き make install (install-share.py は version.txt 一致で download を省く)
#   ranges  : 範囲ごとに retdec-decompiler.py を実行し、一時ログ (stderr の TAG_*) の件数を数える
# env:
#   WORK         作業先 (既定 ${RUNNER_TEMP:-/tmp}/rd2019)
#   PE_BIN       block00031_PE.bin (ranges で必須。fl-win64 の extracted/ 配下)
#   RETDEC_ROOT  [RETDEC] (v5.0) の root。代用 share の元 (既定 /opt/retdec。docs/REFERENCES.md §4)
#   JOBS         make -j (既定 4)
# 前提: cmake・make・gcc/g++・flex・bison・python3、apt の libfl-dev (FlexLexer.h)。
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="${WORK:-${RUNNER_TEMP:-/tmp}/rd2019}"
RETDEC_ROOT="${RETDEC_ROOT:-/opt/retdec}"
JOBS="${JOBS:-4}"
REV=6edcaaeaf733bebe3aac57d99cfbc8dd6b835591
PATCH="$HERE/retdec_constants_trace_2405.patch"
# GCC 13 対策 (std::uintN_t・std::string の未 include)。CMAKE_CXX_FLAGS では pelib の sub-build に届かないため環境変数で渡す
export CXXFLAGS="-include cstdint -include string"

do_build() {
  mkdir -p "$WORK"
  [ -d "$WORK/src/.git" ] || git clone -q https://github.com/avast/retdec.git "$WORK/src"
  git -C "$WORK/src" checkout -q "$REV"
  if git -C "$WORK/src" apply --check "$PATCH" 2>/dev/null; then git -C "$WORK/src" apply "$PATCH"; fi
  git -C "$WORK/src" diff --stat
  mkdir -p "$WORK/build"
  cd "$WORK/build"
  cmake ../src -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_INSTALL_PREFIX="$WORK/install"
  uptime
  date -u +'make start %T'
  time make -j"$JOBS"
  uptime
}

do_install() {
  local s="$WORK/install/share/retdec/support"
  rm -rf "$s"
  mkdir -p "$(dirname "$s")"
  cp -a "$RETDEC_ROOT/share/retdec/support" "$s"
  printf '2019-03-03\n' > "$s/version.txt"
  mkdir -p "$s/x86" "$s/arm"
  ln -sfn ../ordinals/x86 "$s/x86/ords"
  ln -sfn ../ordinals/arm "$s/arm/ords"
  make -C "$WORK/build" install | grep -E "support|share" || true
}

count() { grep -c "^$1" "$2" || true; }

run_range() {
  local label="$1" range="$2" out="$WORK/run/$1" t0 t1 rc=0
  rm -rf "$out"; mkdir -p "$out"
  cp "$PE_BIN" "$out/in.bin"
  t0=$(date +%s.%N)
  (cd "$out" && TMPDIR="$out" python3 "$WORK/install/bin/retdec-decompiler.py" in.bin -o "$out/f.c" \
    --select-ranges "$range" --select-decode-only --stop-after bin2llvmir > stdout.log 2> stderr.log) || rc=$?
  t1=$(date +%s.%N)
  printf '%-12s %-22s rc=%d real=%6.3fs SITE1=%s SITE2=%s SITE3_GV=%s PRE_GV=%s\n' "$label" "$range" "$rc" \
    "$(echo "$t1 - $t0" | bc)" "$(count TAG_SITE1_MAXROOT "$out/stderr.log")" "$(count TAG_SITE2_USERI "$out/stderr.log")" \
    "$(count TAG_SITE3_GV "$out/stderr.log")" "$(count TAG_PRE_GV "$out/stderr.log")"
  rm -f "$out/in.bin" "$out/f.dsm"
}

do_ranges() {
  : "${PE_BIN:?PE_BIN (block00031_PE.bin) を指定}"
  uptime
  run_range 41a693      0x41a693-0x41a69a
  run_range 41a6a0      0x41a6a0-0x41a6a3
  run_range 41a6d3      0x41a6d3-0x41a6d6
  run_range 666b10      0x666b10-0x666b13
  run_range 666b20      0x666b20-0x666b23
  run_range ctl_41a6b3  0x41a6b3-0x41a6b7
  run_range full_41a670 0x41a670-0x41a6f4
  run_range full_666a60 0x666a60-0x666b20
  echo "--- gv 分岐 (SITE3_GV) 発火の root と命令 (単独範囲)"
  for l in 41a6a0 41a6d3 666b10 666b20; do
    echo "$l: $(grep -h '^TAG_PRE_GV.*isLoad=1 gv=1' "$WORK/run/$l/stderr.log" | cut -c1-200)"
  done
  uptime
}

case "${1:-all}" in
  build) do_build ;;
  install) do_install ;;
  ranges) do_ranges ;;
  all) do_build; do_install; do_ranges ;;
  *) echo "usage: $0 {build|install|ranges|all}" >&2; exit 2 ;;
esac
