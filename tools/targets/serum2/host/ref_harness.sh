#!/usr/bin/env bash
# SR-5 (#73): Serum 2 参照音源との dB 誤差ハーネス (bit-exact でなく許容誤差判定)。
# 参照は wine64 上の実 Serum2 DLL (native 機械語) が出した WAV (ref_render.sh)。判定は tools/flp の judgeWav (ORACLE §4)。
#
# usage: bash ref_harness.sh [candidate.wav] [class]
#   candidate.wav  wasm 側の WAV (SR-4 出力の差し込み口)。省略時は参照同士の self-test とネガコンのみ。
#   class          A-exact | B-ulp | C-statistical | D-spectral (既定 D-spectral: 参照は実 DSP の出力で bit 一致を要求しない)
# 判定結果は work/harness/ (gitignore) に出し、ここでは 1 行ずつ [OK]/[NG] を表示する。
# 参照 WAV は content dir (ref_render.sh の S2REF_CONTENT。既定は installer 全展開 = ref_content.sh) で変わる。
# pin は条件ごと: 全展開 = ref_manifest.json の主エントリ (main)、空 dir = content_empty (REPORT_SR5 §1・§4)。
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
FLP="$(cd "$HERE/../../../flp" && pwd)"
W="$HERE/work"
H="$W/harness"
CAND="${1:-}"
CLS="${2:-D-spectral}"
mkdir -p "$H"
NG=0
ok()  { echo "  [OK] $*"; }
ng()  { echo "  [NG] $*"; NG=$((NG+1)); }

judge() { # $1=a.wav $2=b.wav $3=class $4=out.json → exit 0 = PASS
  (cd "$FLP" && bun cli/wavcmp.ts "$1" "$2" "$3") > "$4" 2>&1
}
verdict() { python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print(d['verdict']['pass'], d['verdict']['why'])" "$1"; }

echo "== [1] 参照レンダ (実 DLL・既定 state・C4) × 3 回 — 決定性 (ORACLE T2) =="
for i in 1 2 3; do bash "$HERE/ref_render.sh" "$H/ref_$i" 60 > "$H/ref_$i.log" 2>&1 || { ng "ref_$i の render 失敗 ($H/ref_$i.log)"; }; done
SHA=()
for i in 1 2 3; do
  [ -f "$H/ref_$i/render_f32.wav" ] && SHA+=("$(sha256sum "$H/ref_$i/render_f32.wav" | cut -d' ' -f1)")
done
if [ "${#SHA[@]}" -eq 3 ] && [ "${SHA[0]}" = "${SHA[1]}" ] && [ "${SHA[1]}" = "${SHA[2]}" ]; then
  ok "3 回の file SHA-256 が一致 (${SHA[0]:0:16}…)"
else
  ng "SHA-256 が不一致 (${SHA[*]}) — 非決定部分を許容クラス D で判定する必要あり"
fi
REF="$H/ref_1/render_f32.wav"
CONTENT_LINE="$(grep -m1 '^content=' "$H/ref_1.log" 2>/dev/null || echo 'content=? tables=?')"
case "$CONTENT_LINE" in
  *" tables=yes") PIN_KEY=main ;;
  *)              PIN_KEY=content_empty ;;
esac
echo "  content 条件: ${CONTENT_LINE##*/} (pin = ref_manifest.json の $PIN_KEY)"
PIN=$(python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print((d if sys.argv[2]=='main' else d[sys.argv[2]])['sha256_file'])" "$HERE/ref_manifest.json" "$PIN_KEY")
if [ "${SHA[0]}" = "$PIN" ]; then
  ok "参照 sha256 が ref_manifest.json ($PIN_KEY) と一致"
else
  ng "参照 sha256 が ref_manifest.json ($PIN_KEY) と不一致 (${SHA[0]:0:16} vs ${PIN:0:16})。DLL/state/MIDI/content dir が変わった可能性"
fi

echo "== [2] 参照同士の self-test (A-exact で PASS) =="
judge "$REF" "$H/ref_2/render_f32.wav" A-exact "$H/self.json" && ok "ref_1 vs ref_2: $(verdict "$H/self.json" | cut -c1-80)" || ng "self-test が FAIL: $(verdict "$H/self.json")"

echo "== [3] ネガコン: 別ノート (C4→C#4) で FAIL すること =="
bash "$HERE/ref_render.sh" "$H/neg_pitch" 61 > "$H/neg_pitch.log" 2>&1
if judge "$REF" "$H/neg_pitch/render_f32.wav" "$CLS" "$H/neg_pitch.json"; then
  ng "別ノートが PASS した (判定が甘い): $(verdict "$H/neg_pitch.json" | cut -c1-120)"
else
  ok "別ノートを FAIL と判定: $(verdict "$H/neg_pitch.json" | cut -c1-120)"
fi

echo "== [4] ネガコン: 同一音源で 1 サンプルだけ改変 (判定が bit 差を拾うこと) =="
python3 - "$REF" "$H/neg_sample.wav" <<'PY'
import struct, sys
src, dst = sys.argv[1], sys.argv[2]
b = bytearray(open(src, "rb").read())
i = b.find(b"data")
off = i + 8 + 4 * 1000
v = struct.unpack_from("<f", b, off)[0]
struct.pack_into("<f", b, off, v + 0.01)
open(dst, "wb").write(bytes(b))
PY
if judge "$REF" "$H/neg_sample.wav" A-exact "$H/neg_sample.json"; then
  ng "1 サンプル改変が A-exact で PASS した"
else
  ok "1 サンプル改変を A-exact で FAIL: $(verdict "$H/neg_sample.json" | cut -c1-80)"
fi

echo "== [5] factory preset 参照 (SY - Action Hero) — 決定性・pin・self-test・ネガコン (SR-46 #2384) =="
PRE_ROOT="$HERE/../work/content_full/Presets/Factory"
PRE_MAIN="$PRE_ROOT/Synth/SY - Action Hero.SerumPreset"
PRE_NEG="$PRE_ROOT/Pad/PD - 1970s String Machine.SerumPreset"
if [ "$PIN_KEY" != main ]; then
  echo "  [skip] preset 参照は全展開 content のみ (現在の条件: $PIN_KEY)"
elif [ ! -f "$PRE_MAIN" ] || [ ! -f "$PRE_NEG" ]; then
  ng "preset が無い ($PRE_MAIN)。bash host/ref_content.sh で全展開を作る"
else
  for i in 1 2 3; do bash "$HERE/ref_render.sh" "$H/pre_$i" 60 "$PRE_MAIN" > "$H/pre_$i.log" 2>&1 || ng "pre_$i の render 失敗 ($H/pre_$i.log)"; done
  PSHA=()
  for i in 1 2 3; do
    [ -f "$H/pre_$i/render_f32.wav" ] && PSHA+=("$(sha256sum "$H/pre_$i/render_f32.wav" | cut -d' ' -f1)")
  done
  if [ "${#PSHA[@]}" -eq 3 ] && [ "${PSHA[0]}" = "${PSHA[1]}" ] && [ "${PSHA[1]}" = "${PSHA[2]}" ]; then
    ok "preset 3 回の file SHA-256 が一致 (${PSHA[0]:0:16}…)"
  else
    ng "preset の SHA-256 が不一致 (${PSHA[*]})。preset 描画の非決定 (REPORT_SR5 §5)"
  fi
  PPIN="$(python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print(d['presets'][sys.argv[2]]['sha256_file'])" "$HERE/ref_manifest.json" "SY - Action Hero" 2>/dev/null || echo none)"
  if [ "${PSHA[0]:-}" = "$PPIN" ]; then ok "preset sha256 が ref_manifest.json (presets) と一致"; else ng "preset sha256 が pin と不一致 (${PSHA[0]:0:16} vs ${PPIN:0:16})"; fi
  PREF="$H/pre_1/render_f32.wav"
  judge "$PREF" "$H/pre_2/render_f32.wav" A-exact "$H/pre_self.json" && ok "preset self-test (pre_1 vs pre_2): $(verdict "$H/pre_self.json" | cut -c1-80)" || ng "preset self-test が FAIL: $(verdict "$H/pre_self.json")"
  bash "$HERE/ref_render.sh" "$H/pre_neg" 60 "$PRE_NEG" > "$H/pre_neg.log" 2>&1
  if judge "$PREF" "$H/pre_neg/render_f32.wav" "$CLS" "$H/pre_neg.json"; then
    ng "別 preset (1970s String Machine) が PASS した (判定が甘い): $(verdict "$H/pre_neg.json" | cut -c1-120)"
  else
    ok "別 preset (1970s String Machine) を FAIL と判定: $(verdict "$H/pre_neg.json" | cut -c1-120)"
  fi
  S2REF_PRESET_MODE=exact bash "$HERE/ref_render.sh" "$H/pre_exact" 60 "$PRE_MAIN" > "$H/pre_exact.log" 2>&1
  EXL="$(grep -a -c 'component->setState(slot12) = kResultFalse' "$H/pre_exact/log.txt" 2>/dev/null || echo 0)"
  if judge "$PREF" "$H/pre_exact/render_f32.wav" "$CLS" "$H/pre_exact.json"; then
    ng "preset 未復元 (exact, setState=kResultFalse=$EXL) が PASS した (判定が甘い)"
  else
    ok "preset 未復元 (exact, setState=kResultFalse 行 $EXL 件) を FAIL と判定: $(verdict "$H/pre_exact.json" | cut -c1-120)"
  fi
fi

if [ -n "$CAND" ]; then
  echo "== [6] wasm 候補 ($CAND) vs 参照 ($CLS) =="
  if [ ! -f "$CAND" ]; then
    ng "候補 WAV が無い: $CAND"
  else
    judge "$REF" "$CAND" "$CLS" "$H/cand.json" && ok "候補 PASS ($CLS): $(verdict "$H/cand.json" | cut -c1-160)" || ng "候補 FAIL ($CLS): $(verdict "$H/cand.json" | cut -c1-240)"
  fi
else
  echo "== [6] wasm 候補: 未指定 (SR-4 の WAV を第 1 引数に渡すと比較する。本 run では未実施) =="
fi

echo "== 結果: NG=$NG =="
[ "$NG" -eq 0 ]
