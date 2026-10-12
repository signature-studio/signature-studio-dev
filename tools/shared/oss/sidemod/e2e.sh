#!/usr/bin/env bash
# LGL-4 e2e: side module のロード・動作 + GPL 検出 CI (ネガコン込み)。rc=0 で全 PASS。
#   usage: bash oss/sidemod/e2e.sh [--no-build]
#   1) build.sh (configure 前の GPL 検出 → 再ビルド → 成果物検査)
#   2) host.cjs (MAIN_MODULE) が ffmpeg.wasm / lame.wasm を dlopen し、native の .so 版と同じ結果を出す
#   3) 差し替え: 別パスにコピーした side module でも同じ結果 (dlopen のパスだけで差し替え可能)
#   4) 検出ネガコン: --enable-gpl / --enable-version3 / --enable-libx264 / mpglib 混入で必ず落ちる
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
B="$ROOT/work/build/sidemod"; G="$HERE/check_license_flags.py"
export SS_EMSDK_ENV="${SS_EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}"
[ -f "$SS_EMSDK_ENV" ] || { echo "[e2e] emsdk_env.sh not found: $SS_EMSDK_ENV"; exit 2; }
export TMPDIR="${TMPDIR:-${RUNNER_TEMP:-/tmp}}"
source "$SS_EMSDK_ENV" >/dev/null 2>&1
T0=$(date +%s)
[ "${1:-}" = "--no-build" ] || bash "$HERE/build.sh" 2>&1 | grep -E '^\[sidemod\]|GPL-GUARD'
FAIL=0; ok() { echo "[e2e] PASS $*"; }; ng() { echo "[e2e] FAIL $*"; FAIL=1; }

echo "=== 0. 検出テスト自己検査 ==="
python3 "$G" selftest | tail -1

echo "=== 入力 (WAV: 乱数 PCM / FLAC・MP3 は他 e2e の成果があれば追加) ==="
mkdir -p "$B/in"
python3 - "$B/in/gen.wav" <<'PY'
import sys, wave, struct
x1=0.037; x2=-0.021; yl=0.0; yr=0.013; s=88172645463325252; buf=bytearray()
for i in range(11025):
    s ^= (s<<13)&0xFFFFFFFFFFFFFFFF; s ^= s>>7; s ^= (s<<17)&0xFFFFFFFFFFFFFFFF
    xn=((s>>40)/16777216.0)*2.0-1.0
    yl=0.9821*yl-0.0179*x1+0.0007*x2+xn*0.31; yr=0.9821*yr-0.0179*x2+0.0007*x1+xn*0.29
    x2=x1; x1=xn
    buf+=struct.pack('<hh', int(max(-1,min(1,yl*0.5))*32000), int(max(-1,min(1,yr*0.5))*32000))
with wave.open(sys.argv[1],'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(44100); w.writeframes(bytes(buf))
PY
INS="$B/in/gen.wav"
# 同じ side module が作った MP3 も入力にする (LAME → FFmpeg の往復)。1 回目は host が生成するので 2 パス
echo "=== 1. native 基準 (.so を dlopen) ==="
"$B/host-native" "$B/ffmpeg-native.so" "$B/lame-native.so" "$B/out-native.mp3" $INS > "$B/native.txt"
"$B/host-native" "$B/ffmpeg-native.so" "$B/lame-native.so" "$B/out-native.mp3" $INS "$B/out-native.mp3" > "$B/native.txt"

echo "=== 2. wasm side module を MAIN_MODULE から dlopen ==="
( cd "$B" && node host.cjs ffmpeg.wasm lame.wasm out-wasm.mp3 in/gen.wav out-wasm.mp3 > wasm.txt )
sel() { grep -E '^(LAME|DECODE)' "$1" | sed -E 's#(DECODE )[^ :]*/#\1#; s#out-(native|wasm|swap)#out-X#g'; }
sel "$B/native.txt" > "$B/native.sel"; sel "$B/wasm.txt" > "$B/wasm.sel"
sed 's/^/    /' "$B/wasm.sel"
grep -q '^SIDE ffmpeg abi=1 license="LGPL version 2.1 or later"' "$B/wasm.txt" && ok "ffmpeg.wasm ロード: abi=1 license=LGPL version 2.1 or later" || ng "ffmpeg.wasm license"
grep -q '^SIDE lame abi=1 version=3.99.5' "$B/wasm.txt" && ok "lame.wasm ロード: abi=1 version=3.99.5" || ng "lame.wasm load"
if diff -q "$B/native.sel" "$B/wasm.sel" >/dev/null; then ok "wasm side module == native .so (LAME stream hash / DECODE pcm_hash 一致)"; else ng "wasm != native"; diff "$B/native.sel" "$B/wasm.sel" || true; fi
cmp -s "$B/out-native.mp3" "$B/out-wasm.mp3" && ok "MP3 出力バイト列 native == wasm" || ng "MP3 bytes differ"
grep -q 'codec=mp3' "$B/wasm.sel" && ok "LAME 出力を FFmpeg side module が mp3 として復号" || ng "mp3 roundtrip"

echo "=== 3. 差し替え (別パスの side module を dlopen) ==="
mkdir -p "$B/swap"; cp "$B/ffmpeg.wasm" "$B/swap/ffmpeg-replaced.wasm"; cp "$B/lame.wasm" "$B/swap/lame-replaced.wasm"
( cd "$B" && node host.cjs swap/ffmpeg-replaced.wasm swap/lame-replaced.wasm out-swap.mp3 in/gen.wav out-swap.mp3 > swap.txt )
sel "$B/swap.txt" > "$B/swap.sel"
diff -q "$B/wasm.sel" "$B/swap.sel" >/dev/null && ok "パス差し替えで同一結果 (host の再リンク不要)" || ng "swap differs"
# ABI 不整合 (存在しない side module) は host が明示エラーで落ちる
( cd "$B" && ! node host.cjs swap/none.wasm lame.wasm x.mp3 in/gen.wav >/dev/null 2>&1 ) && ok "存在しない side module は dlopen 失敗で rc!=0" || ng "missing module not rejected"
# 依存の分離: host / side module の import に FL 由来シンボルが無い (env 以外の import だけ確認)
node -e '
const fs=require("fs");
for (const f of ["ffmpeg.wasm","lame.wasm"]) {
  const m=new WebAssembly.Module(fs.readFileSync(process.argv[1]+"/"+f));
  const mods=[...new Set(WebAssembly.Module.imports(m).map(i=>i.module))];
  const ex=WebAssembly.Module.exports(m).filter(e=>e.name.startsWith("ss_")).map(e=>e.name);
  console.log("[e2e] "+f+" imports from "+JSON.stringify(mods)+" ; ss_* exports="+ex.length);
  if (mods.some(x=>x!=="env"&&x!=="wasi_snapshot_preview1"&&x!=="GOT.mem"&&x!=="GOT.func")) process.exit(1);
}' "$B" && ok "side module の import は env/GOT/wasi のみ (他の wasm への直接依存なし)" || ng "unexpected import module"

echo "=== 4. 検出ネガコン (混入すると必ず落ちる) ==="
FFA="$(cat "$B/ffmpeg.configure")"
neg() { # name expected-fail command...
  local n="$1"; shift
  if "$@" >/dev/null 2>&1; then ng "NEG MISSED: $n (混入しても通った)"; else ok "NEG CAUGHT: $n"; fi
}
neg "--enable-gpl"       python3 "$G" config "$FFA --enable-gpl"
neg "--enable-version3"  python3 "$G" config "$FFA --enable-version3"
neg "--enable-nonfree"   python3 "$G" config "$FFA --enable-nonfree"
neg "--enable-libx264"   python3 "$G" config "$FFA --enable-libx264"
neg "--enable-libx265"   python3 "$G" config "$FFA --enable-libx265"
neg "LAME --disable-decoder 欠落 (mpglib)" python3 "$G" lame "--disable-shared" -- /dev/null
sed 's/CONFIG_GPL 0/CONFIG_GPL 1/' "$B/ffmpeg-config.h" > "$B/neg-config.h"
neg "config.h CONFIG_GPL=1" python3 "$G" configh "$B/neg-config.h"
# 実ビルドに対するネガコン: GPL フラグを build.sh に注入すると configure 前に落ちてビルドされない
if FF_EXTRA_ARGS="--enable-gpl" bash "$HERE/build.sh" >"$B/neg-build.log" 2>&1; then ng "NEG MISSED: build.sh に --enable-gpl を注入しても成功した"; else
  grep -q 'GPL-GUARD FAIL: forbidden configure flag: --enable-gpl' "$B/neg-build.log" && ok "NEG CAUGHT: build.sh + FF_EXTRA_ARGS=--enable-gpl は configure 前に失敗" || ng "build failed for another reason"; fi
if FF_EXTRA_ARGS="--enable-version3" bash "$HERE/build.sh" >"$B/neg-build2.log" 2>&1; then ng "NEG MISSED: --enable-version3 build"; else
  grep -q 'forbidden configure flag: --enable-version3' "$B/neg-build2.log" && ok "NEG CAUGHT: build.sh + FF_EXTRA_ARGS=--enable-version3 は失敗" || ng "build failed for another reason (version3)"; fi
# build.sh が失敗しても成果物は壊れていない (guard は configure 前なので work/build を触らない) ことを再確認
python3 "$G" artifact "$B/ffmpeg.wasm" "$B/lame.wasm" "$B/ffmpeg-config.h" >/dev/null && ok "ネガコン後も成果物は検査クリーン" || ng "artifact dirty after negctl"

echo "[e2e] elapsed $(( $(date +%s) - T0 )) s, loadavg $(cut -d' ' -f1-3 /proc/loadavg), nproc $(nproc)"
[ $FAIL = 0 ] && echo "[e2e] ALL PASS" || echo "[e2e] SOME FAILED"
exit $FAIL
