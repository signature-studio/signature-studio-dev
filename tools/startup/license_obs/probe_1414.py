#!/usr/bin/env python3
"""#1414: (1) 0x10c7cd0 内の間接 call の実行時ターゲットを記録 (通常経路・6 入力)、
(2) 0x10d3a30 を g1/g2 を書き換えて強制実行 (実機経路とは別。発火条件の検証用)。

usage: python probe_1414.py   (要 FL_WIN64_DIR, venv: tools/startup/license_obs/env.sh)
出力: results/probe_1414.json
"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from capstone import Cs, CS_ARCH_X86, CS_MODE_64  # noqa: E402
from capstone.x86 import X86_OP_MEM, X86_OP_REG  # noqa: E402
import unicorn.x86_const as C  # noqa: E402
from unicorn import UC_HOOK_CODE  # noqa: E402
from emu_reg import Emu, Reg  # noqa: E402
from run_cases import seed_license  # noqa: E402
from peidx import Image, rip_target  # noqa: E402

CASES = (
    ('A1 ILRegKey 無し cl=0', dict(drop_il=True), 0),
    ('A2 ILRegKey 無し cl=1', dict(drop_il=True), 1),
    ('B1 vreg seed cl=0', dict(), 0),
    ('B2 vreg seed cl=1', dict(), 1),
    ('D2 空 ILRegKey cl=1', dict(il_override=''), 1),
    ('D1 非正規 128 文字 cl=1', dict(il_override='0123456789ABCDEF' * 8), 1),
)

G1_SLOT = 0x15e14a8   # g1 のスロット (rip 相対参照の対象)
G1 = 0x14f852c        # 0x10d3a30 の g1・g3・g4 が指す dword (sentinel 0x7fffffff)
G2 = 0x16b6e58        # g2 (byte)
F = 0x10d3a30
R = 0x10c7850
DISP = 0x10c7cd0
TARGETS = {0x11cb000, 0x10d50d0}


def indirect_sites(img):
    lo = [f for f in img.funcs if f[0] == DISP][0]
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    out = []
    for ins in md.disasm(img.read(lo[0], lo[1] - lo[0]), lo[0]):
        if ins.mnemonic == 'call' and not ins.op_str.startswith('0x'):
            out.append((ins.address, ins.size, ins.operands[0], md))
    return out


def static_enum(img):
    rip_g1 = []
    rip_slot = []
    imm_7fff = []
    for lo, hi, insns in img.iter_insns():
        for ins in insns:
            tgt = rip_target(ins)
            if tgt == G1:
                rip_g1.append(hex(ins.address))
            if tgt == G1_SLOT:
                rip_slot.append(hex(ins.address))
            if ins.mnemonic == 'mov' and ins.op_str.endswith(', 0x7fffffff') and ' ptr [' in ins.op_str:
                imm_7fff.append(hex(ins.address))
    return {'rip_ref_G1_0x14f852c': len(rip_g1), 'rip_ref_G1_SLOT_0x15e14a8': len(rip_slot),
            'write_mov_imm_0x7fffffff_to_mem': len(imm_7fff),
            'addrs_rip_ref_G1_SLOT': rip_slot, 'addrs_write_mov_imm_0x7fffffff': imm_7fff}


def resolve(uc, op, md, addr, size):
    if op.type == X86_OP_REG:
        return uc.reg_read(getattr(C, 'UC_X86_REG_' + md.reg_name(op.reg).upper()))
    if op.type != X86_OP_MEM:
        return None
    m = op.mem
    if m.base and md.reg_name(m.base) == 'rip':
        base = addr + size
    else:
        base = uc.reg_read(getattr(C, 'UC_X86_REG_' + md.reg_name(m.base).upper())) if m.base else 0
    idx = uc.reg_read(getattr(C, 'UC_X86_REG_' + md.reg_name(m.index).upper())) * m.scale if m.index else 0
    ea = base + idx + m.disp
    return struct.unpack('<Q', bytes(uc.mem_read(ea, 8)))[0]


def run_trace(name, reg, cl):
    e = Emu(reg)
    e.setup_globals()
    e.init_units()
    img = Image()
    sites = indirect_sites(img)
    seen = {}
    flags = []
    for addr, size, op, md in sites:
        def cb(uc, a, s, ud, addr=addr, size=size, op=op, md=md):
            t = resolve(uc, op, md, a, s)
            k = hex(addr)
            seen.setdefault(k, {}).setdefault(hex(t) if t is not None else 'na', 0)
            seen[k][hex(t) if t is not None else 'na'] += 1
            if t in TARGETS:
                flags.append((k, hex(t)))
        e.uc.hook_add(UC_HOOK_CODE, cb, begin=addr, end=addr)
    st = e.run(cl=cl)
    return {'case': name, 'status': st if st == 'ok' else st[:160], 'static_indirect_sites': len(sites),
            'sites_executed': len(seen),
            'targets_hit': flags, 'seen': seen}


def run_force(name, g1, g2):
    e = Emu(Reg())
    e.setup_globals()
    e.init_units()
    e.uc.mem_write(G1, struct.pack('<I', g1))
    e.uc.mem_write(G2, struct.pack('<B', g2))
    cnt = {'R': 0}

    def rcb(uc, a, s, ud):
        cnt['R'] += 1
    e.uc.hook_add(UC_HOOK_CODE, rcb, begin=R, end=R)
    before = e.rd(e.grade_ptr, 1).hex()
    # 0x10d3a30 の入口を直接実行 (run の entry 指定)
    st = e.run(entry=F, cl=0)
    rax = e.uc.reg_read(C.UC_X86_REG_RAX) & 0xffffffff
    return {'case': name, 'g1_in': hex(g1), 'g2_in': g2, 'status': st if st == 'ok' else st[:160],
            'calls_0x10c7850': cnt['R'], 'ret_eax': hex(rax),
            'gradeChar_before': before, 'gradeChar_after': e.rd(e.grade_ptr, 1).hex(),
            'g1_after': e.rd(G1, 4).hex(), 'g2_after': e.rd(G2, 1).hex()}


def main():
    trace = []
    for name, kw, cl in CASES:
        r = Reg()
        seed_license(r, **kw)
        trace.append(run_trace(name, r, cl))
    force = [
        run_force('F1 g1=sentinel g2=0 (通常分岐)', 0x7fffffff, 0),
        run_force('F2 g1=0 g2=0 (強制)', 0, 0),
        run_force('F3 g1=sentinel g2=1 (強制)', 0x7fffffff, 1),
    ]
    os.makedirs(os.path.join(HERE, 'results'), exist_ok=True)
    static = static_enum(Image())
    json.dump({'static': static, 'trace': trace, 'force': force}, open(os.path.join(HERE, 'results', 'probe_1414.json'), 'w'),
              indent=1, ensure_ascii=False)
    for t in trace:
        print(t['case'], '|', t['status'][:80], '| sites executed', t['sites_executed'], '| targets hit', t['targets_hit'])
    for f in force:
        print(f)


if __name__ == '__main__':
    main()
