#!/usr/bin/env python3
"""#3725 (ST-1): 0x10c7850 の戻り値 (eax) の計算式を、逆アセンブルから組んだ式と実行で突き合わせる。

逆アセンブルから読んだ式 (定数スロットは全て 0.0 と確認済み):
  v98 = min(v88, v90) (両方 > 0 のとき) / v90 (v90 > 0 のみ) / v88 (v88 > 0 のみ) / 0 (両方 <= 0)
  v88 = 0x8e7e10(rcx=0) の戻り値, v90 = 0x8e7e10 の戻り値 (flag = [[0x15e3d80]] の値で呼び先が変わる)
  G   = *( *0x15e1608 ) (double)。G == 0 の分岐 (0x10c79c7〜) は通らないよう G != 0 に限る
  ret = 0x7fffffff (v98 == 0) / low32(trunc(v98 - trunc(G))) (それ以外。0x10c7b84 の call 0x40c750 の後で cvtsi2sd により trunc(G) を double に戻してから引く)

0x8e7e10 と 0x40c750 以外の実 call (0x412d60 の後始末) はスタブにする。
v88・v90・G の値は probe 側の入力で、その算出元 (0x8e7e10・0x442bd0) は確定しない。

usage: python probe_3725_retformula.py   (要 FL_WIN64_DIR, venv: tools/startup/license_obs/env.sh)
出力: results/probe_3725_retformula.json
"""
import json, math, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import unicorn.x86_const as C  # noqa: E402
from unicorn import UC_HOOK_CODE  # noqa: E402
from emu_reg import Emu, Reg  # noqa: E402

R = 0x10c7850          # 0x10c7850 (ret を返す関数)
F88 = 0x10c78bf + 5    # v88 の call 0x8e7e10 の戻り先 (flag に依らず使う)
F90A = 0x10c7897 + 5   # v90 の call 0x8e7e10 (flag == 1)
F90B = 0x10c78b0 + 5   # v90 の call 0x8e7e10 (flag == 2)
SLOT_G = 0x15e1608     # G の参照先ポインタ
SLOT_FLAG = 0x15e3d80  # flag バイトへのポインタ
SLOT_P1 = 0x15e1948    # flag == 1 の v90 引数 (ポインタ)
SLOT_P2 = 0x15e4cb8    # flag == 2 の v90 引数 (ポインタ)
SENT = 0x7fffffff
STUB_412D60 = 0x412d60

CASES = (
    # name, flag, v88, v90, G  (ret は式で予測)
    ('C1 両方正・min', 1, 5.0, 3.0, 1.0),
    ('C2 v90 負・v88 のみ', 1, 5.0, -2.0, 1.0),
    ('C3 v88 負・v90 のみ', 1, -1.0, 7.9, 2.5),
    ('C4 両方 0', 1, 0.0, 0.0, 1.0),
    ('C5 v90 0・v88 のみ', 1, 4.0, 0.0, 1.0),
    ('C6 境界 ret=0', 1, 2.0, 3.0, 2.0),
    ('C7 ret 負', 1, 1.0, 3.0, 2.9),
    ('C8 両方負', 1, -3.0, -1.0, 1.0),
    ('C9 flag=2 の v90 経路', 2, 6.0, 4.0, 1.5),
    ('C10 非整数 G (trunc(G) 版と区別)', 1, 3.2, 9.0, 1.7),
    ('C11 小数の差 (切り捨ての向き)', 1, 3.9, 9.0, 1.5),
)


def dbl(x):
    return int.from_bytes(struct.pack('<d', x) + b'\0' * 8, 'little')


def predict(v88, v90, g):
    pos = [x for x in (v88, v90) if x > 0]
    v98 = min(pos) if pos else 0.0
    if v98 == 0:
        return SENT
    t = math.trunc(v98 - math.trunc(g))
    return ((t + 2**31) % 2**32) - 2**31


def run_case(name, flag, v88, v90, g):
    e = Emu(Reg())
    e.setup_globals()
    e.init_units()
    # 参照先を用意する (flag バイト・G の double・v90 の引数ポインタ)
    fl = e.alloc(16)
    e.uc.mem_write(fl, bytes([flag]))
    e.uc.mem_write(SLOT_FLAG, struct.pack('<Q', fl))
    gp = e.alloc(16)
    e.uc.mem_write(gp, struct.pack('<d', g))
    e.uc.mem_write(SLOT_G, struct.pack('<Q', gp))
    p1 = e.alloc(16)
    e.uc.mem_write(SLOT_P1, struct.pack('<Q', p1))
    e.uc.mem_write(SLOT_P2, struct.pack('<Q', p1))
    vals = {F88: v88, F90A: v90, F90B: v90}
    calls = []

    def ret_with(uc, val):
        rsp = e.r(C.UC_X86_REG_RSP)
        ra = struct.unpack('<Q', e.rd(rsp, 8))[0]
        uc.reg_write(C.UC_X86_REG_XMM0, dbl(val))
        uc.reg_write(C.UC_X86_REG_RSP, rsp + 8)
        uc.reg_write(C.UC_X86_REG_RIP, ra)
        return ra

    def stub_8e(uc, a, s, ud):
        ra = struct.unpack('<Q', e.rd(e.r(C.UC_X86_REG_RSP), 8))[0]
        calls.append(hex(ra))
        ret_with(uc, vals.get(ra, 0.0))

    def stub_412d60(uc, a, s, ud):
        rsp = e.r(C.UC_X86_REG_RSP)
        uc.reg_write(C.UC_X86_REG_RSP, rsp + 8)
        uc.reg_write(C.UC_X86_REG_RIP, struct.unpack('<Q', e.rd(rsp, 8))[0])

    e.uc.hook_add(UC_HOOK_CODE, stub_8e, begin=0x8e7e10, end=0x8e7e10)
    e.uc.hook_add(UC_HOOK_CODE, stub_412d60, begin=STUB_412D60, end=STUB_412D60)
    st = e.run(entry=R, cl=0)
    ret = e.r(C.UC_X86_REG_RAX) & 0xffffffff
    ret = ret - 2**32 if ret >= 2**31 else ret
    exp = predict(v88, v90, g)
    return {'case': name, 'flag': flag, 'v88': v88, 'v90': v90, 'G': g,
            'status': st if st == 'ok' else st[:160], 'calls_0x8e7e10': calls,
            'ret': ret, 'expected': exp, 'match': st == 'ok' and ret == exp}


def main():
    rows = [run_case(*c) for c in CASES]
    for r in rows:
        print(json.dumps(r, ensure_ascii=False))
    ok = all(r['match'] for r in rows)
    out = os.path.join(HERE, 'results', 'probe_3725_retformula.json')
    with open(out, 'w') as f:
        json.dump({'all_match': ok, 'cases': rows}, f, ensure_ascii=False, indent=1)
    print('all_match', ok)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
