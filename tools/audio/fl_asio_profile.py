#!/usr/bin/env python3
"""FLEngine_x64.dll の ASIO 利用面を静的検証する (AU-7 #193)。全項目 PASS で exit 0。
 A. getBufferSize: min/max/granularity は FL が読まない (出力先は呼出ラッパ自身のスタック, call 直後に ret)。pref だけが大域へ入る
 B. その pref が FL のバッファサイズ大域へコピーされ createBuffers の bufferSize 引数になる
 C. getLatencies は createBuffers 成功直後に一度読まれる (0xc57a00 内)
 D. bufferSwitchTimeInfo (0xc56ae0) が ASIOTime から読むのは flags(+0x30) と systemTime(+0x18) だけ。samplePosition(+0x20) は読まない。
    systemTime は ns/1e6 → int32 ms で、フォールバックは winmm!timeGetTime
 E. 基準ドライバ ILWASAPI2ASIO は systemTime = timeGetTime()×1e6 (コールバック時刻)、getSamplePosition(+0x88) の後に bufferSwitchTimeInfo(+0x18) を呼ぶ
使い方: FL_WIN64_DIR=<展開先> python3 tools/audio/fl_asio_profile.py [--negctl]   (--negctl: D を別関数に向け、FAIL を検出できることを確認)"""
import sys, os, re, struct
NEG = "--negctl" in sys.argv
__file__ = os.path.abspath(__file__)
sys.argv = ["x"]
exec(open(os.path.join(os.path.dirname(__file__), "fl_audio_xref.py")).read().split("out = {")[0])   # fl_asio_surface.py と同じ流儀

W_GBS, W_GL, W_CB, BSTI, BS_WRAP = 0xc53e30, 0xc53ef0, 0xc53de0, 0xc56ae0, 0xc57420   # fl_asio_surface.py の実測 (ラッパ 0xc53da0–0xc53ff0)
results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("PASS" if ok else "FAIL"), name, detail)

def fn(va, image=None, b0=None, mdx=None):
    f = func_of(va - base); assert f, hex(va)
    return base + f[0], list(md.disasm(img[f[0]:f[1]], base + f[0]))

def callers(target):
    res = []
    for m in re.finditer(rb"[\xe8\xe9]", code):
        i = m.start()
        if i + 5 <= len(code) and base + t0 + i + 5 + struct.unpack_from("<i", code, i + 1)[0] == target:
            res.append(base + t0 + i)
    return res

def riptgt(i):
    m = re.search(r"\[rip ([+-]) (0x[0-9a-f]+)\]", i.op_str)
    return i.address + i.size + int(m.group(2), 16) * (1 if m.group(1) == "+" else -1) if m else None

# A
cs = callers(W_GBS)
check("A1 getBufferSize ラッパ 0xc53e30 の呼出元は 1 箇所", len(cs) == 1, [hex(c) for c in cs])
fa, ia = fn(cs[0])
ic = next(k for k, i in enumerate(ia) if i.address == cs[0])
tail = [f"{i.mnemonic}" for i in ia[ic + 1:]]
leas = [i.op_str for i in ia[:ic] if i.mnemonic == "lea" and "[rsp +" in i.op_str]
check("A2 min/max/gran の出力先 3 つはラッパ自身のスタック (lea [rsp+X])", len(leas) == 3, leas)
check("A3 call 直後は add rsp; ret のみ = 出力先を読まない", tail[:2] == ["add", "ret"], tail[:2])
G = next((riptgt(i) for i in ia[:ic] if i.mnemonic == "lea" and i.op_str.startswith("r9,")), None)
check("A4 pref の出力先 (r9) は大域変数", G is not None, hex(G) if G else "")
# B
fc, ib = fn(callers(W_CB)[0])
kc = next(k for k, i in enumerate(ib) if i.mnemonic == "call" and i.op_str == hex(W_CB))
kg = next((k for k, i in enumerate(ib) if i.mnemonic == "mov" and i.op_str.startswith("eax, dword ptr [rip") and riptgt(i) == G), None)
Bg = riptgt(ib[kg + 1]) if kg is not None and ib[kg + 1].mnemonic == "mov" and ib[kg + 1].op_str.endswith(", eax") else None
r9 = next((riptgt(i) for i in ib[max(kc - 8, 0):kc] if i.mnemonic == "mov" and i.op_str.startswith("r9d, dword ptr [rip")), None)
check("B pref(G) → バッファサイズ大域 → createBuffers の r9d(bufferSize)", Bg is not None and Bg == r9, f"G={hex(G or 0)} B={hex(Bg or 0)} r9d<-{hex(r9 or 0)} in fn {hex(fc)}")
# C
gl = callers(W_GL)
kgl = next((k for k, i in enumerate(ib) if i.mnemonic == "call" and i.op_str == hex(W_GL)), None)
check("C getLatencies は createBuffers 成功直後 (同一関数内で call の後)", kgl is not None and kgl > kc, f"call sites={[hex(c) for c in gl]}")
# D
fd, idd = fn(BS_WRAP if NEG else BSTI)
pre = []
for i in idd:
    pre.append(i)
    if i.mnemonic == "call": break
uses = sorted(f"{i.mnemonic} {i.op_str}" for i in pre if "rcx" in i.op_str)
want = ["lea rcx, [rcx + 0x18]", "mov eax, dword ptr [rcx + 0x30]"]
check("D1 最初の call までに params(rcx) を使うのは flags(+0x30) と &systemTime(+0x18) だけ", uses == want, uses)
check("D2 params は保存されない (rcx を他レジスタ/メモリへ mov しない)", not any(i.mnemonic == "mov" and re.search(r", rcx$", i.op_str) for i in pre))
magic = (1 << 82) // 10**6 + 1
check("D3 ns→ms は /1e6 (imul 0x431bde82d7b634db; sar 0x12)", magic == 0x431bde82d7b634db and any("0x431bde82d7b634db" in i.op_str for i in idd) and any(i.mnemonic == "sar" and i.op_str.endswith("0x12") for i in idd))
fb = next((int(i.op_str, 16) for i in idd if i.mnemonic == "call" and i.op_str.startswith("0x6") and i.op_str == "0x663480"), None)
tj = md.disasm(img[fb - base:fb - base + 6], fb).__next__() if fb else None
slot = riptgt(tj) if tj else None
check("D4 フォールバック 0x663480 は winmm!timeGetTime の thunk", slot is not None and iat.get(slot - base) == ("winmm.dll", "timeGetTime"), iat.get((slot or 0) - base))
# E
pe2 = pefile.PE(os.path.join(FL_WIN64_DIR, "extracted", "block00001_PE.bin")); img2 = pe2.get_memory_mapped_image(); b2 = pe2.OPTIONAL_HEADER.ImageBase
iat2 = {imp.address - b2: imp.name.decode() for e in pe2.DIRECTORY_ENTRY_IMPORT for imp in e.imports if imp.name}
def d2(lo, hi): return list(md.disasm(img2[lo - b2:hi - b2], lo))
h = d2(0x1800039b0, 0x1800039b0 + 87)
tg = next((riptgt(i) for i in h if i.mnemonic == "call" and "rip" in i.op_str), None)
check("E1 ILWASAPI 0x1800039b0 は timeGetTime を呼び ×1e6 級の double 演算で ASIOTimeStamp{hi,lo} を作る",
      iat2.get((tg or 0) - b2) == "timeGetTime" and sum(i.mnemonic == "mulsd" for i in h) >= 3, iat2.get((tg or 0) - b2))
s = d2(0x1800032e0, 0x1800032e0 + 145)
o = [i.op_str for i in s if i.mnemonic == "call"]
check("E2 ILWASAPI のコールバック発火: 0x1800039b0 → vtable+0x88(getSamplePosition) → callbacks+0x18(bufferSwitchTimeInfo)",
      o[:3] == ["0x1800039b0", "qword ptr [rax + 0x88]", "qword ptr [rax + 0x18]"], o[:3])

print(f"{sum(results)}/{len(results)} PASS")
if NEG:
    print("negctl: D を bufferSwitch ラッパ (0xc57420) に向けた → D1/D3/D4 が FAIL すれば検出能力あり")
    sys.exit(0 if not all(results) else 1)
sys.exit(0 if all(results) else 1)
