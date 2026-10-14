#!/usr/bin/env bash
# SHX-T37 (#3070) 再現スクリプト: HeapReAlloc / GlobalLock / GlobalUnlock / GlobalFree の不正入力の
# 戻り値と GetLastError を shimx (ST ビルド) で実測する。
#   - 表本体: work/probe.tsv (gitignore 対象)
#   - 負の対照: src の blk_ok に範囲検査 (#3056 の A 項と同じ式) を入れた複製で同じ probe を回し、
#     0xFFFFFFF0 の trap が消えることを確かめる。複製は work/src_rc/ に作り、commit 対象の src は変えない。
# 使い方: EMSDK_ENV=<docs/REFERENCES.md [EMSDK] の emsdk_env.sh> bash tools/shimx/evidence_3070/run.sh
set -uo pipefail

HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
SHX="$(cd -- "$HERE/.." && pwd)"
WORK="$HERE/work"
mkdir -p "$WORK"

if ! command -v emcc >/dev/null; then
    set +u; . "${EMSDK_ENV:?EMSDK_ENV に emsdk_env.sh を指定する}" >/dev/null 2>&1 || true; set -u
fi
command -v emcc >/dev/null || { echo "run.sh: emcc が見つかりません" >&2; exit 2; }
source "$SHX/flags.sh"

build_probe() { # <src-dir> <out-base>
    local src="$1" out="$2"
    emcc "${SHIMX_CLANG_FLAGS[@]}" "${SHIMX_EMCC_ST[@]}" -I"$src" -I"$SHX/pathreg/include" "$src"/*.c \
        "$SHX/pathreg/src/pathmap.c" "$HERE/probe_errcode.c" -o "$out.js" || return 1
    mv "$out.js" "$out.cjs"
}

run_case() { # <cjs> <fn> <value>
    local rc=0 out
    out="$(node "$1" "$2" "$3" 2>"$WORK/err_$2_$3.txt")" || rc=$?
    if [ "$rc" -ne 0 ]; then
        printf '%s\t%s\tTRAP\trc=%s\t%s\n' "$2" "$3" "$rc" "$(grep -m1 -oE 'RuntimeError: [^ ]+( [a-z ]+)?' "$WORK/err_$2_$3.txt" || echo '-')"
    else
        printf '%s\n' "$out"
    fi
}

build_probe "$SHX/src" "$WORK/probe" || { echo "run.sh: emcc 失敗 (表本体)" >&2; exit 1; }
{
    for fn in HeapReAlloc GlobalLock GlobalUnlock GlobalFree; do
        for v in 0x0 0x1 0x3 0x10 0x1000 0xFFFFFFFC 0xFFFFFFF0; do
            run_case "$WORK/probe.cjs" "$fn" "$v"
        done
    done
    run_case "$WORK/probe.cjs" freed 0x0
    run_case "$WORK/probe.cjs" unlocked 0x0
} | tee "$WORK/probe.tsv"

# 負の対照: blk_ok に範囲検査を入れた複製 (式は tools/shimx/src/heap.c の #3056 A 項と同じ)
rm -rf "$WORK/src_rc" && mkdir -p "$WORK/src_rc" && cp "$SHX"/src/*.c "$SHX"/src/*.h "$WORK/src_rc/"
ANCHOR='    if (!user || ((uintptr_t)user & 15u)) return 0;'
RANGE='    if ((uintptr_t)user < HEAP_HDR || (uintptr_t)user > (uintptr_t)__builtin_wasm_memory_size(0) * 65536u) return 0;'
[ "$(grep -cxF -- "$ANCHOR" "$WORK/src_rc/heap.c")" = 1 ] || { echo "run.sh: blk_ok の挿入位置が一意に見つからない" >&2; exit 1; }
awk -v a="$ANCHOR" -v n="$RANGE" '{ print } $0 == a { print n }' "$WORK/src_rc/heap.c" > "$WORK/src_rc/heap.c.new" && mv "$WORK/src_rc/heap.c.new" "$WORK/src_rc/heap.c"
build_probe "$WORK/src_rc" "$WORK/probe_rc" || { echo "run.sh: emcc 失敗 (対照)" >&2; exit 1; }
{
    echo "# 対照: blk_ok 範囲検査あり (work/src_rc)"
    for fn in HeapReAlloc GlobalLock GlobalUnlock GlobalFree; do
        run_case "$WORK/probe_rc.cjs" "$fn" 0xFFFFFFF0
    done
} | tee "$WORK/probe_rc.tsv"
