#!/usr/bin/env bash
# M11 build: boot_final.ll → (m11_post: weak 化 + 間接 call トランポリン) → emcc → work/m11_boot.cjs(+wasm)
# 各翻訳単位を work/obj/*.o にキャッシュ (入力より新しければ再コンパイルしない) し,
# 反復 build (m11_ov.c など C 側修正) を数十秒で回せるようにする.
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$HERE"
source "$HERE/../shared/env.sh"   # FL_WIN64_DIR (既定 $ANALYSIS_DIR/win64 = /home/ubuntu/work/analysis/win64)
# #730: emsdk 無しで後段の emcc が不明瞭に失敗するのを避け、前提不足の理由を明示して止める (m11_e2e.sh の prerequisite チェックと揃える)
if [ ! -f /opt/emsdk/emsdk_env.sh ]; then
  echo "[m11build] ERROR: prerequisite missing: emsdk 無し (/opt/emsdk/emsdk_env.sh が見つからない)" >&2; exit 1
fi
source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1
export TMPDIR="$HERE/work/tmp"
mkdir -p work/tmp work/obj
M11_LB_BASE="${M11_LB_BASE:-0}"; export M11_LB_BASE   # #222: LVA = RVA + M11_LB_BASE (0 = 従来)
M11_OV_CLASSCREATE="${M11_OV_CLASSCREATE:-0}"   # #419: 1 = m11_ov.c の実験 override (410360 のみ; 8cbda0/8cbce0 は #503 で既定 ON) を有効化 (既定 0)
M11_OV_414AD0="${M11_OV_414AD0:-0}"   # #683: 1 = m11_ov.c の UStrSetLength 版 function_414ad0 (arg1 deref 復元) に切替; 0 = main の LStrSetLength 版 (#134) を使う (既定; closure 退行 7 件が未解決のため)
M11_FIX_652500="${M11_FIX_652500:-0}"   # #748: 1 = m11_ov.c の function_652500 (*arg1 の 1 段 deref 復元) を有効化; 0 = lift 版 (既定)
M11_OV_413060="${M11_OV_413060:-0}"   # #944: 1 = m11_ov.c の function_413060 (dest の旧値 deref 復元, D4) を有効化; 0 = lift 版 (既定)。413060 だけを切り替える独立 gate
M11_NEG_413060="${M11_NEG_413060:-0}"   # #944 ネガコン: 1 = dest に p+0x40 を書く既知変更 (b)。感度確認用。既定 0
M11_INSTR_413060="${M11_INSTR_413060:-0}"   # #944: 1 = 計測専用に function_413060 へ probe (index 8) と dest 観測 hook を post で入れる。既定 0 は main と同一の post 出力
M11_RT_INSTR="${M11_RT_INSTR:-$M11_INSTR_413060}"   # #1701: rt.o をコンパイルする時の M11_INSTR_413060 値 (既定は M11_INSTR_413060 と同じ = 従来どおり)。1 を 0 にすると rt.o だけ計測 OFF
M11_OV_INSTR="${M11_OV_INSTR:-$M11_INSTR_413060}"   # #1701: ov.o をコンパイルする時の M11_INSTR_413060 値 (既定は同じ)。1 を 0 にすると ov.o だけ計測 OFF
M11_LINK_INSTR="${M11_LINK_INSTR:-$M11_INSTR_413060}"   # #1701: リンク時の EXPORTS (_m11_dest_obs_* 等) を足すか。既定は M11_INSTR_413060 と同じ
M11_DEST_READ="${M11_DEST_READ:-1}"   # #944: 0 = 413060 後の dest 読出し (指紋) を止める。読出しが挙動を変えるかの切り分け用。既定 1
M11_FIX_535BF2="${M11_FIX_535BF2:-0}"   # #714: 1 = m11_ov.c の function_535c11/535bf2 転記 (IR 未定義 535c2e・境界 535c11 の再現); 0 = lift 版 (既定)
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=$M11_LB_BASE -DM11_OV_CLASSCREATE=$M11_OV_CLASSCREATE -DM11_OV_414AD0=$M11_OV_414AD0 -DM11_FIX_652500=$M11_FIX_652500 -DM11_OV_413060=$M11_OV_413060 -DM11_NEG_413060=$M11_NEG_413060 -DM11_DEST_READ=$M11_DEST_READ -DM11_INSTR_413060=$M11_INSTR_413060 -DM11_FIX_535BF2=$M11_FIX_535BF2 -DM11_INSTR_K12=${M11_INSTR_K12:-0} -DM11_INSTR_40FF70=${M11_INSTR_40FF70:-0} -DM11_DEST_GUARD=${M11_DEST_GUARD:-0} -DM11_INSTR_40F960=${M11_INSTR_40F960:-0} -DM11_INSTR_40FFE0=${M11_INSTR_40FFE0:-0} -DM11_INSTR_60A270=${M11_INSTR_60A270:-0} -DM11_TRACE_ISOLATE=${M11_TRACE_ISOLATE:-1} -DM11_ENTRY_PROBE=${M11_ENTRY_PROBE:-0} -DM11_NOVCALL=${M11_NOVCALL:-0} -DM11_RT_PADPRE=${M11_RT_PADPRE:-0} -DM11_RT_PADPOST=${M11_RT_PADPOST:-0} -DM11_RT_EMPTY=${M11_RT_EMPTY:-0}"
# image 終端 (SizeOfImage 0x18c0000) + LB_BASE が GLOBAL_BASE (0x10000000) 以内であること
python3 - <<PYEOF
import sys
lb = int("$M11_LB_BASE", 0)
assert lb % 0x10000 == 0 and lb + 0x18c0000 <= 0x10000000, "M11_LB_BASE=0x%x が image 配置制約に反する" % lb
PYEOF
# LB_BASE が変わったら LB 依存成果物 (IR 後処理 / .o) を無効化
if [ "$(cat work/lb_base.stamp 2>/dev/null || echo 0)" != "$M11_LB_BASE" ]; then
  rm -f work/boot_final3.ll work/obj/*.o
fi
echo "$M11_LB_BASE" > work/lb_base.stamp
# IR (boot_final.ll) の VA→LVA remap と image/data は同じ LB_BASE で生成済みであること (m11_e2e.sh が stamp を管理)
for st in ir_lb_base img_lb_base; do
  if [ -f work/$st.stamp ] && [ "$(cat work/$st.stamp)" != "$M11_LB_BASE" ]; then
    echo "[m11build] work/$st.stamp=$(cat work/$st.stamp) != M11_LB_BASE=$M11_LB_BASE: bash m11_e2e.sh で再生成を" >&2; exit 2
  fi
done

if [ ! -f work/boot_final.ll ]; then echo "[m11build] work/boot_final.ll 無し: m11_gen_ir2.sh を先に" >&2; exit 2; fi
PE_QS="${PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}"
# #680: ldfix 適用の記録が無い IR (旧スナップショット等) は build しない (m11_gen_ir2.sh で作り直す)
if [ "$(python3 m11_cond.py --get ldfix)" = disabled ] && [ "${M11_ALLOW_LDFIX_DISABLED:-0}" = 1 ]; then
  # #1165: ldfix 無し IR (M11_LDFIX=0 で生成したもの) の build は明示 opt-in のときだけ許す。既定は拒否のまま。
  #   指紋 (--check) と PE の一致は下で従来どおり検査する。測定時は ldfix=disabled を REPORT に明記すること。
  echo "[m11build] WARNING: M11_ALLOW_LDFIX_DISABLED=1: ldfix 無しの IR で build する (ir_conditions.json ldfix=disabled)" >&2
elif [ "$(python3 m11_cond.py --get ldfix)" != applied ]; then
  echo "[m11build] ERROR: work/ir_conditions.json に ldfix=applied の記録無し (現在: '$(python3 m11_cond.py --get ldfix)')。m11_gen_ir2.sh で IR を作り直すこと (ldfix 無しで測るなら M11_ALLOW_LDFIX_DISABLED=1)" >&2; exit 2
fi
# #2402: ldfix 適用 IR は fix_ld108 (41a670 の head 解除 store, D20) の適用記録も要る。M11_FIX_LD108=0 で作った IR (ld108=disabled) は A/B 測定用で、明示 opt-in のときだけ build する
if [ "$(python3 m11_cond.py --get ldfix)" = applied ]; then
  if [ "$(python3 m11_cond.py --get ld108)" = disabled ] && [ "${M11_ALLOW_LD108_DISABLED:-0}" = 1 ]; then
    echo "[m11build] WARNING: M11_ALLOW_LD108_DISABLED=1: fix_ld108 無しの IR で build する (ir_conditions.json ld108=disabled)" >&2
  elif [ "$(python3 m11_cond.py --get ld108)" != applied ]; then
    echo "[m11build] ERROR: work/ir_conditions.json に ld108=applied の記録無し (現在: '$(python3 m11_cond.py --get ld108)')。m11_gen_ir2.sh で IR を作り直すこと (fix_ld108 無しで測るなら M11_FIX_LD108=0 で作り直し、M11_ALLOW_LD108_DISABLED=1)" >&2; exit 2
  fi
fi
# #680 (review): 記録の無い差替え (正規 pass を経ない IR の書換え) を拒否する。正規 pass は直後に --bind で指紋を更新する
if ! python3 m11_cond.py --check work/boot_final.ll; then
  echo "[m11build] ERROR: work/boot_final.ll が ir_conditions.json の指紋と不一致。m11_gen_ir2.sh で IR を作り直すこと" >&2; exit 2
fi
# #680 (review): IR を生成した PE と現在の PE が違えば build しない
if [ "$(python3 m11_cond.py --get pe)" != "$PE_QS" ]; then
  echo "[m11build] ERROR: IR の生成 PE ('$(python3 m11_cond.py --get pe)') と現在の PE ($PE_QS) が違う。m11_gen_ir2.sh で作り直すこと" >&2; exit 2
fi
# qstore (#516): 機械語 `mov qword [rbp+X],imm` が IR で `store ptr null`/`store i32 imm` (4B) に縮む site を `store i64` に戻す
#   (capstone 突合で確定した site のみ; idempotent)。M11_QSTORE=0 で無効化 (ネガコン; 無効化は m11_gen_ir2.sh で IR を作り直してから)。
#   #680: skip は失敗扱い (fail-closed)。適用有無は work/ir_conditions.json に記録する (m11_cond.py)。
if [ "${M11_QSTORE:-1}" = 1 ]; then
  if [ -f "$PE_QS" ] && python3 -c 'import capstone, pefile' 2>/dev/null; then
    python3 qstore/m11_qstore.py work/boot_final.ll work/boot_final.qstore.tmp.ll --pe "$PE_QS" --report work/qstore_report.json > work/qstore.log
    if ! cmp -s work/boot_final.ll work/boot_final.qstore.tmp.ll; then mv work/boot_final.qstore.tmp.ll work/boot_final.ll; else rm -f work/boot_final.qstore.tmp.ll; fi
    python3 m11_cond.py qstore=applied
    python3 m11_cond.py --bind work/boot_final.ll
  else
    # 適用済み IR (applied) の記録は残す: M11_QSTORE=0 の拒否 (下の else 側) を外さないため
    [ "$(python3 m11_cond.py --get qstore)" = applied ] || python3 m11_cond.py qstore=skipped
    echo "[m11build] ERROR: qstore skip (PE 無し: $PE_QS / capstone・pefile 無し) — fail-closed で失敗。明示的に外すなら M11_QSTORE=0" >&2
    exit 1
  fi
else
  if [ "$(python3 m11_cond.py --get qstore)" = applied ]; then
    echo "[m11build] ERROR: work/boot_final.ll は qstore 適用済み (ir_conditions.json)。M11_QSTORE=0 の前に m11_gen_ir2.sh で IR を作り直すこと" >&2
    exit 2
  fi
  python3 m11_cond.py qstore=disabled
fi
# alloca 縮退修正 (CAB-129 + #132 R8): RetDec が `alloca i64` (8B) に潰したローカルを拡幅 (idempotent)。
#   unit #18 OOB の真因 = 44bae0 の stack_var が callee 44ba50 に書かれ 44bb70 の record を破壊 (R8)。
#   内容が変わった時だけ boot_final.ll を差し替える (mtime を更新して毎回 post/cc を走らせない)。
python3 alloca/m11_alloca.py work/boot_final.ll work/boot_final.alloca.tmp.ll --report work/alloca_report.json > work/alloca.log
if ! cmp -s work/boot_final.ll work/boot_final.alloca.tmp.ll; then mv work/boot_final.alloca.tmp.ll work/boot_final.ll; else rm -f work/boot_final.alloca.tmp.ll; fi
# #699: 8c5eb0 の件数 0 ループ先頭ガード (RetDec が落とした cmp/jg) を IR に復元 (冪等)。
#   M11_GUARD699=off で脱落状態に戻す (ネガコン)。M11_GUARD699_COND で条件を差し替え (ネガコン: 常に不成立)。
python3 guard699/m11_guard699.py work/boot_final.ll work/boot_final.guard699.tmp.ll --mode "${M11_GUARD699:-on}" --cond "${M11_GUARD699_COND:-icmp sle i32 %9, 0}" --report work/guard699_report.json
if ! cmp -s work/boot_final.ll work/boot_final.guard699.tmp.ll; then mv work/boot_final.guard699.tmp.ll work/boot_final.ll; else rm -f work/boot_final.guard699.tmp.ll; fi
# #912: 4fb090 の 4fa070 呼出し第 2 引数 dl を機械語 (mov dl,1) どおりに戻す (冪等)。既定 0 (OFF)。M11_FIX_912=1 で有効化。
#   現 head (M2q 込み IR) では ON/OFF の survey 差 0 (REPORT_912 §10)。旧 IR (a5e9c1ed) では 101/291/296 の oob を解消した (REPORT_912 §7-旧)。
python3 fix912/m11_fix912.py work/boot_final.ll work/boot_final.fix912.tmp.ll --mode "$([ "${M11_FIX_912:-0}" = 1 ] && echo on || echo off)" --report work/fix912_report.json
if ! cmp -s work/boot_final.ll work/boot_final.fix912.tmp.ll; then mv work/boot_final.fix912.tmp.ll work/boot_final.ll; else rm -f work/boot_final.fix912.tmp.ll; fi
# #680: IR 書換え後に指紋を更新する (guard699 の後に置く。main 側の --bind を残す)
python3 m11_cond.py --bind work/boot_final.ll
# #131: sigfix 復元モードが変わったら post 結果を無効化 (stamp)
if [ "$(cat work/sigfix_recover.stamp 2>/dev/null || echo 0)" != "${M11_SIGFIX_RECOVER:-0}" ]; then rm -f work/boot_final3.ll; fi
# #944: 計測 probe の有無が変わったら post 結果を無効化 (stamp)
S_INSTR="$M11_INSTR_413060${M11_PROBE_VARIANT:+:$M11_PROBE_VARIANT}"   # #1542: 変種 (M11_PROBE_VARIANT) も stamp に含める。未設定時は従来の値と同一
if [ "$(cat work/instr_413060.stamp 2>/dev/null || echo none)" != "$S_INSTR" ]; then rm -f work/boot_final3.ll; fi
echo "$S_INSTR" > work/instr_413060.stamp
# #882: 40ff70 観測 probe の有無が変わったら post 結果を無効化 (stamp)
S_INSTR40="${M11_INSTR_40FF70:-0}:${M11_INSTR_40FFE0:-0}:${M11_INSTR_60A270:-0}"
if [ "$(cat work/instr_40ff70.stamp 2>/dev/null || echo none)" != "$S_INSTR40" ]; then rm -f work/boot_final3.ll; fi
echo "$S_INSTR40" > work/instr_40ff70.stamp
echo "${M11_SIGFIX_RECOVER:-0}" > work/sigfix_recover.stamp
if [ ! -f work/boot_final3.ll ] || [ work/boot_final.ll -nt work/boot_final3.ll ] || [ m11_post.py -nt work/boot_final3.ll ] || [ m11_argrecover.py -nt work/boot_final3.ll ]; then
  # M11_SIGFIX_RECOVER=1 (#131): sigfix の 0 詰め site を機械語突合し、定数代入が確定する引数だけ復元 (m11_argrecover.py)
  if [ "${M11_SIGFIX_RECOVER:-0}" = 1 ]; then
    PE="${PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}"
    python3 m11_post.py work/boot_final.ll work/boot_final3.ll --report work/post_report.json --pads work/sigfix_pads.json
    FIXES="${M11_SIGFIX_FIXES:-work/sigfix_fixes.json}"
    [ -n "${M11_SIGFIX_FIXES:-}" ] || python3 m11_argrecover.py work/sigfix_pads.json --pe "$PE" --lb "$M11_LB_BASE" --out "$FIXES"
    python3 m11_post.py work/boot_final.ll work/boot_final3.ll --report work/post_report.json --fixes "$FIXES"
  else
    python3 m11_post.py work/boot_final.ll work/boot_final3.ll --report work/post_report.json
  fi
fi
# SIMD helper (C) は IR の declare から署名駆動で再生成 (m11_simd2.py)
if [ ! -f work/m11_simd.c ] || [ work/boot_final.ll -nt work/m11_simd.c ] || [ m11_simd2.py -nt work/m11_simd.c ]; then
  python3 m11_simd2.py work/boot_final.ll > work/m11_simd.c 2> work/simd2.log
fi

cc() { # cc <src> <obj> [extra deps...]
  local src="$1" obj="$2"; shift 2
  local need=0
  [ ! -f "$obj" ] && need=1
  [ "$src" -nt "$obj" ] && need=1
  for d in "$@"; do [ "$d" -nt "$obj" ] && need=1; done
  if [ $need = 1 ]; then
    echo "[m11build] cc $src"
    case "$src" in
      *.ll) emcc -c "$src" -o "$obj" $CF ;;
      *)    emcc -c "$src" -o "$obj" $CF -I. ;;
    esac
  fi
}
# 別 TU (tools/shim, m11_rt/ov/win) が定義する Win32 API は winstubs から除外 (duplicate symbol 回避)
for f in heap failfast file timer sync; do cc ../shim/src/$f.c work/obj/shim_$f.o; done
S_NEG="$M11_NEG_413060-$M11_DEST_READ-$M11_INSTR_413060-rt$M11_RT_INSTR$( [ "${M11_RT_PADPRE:-0}${M11_RT_PADPOST:-0}${M11_RT_EMPTY:-0}" = 000 ] || echo "-pre${M11_RT_PADPRE:-0}-post${M11_RT_PADPOST:-0}-empty${M11_RT_EMPTY:-0}" )$( [ "${M11_DEST_GUARD:-0}" = 0 ] || echo "-guard${M11_DEST_GUARD}" )"   # #1952: 対照 knob (既定 0 のときは従来の stamp と同一)。#1547: DEST_GUARD も rt.o の作り直し判定 (既定 0 は従来と同一)
if [ "$(cat work/neg_413060.stamp 2>/dev/null || echo none)" != "$S_NEG" ]; then rm -f work/obj/rt.o; fi
echo "$S_NEG" > work/neg_413060.stamp
# #1176: work-m11 同梱の rt.o/win.o は古い snapshot のことがある (mtime だけでは判定できない: 同梱 obj が source より新しく見える)。
#   ソースの sha256 が記録と違えば作り直す (stamp 無し = 初回・snapshot 由来も作り直す)。
RTWIN_SHA="$(cat m11_rt.c m11_win.c | sha256sum | cut -d' ' -f1)"
if [ "$(cat work/rtwin.sha256 2>/dev/null || echo none)" != "$RTWIN_SHA" ]; then rm -f work/obj/rt.o work/obj/win.o; fi
CF_BASE="$CF"
CF="${CF_BASE//-DM11_INSTR_413060=$M11_INSTR_413060/-DM11_INSTR_413060=$M11_RT_INSTR}" cc m11_rt.c work/obj/rt.o
CF="$CF_BASE" cc m11_win.c work/obj/win.o
echo "$RTWIN_SHA" > work/rtwin.sha256
llvm-nm --defined-only work/obj/shim_*.o work/obj/rt.o work/obj/win.o 2>/dev/null | awk '$2 ~ /^[TtWwDd]$/ {print $3}' | sort -u > work/defined_c.txt
if [ ! -f work/m11_winstubs.c ] || [ work/defined_c.txt -nt work/m11_winstubs.c ] || [ m11_genstubs.py -nt work/m11_winstubs.c ] || [ work/boot_final.ll -nt work/m11_winstubs.c ]; then
  M11_EXCLUDE=work/defined_c.txt python3 m11_genstubs.py work/boot_final.ll work > work/genstubs.log
  touch work/m11_winstubs.c work/m11_fnstubs.c
fi
if [ "${M11_KEEP_BOOT_O:-0}" != 1 ] || [ ! -f work/obj/boot.o ]; then cc work/boot_final3.ll work/obj/boot.o; fi   # #1756: probe_entry.sh は差し替えた probe 版 boot.o を残す
cc work/m11_simd.c work/obj/simd.o msimd11_core.h
cc work/m11_winstubs.c work/obj/winstubs.o
cc work/m11_fnstubs.c work/obj/fnstubs.o
# M11_OV_CLASSCREATE が変わったら ov.o だけ無効化 (stamp; ON/OFF の切替で古い ov.o を再リンクしない)
if [ "$(cat work/ov_classcreate.stamp 2>/dev/null || echo 0)" != "$M11_OV_CLASSCREATE" ]; then rm -f work/obj/ov.o; fi
echo "$M11_OV_CLASSCREATE" > work/ov_classcreate.stamp
# M11_OV_414AD0 が変わったら ov.o だけ無効化 (#683: ON/OFF の切替で古い ov.o を再リンクしない)
if [ "$(cat work/ov_414ad0.stamp 2>/dev/null || echo none)" != "$M11_OV_414AD0" ]; then rm -f work/obj/ov.o; fi
echo "$M11_OV_414AD0" > work/ov_414ad0.stamp
# M11_FIX_652500 が変わったら ov.o だけ無効化 (#748)
if [ "$(cat work/ov_652500.stamp 2>/dev/null || echo none)" != "$M11_FIX_652500" ]; then rm -f work/obj/ov.o; fi
echo "$M11_FIX_652500" > work/ov_652500.stamp
# M11_OV_413060 が変わったら ov.o だけ無効化 (#944)
S413="$M11_OV_413060-$M11_NEG_413060-$M11_INSTR_413060-ov$M11_OV_INSTR"
if [ "$(cat work/ov_413060.stamp 2>/dev/null || echo none)" != "$S413" ]; then rm -f work/obj/ov.o; fi
echo "$S413" > work/ov_413060.stamp
# M11_FIX_535BF2 が変わったら ov.o だけ無効化 (#714)
if [ "$(cat work/ov_535bf2.stamp 2>/dev/null || echo none)" != "$M11_FIX_535BF2" ]; then rm -f work/obj/ov.o; fi
# M11_INSTR_K12 が変わったら ov.o だけ無効化 (計測 probe の ON/OFF で古い ov.o を再リンクしない)
if [ "$(cat work/ov_instr_k12.stamp 2>/dev/null || echo none)" != "${M11_INSTR_K12:-0}" ]; then rm -f work/obj/ov.o; fi
echo "${M11_INSTR_K12:-0}" > work/ov_instr_k12.stamp
# M11_TRACE_ISOLATE が変わったら ov.o だけ無効化 (#495 のネガコン: trace の SP 退避を外した build)
if [ "$(cat work/ov_trace_isolate.stamp 2>/dev/null || echo 1)" != "${M11_TRACE_ISOLATE:-1}" ]; then rm -f work/obj/ov.o; fi
echo "${M11_TRACE_ISOLATE:-1}" > work/ov_trace_isolate.stamp
# #882: 40ff70 観測 probe の ON/OFF で古い ov.o を再リンクしない
if [ "$(cat work/ov_instr_40ff70.stamp 2>/dev/null || echo none)" != "$S_INSTR40" ]; then rm -f work/obj/ov.o; fi
# #1894: entry probe (417b70 の ov 版) の ON/OFF で古い ov.o を再リンクしない
if [ "$(cat work/ov_entry_probe.stamp 2>/dev/null || echo 0)" != "${M11_ENTRY_PROBE:-0}" ]; then rm -f work/obj/ov.o; fi
echo "${M11_ENTRY_PROBE:-0}" > work/ov_entry_probe.stamp
echo "$S_INSTR40" > work/ov_instr_40ff70.stamp
if [ "$(cat work/ov_instr_40f960.stamp 2>/dev/null || echo none)" != "${M11_INSTR_40F960:-0}" ]; then rm -f work/obj/ov.o; fi
echo "${M11_INSTR_40F960:-0}" > work/ov_instr_40f960.stamp
echo "$M11_FIX_535BF2" > work/ov_535bf2.stamp
CF="${CF_BASE//-DM11_INSTR_413060=$M11_INSTR_413060/-DM11_INSTR_413060=$M11_OV_INSTR}" cc m11_ov.c work/obj/ov.o work/boot_final3_sigs.h
cc work/m11_data.c work/obj/data.o

INITMEM="$((0x12000000))"
MAXMEM="$((0x72000000))"
EXPORTS=_m11_boot_enter,_entry_point,_m11_init_count,_m11_boot_stage,_VirtualAlloc,_VirtualFree,_m11_va_used,_m11_va_calls,_m11_va_live,_m11_va_peak,_m11_va_oom,_m11_va_freed,_m11_va_freed_bytes,_m11_va_free_unknown,_m11_va_free_skipped,_m11_va_decommit,_m11_va_big,_m11_set_vfree_noop,_m11_set_va_bigtrace,_m11_set_va_stack_at,_m11_set_va_unit_budget,_m11_va_unit_begin,_m11_va_denied,_m11_set_trace,_m11_icall_ok,_m11_icall_miss,_m11_icall_miss_uniq,_m11_icall_miss_at,_m11_icall_cnt_n,_m11_icall_cnt_key,_m11_icall_cnt_ok,_m11_icall_cnt_miss,_m11_icall_cnt_drop,_m11_disp_count,_m11_units_run,_m11_units_total,_m11_units_skipped,_m11_stub_total,_m11_stub_uniq,_m11_stub_name,_m11_stub_count,_m11_probe_count,_m11_longjmp_hit,_m11_set_survey,_m11_call_unit,_m11_unit_va,__emscripten_stack_restore,_emscripten_stack_get_current
emcc work/obj/*.o -o work/m11_boot.cjs.tmp \
  -O0 -g1 -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB -sGLOBAL_BASE="$((0x10000000))" \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=m11create \
  -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 \
  --no-entry -Wl,--export-all \
  -sEXPORTED_RUNTIME_METHODS=UTF8ToString,HEAPU8,HEAPF32,HEAP32,HEAPF64,HEAPU32,HEAP64,wasmTable,addFunction \
  -sEXPORTED_FUNCTIONS=$EXPORTS$( [ "$M11_LINK_INSTR" = 1 ] && echo ,_m11_dest_obs_n,_m11_dest_obs_hhi,_m11_dest_obs_hlo,_m11_dest_rec )$( [ "${M11_ENTRY_PROBE:-0}" = 1 ] && echo ,_m11_fe_get,_m11_fe_clear ) \
  -Wl,--initial-memory="$INITMEM" -Wl,--max-memory="$MAXMEM" 2> work/link.log || { tail -30 work/link.log; exit 1; }
mv work/m11_boot.cjs.tmp work/m11_boot.cjs
python3 m11_postjs.py work/m11_boot.cjs 2>/dev/null
echo "[m11build] OK: work/m11_boot.cjs(+.wasm)  wasm-ld signature mismatch: $(grep -c 'signature mismatch' work/link.log || true), undefined symbol: $(grep -c 'undefined symbol' work/link.log || true)"
