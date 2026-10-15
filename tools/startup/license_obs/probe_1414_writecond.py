#!/usr/bin/env python3
"""#1414 (#786 受入 2): 0x10d3a30 が gradeChar を '?' (0x3f) に書く条件を、0x10c7850 の戻り値を固定して確定する。

(1) 静的: 0x10d3a30 の逆アセンブルと、g1〜g5 の rip 相対スロットの指す先 (g3・g4 が g1 と同じ dword か)。
(2) 動的: 0x10c7850 の入口で戻り値 (eax) を固定して戻らせ、0x10d3a30 の戻り後の gradeChar を読む。
    0x10c7850 の中身は実行しない (実機経路とは別の検証。戻り値そのものの決定条件は未確定)。

usage: python probe_1414_writecond.py   (要 FL_WIN64_DIR, venv: tools/startup/license_obs/env.sh)
出力: results/probe_1414_writecond.json
"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import unicorn.x86_const as C  # noqa: E402
from unicorn import UC_HOOK_CODE  # noqa: E402
from capstone import Cs, CS_ARCH_X86, CS_MODE_64  # noqa: E402
from emu_reg import Emu, Reg  # noqa: E402
from peidx import Image, rip_target  # noqa: E402
from probe_1414 import F, R, G1, G2  # noqa: E402

SENT = 0x7fffffff
CASES = (
    # name, g1 入力, g2 入力, 0x10c7850 の固定戻り値 (None = 呼ばれないことを期待)
    ('W1 sentinel・g2=0 (早期 return)', SENT, 0, None),
    ('W2 sentinel・g2=1・戻り値 sentinel', SENT, 1, SENT),
    ('W3 sentinel・g2=1・戻り値 0', SENT, 1, 0),
    ('W4 g1=0・g2=0・戻り値 sentinel', 0, 0, SENT),
    ('W5 g1=0・g2=0・戻り値 -1', 0, 0, -1),
    ('W6 g1=0・g2=1・戻り値 1', 0, 1, 1),
    ('W7 g1=0・g2=1・戻り値 INT_MIN', 0, 1, -0x80000000),
)


def static_check():
    img = Image()
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = False
    out = []
    for ins in md.disasm(img.read(F, 91), F):
        tgt = rip_target(ins)
        if tgt is None:
            continue
        ptr = struct.unpack('<Q', img.read(tgt, 8))[0]
        out.append({'addr': hex(ins.address), 'insn': f'{ins.mnemonic} {ins.op_str}', 'slot': hex(tgt), 'slot_value': hex(ptr)})
    return out


def run_case(name, g1, g2, ret):
    e = Emu(Reg())
    e.setup_globals()
    e.init_units()
    e.uc.mem_write(G1, struct.pack('<I', g1 & 0xffffffff))
    e.uc.mem_write(G2, struct.pack('<B', g2))
    calls = []

    def stub(uc, a, s, ud):
        rsp = e.r(C.UC_X86_REG_RSP)
        ra = struct.unpack('<Q', e.rd(rsp, 8))[0]
        calls.append(hex(ra))
        uc.reg_write(C.UC_X86_REG_RAX, ret & 0xffffffff)
        uc.reg_write(C.UC_X86_REG_RSP, rsp + 8)
        uc.reg_write(C.UC_X86_REG_RIP, ra)

    e.uc.hook_add(UC_HOOK_CODE, stub, begin=R, end=R)
    before = e.rd(e.grade_ptr, 1).hex()
    st = e.run(entry=F, cl=0)
    after = e.rd(e.grade_ptr, 1).hex()
    g1_after = struct.unpack('<i', e.rd(G1, 4))[0]
    if ret is None:
        expect_write = False
    else:
        expect_write = (g1 != SENT or g2 != 0) and ret <= 0
    wrote = after == '3f'
    return {'case': name, 'g1_in': hex(g1 & 0xffffffff), 'g2_in': g2,
            'stub_ret': None if ret is None else hex(ret & 0xffffffff),
            'status': st if st == 'ok' else st[:160], 'calls_0x10c7850': len(calls),
            'gradeChar_before': before, 'gradeChar_after': after, 'g1_after_signed': g1_after,
            'wrote_3f': wrote, 'expected_write': expect_write, 'match': wrote == expect_write}


def main():
    static = static_check()
    rows = [run_case(*c) for c in CASES]
    os.makedirs(os.path.join(HERE, 'results'), exist_ok=True)
    json.dump({'static': static, 'cases': rows}, open(os.path.join(HERE, 'results', 'probe_1414_writecond.json'), 'w'),
              indent=1, ensure_ascii=False)
    for s in static:
        print(s)
    for r in rows:
        print(r)
    print('all_match', all(r['match'] for r in rows))


if __name__ == '__main__':
    main()
