#!/usr/bin/env python3
"""MX-58 (#5399): REX の直後に来る F0 (LOCK) の実機観測。

関数 void f(u64 *p, u64 v) を mmap の実行可能領域に置き、`mov rax, rsi` の後に各ケースの
`add [rdi], eax` (01 07) / `add [rdi], rax` (48 01 07) を実行する。初期値 *p = 0x1_FFFFFFFF, v = 1。
  REX.W が効く  -> 0x2_00000000 (64 bit 加算)
  REX.W が効かず 32 bit 加算 -> 0x1_00000000
SIGILL (#UD) になるケースは子プロセスの returncode が -4 (または 132) になる。

usage: mx58_rex_probe.py            (全ケースを子プロセスで実行)
       mx58_rex_probe.py <hex>      (1 ケースを直接実行。子プロセス用)
"""
import ctypes, mmap, subprocess, sys

MOV = bytes.fromhex('48 89 f0')
CASES = {
    'nolock_plain':   '01 07 c3',
    'lock_plain':     'f0 01 07 c3',
    'lock_then_rexw': 'f0 48 01 07 c3',
    'rexw_then_lock': '48 f0 01 07 c3',
    'rex_then_lock':  '40 f0 01 07 c3',
    'rexb_then_lock': '41 f0 01 07 c3',
    'rexw_f2_lock':   '48 f2 f0 01 07 c3',
    'rex_f2_lock':    '40 f2 f0 01 07 c3',
    'rexw_f3_lock':   '48 f3 f0 01 07 c3',
}


def run(code):
    buf = mmap.mmap(-1, 4096, prot=mmap.PROT_READ | mmap.PROT_WRITE | mmap.PROT_EXEC)
    buf.write(MOV + code)
    addr = ctypes.addressof(ctypes.c_char.from_buffer(buf))
    fn = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint64)(addr)
    cell = ctypes.c_uint64(0x1_FFFFFFFF)
    fn(ctypes.addressof(cell), 1)
    return hex(cell.value)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        print(run(bytes.fromhex(sys.argv[1])))
        sys.exit(0)
    for name, hx in CASES.items():
        p = subprocess.run([sys.executable, __file__, hx.replace(' ', '')], capture_output=True, text=True, timeout=30)
        print('%-16s %-20s rc=%d %s' % (name, hx, p.returncode, p.stdout.strip() or p.stderr.strip()[-80:]))
