#!/usr/bin/env python3
"""#1221: 関数ポインタ表経由で呼ばれる 0x11cb000 / 0x10d50d0 の起動元を unicorn の code hook で動的に特定する。
併せて 0x10d3a30 の g1〜g8 (グローバル) の値と、0x10c7850 の戻り値を観測する (実行は改変しない)。

usage: python probe_1221.py   (要 FL_WIN64_DIR, uv pip install pefile capstone unicorn)
出力: results/probe_1221.json
"""
import json, os, re, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from emu_reg import Emu, Reg, ENTRY, UNIT_INITS, PROBES  # noqa: E402
from run_cases import seed_license  # noqa: E402
from unicorn.x86_const import UC_X86_REG_RSP, UC_X86_REG_RIP, UC_X86_REG_RAX  # noqa: E402
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ  # noqa: E402
from peidx import Image  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TARGETS = {0x11cb000: 'T1 (0x11cb000)', 0x10d50d0: 'T2 (0x10d50d0)', 0x10d3a30: 'F (0x10d3a30)', 0x10c7850: 'R (0x10c7850)'}
RIP = re.compile(r'\[rip ([+-]) (0x[0-9a-f]+)\]')


def globals_of(func, hi_fallback=0x200):
    """0x10d3a30 の rip 相対参照先を (命令VA, 参照先) で列挙し、g1〜g8 候補を得る。"""
    img = Image()
    hi = [e for b, e in img.funcs if b == func]
    hi = hi[0] if hi else func + hi_fallback
    out = []
    for ins in img.disasm_func(func, hi):
        m = RIP.search(ins.op_str)
        if m:
            t = ins.address + ins.size + int(m.group(2), 16) * (1 if m.group(1) == '+' else -1)
            out.append((ins.address, t))
    return out


TABLES = ((0x11740f5, 0x117423d + 8), (0x1378820, 0x137a1f0))


def run_one(name, reg, units=True, cl=0):
    e = Emu(reg)
    e.setup_globals()
    hits = {hex(k): [] for k in TARGETS}
    for va, label in TARGETS.items():
        def cb(uc, addr, size, ud, va=va):
            rsp = uc.reg_read(UC_X86_REG_RSP)
            ret = struct.unpack('<Q', bytes(uc.mem_read(rsp, 8)))[0]
            hits[hex(va)].append({'rsp': hex(rsp), 'ret': hex(ret)})
        e.uc.hook_add(UC_HOOK_CODE, cb, begin=va, end=va)
    table_readers = {}

    def rd_cb(uc, access, addr, size, value, ud):
        rip = uc.reg_read(UC_X86_REG_RIP)
        table_readers.setdefault(hex(rip), 0)
        table_readers[hex(rip)] += 1
    for lo, hi in TABLES:
        e.uc.hook_add(UC_HOOK_MEM_READ, rd_cb, begin=lo, end=hi)
    ret_val = {}

    def ret_cb(uc, addr, size, ud):
        ret_val.setdefault('eax_after_call_0x10c9bf2', []).append(hex(uc.reg_read(UC_X86_REG_RAX) & 0xffffffff))
    e.uc.hook_add(UC_HOOK_CODE, ret_cb, begin=0x10c9bf2, end=0x10c9bf2)
    if units:
        e.init_units()
    st = e.run(cl=cl)

    def deref(slot, n):
        p = struct.unpack('<Q', e.rd(slot, 8))[0]
        try:
            return {'slot': hex(slot), 'ptr': hex(p), 'val': e.rd(p, n).hex()}
        except Exception as ex:  # noqa: BLE001
            return {'slot': hex(slot), 'ptr': hex(p), 'err': str(ex)[:80]}
    gv = {hex(t): deref(t, 4 if a == 0x10d3a34 or a == 0x10d3a58 or a == 0x10d3a61 else 8) for a, t in GLOBALS}
    return {'case': name, 'status': st if st == 'ok' else st[:160], 'hits': hits,
            'table_readers': table_readers, 'ret_0x10c7850': ret_val,
            'globals': gv, 'probe_hits': dict(e.probe_hits)}


GLOBALS = globals_of(0x10d3a30)


CASES = (
    ('A1 ILRegKey 無し cl=0', dict(drop_il=True), 0),
    ('A2 ILRegKey 無し cl=1', dict(drop_il=True), 1),
    ('B1 vreg seed cl=0', dict(), 0),
    ('B2 vreg seed cl=1', dict(), 1),
    ('D2 空 ILRegKey cl=1', dict(il_override=''), 1),
    ('D1 非正規 128 文字 cl=1', dict(il_override='0123456789ABCDEF' * 8), 1),
)


def main():
    out = []
    for name, kw, cl in CASES:
        r = Reg()
        seed_license(r, **kw)
        out.append(run_one(name, r, cl=cl))
    os.makedirs(os.path.join(HERE, 'results'), exist_ok=True)
    json.dump({'globals': [(hex(a), hex(t)) for a, t in GLOBALS], 'runs': out},
              open(os.path.join(HERE, 'results', 'probe_1221.json'), 'w'), indent=1, ensure_ascii=False)
    for o in out:
        print(o['case'], '|', o['status'][:90])
        for k, v in o['hits'].items():
            print('   hit', k, len(v), v[:3])
        print('   table readers', o['table_readers'])
        print('   ret 0x10c7850', o['ret_0x10c7850'])
        print('   globals', o['globals'])


if __name__ == '__main__':
    main()
