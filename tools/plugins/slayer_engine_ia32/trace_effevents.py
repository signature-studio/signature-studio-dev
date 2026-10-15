#!/usr/bin/env python3
"""engine (block22434) の effProcessEvents (opcode 25) が VstEvents を読む箇所の到達解析 (#3880)。

  trace_effevents.py         呼出し連鎖を静的に辿り、events を読む関数と読取命令を表示する。 不一致で exit 1。
  trace_effevents.py --nega  ネガコン (壊した期待は必ず FAIL)。 miss > 0 で exit 1。

素材: $FL_WIN64_DIR/extracted/block22434_PE.bin (既定 $RUNNER_TEMP/fl-win64)。 依存: capstone==5.0.7。
方式: 線形掃引の形列挙ではなく、AEffect の dispatcher (thunk) から opcode 25 の経路を辿る。
"""
import argparse, os, struct, sys

try:
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
except ImportError:
    sys.exit('capstone が無い: uv pip install --python <python> capstone==5.0.7')

EXPECT_CAPSTONE = '5.0.7'
EXPECT_SHA256 = '84b64c43cc6528401e1c4e84074785e100e8453c4db4c8322a5d5f608de724a9'
IMAGE_BASE = 0x10000000
TEXT_RVA, TEXT_FOFF, TEXT_SIZE = 0x1000, 0x1000, 73002

# 静的に確定した経路 (VA)。 各値は下の検証で実バイナリと突き合わせる。
THUNK = 0x10001000        # AEffect.dispatcher (ctor が this+0x24 に格納)
AE_DISPATCH_OFF = 0x24
CTOR = 0x100010E0         # engine AEffect 構築関数 (RVA 0x10E0)
VT_BASE = 0x100130E0      # ctor が object に書く基底 vtable
DISPATCH_BASE = 0x10001300  # 基底 vtable[+0x18]
VT_DERIVED = 0x100131E8   # 派生 vtable (0x1bb3・0x1be0 で設定)
DISPATCH_DERIVED = 0x10001BF0  # 派生 vtable[+0x18]: switch は opcode 25 (0x19) から始まる
JUMP_TABLE_DERIVED = 0x1000217C  # 派生 dispatcher の jump table (case 25 から)
CASE25_TARGET = 0x10001C0D    # 派生 dispatcher の case 25
PROCESS_EVENTS_SLOT = 0xC8    # case 25 が call する vtable オフセット
NOOP_STUB = 0x10001A90        # 派生 vtable[+0xc8] = xor eax,eax; ret 4 (events を読まない)
VT_EVENTS = 0x10013690        # events 走査本体を持つ vtable (ctor 0x7f30 が設定)
VT_EVENTS_IMPL = 0x10008FA0   # vtable 0x13690 の +0xc8 (events 走査本体)
EVENTS_LOOP_STEP = 0x100091B9 # 走査ループ末尾 (esi += 4 は 0x100091C8)


def load():
    root = os.environ.get('FL_WIN64_DIR') or os.path.join(os.environ.get('RUNNER_TEMP', '/tmp'), 'fl-win64')
    path = os.path.join(root, 'extracted', 'block22434_PE.bin')
    data = open(path, 'rb').read()
    return path, data


def rva_to_off(va):
    return va - IMAGE_BASE - TEXT_RVA + TEXT_FOFF


def dword(data, va):
    return struct.unpack_from('<I', data, va - IMAGE_BASE)[0]


def disasm(data, va, n):
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    off = va - IMAGE_BASE
    return [(i.address, i.mnemonic, i.op_str) for i in md.disasm(data[off:off + n], va)]


def check(data):
    """期待値を実バイナリで確認。 返り値 = 失敗理由のリスト。"""
    fails = []
    got = {
        'base_vt_slot18': dword(data, VT_BASE + 0x18),
        'events_vt_slot18': dword(data, VT_EVENTS + 0x18),
        'derived_case25': dword(data, JUMP_TABLE_DERIVED),
        'events_vt_slot_c8': dword(data, VT_EVENTS + PROCESS_EVENTS_SLOT),
        'derived_vt_slot_c8': dword(data, VT_DERIVED + PROCESS_EVENTS_SLOT),
    }
    # thunk: opcode 1 以外を object vtable[+0x18] へ転送 (call dword ptr [edx+0x18])
    if not any(m == 'call' and s == 'dword ptr [edx + 0x18]' for _, m, s in disasm(data, THUNK, 0x40)):
        fails.append('thunk に call [edx+0x18] が無い')
    # 派生 dispatcher: sub 0x19 して cmp 0x33 (= opcode 25..76 の範囲)
    d_asm = disasm(data, DISPATCH_DERIVED, 0x20)
    if not any(m == 'lea' and s == 'edx, [esi - 0x19]' for _, m, s in d_asm):
        fails.append('派生 dispatcher は opcode 25 (0x19) から始まらない')
    if not any(m == 'cmp' and s == 'edx, 0x33' for _, m, s in d_asm):
        fails.append('派生 dispatcher の範囲 (cmp edx,0x33) が無い')
    # events 走査: [arg+0] (numEvents) を cmp して、[arg+8] の 4 B 配列を走査
    ev_asm = disasm(data, VT_EVENTS_IMPL, 0x30)
    if not any(m == 'cmp' and s == 'dword ptr [eax], 0' for _, m, s in ev_asm):
        fails.append('events 走査が numEvents (cmp [eax],0) を読まない')
    if not any(m == 'add' and s == 'esi, 4' for _, m, s in disasm(data, EVENTS_LOOP_STEP, 0x18)):
        fails.append('events 走査のポインタ増分 (add esi,4) が無い')

    want = {
        'base_vt_slot18': DISPATCH_BASE,
        'events_vt_slot18': DISPATCH_DERIVED,
        'derived_case25': CASE25_TARGET,
        'events_vt_slot_c8': VT_EVENTS_IMPL,
        'derived_vt_slot_c8': NOOP_STUB,
    }
    for k, w in want.items():
        if got[k] != w:
            fails.append(f'{k} = 0x{got[k]:08x}, want 0x{w:08x}')
    return fails


def report(path, data):
    print(f'[input] {path}')
    print(f'[route] host -> AEffect.dispatcher 0x{THUNK:08x} -> object(this) vtable[+0x18] = 0x{dword(data, VT_EVENTS + 0x18):08x}')
    print(f'[route] case 25 (jump table 0x{JUMP_TABLE_DERIVED:08x}) -> 0x{CASE25_TARGET:08x} -> vtable[+0xc8] = 0x{VT_EVENTS_IMPL:08x}')
    print(f'[route] 参考: 基底 vtable 0x{VT_BASE:08x}[+0x18] = 0x{DISPATCH_BASE:08x} (opcode 25 は既定分岐)')
    print('[events] numEvents = [arg+0] (cmp dword ptr [eax],0)、events[i] = [arg+8 + 4*i] (ポインタ 4 B、stride 4)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--nega', action='store_true')
    args = ap.parse_args()
    import capstone
    if capstone.__version__ != EXPECT_CAPSTONE:
        sys.exit(f'[pin] capstone {capstone.__version__} != {EXPECT_CAPSTONE}')
    path, data = load()
    import hashlib
    if hashlib.sha256(data).hexdigest() != EXPECT_SHA256:
        sys.exit('[input] FAIL sha256 mismatch')
    if args.nega:
        return nega(data)
    report(path, data)
    fails = check(data)
    for f in fails:
        print('[FAIL]', f)
    if fails:
        sys.exit(1)
    print('[trace] OK')


def nega(data):
    miss = 0
    # N1: 基底 vtable[+0x18] の期待を 1 bit ずらす → FAIL になるべき
    bad = bytearray(data)
    off = VT_BASE + 0x18 - IMAGE_BASE
    bad[off] ^= 0x01
    fails = check(bytes(bad))
    hit = any('base_vt_slot18' in f for f in fails)
    print(f'[nega N1] base_vt_slot18 1bit 破壊: {"HIT" if hit else "MISS"}')
    miss += 0 if hit else 1
    # N2: 派生 dispatcher の範囲 (cmp 0x33) を変える → FAIL になるべき
    bad = bytearray(data)
    d_off = DISPATCH_DERIVED - IMAGE_BASE
    # 派生 dispatcher の cmp edx,0x33 の即値 (ca. +0x0f: 83 fa 33) を 0x34 に変える
    idx = bytes(data[d_off:d_off + 0x20]).find(b'\x83\xfa\x33')
    if idx >= 0:
        bad[d_off + idx + 2] = 0x34
    fails = check(bytes(bad))
    hit = any('範囲' in f for f in fails)
    print(f'[nega N2] 派生 dispatcher の範囲 0x33→0x34: {"HIT" if hit else "MISS"}')
    miss += 0 if hit else 1
    # N3: events 走査の numEvents 読取 (cmp dword ptr [eax], 0) を壊す → FAIL になるべき
    bad = bytearray(data)
    e_off = VT_EVENTS_IMPL - IMAGE_BASE
    idx = bytes(data[e_off:e_off + 0x30]).find(b'\x83\x38\x00')
    if idx >= 0:
        bad[e_off + idx + 2] = 0x01
    fails = check(bytes(bad))
    hit = any('numEvents' in f for f in fails)
    print(f'[nega N3] numEvents 読取の即値 0→1: {"HIT" if hit else "MISS"}')
    miss += 0 if hit else 1
    print(f'nega: {3 - miss}/3 hit, {miss} miss')
    sys.exit(1 if miss else 0)


if __name__ == '__main__':
    main()
