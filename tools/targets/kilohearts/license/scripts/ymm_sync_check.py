#!/usr/bin/env python3
"""ymm_sync_check.py — kh_lower の xmmN / ymmN 下位 128bit 同期規則 (KH-51 #3306) の検証。

2 関数の模擬 (実機 0x180f89cf0 / 0x180fb6124 と同じ形): A は VEX-128 で xmm2 を書き、B は ymm2 を読んで
vinsertf128 で書く。C は vzeroupper (`store i256 undef, @ymmN`)。RetDec stage-0 と同じ形の IR を kh_lower に通し、
clang で実行して xmm2 と ymm2 の整合を見る。

  on  : 同期規則あり (既定) → OK (rc 0) を期待
  off : `--skip ymmsync` (規則を外す = ネガティブコントロール) → MISMATCH (rc 1) を期待
  one : vzeroupper を含まず ymm 参照が 1 つだけの 2 関数 (A と B) → kh_lower rc 0 かつ `clang -c` 成功 (rc 0) を期待。
        wrapper の ymm_sync が参照する @ymmN の宣言漏れ (未宣言なら `use of undefined value`) を検出する

  usage: python3 scripts/ymm_sync_check.py   (license/ で実行。成果物は license/work/ymm_sync/ = gitignore)
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIC = os.path.dirname(HERE)
KH_LOWER = os.path.join(LIC, 'lift', 'kh_lower.py')
CORE = os.path.join(LIC, '..', 'work', 'winpkg', 'HeartCore.core_64')
W = os.path.join(LIC, 'work', 'ymm_sync')

S0 = """@_asm_program_counter = internal global i64 0
declare i128 @__asm_vmovd(i32)
declare i128 @__asm_vpshufd(i128, i8)
declare i256 @__asm_vinsertf128(i256, i128, i8)
declare void @__asm_vzeroupper()
define i64 @function_180f89cf0() {
; 0x180f89cf0
  store volatile i64 1, i64* @_asm_program_counter
  %a1 = call i128 @__asm_vmovd(i32 305419896)
  store i128 %a1, i128* @xmm2
; 0x180f89cf5
  store volatile i64 2, i64* @_asm_program_counter
  %a2 = load i128, i128* @xmm2
  %a3 = call i128 @__asm_vpshufd(i128 %a2, i8 0)
  store i128 %a3, i128* @xmm2
; 0x180f89cfb
  store volatile i64 3, i64* @_asm_program_counter
  ret i64 undef
}
define i64 @function_180fb6124() {
; 0x180fb6124
  store volatile i64 4, i64* @_asm_program_counter
  %b1 = load i256, i256* @ymm2
  %b2 = load i128, i128* @xmm2
  %b3 = call i256 @__asm_vinsertf128(i256 %b1, i128 %b2, i8 1)
  store i256 %b3, i256* @ymm2
; 0x180fb612b
  store volatile i64 5, i64* @_asm_program_counter
  ret i64 undef
}
define i64 @function_180fb6130() {
; 0x180fb6130
  store volatile i64 6, i64* @_asm_program_counter
  call void @__asm_vzeroupper()
""" + ''.join('  store i256 undef, i256* @ymm%d\n' % k for k in range(32)) + """  ret i64 undef
}
"""

S1 = S0.split('define i64 @function_180fb6130()')[0]

HELPERS = """define i128 @__asm_vmovd(i32 %a) {
  %z = zext i32 %a to i128
  ret i128 %z
}
define i128 @__asm_vpshufd(i128 %x, i8 %i) {
  %r = add i128 %x, 257
  ret i128 %r
}
define i256 @__asm_vinsertf128(i256 %a, i128 %b, i8 %i) {
  %lo = and i256 %a, 340282366920938463463374607431768211455
  %hi = zext i128 %b to i256
  %hs = shl i256 %hi, 128
  %r = or i256 %lo, %hs
  ret i256 %r
}
define void @__asm_vzeroupper() {
  ret void
}
"""


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def main():
    shutil.rmtree(W, ignore_errors=True)
    os.makedirs(W)
    open(os.path.join(W, 's0.ll'), 'w').write(S0)
    open(os.path.join(W, 'helpers.ll'), 'w').write(HELPERS)
    shutil.copy(os.path.join(HERE, 'ymm_sync_driver.c'), os.path.join(W, 'driver.c'))
    res = {}
    for tag, skip in (('on', 'icall'), ('off', 'icall,ymmsync')):
        d = os.path.join(W, tag)
        os.makedirs(d)
        low = os.path.join(d, 'lowered.ll')
        r = run([sys.executable, KH_LOWER, os.path.join(W, 's0.ll'), low, '--core', CORE,
                 '--lift', '180f89cf0,180fb6124,180fb6130', '--skip', skip])
        if r.returncode:
            print(r.stdout[-2000:], r.stderr[-2000:])
            return 2
        exe = os.path.join(d, 'a.out')
        c = run(['clang', '-O0', '-w', '-o', exe, low, os.path.join(W, 'helpers.ll'), os.path.join(W, 'driver.c')])
        if c.returncode:
            print(c.stderr[-3000:])
            return 2
        x = run([exe])
        ir = open(low).read()
        res[tag] = {
            'rc': x.returncode,
            'out': x.stdout.strip(),
            'kh_lower': r.stdout.strip(),
            'ymm_store_undef_lt16': len([l for l in ir.split('\n') if 'store i256 undef, i256* @ymm' in l and int(l.rsplit('@ymm', 1)[1]) < 16]),
            'xmm_loads_in_zero': ir.count('load i128, i128* @xmm'),
        }
    d = os.path.join(W, 'one')
    os.makedirs(d)
    s1 = os.path.join(d, 's1.ll')
    open(s1, 'w').write(S1)
    low = os.path.join(d, 'lowered.ll')
    r = run([sys.executable, KH_LOWER, s1, low, '--core', CORE, '--lift', '180f89cf0,180fb6124', '--skip', 'icall'])
    c = run(['clang', '-c', '-w', '-o', os.path.join(d, 'lowered.o'), low])
    res['one'] = {'lower_rc': r.returncode, 'clang_c_rc': c.returncode, 'clang_err': c.stderr.strip()[-300:]}
    ok = (res['on']['rc'] == 0 and res['on']['out'].startswith('OK') and res['off']['rc'] == 1 and res['off']['out'].startswith('MISMATCH')
          and res['one']['lower_rc'] == 0 and res['one']['clang_c_rc'] == 0)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    print('RESULT', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
