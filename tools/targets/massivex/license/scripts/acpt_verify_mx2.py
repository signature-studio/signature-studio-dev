#!/usr/bin/env python3
"""CAB-250 (MX-2) 検収: 独立再計算 (検収 agent 側・別アルゴリズム)。

1. stub 12 点の実在: IR (!insn.addr) と機械語の両方で確認
   - 3 評価関数 (evaluateRAS2 0x18115de60 / productCheckSerialNumber 0x1805b3510 /
     productGetSubscription 0x1805b3ad0) が IR に define として存在
   - 12 差し替え点 (N1a,N1b,N1c,N2a,N2b,N2c,N2d,N2e,N3a,N3b,N3c,N3d) の machine VA が
     raw IR のメタデータに存在し、patched IR で br/store が実際に変わっている
2. patched / 未 patch の IR 差分 (別集計: br_i1 数・store const 数・到達性)
3. JWT 「到達不能」主張の検証 (直接 call / vtable / 静的VA参照 の 3 方向から)
4. N1-N8 (CAB-46 REPORT §6) の実在確認 (mechan 語 + 文字列)

usage: verify_mx2.py <license_work_dir> <pe>
"""
import sys, os, re, json, struct, collections
import capstone, pefile
from capstone import CS_ARCH_X86, CS_MODE_64

WORK = sys.argv[1]
PE = sys.argv[2]
out = {}

FNS = {0x18115de60: 'evaluateRAS2ActivationState', 0x1805b3510: 'productCheckSerialNumber',
       0x1805b3ad0: 'productGetSubscription'}
RULES = [('N1a', 0x18115de60, 0x18115e038), ('N1b', 0x18115de60, 0x18115e142),
         ('N1c', 0x18115de60, 0x18115e88d), ('N2a', 0x1805b3510, 0x1805b36d6),
         ('N2b', 0x1805b3510, 0x1805b36e9), ('N2c', 0x1805b3510, 0x1805b37d5),
         ('N2d', 0x1805b3510, 0x1805b3843), ('N2e', 0x1805b3510, 0x1805b3819),
         ('N3a', 0x1805b3ad0, 0x1805b3c99), ('N3b', 0x1805b3ad0, 0x1805b3cac),
         ('N3c', 0x1805b3ad0, 0x1805b3cd7), ('N3d', 0x1805b3ad0, 0x1805b3d88)]

def load_ir(p):
    return open(p).read().splitlines()

def ir_meta(lines):
    m = {}
    for l in lines:
        x = re.match(r'^!(\d+)\s*=\s*!\{i64 (\d+)\}', l.strip())
        if x: m[int(x.group(1))] = int(x.group(2))
    return m

def stats(lines):
    return dict(defines=sum(1 for l in lines if l.startswith('define')),
                br_i1=sum(1 for l in lines if re.match(r'^\s*br i1', l)),
                br_uncond=sum(1 for l in lines if re.match(r'^\s*br label', l)),
                store=sum(1 for l in lines if re.match(r'^\s*store ', l)),
                store_const=sum(1 for l in lines if re.match(r'^\s*store \S+ -?\d+,', l)),
                call=sum(1 for l in lines if re.match(r'^\s*(?:%\S+ = )?call ', l)),
                lines=len(lines))

# --- 1+2: IR 側 ---
lic_raw = os.path.join(WORK, 'lift/lic.drc.ll')
eng_raw = os.path.join(WORK, 'lift/eng.drc.ll')
lic_pat = os.path.join(WORK, 'lic_patched.ll')
eng_pat = os.path.join(WORK, 'eng_patched.ll')
for tag, p in (('lic_raw', lic_raw), ('eng_raw', eng_raw), ('lic_patched', lic_pat), ('eng_patched', eng_pat)):
    if os.path.exists(p):
        L = load_ir(p)
        out[tag + '_stats'] = stats(L)
        out[tag + '_defines'] = sorted(set(re.findall(r'define \S+ @(function_[0-9a-f]+)\(', '\n'.join(L))))
    else:
        out[tag + '_stats'] = None

# 差し替え点の VA が raw にあり patched で br が単一化されているか
check = {}
for rid, fnva, at in RULES:
    src = lic_raw if fnva == 0x18115de60 else eng_raw
    dst = lic_pat if fnva == 0x18115de60 else eng_pat
    if not (os.path.exists(src) and os.path.exists(dst)): continue
    meta_before = ir_meta(load_ir(src))
    meta_after = ir_meta(load_ir(dst))
    va_in = at in set(meta_before.values())
    # patched 側: その !insn.addr に対応する br が無条件化しているか
    dm = {v: k for k, v in meta_after.items()}
    idn = dm.get(at)
    unconditional = False
    if idn is not None:
        for l in load_ir(dst):
            if ('!insn.addr !%s' % idn) in l and re.match(r'^\s*br label', l):
                unconditional = True
    check[rid] = dict(machine_VA_in_raw_IR=va_in, patched_br_unconditional=unconditional)
out['rules_ir_check'] = check

# --- 3: JWT 到達不能の検証 (3 方向) ---
pe = pefile.PE(PE, fast_load=True)
data = open(PE, 'rb').read()
base = pe.OPTIONAL_HEADER.ImageBase
t = next(s for s in pe.sections if s.Name.rstrip(b'\0').decode() == '.text')
t_lo, t_hi = t.VirtualAddress, t.VirtualAddress + t.Misc_VirtualSize
md = capstone.Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
blob = data[t.PointerToRawData:t.PointerToRawData + t.Misc_VirtualSize]
JWT = [0x181754f70, 0x180f94350, 0x18116fb20]
STUB = [0x18115de60, 0x1805b3510, 0x1805b3ad0]
j = {}
for va in JWT + STUB:
    rva = va - base
    sites = [i for i in range(len(blob) - 5) if blob[i] in (0xE8, 0xE9)
             and (t_lo + i + 5 + struct.unpack_from('<i', blob, i + 1)[0]) == rva]
    # 静的 VA ポインタ参照 (全 section)
    ptrs = 0
    for s in pe.sections:
        if not s.SizeOfRawData: continue
        b = data[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
        ptrs += sum(1 for o in range(0, len(b) - 4, 4) if struct.unpack_from('<I', b, o)[0] == va)
    j[hex(va)] = dict(direct_call_sites=len(sites), static_VA_refs=ptrs)
out['jwt_and_stub_reachability'] = j

# --- 4: N1-N8 の実在 ---
npoints = {
 'N1 evaluateRAS2ActivationState': 0x18115de60,
 'N2 productCheckSerialNumber': 0x1805b3510,
 'N3 productGetSubscription': 0x1805b3ad0,
 'N3 CXDB3 verify': 0x18116fb20,
 'N4 ras3 dir resolve': 0x181754f70,
 'N4 .jwt enumerate': 0x180f94350,
 'N5 QML MXDemoPopup': 0x18415f411,
 'N6 Native Access 文言': 0x184ffcf87,
 'N2 serial-incorrect 文言': 0x181142160,
 'N3 Subscription expired': 0x18010e4e0,
}
def rva2off(rva):
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            d = rva - s.VirtualAddress
            if d < s.SizeOfRawData: return s.PointerToRawData + d
    return None
np_res = {}
for k, va in npoints.items():
    rva = va - base
    o = rva2off(rva)
    if o is None:
        np_res[k] = 'RVA unmapped'
        continue
    np_res[k] = data[o:o + 56].split(b'\x00')[0][:48].decode(errors='replace')
out['N_points_bytes'] = np_res

print(json.dumps(out, indent=1))
