#!/usr/bin/env python3
"""FLEngine_x64.dll の ASIO/DirectSound vtable 呼出面を実測する。
 - ASIO: 「小関数 (<=40B) が [reg+disp] を 1 回 call する」ラッパ群のうち disp が IASIO スロット表に一致するもの
 - DirectSound: DirectSoundCreate 呼出元近傍 (±0x2000) の全関数の call [reg+disp] 集計"""
import sys, json
sys.argv = ["x"]
exec(open(__file__.replace("fl_asio_surface.py", "fl_audio_xref.py")).read().split("out = {")[0])
IASIO = {0: "QueryInterface", 8: "AddRef", 0x10: "Release", 0x18: "init", 0x20: "getDriverName", 0x28: "getDriverVersion",
         0x30: "getErrorMessage", 0x38: "start", 0x40: "stop", 0x48: "getChannels", 0x50: "getLatencies",
         0x58: "getBufferSize", 0x60: "canSampleRate", 0x68: "getSampleRate", 0x70: "setSampleRate",
         0x78: "getClockSources", 0x80: "setClockSource", 0x88: "getSamplePosition", 0x90: "getChannelInfo",
         0x98: "createBuffers", 0xa0: "disposeBuffers", 0xa8: "controlPanel", 0xb0: "future", 0xb8: "outputReady"}
anchor_lo, anchor_hi = 0xc50000, 0xc60000   # "ASIO: ... failed" 文字列を参照する関数群の近傍 (fl_audio_xref.py の anchors)
wr = []
for (b, e) in funcs:
    if anchor_lo <= base + b < anchor_hi and e - b <= 40:
        vc = vcalls((b, e))
        if len(vc) == 1:
            d = next(iter(vc))
            if d in IASIO and d >= 0x18:
                wr.append((base + b, e - b, d, IASIO[d]))
print("## ASIO wrapper functions (IASIO method called)")
for a, sz, d, n in wr:
    print(f"  {a:#x} size={sz:3d} [+{d:#04x}] {n}")
print(f"  -> {len(wr)} distinct methods:", sorted({n for *_, n in wr}))
missing = [n for d, n in IASIO.items() if d >= 0x18 and n not in {x[3] for x in wr}]
print("  not wrapped (no direct FL call):", missing)

DS = {0x18: "IDirectSound::CreateSoundBuffer | IDirectSoundBuffer::GetCaps | IDirectSoundNotify::SetNotificationPositions",
      0x20: "IDirectSoundBuffer::GetCurrentPosition | IDirectSound::GetCaps", 0x28: "IDirectSoundBuffer::GetFormat | IDirectSound::DuplicateSoundBuffer",
      0x30: "IDirectSound::SetCooperativeLevel | IDirectSoundBuffer::GetVolume", 0x58: "IDirectSoundBuffer::Lock",
      0x60: "IDirectSoundBuffer::Play", 0x68: "IDirectSoundBuffer::SetCurrentPosition", 0x70: "IDirectSoundBuffer::SetFormat",
      0x78: "IDirectSoundBuffer::SetVolume", 0x88: "IDirectSoundBuffer::SetFrequency", 0x90: "IDirectSoundBuffer::Stop",
      0x98: "IDirectSoundBuffer::Unlock"}
agg = {}
for (b, e) in funcs:
    if 0x12ae000 <= base + b < 0x12b2000:
        for d, n in vcalls((b, e)).items():
            if d in DS:
                agg.setdefault(d, 0); agg[d] += n
print("## DirectSound vtable calls (functions 0x12ae000..0x12b2000, around DirectSoundCreate/Enumerate callers)")
for d in sorted(agg):
    print(f"  [+{d:#04x}] x{agg[d]}  {DS[d]}")

# ---- FL が ASIO ドライバへ渡す ASIOCallbacks (4 関数ポインタ) の復元 ----
# createBuffers ラッパ (0xc53de0) を呼ぶ直前の `lea rax,[rip+X]` が callbacks 構造体 (Delphi packed record)。
# その +0/+8/+16/+24 への `mov [rip+..],rax` の直前の `lea rax,[rip+fn]` が各コールバック。
import re, struct
cb_struct = None
for m in re.finditer(rb"\xe8", code):
    i = m.start()
    if i + 5 > len(code): continue
    d = struct.unpack_from("<i", code, i + 1)[0]
    if base + t0 + i + 5 + d == 0xc53de0:
        pre = code[i - 14:i]
        k = pre.rfind(b"\x48\x8d\x05")
        if k >= 0:
            dd = struct.unpack_from("<i", pre, k + 3)[0]
            cb_struct = base + t0 + i - 14 + k + 7 + dd
            break
print("## ASIOCallbacks 構造体 VA =", hex(cb_struct) if cb_struct else None)
names = ["bufferSwitch", "sampleRateDidChange", "asioMessage", "bufferSwitchTimeInfo"]
if cb_struct:
    stores = {}
    for m in re.finditer(rb"\x48\x89[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]", code):
        i = m.start(); d = struct.unpack_from("<i", code, i + 3)[0]
        tgt = base + t0 + i + 7 + d
        if cb_struct <= tgt < cb_struct + 32 and (tgt - cb_struct) % 8 == 0:
            prev = code[i - 7:i]
            if prev[:3] == b"\x48\x8d\x05":
                dd = struct.unpack_from("<i", prev, 3)[0]
                stores[(tgt - cb_struct) // 8] = base + t0 + i - 7 + 7 + dd
    for k, nm in enumerate(names):
        if k in stores:
            f = func_of(stores[k] - base)
            print(f"  callbacks[{k}] {nm:21s} = {stores[k]:#x} (size {f[1]-f[0]})")
