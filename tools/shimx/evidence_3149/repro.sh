#!/usr/bin/env bash
# SHX-T39 (#3149) の再現: unit 23 (0x67f00) で 0xf960 の後に入る分岐の IR 行を抜き出す。
# 前提: tools/m11/work/boot_final3.ll (m11_gen_ir2.sh → m11_build.sh の emcc 直前まで)。emsdk は不要。
# 期待: 各 assert が通ること。通らなければ IR の行が変わったので、本付録の行番号を更新する。
set -euo pipefail
cd "$(dirname "$0")/../../.."
F=tools/m11/work/boot_final3.ll
span() { awk -v s="$1" -v e="$2" 'NR>=s && NR<=e {print NR": "$0}' "$F"; }
# 関数定義行 $1 から後ろで、文字列 $2 を含む最初の行 (関数の範囲内に限る)
find_in() { awk -v s="$1" -v pat="$2" 'NR>=s && index($0, pat) {print NR; exit}' "$F"; }
fn() { grep -n -- "^define weak i64 @$1(" "$F" | cut -d: -f1; }

echo "== (1) function_467c40: slot の読み (VA 0x15E3AF0 = LVA 0x11E3AF0) と分岐"
A=$(grep -n -- 'inttoptr i64 22952688 to ptr' "$F" | head -1 | cut -d: -f1)
span "$A" "$((A+5))"
[ "$(sed -n "$((A+4))p" "$F" | grep -c 'icmp eq i64 %2, 0')" = 1 ] || { echo "assert: gate changed" >&2; exit 1; }
[ "$(sed -n "$((A+5))p" "$F" | grep -c 'label %dec_label_pc_467e07, label %dec_label_pc_467cac')" = 1 ] || { echo "assert: br changed" >&2; exit 1; }

echo "== (2) function_467f00: 初期化フラグ (VA 0x11F1114) の分岐と init 経路の呼出し"
B=$(fn function_467f00)
F1=$(find_in "$B" 'inttoptr (i64 18813204')
span "$F1" "$((F1+5))"
[ "$(sed -n "$((F1+5))p" "$F" | grep -c 'label %dec_label_pc_467fcf, label %dec_label_pc_467f1d')" = 1 ] || { echo "assert: flag br changed" >&2; exit 1; }
C1=$(find_in "$B" 'call i64 @function_40f9e0(')
span "$C1" "$C1"
C2=$(find_in "$B" 'call i64 @function_467c40()')
span "$C2" "$C2"

echo "== (3) function_40f9e0: low8(arg2) != 0 なら function_410320 を呼ぶ"
D=$(fn function_40f9e0)
span "$D" "$((D+5))"
D1=$(find_in "$D" 'call i64 @function_410320(')
span "$D1" "$D1"

echo "== (4) function_410320: IR は ret arg1 のみ (間接 call は C 転記 m11_ov.c:556-558 が ICALL 0x41032e で補う)"
E=$(fn function_410320)
span "$E" "$((E+2))"
