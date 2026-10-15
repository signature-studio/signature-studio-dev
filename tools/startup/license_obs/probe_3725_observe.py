#!/usr/bin/env python3
"""#3725 (ST-1): 実機経路 (通常の登録パーサ実行・6 入力) で 0x10c7850 の戻り値と、その式の入力を観測する。

観測点:
  - 0x10c7850 の戻り先 0x10c9bf2 で eax (戻り値 = g1 への格納値)
  - 0x10c7850 の入口で ret の式の入力 (flag・G・v88・v90 の算出元の戻り値) を記録する
    v88 は 0x10c78c4 (movsd [rbp+0x88], xmm0 の直後) で、v90 は 0x10c789c/0x10c78b5 の直後で読む

usage: python probe_3725_observe.py   (要 FL_WIN64_DIR, venv: tools/startup/license_obs/env.sh)
出力: results/probe_3725_observe.json
"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import unicorn.x86_const as C  # noqa: E402
from unicorn import UC_HOOK_CODE  # noqa: E402
from emu_reg import Emu, Reg  # noqa: E402
from run_cases import seed_license  # noqa: E402
from probe_1414 import CASES, G1, R  # noqa: E402

RET_SITE = 0x10c9bf2     # 0x10c7850 の戻り先 (eax を g1 へ格納する箇所の直前)
V88_SITE = 0x10c78cc     # v88 (0x10c78c4 の movsd 格納の後) と v90 (0x10c789c の後) を読む
V98_SITE = 0x10c7985     # v98 の全分岐の合流点 (格納は 0x10c792c・0x10c7948・0x10c796a・0x10c797a のいずれか)
G_SITE = 0x10c7b8f       # G の double (0x15e1608 の指す先) を xmm0 に読んだ後


def run_case(name, kw, cl):
    r = Reg()
    seed_license(r, **kw)
    e = Emu(r)
    e.setup_globals()
    e.init_units()
    obs = {}

    def on_ret(uc, a, s, ud):
        obs['ret_eax_at_0x10c9bf2'] = hex(uc.reg_read(C.UC_X86_REG_RAX) & 0xffffffff)
    def on_v88(uc, a, s, ud):
        rbp = uc.reg_read(C.UC_X86_REG_RBP)
        obs['v88'] = struct.unpack('<d', bytes(uc.mem_read(rbp + 0x88, 8)))[0]
        obs['v90'] = struct.unpack('<d', bytes(uc.mem_read(rbp + 0x90, 8)))[0]
    def on_v98(uc, a, s, ud):
        rbp = uc.reg_read(C.UC_X86_REG_RBP)
        obs['v98'] = struct.unpack('<d', bytes(uc.mem_read(rbp + 0x98, 8)))[0]
    def on_G(uc, a, s, ud):
        obs['G'] = struct.unpack('<d', bytes(uc.reg_read(C.UC_X86_REG_XMM0))[:8])[0]
    e.uc.hook_add(UC_HOOK_CODE, on_ret, begin=RET_SITE, end=RET_SITE)
    e.uc.hook_add(UC_HOOK_CODE, on_v88, begin=V88_SITE, end=V88_SITE)
    e.uc.hook_add(UC_HOOK_CODE, on_v98, begin=V98_SITE, end=V98_SITE)
    e.uc.hook_add(UC_HOOK_CODE, on_G, begin=G_SITE, end=G_SITE)
    st = e.run(cl=cl)
    obs['g1_after_signed'] = struct.unpack('<i', e.rd(G1, 4))[0]
    obs['gradeChar_after'] = e.rd(e.grade_ptr, 1).hex()
    return {'case': name, 'status': st if st == 'ok' else st[:160],
            'obs': {k: (v if isinstance(v, str) or isinstance(v, int) else round(v, 6)) for k, v in obs.items()}}


def main():
    rows = [run_case(n, kw, cl) for n, kw, cl in CASES]
    for x in rows:
        print(json.dumps(x, ensure_ascii=False))
    out = os.path.join(HERE, 'results', 'probe_3725_observe.json')
    json.dump({'cases': rows}, open(out, 'w'), ensure_ascii=False, indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
