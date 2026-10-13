#!/usr/bin/env python3
"""kh710_check.py — #710 の named import 節 (HeapAlloc shim / decl_named_imports) のネイティブ検査。
emsdk・winpkg を要さない。lic_build.py の decl_named_imports と gen_stubs_sigs.py の HEAP_C を読み、
(1) 宣言補完の正例/負例 (2) kh_heap_alloc の境界・失敗値 (0 返却) をホスト gcc で確認する。
usage: python3 scripts/kh710_check.py   (終了 0 = 全 PASS)"""
import os
import re
import subprocess
import sys
import tempfile

LIC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(LIC, 'lift'))
import gen_stubs_sigs as g  # noqa: E402

fails = []


def check(name, cond, detail=''):
    print('%s %s %s' % ('PASS' if cond else 'FAIL', name, detail))
    if not cond:
        fails.append(name)


def decl_cases():
    src = open(os.path.join(LIC, 'lic_build.py')).read()
    ns = {'re': re, 'sys': sys}
    exec(src[src.index('def decl_named_imports'):src.index('def build(')], ns)
    d = ns['decl_named_imports']
    trap = 'declare void @llvm.trap()'
    body = 'define i64 @function_1()\n{\n  %%1 = call %s\n  ret i64 %%1\n}\n'
    out = d(body % 'i64 @GetCurrentThreadId()' + trap + '\n')
    check('decl:noarg_i64_added', 'declare i64 @GetCurrentThreadId()' in out)
    for name, call in [('with_args', 'i64 @HeapFree(i64 1, i64 2)'), ('fastcc', 'fastcc i64 @HeapFree(i64 1)')]:
        try:
            d(body % call + trap + '\n')
            check('decl:%s_rejected' % name, False)
        except SystemExit:
            check('decl:%s_rejected' % name, True)
    attr = 'define internal i64 @Foo(i64 %a) #0\n{\n  ret i64 0\n}\n'
    out = d(attr + body % 'i64 @Foo(i64 1)' + trap + '\n')
    check('decl:attr_define_no_dup', not re.search(r'^declare \S+ @Foo\b', out, re.M))
    try:
        d(body % 'i64 @GetCurrentThreadId()')
        check('decl:no_trap_rejected', False)
    except SystemExit:
        check('decl:no_trap_rejected', True)


def libc_clash_cases():
    ll = 'define i64 @function_1()\n{\n  %%1 = call i64 @%s()\n  ret i64 %%1\n}\ndeclare void @llvm.trap()\n'
    gen = os.path.join(LIC, 'lift', 'gen_stubs_sigs.py')
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, 'f.ll')
        for name, want in [('memcpy', 1), ('GetCurrentThreadId', 0)]:
            open(src, 'w').write(ll % name)
            r = subprocess.run([sys.executable, gen, src, os.path.join(td, 's.c'), os.path.join(td, 's.json')],
                               capture_output=True, text=True)
            check('libc_clash:%s_%s' % (name, 'rejected' if want else 'accepted'), (r.returncode != 0) == bool(want))
        open(src, 'w').write('define internal i64 @LocalHelper(i64 %a) #0 {\n  ret i64 %a\n}\n'
                             'define i64 @function_1()\n{\n  %1 = call i64 @LocalHelper(i64 1)\n  ret i64 %1\n}\n'
                             'declare void @llvm.trap()\nattributes #0 = { nounwind }\n')
        r = subprocess.run([sys.executable, gen, src, os.path.join(td, 's.c'), os.path.join(td, 's.json')],
                           capture_output=True, text=True)
        stubbed = 'LocalHelper(void)' in open(os.path.join(td, 's.c')).read()
        check('define_not_stubbed', r.returncode == 0 and not stubbed)


def heap_cases():
    c = g.HEAP_C
    c = c.replace('#define KH_HEAP 0x05000000ULL', '#define KH_HEAP ((u64)(uintptr_t)HB)')
    c = c.replace('#define KH_HEAP_END (0x05000000ULL + 0x100000ULL)', '#define KH_HEAP_END (KH_HEAP + 0x100000ULL)')
    c = c.replace('(unsigned int)0x04000100ULL', '(unsigned long)&ST')
    c = c.replace('(unsigned int)a', '(unsigned long)a')
    prog = ('#include <stdint.h>\n#include <stdio.h>\n#include <stdlib.h>\ntypedef uint64_t u64;\ntypedef uint8_t u8;\n'
            'static u8 HB[0x100000 + 0x1000] __attribute__((aligned(16)));\nstatic u64 ST;\n' + c + r'''
int main(void) {
  u64 p1 = kh_heap_alloc(100), p2 = kh_heap_alloc(16);
  printf("p1=%llu\n", (unsigned long long)(p1 != 0));
  printf("p2=%llu\n", (unsigned long long)(p2 != 0));
  printf("aligned=%d\n", (int)(((p1 | p2) & 15) == 0));
  for (int i = 0; i < 100; i++) ((u8*)(uintptr_t)p1)[i] = 0xAB;
  printf("big=%llu\n", (unsigned long long)kh_heap_alloc(0x200000));
  printf("huge=%llu\n", (unsigned long long)kh_heap_alloc(0xFFFFFFFFFFFFFFF0ULL));
  printf("max=%llu\n", (unsigned long long)kh_heap_alloc(0xF0000));
  printf("overflow=%llu\n", (unsigned long long)kh_heap_alloc(0xF0000));
  int ok = 1;
  for (int i = 0; i < 100; i++) if (((u8*)(uintptr_t)p1)[i] != 0xAB) ok = 0;
  printf("p1_intact=%d\n", ok);
  return 0;
}
''')
    with tempfile.TemporaryDirectory() as td:
        cf, exe = os.path.join(td, 'h.c'), os.path.join(td, 'h')
        open(cf, 'w').write(prog)
        subprocess.run(['gcc', '-O1', '-w', cf, '-o', exe], check=True)
        out = subprocess.run([exe], capture_output=True, text=True, check=True).stdout
    kv = dict(l.split('=') for l in out.split('\n') if '=' in l)
    check('heap:basic_alloc', kv['p1'] == '1' and kv['p2'] == '1', str(kv))
    check('heap:16B_aligned', kv['aligned'] == '1')
    check('heap:oversize_2MB_returns_0', kv['big'] == '0')
    check('heap:huge_returns_0', kv['huge'] == '0')
    check('heap:max_region_ok', kv['max'] != '0')
    check('heap:exhausted_returns_0', kv['overflow'] == '0')
    check('heap:live_block_intact', kv['p1_intact'] == '1')


def placement_cases():
    """HeapAlloc のカーソル (static) と TLS 返却値が、arena (0x04000000..0x04800000) の
    operator new 域・sys・cave (0x05000000 4KB) と重ならないことを生成コードの定数で確認する (#710 review)。"""
    arena = (0x04000000, 0x04800000)
    cave = (0x05000000, 0x05001000)
    heap = (0x05000000, 0x05100000)
    tls = int(re.search(r'#define KH_TLS (0x[0-9A-Fa-f]+)ULL', g.HEAP_C).group(1), 16)
    check('placement:tls_outside_arena', not (arena[0] <= tls < arena[1]) and not (cave[0] <= tls < cave[1]), hex(tls))
    check('placement:tls_outside_heap', not (heap[0] <= tls < heap[1]), hex(tls))
    check('placement:cursor_is_static', 'static u64 kh_cursor' in g.HEAP_C and '0x04000100' not in g.HEAP_C)
    shim_tls = [g.IMP_SHIM[k] for k in ('TlsGetValue', 'FlsGetValue')]
    check('placement:tls_shim_uses_KH_TLS', all('KH_TLS' in s and '0x04000200' not in s for s in shim_tls))


decl_cases()
libc_clash_cases()
heap_cases()
placement_cases()
print('RESULT %s' % ('PASS' if not fails else 'FAIL ' + ','.join(fails)))
sys.exit(1 if fails else 0)
