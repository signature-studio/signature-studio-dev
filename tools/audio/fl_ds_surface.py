#!/usr/bin/env python3
"""FLEngine_x64.dll の DirectSound 利用面を「受け手 (this) 別」に静的抽出する (AU-4 #189)。

fl_asio_surface.py は 0x12ae000..0x12b2000 の `call [reg+disp]` を disp だけで集計するため、
IDirectSound / IDirectSoundBuffer / IDirectSoundNotify と Delphi オブジェクトの仮想呼出 (SetVolume/SetFrequency 等) を
区別できない。本スクリプトは rcx (this) がロードされた rip 相対グローバルを追跡して受け手を分類し、
併せて FL が組み立てる WAVEFORMATEX(EXTENSIBLE) の形式 (16bit PCM / float32) を決める分岐を機械的に確認する。

出力: stdout (results/ds_static.txt の生成元)。再現: bash tools/audio/ds_static.sh
入力: $FL_WIN64_DIR/extracted/block00031_PE.bin (tools/shared/env.sh)。依存: pefile, capstone。"""
import sys, re, struct, collections, os
sys.argv = ["x"]
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "fl_audio_xref.py")).read().split("out = {")[0])

DS_LO, DS_HI = 0x12ae000, 0x12b2000
SLOTS = {0x16bd4f8: "IDirectSound", 0x16bd500: "primary IDirectSoundBuffer",
         0x16bd498: "secondary IDirectSoundBuffer", 0x16bd508: "IDirectSoundNotify"}
METHODS = {
    "IDirectSound": {0x00: "QueryInterface", 0x18: "CreateSoundBuffer", 0x30: "SetCooperativeLevel"},
    "primary IDirectSoundBuffer": {0x28: "GetFormat", 0x70: "SetFormat"},
    "secondary IDirectSoundBuffer": {0x00: "QueryInterface", 0x20: "GetCurrentPosition", 0x58: "Lock", 0x60: "Play",
                                     0x68: "SetCurrentPosition", 0x90: "Stop", 0x98: "Unlock"},
    "IDirectSoundNotify": {0x18: "SetNotificationPositions"},
}

def rip_target(ins):
    m = re.search(r"rip ([+-]) (0x[0-9a-f]+)", ins.op_str)
    if not m: return None
    return ins.address + ins.size + int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)

rows = []
for (b, e) in funcs:
    if not (DS_LO <= base + b < DS_HI): continue
    last = {}
    for ins in md.disasm(img[b:e], base + b):
        m = re.match(r"(\w+), qword ptr \[rip [+-] 0x[0-9a-f]+\]$", ins.op_str)
        if ins.mnemonic == "mov" and m:
            last[m.group(1)] = rip_target(ins)
        elif ins.mnemonic == "lea" and "rip" in ins.op_str:
            last.pop(ins.op_str.split(",")[0], None)
        elif ins.mnemonic == "mov" and re.match(r"\w+, \w+$", ins.op_str):
            a, c = ins.op_str.split(", ")
            if c in last: last[a] = last[c]
            else: last.pop(a, None)
        if ins.mnemonic == "call" and "ptr [" in ins.op_str and "rip" not in ins.op_str:
            mm = re.search(r"\[(\w+)(?: \+ (0x[0-9a-f]+))?\]", ins.op_str)
            if not mm: continue
            d = int(mm.group(2), 16) if mm.group(2) else 0
            recv = last.get("rcx")
            if recv is not None and last.get(mm.group(1)) is not None and last.get(mm.group(1)) != recv:
                recv = None   # vtable を引いたレジスタの出所が this と別グローバル = 関数ポインタ呼出 (COM 呼出ではない)
            rows.append((base + b, ins.address, d, recv))

print("## DirectSound 呼出面 (受け手 = rcx のロード元 rip 相対グローバル; 0x12ae000..0x12b2000)")
agg = collections.Counter()
other = collections.Counter()
for fn, site, d, recv in rows:
    cls = SLOTS.get(recv)
    if cls and d in METHODS[cls]:
        agg[(cls, METHODS[cls][d])] += 1
    else:
        other[(hex(recv) if recv else "?", hex(d))] += 1
for (cls, name), n in sorted(agg.items()):
    print(f"  {cls:30s} {name:26s} x{n}")
print("## DS オブジェクト以外への仮想呼出 (Delphi 側。disp 衝突で INVENTORY §2 の集計に混入していたもの)")
for (r, d), n in sorted(other.items()):
    print(f"  receiver {r:10s} [+{d}] x{n}")

# ---- 形式決定の確認 -------------------------------------------------------------------------
print("## バッファ形式の決定 (primary SetFormat 組立 0x12afcd0..0x12afd3d)")
def fn_ins(addr):
    for (b, e) in funcs:
        if b <= addr - base < e: return list(md.disasm(img[b:e], base + b))
L = fn_ins(0x12afb50)
flag = [i for i in L if i.address == 0x12afcd0][0]
FLAG = rip_target(flag)
print(f"  0x12afcd0 cmp byte [{FLAG:#x}], 0 ; jne 経路 → 0x674e50(wfx, tag=0xFFFE, rate, bits=0x20, ch=2) / 0 経路 → 0x674e10(wfx, rate, bits=0x10, ch=2)")
ex = {i.address: i for i in L}
assert ex[0x12afce0].op_str == "edx, 0xfffe" and ex[0x12afcef].op_str == "r9d, 0x20"
assert ex[0x12afd14].op_str == "r8d, 0x10" and ex[0x12afd1a].op_str == "r9d, 2"
g = rip_target([i for i in fn_ins(0x674e50) if i.address == 0x674e6e][0])
guid = bytes(img[g - base:g - base + 16])
import uuid
print(f"  0x674e50: wFormatTag=dx(0xFFFE) cbSize=0x16 wValidBitsPerSample=0x20 dwChannelMask=3 (FL+FR) SubFormat={uuid.UUID(bytes_le=guid)} (= KSDATAFORMAT_SUBTYPE_IEEE_FLOAT)")
print(f"  0x674e10: wFormatTag=1 (PCM) cbSize=0")
# 形式フラグのオプション対応: ctl+0xc38/0xc40/0xc48 → 3 つの bool グローバル (0x135b000 の同期関数)
f135 = fn_ins(0x135b000)
tbl = []
for i, ins in enumerate(f135):
    m = re.match(r"rax, qword ptr \[rip [+-] 0x[0-9a-f]+\]$", ins.op_str)
    if ins.mnemonic == "mov" and m:
        slot = rip_target(ins)
        nxt = f135[i + 1].op_str
        off = re.search(r"\+ (0xc[0-9a-f]+)\]", nxt)
        if off: tbl.append((int(off.group(1), 16), struct.unpack_from("<Q", img, slot - base)[0]))
print("  設定→bool グローバル (0x135b000: ctl[+off]->byte[+0x49e] を bool へコピー):", ", ".join(f"ctl+{o:#x}->{v:#x}" for o, v in tbl))
# 他 2 つの bool の用途 (secondary 作成フラグ)
f5c0 = fn_ins(0x12af5c0)
use = {}
for i, ins in enumerate(f5c0):
    if ins.mnemonic == "cmp" and ins.op_str.endswith(", 0") and "byte ptr [rip" in ins.op_str:
        t = rip_target(ins)
        nxt = f5c0[i + 2]
        what = nxt.op_str if nxt.mnemonic == "or" else f"{f5c0[i + 1].mnemonic} {f5c0[i + 1].op_str} (通知設定をスキップ)"
        use.setdefault(t, []).append(f"{ins.address:#x}: {what}")
for t, s in sorted(use.items()):
    print(f"  0x12af5c0: byte [{t:#x}] の参照: " + " / ".join(s))
print("  → 0x15d3294 != 0 で IDirectSoundNotify 設定をスキップ (0 のとき DSBCAPS_CTRLPOSITIONNOTIFY=0x100 を要求) = 'pollbox' (ポーリング) と整合。0x15d3295 == 0 で DSBCAPS_LOCSOFTWARE=0x8 = 'hardbufbox' (ハードウェアバッファ) の否定と整合。残る 0x15d3296 が形式フラグ = 'ds_32bitbufbox' (UI 名との対応は用途の整合による推定。形式フラグが分岐を決める事実自体は上記 0x12afcd0 の命令列から確定。DFM フィールド表は未解析)")
# 初期値 (静的イメージ)
print(f"  静的イメージ上の初期値: byte[0x15d3294]={img[0x15d3294-base]} byte[0x15d3295]={img[0x15d3295-base]} byte[0x15d3296]={img[0x15d3296-base]} (実際の値は保存設定 (FL の設定ファイル) 由来で静的には不定)")
# secondary は primary と同じ wfx を使う
sec = [i for i in f5c0 if i.address == 0x12af716][0]
print(f"  secondary の lpwfxFormat = lea [rip+..] = {rip_target(sec):#x}  (primary SetFormat が渡す wfx {rip_target(ex[0x12afd2c]):#x} と同一 = secondary も同形式)")
print(f"  secondary dwFlags 基底 0x18000 (GETCURRENTPOSITION2|GLOBALFOCUS) | 0x100 (非ポーリング時) | 0x8 (ソフトウェア時)")
# 書込み側分岐 (0x12af12b)
print("## secondary への書込み (0x12aeec0 の Lock 後)")
print("  cmp word [0x16bd4be](=wBitsPerSample), 0x20 → 0x20 なら関数ポインタ [0x15e2d40] 経由 (引数 count = bytes>>3 = ステレオ float32 のフレーム数) / それ以外は 0x12c7420 (count = bytes>>2 = ステレオ 16bit のフレーム数) で 16bit PCM へ変換。変換の係数 (xmm2/xmm3 定数)・ディザ/クリップの有無は未解析")
print("## 通知位置 (0x12af82f..0x12af886): 2 点。ループ ecx=0..1 で offset_i = (i*A + B) mod C (idiv; A/B/C は 0x16bd4xx のグローバルで内訳は未解析)、各要素の 2 つ目の 8 バイトはイベントハンドル表から")
print("## secondary 総長 (0x12af67e..0x12af698): [0x16bd4a8] = X × nBlockAlign、[0x16bd4a4] = 2 × [0x16bd4a8] (X = 設定のバッファ長由来のフレーム数、下限 0x80)")
print("## GetCurrentPosition (arg: rdx=play, r8=write): 0x12aef11 は r8=NULL (play のみ取得)、0x12af1e5 は rdx=NULL (write のみ取得)")
