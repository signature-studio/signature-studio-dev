#!/usr/bin/env python3
"""probe_d9_disp.py — D9 (capstone disp_size が 66/F2 prefix 付き SSE rip-rel で誤る) の x64c 影響検証。

x64c は rip-rel target を `ins.address + ins.size + op.mem.disp` で自前計算し、capstone の
disp_size/disp_offset フィールドに依存しない (tools/icall REPORT.md §4 D9 の該当箇所回避)。
本検証は FLEngine 全 .pdata 関数の walking decode で rip-rel operand 全件を拾い、
生バイトから prefixes + modrm を手動解釈した disp と capstone の disp を突合する
(prefix 群 66/F2/F3/REX/segment/67/F0 別に集計)。不一致 0 なら D9 は x64c に影響しない。
"""
import pefile, capstone, struct, collections, os, sys
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_REG_RIP

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'shared'))
from paths import FL_WIN64_DIR
PE = os.environ.get('FLE_PE') or os.path.join(FL_WIN64_DIR, 'extracted', 'block00031_PE.bin')
IMG = 0x400000

pe = pefile.PE(data=open(PE, 'rb').read())
img = pe.get_memory_mapped_image()
pd = [s for s in pe.sections if s.Name.startswith(b'.pdata')][0].get_data()
funcs = []
for i in range(0, len(pd) // 12 * 12, 12):
    b, e, u = struct.unpack_from('<III', pd, i)
    if b == 0 and e == 0:
        break
    funcs.append((IMG + b, IMG + e))

md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True


LEGACY = {0x67, 0xF2, 0xF3, 0xF0, 0x2E, 0x3E, 0x26, 0x36, 0x64, 0x65}
# 1 byte opcode のうち modrm を持たないもの (F6/F7 は imm 付きだが modrm 持ち; 0x8F x は除く)
ONEBYTE_NOMODRM = set(range(0x50, 0x60)) | set(range(0x90, 0x9F)) | {0x98, 0x99, 0x9B, 0x9C, 0x9D, 0x9E, 0x9F} \
    | set(range(0x70, 0x80)) | {0xE8, 0xE9, 0xEB, 0xF4, 0xFC, 0xFD, 0xA8, 0xA9} \
    | {0x04, 0x0A, 0x0C, 0x14, 0x1C, 0x24, 0x2C, 0x34, 0x3C, 0x05, 0x0D, 0x15, 0x1D, 0x25, 0x2D, 0x35, 0x3D,
       0x68, 0x6A} | set(range(0xB0, 0xB8)) | set(range(0xB8, 0xC0))
# 0F 2byte opcode のうち modrm を持たないもの
TWOBYTE_NOMODRM = set(range(0x18, 0x20)) | {0x0A, 0x0B, 0x0D, 0x31, 0x32, 0x33, 0x34, 0x35, 0x77, 0x80, 0x81,
                                            0x82, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8A, 0x8B, 0x8C,
                                            0x8D, 0x8E, 0x8F, 0xA0, 0xA1, 0xA8, 0xA9, 0xAA, 0xAB, 0xAC, 0xAD,
                                            0xAE, 0xAF, 0xC8, 0xC9, 0xCC, 0xCD}


def manual_rip_disp(raw):
    """生バイトから prefix/opcode/modrm を手動解釈し rip-rel disp (符号付) を返す (RIP 絶対形のみ)。"""
    i = 0
    while i < len(raw):
        b = raw[i]
        if b == 0x66 or b in LEGACY:
            i += 1
        elif 0x40 <= b <= 0x4F:
            i += 1
        else:
            break
    if i >= len(raw):
        return None
    op = raw[i]; i += 1
    if op == 0x0F:
        if i >= len(raw):
            return None
        op2 = raw[i]; i += 1
        if op2 in TWOBYTE_NOMODRM:
            return None
    else:
        if op in ONEBYTE_NOMODRM:
            return None
    if i >= len(raw):
        return None
    modrm = raw[i]; i += 1
    mod = modrm >> 6; rm = modrm & 7
    if mod == 3:
        return None
    if rm == 4:  # SIB
        if i >= len(raw):
            return None
        sib = raw[i]; i += 1
        if (sib & 7) == 5 and mod == 0:
            i += 4  # base なし disp32 (絶対 — RIP ではない)
            return None
    if mod == 0 and rm == 5:
        if i + 4 > len(raw):
            return None
        return struct.unpack_from('<i', raw, i)[0]
    if mod == 1:
        if i + 1 > len(raw):
            return None
        return struct.unpack_from('<b', raw, i)[0]
    if mod == 2:
        if i + 4 > len(raw):
            return None
        return struct.unpack_from('<i', raw, i)[0]
    return None


total = 0
mismatch = 0
per_prefix = collections.Counter()
samples = []
for (b, e) in funcs:
    va = b
    while va < e:
        got = None
        for ins in md.disasm(img[va - IMG:e - IMG], va, 1):
            got = ins
            break
        if got is None:
            va += 1
            continue
        ins = got
        va += ins.size
        raw = img[ins.address - IMG:ins.address - IMG + ins.size]
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == X86_REG_RIP:
                total += 1
                cap_t = ins.address + ins.size + op.mem.disp
                mdisp = manual_rip_disp(raw)
                if mdisp is None:
                    per_prefix['manual-unparsed'] += 1
                    continue
                pfx = 'none'
                for bb in raw:
                    if bb in (0x66, 0xF2, 0xF3):
                        pfx = '%02x' % bb
                        break
                    if 0x40 <= bb <= 0x4F:
                        pfx = 'rex'
                        break
                    if bb == 0x0F or bb not in LEGACY:
                        break
                per_prefix[pfx] += 1
                man_t = ins.address + ins.size + mdisp
                if cap_t != man_t:
                    mismatch += 1
                    if len(samples) < 8:
                        samples.append((ins.address, ins.mnemonic, ins.op_str, hex(cap_t), hex(man_t),
                                        ' '.join('%02x' % x for x in raw)))

print('[D9] rip-rel sites: %d, capstone-vs-manual-modrm mismatch: %d' % (total, mismatch))
print('     by prefix:', dict(per_prefix))
for s in samples:
    print('     MISMATCH va=%x %s %s cap=%s man=%s bytes=%s' % s)
raise SystemExit(0 if mismatch == 0 else 1)
