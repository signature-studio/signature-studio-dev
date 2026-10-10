#!/usr/bin/env python3
"""dispfix 単体テスト (python3 tests/test_dispfix.py; pytest 不要)。実バイナリ不要。"""
import os, sys, struct
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import capstone
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
import dispfix as D

cs = Cs(CS_ARCH_X86, CS_MODE_64)
cs.detail = True
fails = []


def check(name, cond, info=''):
    print(('PASS ' if cond else 'FAIL ') + name + (' ' + str(info) if info and not cond else ''))
    if not cond:
        fails.append(name)


def dis(hexs, addr=0x1000):
    return next(cs.disasm(bytes.fromhex(hexs.replace(' ', '')), addr))


# (hex, disp_span, rip, 説明)
CASES = [
    ('66 0f 2f 05 10 00 00 00', (4, 4), True, '66 comisd xmm0,[rip+0x10] (D9 本体)'),
    ('66 01 05 10 00 00 00', (3, 4), True, '66 add [rip],ax'),
    ('66 c7 05 10 00 00 00 34 12', (3, 4), True, '66 mov word [rip],imm16 (imm は disp の後)'),
    ('f2 0f 10 05 10 00 00 00', (4, 4), True, 'F2 movsd (無害)'),
    ('f3 0f 10 05 10 00 00 00', (4, 4), True, 'F3 movss (無害)'),
    ('66 48 0f 6e 05 10 00 00 00', (5, 4), True, '66 REX.W movq (capstone も正)'),
    ('66 f2 0f 38 f1 05 10 00 00 00', (6, 4), True, '66 F2 0F38 crc32 w/ rip'),
    ('66 8b 80 44 33 22 11', (3, 4), False, '66 mov ax,[rax+disp32] (rip 以外の disp32 も誤る)'),
    ('66 8b 84 24 44 33 22 11', (4, 4), False, '66 mov ax,[rsp+disp32] (SIB)'),
    ('66 8b 04 25 44 33 22 11', (4, 4), False, '66 mov ax,[disp32] (SIB base 無し)'),
    ('66 8b 40 08', (3, 1), False, '66 disp8 (capstone も 1 で正)'),
    ('c5 f9 10 05 10 00 00 00', (4, 4), True, 'VEX2 pp=66 vmovupd (66 byte 無しでも誤る)'),
    ('c5 fa 10 05 10 00 00 00', (4, 4), True, 'VEX2 pp=F3 vmovss (無害)'),
    ('c4 e1 79 10 05 10 00 00 00', (5, 4), True, 'VEX3 pp=66 (capstone 正)'),
    ('62 f1 fd 08 10 05 10 00 00 00', (6, 4), True, 'EVEX'),
    ('67 8b 05 10 00 00 00', (3, 4), True, '67 (eip 相対) disp32'),
    ('66 a1 88 77 66 55 44 33 22 11', (2, 8), False, '66 mov ax,[moffs64]'),
    ('8b 00', None, False, 'disp 無し'),
    ('66 8b 00', None, False, '66 disp 無し'),
    ('66 0f 2f c1', None, False, 'reg-reg'),
]
for hx, span, rip, desc in CASES:
    ins = dis(hx)
    got = D.disp_span(ins)
    lay = D.layout(bytes(ins.bytes))
    check('disp_span %s' % desc, got == span, 'got=%s want=%s' % (got, span))
    check('layout(raw, 表引き) %s' % desc, ((lay.disp_offset, lay.disp_size) if lay.disp_size else None) == span, lay)
    check('rip 判定 %s' % desc, D.is_rip_relative(ins) == rip)

# rip_target
ins = dis('66 0f 2f 05 10 00 00 00')
check('rip_target = address+size+disp', D.rip_target(ins) == 0x1000 + 8 + 0x10, hex(D.rip_target(ins) or 0))
check('rip_target (非 rip) None', D.rip_target(dis('8b 80 44 33 22 11')) is None)
ins = dis('67 8b 05 f0 ff ff ff', 0x1000)
check('rip_target 67 は 32bit 折返し', D.rip_target(ins) == (0x1000 + 7 - 0x10) & 0xFFFFFFFF)

# zero_disp32
buf = bytearray(bytes.fromhex('90 66 01 05 44 33 22 11 90'.replace(' ', '')))
ins = dis('66 01 05 44 33 22 11')
check('zero_disp32 実施', D.zero_disp32(buf, 1, ins) and bytes(buf) == bytes.fromhex('90 66 01 05 00 00 00 00 90'.replace(' ', '')), buf.hex())
buf = bytearray(bytes.fromhex('66 8b 40 08'.replace(' ', '')))
check('zero_disp32 disp8 は触らない', not D.zero_disp32(buf, 0, dis('66 8b 40 08')) and buf == bytes.fromhex('668b4008'))

# 実効 operand size
check('opsize 既定 4', D.opsize(D.layout(bytes.fromhex('0105100000 00'.replace(' ', '')))) == 4)
check('opsize 66 → 2', D.opsize(D.layout(bytes.fromhex('6601051000 0000'.replace(' ', '')))) == 2)
check('opsize REX.W → 8', D.opsize(D.layout(bytes.fromhex('480105100000 00'.replace(' ', '')))) == 8)
check('opsize 66+REX.W → 8 (REX.W 優先)', D.opsize(D.layout(bytes.fromhex('66480105100000 00'.replace(' ', '')))) == 8)
check('immz 66 → 2', D.immz_size(D.layout(bytes.fromhex('66c705100000003412'))) == 2)
check('immz 既定 → 4', D.immz_size(D.layout(bytes.fromhex('c7051000000078563412'))) == 4)
check('addrsize 67 → 4', D.addrsize(D.layout(bytes.fromhex('678b0510000000'))) == 4)

# has_modrm 表と capstone modrm_offset の全面一致 (1B/0F/0F38/0F3A × {none,66,F2,F3} × modrm 形式)
bad = []
n = 0
maps = {0: b'', 1: b'\x0f', 2: b'\x0f\x38', 3: b'\x0f\x3a'}
SKIP = {0x0F, 0x26, 0x2E, 0x36, 0x3E, 0x64, 0x65, 0x66, 0x67, 0xF0, 0xF2, 0xF3, 0xC4, 0xC5, 0x62} | set(range(0x40, 0x50))
for mp, pre in maps.items():
    for op in range(256):
        if mp == 0 and op in SKIP:
            continue
        for lead in (b'', b'\x66', b'\xf3', b'\xf2'):
            for modrm in (0x05, 0xC1, 0x45):
                raw = lead + pre + bytes([op, modrm]) + bytes.fromhex('44332211a1a2a3a4a5a6a7a8')
                ins = next(cs.disasm(raw, 0x1000), None)
                if ins is None:
                    continue
                n += 1
                lay = D.layout(raw[:ins.size])
                if (ins.modrm_offset != 0) != (lay.modrm_offset is not None) or (ins.modrm_offset and ins.modrm_offset != lay.modrm_offset):
                    bad.append((raw[:ins.size].hex(), ins.mnemonic))
check('has_modrm 表 == capstone modrm_offset (%d 件)' % n, not bad, bad[:5])

# d9_affected / capstone_has_d9
check('d9_affected 66 rip → True', D.d9_affected(dis('66 01 05 10 00 00 00')))
check('d9_affected 無 prefix rip → False', not D.d9_affected(dis('01 05 10 00 00 00')))
check('d9_affected disp 無し → False', not D.d9_affected(dis('8b 00')))
check('d9_affected disp8 → False', not D.d9_affected(dis('66 8b 40 08')))
check('capstone_has_d9 は comisd probe と一致', D.capstone_has_d9() == (dis('66 0f 2f 05 10 00 00 00').disp_size != 4))

# icall_rewrite.modrm_tail_len (既存の自前計算) と dispfix の sib+disp 長が一致する (= icall_rewrite は D9 の影響を受けない実例)
sys.path.insert(0, os.path.join(HERE, '..', '..'))
import icall_rewrite as R
bad = []
n2 = 0
for hx, span, rip, desc in CASES:
    ins = dis(hx)
    lay = D.layout(bytes(ins.bytes))
    if lay.modrm_offset is None:
        continue
    n2 += 1
    want = (1 if lay.sib_offset else 0) + lay.disp_size
    got = R.modrm_tail_len(bytes(ins.bytes), ins.modrm_offset)
    if want != got:
        bad.append((hx, want, got))
check('icall_rewrite.modrm_tail_len == dispfix (sib+disp 長, %d 件)' % n2, not bad, bad)

# 上流 canary: capstone が修正されたら INFO を出す (失敗にはしない)
ins = dis('66 0f 2f 05 10 00 00 00')
if ins.disp_size == 4:
    print('INFO capstone %s は D9 が修正済み (disp_size=4)。dispfix は冗長だが無害。' % capstone.__version__)
else:
    print('INFO capstone D9 健在: 66 comisd [rip] disp_size=%d (正: 4)' % ins.disp_size)

print('RESULT %s (%d failed)' % ('PASS' if not fails else 'FAIL', len(fails)))
sys.exit(1 if fails else 0)
