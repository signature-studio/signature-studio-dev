#!/usr/bin/env bash
# Negative control (規則 41) for FFmpeg: 合否判定 (復号 PCM hash 一致) が実際に
# デコーダの出力を見ていることを確認する。
#   1) 正常 FLAC を復号 -> PCM hash (baseline)
#   2) FLAC の音声フレーム 1B 反転 -> hash 不一致 or エラー (検出)
#   3) WAV の PCM データ 1 サンプルを +1 -> 復号 PCM hash 不一致 (検出)
# usage: bash oss/ffmpeg/negctl.sh (事前に bash oss/ffmpeg/build.sh)
set -euo pipefail
PATH="/home/ubuntu/.local/share/pnpm/bin:$PATH"
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
B="$ROOT/work/build/ffmpeg"
FLAC="$ROOT/work/build/flac/negctl/ok.flac"
[ -x "$B/native-test" ] && [ -f "$FLAC" ] || { echo "[neg] 先に build.sh と oss/flac/build.sh を実行"; exit 2; }
W="$B/negctl"; mkdir -p "$W"; cd "$W"
echo "=== negative control (FFmpeg 4.4.2) ==="
hash_of() { "$1" "$2" 2>/dev/null | grep -oE "pcm_hash=[0-9a-f]+" | head -1; }
H0=$(hash_of "$B/native-test" "$FLAC")
echo "[neg] baseline FLAC decode: $H0"

# (2) FLAC の音声フレーム 1B 反転
cp "$FLAC" "$W/bad.flac"
python3 - "$W/bad.flac" <<'PY'
import sys
p=sys.argv[1]; d=bytearray(open(p,'rb').read())
i=d.find(b'\xff\xf8')
if i<0: i=300
d[i+200] ^= 0xff
open(p,'wb').write(bytes(d))
PY
H1=$(hash_of "$B/native-test" "$W/bad.flac")
if [ "$H1" != "$H0" ] || [ -z "$H1" ]; then echo "[neg] CAUGHT FLAC 1B 反転: ${H1:-decode-error}"; else echo "[neg] MISSED FLAC 1B 反転 ($H1)"; exit 1; fi

# (3) WAV の PCM データ 1 サンプル +1 (gen.wav が無ければその場で作る)
[ -s "$B/gen.wav" ] || python3 - "$B/gen.wav" <<'PY'
import sys, wave, struct
out=sys.argv[1]
x1=0.037; x2=-0.021; yl=0.0; yr=0.013; s=88172645463325252
frames=11025; buf=bytearray()
for i in range(frames):
    s ^= (s<<13)&0xFFFFFFFFFFFFFFFF; s ^= s>>7; s ^= (s<<17)&0xFFFFFFFFFFFFFFFF
    xn=((s>>40)/16777216.0)*2.0-1.0
    yl=0.9821*yl-0.0179*x1+0.0007*x2+xn*0.31
    yr=0.9821*yr-0.0179*x2+0.0007*x1+xn*0.29
    x2=x1; x1=xn
    vl=max(-1.0,min(1.0,yl*0.5)); vr=max(-1.0,min(1.0,yr*0.5))
    buf+=struct.pack('<hh', int(vl*32000), int(vr*32000))
with wave.open(out,'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(44100); w.writeframes(bytes(buf))
PY
python3 - "$B/gen.wav" "$W/bad.wav" <<'PY'
import sys, wave, struct
a,b=sys.argv[1],sys.argv[2]
with wave.open(a,'rb') as w:
    params=w.getparams(); frames=bytearray(w.readframes(w.getnframes()))
frames[100] = (frames[100] + 1) & 0xff      # 先頭から 100B 目の 1 サンプルを +1
with wave.open(b,'wb') as w:
    w.setparams(params); w.writeframes(bytes(frames))
PY
HW0=$(hash_of "$B/native-test" "$B/gen.wav")
HW1=$(hash_of "$B/native-test" "$W/bad.wav")
if [ "$HW1" != "$HW0" ] || [ -z "$HW1" ]; then echo "[neg] CAUGHT WAV 1 sample: $HW1 != $HW0"; else echo "[neg] MISSED WAV 1 sample"; exit 1; fi
exit 0
