#!/usr/bin/env bash
# M1: 極小 PE/ELF → RetDec → emcc → wasm → node 出力一致の E2E PoC を1本で実行する。
#
# 使い方:  bash tools/m1/m1.sh
#   - 成功: "[M1] E2E OK: ..." を出力して exit 0
#   - 失敗: 失敗箇所を stderr に出力して非ゼロ終了
#
# 環境変数:
#   M1_STRICT=1        固定バージョン (flags.sh の *_VERSION_PIN) と一致しなければ失敗
#   EMSDK_ENV=<path>   emsdk_env.sh のパス (既定 /opt/emsdk/emsdk_env.sh)
#   RETDEC_DECOMPILER=<path>  retdec-decompiler のパス (既定 /opt/retdec/bin/retdec-decompiler)

set -euo pipefail

HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
BUILD="$HERE/build"

info() { echo "[M1] $*"; }
die()  { echo "[M1] FAIL: $*" >&2; exit 1; }
trap 'rc=$?; echo "[M1] FAILED: 実行中断 (exit=$rc)" >&2' ERR

# ---------------------------------------------------------------
# 0/7 環境確認と emsdk 有効化
# ---------------------------------------------------------------
info "0/7 環境確認"
RETC="${RETDEC_DECOMPILER:-/opt/retdec/bin/retdec-decompiler}"
EMSDK="${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}"

[ -x "$RETC" ] || die "retdec-decompiler が見つかりません: $RETC"
if [ -f "$EMSDK" ]; then
    set +u
    # shellcheck disable=SC1090
    . "$EMSDK" >/dev/null 2>&1 || true
    set -u
fi
command -v emcc >/dev/null            || die "emcc が見つかりません (emsdk env を再確認)"
command -v node >/dev/null            || die "node が見つかりません"
command -v gcc >/dev/null             || die "gcc が見つかりません"
command -v x86_64-w64-mingw32-gcc >/dev/null || die "x86_64-w64-mingw32-gcc が見つかりません"
command -v awk  >/dev/null            || die "awk が見つかりません"

source "$HERE/flags.sh"

# バージョン情報の採取 (常時出力し build/versions.txt に記録)
EMCC_VER="$(emcc --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
RETDEC_VER="$("$RETC" --version | awk '/RetDec version/ {print $NF}' | sed 's/^v//')"
MINGW_VER="$(x86_64-w64-mingw32-gcc -dumpfullversion)"
NODE_MAJ="$(node -p 'process.versions.node.split(".")[0]')"

if [ "${M1_STRICT:-0}" = "1" ]; then
    [ "$EMCC_VER"  = "$EMCC_VERSION_PIN"    ] || die "emcc バージョン不一致: $EMCC_VER (pin: $EMCC_VERSION_PIN)"
    [ "$RETDEC_VER" = "$RETDEC_VERSION_PIN" ] || die "RetDec バージョン不一致: $RETDEC_VER (pin: $RETDEC_VERSION_PIN)"
    [ "$MINGW_VER" = "$MINGW_GCC_VERSION_PIN" ] || die "mingw-w64 gcc バージョン不一致: $MINGW_VER (pin: $MINGW_GCC_VERSION_PIN)"
    [ "$NODE_MAJ" -ge 18 ]                        || die "node が古すぎます: $NODE_MAJ.x"
fi

mkdir -p "$BUILD"
{
    echo "emcc           : $EMCC_VER (pin $EMCC_VERSION_PIN)"
    echo "RetDec         : $RETDEC_VER (pin $RETDEC_VERSION_PIN)"
    echo "mingw-w64 gcc  : $MINGW_VER (pin $MINGW_GCC_VERSION_PIN)"
    echo "node           : $(node --version)"
    echo "date           : $(date -Is)"
} > "$BUILD/versions.txt"

# ---------------------------------------------------------------
# 1/7 極小プログラムを x64 ELF と x86_64 PE (PE32+) の両方にビルド
# ---------------------------------------------------------------
info "1/7 ネイティブビルド (x64 ELF / x86_64 PE)"
gcc -O0 "$HERE/poc_main.c" -o "$BUILD/native_elf"
x86_64-w64-mingw32-gcc -O0 "$HERE/poc_main.c" -o "$BUILD/native_pe.exe"

[ "$(dd if="$BUILD/native_elf" bs=1 count=4 2>/dev/null)" = $'\x7fELF' ] || die "native_elf が ELF 形式ではありません"
[ "$(dd if="$BUILD/native_pe.exe" bs=1 count=2 2>/dev/null)" = "MZ" ]   || die "native_pe.exe が PE (MZ) 形式ではありません"

# ---------------------------------------------------------------
# 2/7 native 実行 → 比較用 reference 出力の採取
# ---------------------------------------------------------------
info "2/7 native ELF 実行 (reference 出力の採取)"
"$BUILD/native_elf" > "$BUILD/ref.out"
[ -s "$BUILD/ref.out" ] || die "native ELF の出力が空です"

# ---------------------------------------------------------------
# 3/7 RetDec 逆コンパイル (ELF / PE)
# ---------------------------------------------------------------
info "3/7 RetDec 逆コンパイル (PE32+ 展開はCRT全体を含むため数十秒〜)"
"$RETC" "$BUILD/native_elf"     -o "$BUILD/retdec_elf.c"     >/dev/null 2>&1 || die "RetDec (ELF) に失敗"
"$RETC" "$BUILD/native_pe.exe"  -o "$BUILD/retdec_pe.c"      >/dev/null 2>&1 || die "RetDec (PE) に失敗"
[ -s "$BUILD/retdec_elf.c" ] || die "RetDec ELF 出力が空"
[ -s "$BUILD/retdec_pe.c" ]  || die "RetDec PE 出力が空"

# ---------------------------------------------------------------
# 4/7 必要関数 (main) の抽出
#   - ELF/PE ともに RetDec 出力から main 定義ブロックのみを取り出す。
#     (ELF 出力は _start/CRT を丸ごと展開するため全体コンパイルには
#      __asm_hlt implicit 宣言問題が付いてくる。main 抽出でそれを回避する)
#   - PE 固有の後処理: __mingw_printf → printf 置換、__main() CRT 初期化呼び出しの除去
# ---------------------------------------------------------------
info "4/7 main 関数抽出 (PE は __mingw_printf 置換 / __main() 除去)"
awk -v func=main -f "$HERE/extract_main.awk" "$BUILD/retdec_elf.c" > "$BUILD/main_elf.frag" \
    || die "ELF 出力から main を抽出できませんでした"
awk -v func=main -f "$HERE/extract_main.awk" "$BUILD/retdec_pe.c"  > "$BUILD/main_pe.frag" \
    || die "PE 出力から main を抽出できませんでした"

sed -e 's/__mingw_printf/printf/g' -e '/^[[:space:]]*__main[[:space:]]*(/d' \
    "$BUILD/main_pe.frag" > "$BUILD/main_pe_clean.frag"

{ echo '#include <stdio.h>'; cat "$BUILD/main_elf.frag"; }      > "$BUILD/lifted_elf.c"
{ echo '#include <stdio.h>'; cat "$BUILD/main_pe_clean.frag"; } > "$BUILD/lifted_pe.c"

# ---------------------------------------------------------------
# 5/7 emcc 再コンパイル → wasm 生成 (定型フラグ EMCC_FLAGS_M1)
# ---------------------------------------------------------------
info "5/7 emcc 再コンパイル (flags.sh: EMCC_FLAGS_M1)"
# 注意: 本リポジトリは package.json "type":"module" のため、emcc glue (CommonJS)
# を node が ESM と誤解釈する。出力拡張子を .cjs に改名して回避する。
emcc "${EMCC_FLAGS_M1[@]}" "$BUILD/lifted_elf.c" -o "$BUILD/wasm_elf.js" \
    || die "emcc (ELF) に失敗"
emcc "${EMCC_FLAGS_M1[@]}" "$BUILD/lifted_pe.c"  -o "$BUILD/wasm_pe.js" \
    || die "emcc (PE) に失敗"
mv "$BUILD/wasm_elf.js" "$BUILD/wasm_elf.cjs"
mv "$BUILD/wasm_pe.js"  "$BUILD/wasm_pe.cjs"
[ -f "$BUILD/wasm_elf.wasm" ] || die "ELF wasm が生成されていません"
[ -f "$BUILD/wasm_pe.wasm" ]  || die "PE wasm が生成されていません"

# ---------------------------------------------------------------
# 6/7 node 実行
# ---------------------------------------------------------------
info "6/7 wasm を node で実行"
node "$BUILD/wasm_elf.cjs" > "$BUILD/wasm_elf.out" 2> "$BUILD/wasm_elf.err" \
    || die "node 実行 (ELF wasm) に失敗 (build/wasm_elf.err 参照)"
node "$BUILD/wasm_pe.cjs"  > "$BUILD/wasm_pe.out"  2> "$BUILD/wasm_pe.err" \
    || die "node 実行 (PE wasm) に失敗 (build/wasm_pe.err 参照)"

# ---------------------------------------------------------------
# 7/7 出力比較 (native ELF = wasm ELF = wasm PE)
# ---------------------------------------------------------------
info "7/7 出力比較 (native ELF = wasm ELF = wasm PE)"
"$HERE/compare.sh" "$BUILD/ref.out" "$BUILD/wasm_elf.out" "$BUILD/wasm_pe.out"

info "E2E OK: ELF/PE32+ → RetDec → main抽出 → emcc → wasm → node が native 出力と一致"
info "成果物: $BUILD (gitignored) / versions.txt に実行時バージョンを記録"
exit 0
