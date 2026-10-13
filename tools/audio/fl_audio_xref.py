#!/usr/bin/env python3
"""FLEngine_x64.dll のオーディオ/MIDI 呼出面を実測する。

1. IAT スロット (DirectSoundCreate/midiIn*/... ) への `call [rip+disp]` 参照元関数を .pdata で解決
2. 文字列アンカー (ASIO/DirectSound エラーメッセージ) を参照する関数を解決
3. 各関数内の `call qword ptr [reg+disp]` (COM/ASIO vtable 呼出) の disp 集計
出力: JSON (--json path) と stdout。"""
import sys, os, re, struct, json, bisect, collections
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared"))
from paths import FL_WIN64_DIR

PATH = os.path.join(FL_WIN64_DIR, "extracted", "block00031_PE.bin")
pe = pefile.PE(PATH)
img = pe.get_memory_mapped_image()
base = pe.OPTIONAL_HEADER.ImageBase
md = Cs(CS_ARCH_X86, CS_MODE_64)

text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
t0, t1 = text.VirtualAddress, text.VirtualAddress + text.Misc_VirtualSize

# .pdata
pd = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".pdata"][0]
pdd = img[pd.VirtualAddress:pd.VirtualAddress + pd.Misc_VirtualSize]
funcs = []
for i in range(0, len(pdd) - 11, 12):
    b, e, _ = struct.unpack_from("<III", pdd, i)
    if b == 0: break
    funcs.append((b, e))
funcs.sort()
fstarts = [f[0] for f in funcs]

def func_of(rva):
    k = bisect.bisect_right(fstarts, rva) - 1
    if k >= 0 and funcs[k][0] <= rva < funcs[k][1]:
        return funcs[k]
    return None

# IAT map
iat = {}
for e in pe.DIRECTORY_ENTRY_IMPORT:
    for imp in e.imports:
        if imp.name:
            iat[imp.address - base] = (e.dll.decode().lower(), imp.name.decode())

# 参照スキャン: lea [rip+disp32] / jmp [rip+IAT] thunk / call thunk (e8)
code = img[t0:t1]
lea_refs = collections.defaultdict(list)   # target rva -> [site rva]
iat_calls = collections.defaultdict(list)  # (dll,name) -> [site rva]
thunks = {}                                # thunk rva -> (dll,name)
for m in re.finditer(rb"(?:\x48|\x4c)\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]", code):
    i = m.start()
    d = struct.unpack_from("<i", code, i + 3)[0]
    lea_refs[t0 + i + 7 + d].append(t0 + i)
for m in re.finditer(rb"\xff\x25", code):
    i = m.start()
    d = struct.unpack_from("<i", code, i + 2)[0]
    tgt = t0 + i + 6 + d
    if tgt in iat:
        thunks[t0 + i] = iat[tgt]
for m in re.finditer(rb"[\xe8\xe9]", code):
    i = m.start()
    if i + 5 > len(code): continue
    d = struct.unpack_from("<i", code, i + 1)[0]
    tgt = t0 + i + 5 + d
    if tgt in thunks:
        iat_calls[thunks[tgt]].append(t0 + i)

def vcalls(f):
    b, e = f
    res = collections.Counter()
    for ins in md.disasm(img[b:e], base + b):
        if ins.mnemonic == "call" and "ptr [" in ins.op_str and "rip" not in ins.op_str:
            m = re.search(r"\[(\w+)(?: \+ (0x[0-9a-f]+))?\]", ins.op_str)
            if m:
                res[int(m.group(2), 16) if m.group(2) else 0] += 1
    return res

def find_str(s):
    hits = []
    for enc in ("ascii", "utf-16le"):
        n = s.encode(enc)
        i = 0
        while True:
            i = img.find(n, i)
            if i < 0: break
            hits.append((enc, i)); i += 1
    return hits

out = {"iat_callers": {}, "anchors": {}}
want = [k for k in iat_calls if k[0] in ("dsound.dll", "winmm.dll", "msacm32.dll") and
        (k[0] != "winmm.dll" or k[1].startswith(("midi", "time")))]
for k in sorted(want):
    fs = sorted({func_of(s) for s in iat_calls[k] if func_of(s)})
    out["iat_callers"][f"{k[0]}!{k[1]}"] = [{"fn": hex(base + f[0]), "size": f[1] - f[0]} for f in fs]

ANCH = ["ASIO: CreateBuffers failed with error %d", "ASIO: GetLatencies failed with error %d",
        "ASIO: GetSamplePosition failed with error %d", "ASIO: GetSampleRate failed with error %d",
        "ASIO driver is not open.", "Couldn't create the primary DirectSound buffer.",
        "Couldn't create the streaming ASIO buffer.", "Couldn't init the ASIO driver.",
        "Couldn't open the ASIO driver.", "Error while accessing the ASIO driver.",
        "Could not open ASIO control panel: ", "MIDI input overflow detected"]
for a in ANCH:
    rows = []
    for enc, off in find_str(a):
        for site in lea_refs.get(off, []):
            f = func_of(site)
            if f:
                vc = vcalls(f)
                rows.append({"enc": enc, "fn": hex(base + f[0]), "size": f[1] - f[0],
                             "vtable_disp": {hex(k): v for k, v in sorted(vc.items())}})
    out["anchors"][a] = rows

print(json.dumps(out, indent=1))
if "--json" in sys.argv:
    json.dump(out, open(sys.argv[sys.argv.index("--json") + 1], "w"), indent=1)
