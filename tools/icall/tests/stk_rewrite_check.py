#!/usr/bin/env python3
"""stk_rewrite_check.py — 書換え後の呼出し点 (icall_rewrite.build_site) を x86-64 で直接実行し、
stack 引数 12 語が [rsp+0x20+8k] → BLK+0x100+8k に copy され、stub (stub_code) 経由で値が一致することを確認する (ICALL-118 / #5598)。

  python3 tools/icall/tests/stk_rewrite_check.py          # 正常: 12/12 一致で PASS (rc=0)
  NEG=1 python3 tools/icall/tests/stk_rewrite_check.py     # ネガコン: 期待値を 1 語ずらし FAIL (rc=1)

範囲: 書換え後の site 機械語・stub 機械語・BLK の配置。被呼側は stub_code (BLK を合算して返す)。
wasm 側 icall_rt.c の dispatch と実在の被呼側は通さない (未達は REPORT_APPENDIX_5338.md §4)。
素材: python3 と capstone のみ (OTT・FLEngine 不要)。x86-64 Linux 専用。
"""
import ctypes
import mmap
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import icall_rewrite as R  # noqa: E402

NEG = os.environ.get('NEG') == '1'
NSTK = R.NSTK
SIZE = 1 << 16
BLK_OFF, STUB_OFF, SITE_OFF, TRAMP_OFF, SRC_OFF = 0x0, 0x400, 0x1000, 0x1800, 0x2000
M64 = (1 << 64) - 1
FRAME = 0x100


def imm64(opc, v):
    return opc + struct.pack('<Q', v & M64)


def make_tramp(tramp_va, site_va, src_va, ints, dbls, tgt):
    """SysV の呼出し (rdi = src) から: src の 12 語を site の [rsp+0x20+8k] (site 入口 rsp の 1 つ下) へ置き、
    rcx/rdx/r8/r9/xmm0-3/rax を設定して site を call する。"""
    c = bytearray()
    c += b'\x53'                                  # push rbx
    c += b'\x48\x89\xfb'                          # mov rbx, rdi
    c += b'\x48\x81\xec' + struct.pack('<I', FRAME)   # sub rsp, FRAME
    for k in range(NSTK):
        c += bytes([0x48, 0x8b, 0x43, 8 * k])                    # mov rax, [rbx+8k]
        c += bytes([0x48, 0x89, 0x44, 0x24, 0x18 + 8 * k])       # mov [rsp+0x18+8k], rax  (site 入口 rsp = rsp-8)
    c += imm64(b'\x48\xb9', ints[3])              # mov rcx, imm64
    c += imm64(b'\x48\xba', ints[2])              # mov rdx, imm64
    c += imm64(b'\x49\xb8', ints[4])              # mov r8, imm64
    c += imm64(b'\x49\xb9', ints[5])              # mov r9, imm64
    for n, d in enumerate(dbls):
        c += imm64(b'\x48\xb8', d)                # mov rax, imm64
        c += bytes([0x66, 0x48, 0x0f, 0x6e, 0xc0 | (n << 3)])   # movq xmmN, rax
    c += imm64(b'\x48\xb8', tgt)                  # mov rax, target (cfg thunk: 実 target は rax)
    cur = tramp_va + len(c) + 5
    c += b'\xe8' + struct.pack('<i', site_va - cur)   # call site
    c += b'\x48\x81\xc4' + struct.pack('<I', FRAME)   # add rsp, FRAME
    c += b'\x5b'                                  # pop rbx
    c += b'\xc3'                                  # ret
    return bytes(c)


def main():
    m = mmap.mmap(-1, SIZE, prot=mmap.PROT_READ | mmap.PROT_WRITE | mmap.PROT_EXEC)
    base = ctypes.addressof(ctypes.c_char.from_buffer(m))
    blk, stub_va, site_va = base + BLK_OFF, base + STUB_OFF, base + SITE_OFF
    tramp_va, src_va = base + TRAMP_OFF, base + SRC_OFF

    class _O:
        pass
    it = _O()
    it.ins = _O()
    it.ins.bytes = bytes([0xff, 0x10])           # call qword ptr [rax]
    it.ins.address = 0
    it.ins.size = 2
    n, tpl = R.expansion_template(it, True, cfg=True, nstk=NSTK)   # cfg thunk (target は rax)
    site = R.build_site(it, site_va, blk, stub_va, tpl)
    assert len(site) == n, (len(site), n)
    stub = R.stub_code(stub_va, blk)
    m[SITE_OFF:SITE_OFF + len(site)] = site
    m[STUB_OFF:STUB_OFF + len(stub)] = stub

    tgt = 0x0000700000001234
    ints = [0x1000 + i for i in range(6)]
    dbls = [0x3ff0000000000000 + i for i in range(4)]
    stkv = [0x1111000000000000 + 0x101 * k + 0x40 for k in range(NSTK)]
    for k, v in enumerate(stkv):
        struct.pack_into('<Q', m, SRC_OFF + 8 * k, v)

    tramp = make_tramp(tramp_va, site_va, src_va, ints, dbls, tgt)
    m[TRAMP_OFF:TRAMP_OFF + len(tramp)] = tramp

    fn = ctypes.CFUNCTYPE(ctypes.c_uint64, ctypes.c_void_p)(tramp_va)
    got = fn(src_va)

    # 被呼側相当: site が BLK+0x100 に copy した 12 語を読む (BLK+0x48 の pointer 先)
    words = [struct.unpack_from('<Q', m, BLK_OFF + 0x100 + 8 * k)[0] for k in range(NSTK)]

    expect = [stkv[(k + 1) % NSTK] if NEG else stkv[k] for k in range(NSTK)]
    matched = sum(1 for k in range(NSTK) if words[k] == expect[k])

    # stub の戻り値 = tgt + rcx + rdx + r8 + r9 + xmm0..3 (bit) + stk 12 語 (mod 2^64)
    exp_sum = (tgt + ints[3] + ints[2] + ints[4] + ints[5] + sum(dbls) + sum(expect)) & M64
    sum_ok = got == exp_sum

    print('sum_ok=%d got=0x%016x exp=0x%016x' % (sum_ok, got, exp_sum))
    ok = matched == NSTK and sum_ok
    if NEG:
        print('RESULT %s matched=%d/%d' % ('FAIL (negative control)' if not ok else 'PASS (unexpected)', matched, NSTK))
        return 1 if not ok else 0
    print('RESULT %s matched=%d/%d' % ('PASS' if ok else 'FAIL', matched, NSTK))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
