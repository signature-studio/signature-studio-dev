#!/usr/bin/env python3
"""gen_stubs_sigs.py — 最終 .ll から (1) 未 lift callee (`declare ... @function_<VA>`) の fail-fast C スタブ
(2) harness 用 sigs.json (define された function_<VA> のパラメータ型) を生成する。
usage: gen_stubs_sigs.py FINAL.ll stubs.c sigs.json [shims.json]  (shims: {"<va hex>": "memmove|memset"} = CRT 関数を C 実装へ置換 (レジスタグローバル ABI))"""
import json
import re
import sys

CT = {'i128': 'u128', 'i64': 'u64', 'i32': 'u32', 'i16': 'unsigned short', 'i8': 'u8', 'float': 'float', 'double': 'double', 'void': 'void', 'ptr': 'void*'}

# ---- KH-4: Win32 named import shim (レジスタグローバル ABI: 引数 rcx/rdx/r8..., 戻り rax)。
# 割当アドレス KH_HEAP (0x05000000, 1MB) は arena(0x04000000..0x04800000) の直後で、
# wasm リニアメモリ (96MB) 内。bump 状態は KH_HEAP 先頭 8B に置き native (scenario が IAT を同実装へ
# patch) と wasm で同一進行。割当は常に 16B 整列 + ゼロ充填 = 決定的 (HeapAlloc の未初期化内容も一致)。
HEAP_C = r'''
#include <stdlib.h>
#define KH_HEAP 0x05000000ULL
#define KH_HEAP_END (0x05000000ULL + 0x100000ULL)
static u64 kh_heap_alloc(u64 bytes) {
  u64 cur = *(u64*)(unsigned int)0x04000100ULL;   /* bump 状態はアリーナ内 (scenario が trial 毎に 0 reset) */
  if (cur == 0) cur = KH_HEAP + 16;
  u64 a = (cur + 15) & ~(u64)15;
  if (bytes > KH_HEAP_END - KH_HEAP) return 0;
  u64 n = (bytes + 15) & ~(u64)15;
  if (a + n > KH_HEAP_END) return 0;
  unsigned char* m = (unsigned char*)(unsigned int)a;
  for (u64 i = 0; i < n; i++) m[i] = 0;
  *(u64*)(unsigned int)0x04000100ULL = a + n;
  return a;
}
'''

IMP_SHIM = {
    'HeapAlloc': 'rax = kh_heap_alloc(r8);',
    'HeapFree': 'rax = 1;',
    'GetProcessHeap': 'rax = 1;',
    'SetLastError': 'rax = 0;',
    'EnterCriticalSection': 'rax = 0;',
    'LeaveCriticalSection': 'rax = 0;',
    'InitializeCriticalSection': 'rax = 0;',
    'InitializeCriticalSectionAndSpinCount': 'rax = 1;',
    'InitializeCriticalSectionEx': 'rax = 1;',
    'DeleteCriticalSection': 'rax = 0;',
    'IsProcessorFeaturePresent': 'rax = 1;',
    'IsDebuggerPresent': 'rax = 0;',
    'GetCurrentProcess': 'rax = 0xffffffffffffffffULL;',
    'GetCurrentProcessId': 'rax = 1234;',
    'GetCurrentThreadId': 'rax = 1;',
    'TlsGetValue': 'rax = 0x04000200ULL;',   # arena scratch (native shim と同一)
    'FlsGetValue': 'rax = 0x04000200ULL;',
    'FlsSetValue': 'rax = 1;',
    'RaiseException': 'rax = 1;',
}


def main():
    src, stubs, sigs = sys.argv[1:4]
    shims = json.load(open(sys.argv[4])) if len(sys.argv) > 4 else {}
    out = ['#include "msimd6_core.h"', '#include <emscripten.h>']
    defined, sg = set(), {}
    text = open(src).read().split('\n')
    for l in text:
        m = re.match(r'^define (\S+) @function_([0-9a-f]+)\(([^)]*)\)', l)
        if m:
            defined.add(m.group(2))
            ps = [p.strip().split()[0] for p in m.group(3).split(',') if p.strip()]
            sg[m.group(2)] = {'params': ps, 'ret': m.group(1)}
    nstub = 0
    SH = {'memmove': 'memmove((void*)(u32)rcx, (void*)(u32)rdx, (u32)r8); rax = rcx;', 'memset': 'memset((void*)(u32)rcx, (int)(rdx & 0xff), (u32)r8); rax = rcx;',
          'ret0': ''}   # 早期 return パスのみ使う関数 (Disperser の 0x18004df70: ctx+0xa8 != 1 なら epilogue のみ = 副作用なし)
    # CRT _dint / _fdint (modf 系: 小数部を切り捨て。ImageBase 相対の mask 表を引くため lift 不能 → 同一意味の C 実装。差分試験で検証)
    SH['dint'] = ('{ double* p = (double*)(u32)rcx; u64 b; memcpy(&b, p, 8); unsigned ex = (b >> 52) & 0x7ff; u64 sc = (unsigned short)rdx; u64 res;'
                  ' if (ex == 0x7ff) res = ((b & 0xfffffffffffffULL) == 0) ? 1 : 2;'
                  ' else if ((b & 0x7fffffffffffffffULL) == 0) res = sc;'
                  ' else { int r = (short)(0x433 - (int)ex - (int)sc); if (r <= 0) res = sc; else if (r >= 0x35) { b &= 0x8000000000000000ULL; memcpy(p, &b, 8); res = 0xffffffffULL; }'
                  ' else { u64 m = (1ULL << r) - 1; res = (b & m) ? 0xffff : 0; b &= ~m; memcpy(p, &b, 8); } } rax = res; }')
    SH['fint'] = ('{ float* p = (float*)(u32)rcx; u32 b; memcpy(&b, p, 4); unsigned ex = (b >> 23) & 0xff; u64 sc = (unsigned short)rdx; u64 res;'
                  ' if (ex == 0xff) res = ((b & 0x7fffff) == 0) ? 1 : 2;'
                  ' else if ((b & 0x7fffffffU) == 0) res = sc;'
                  ' else { int r = (short)(0x96 - (int)ex - (int)sc); if (r <= 0) res = sc; else if (r >= 0x18) { b &= 0x80000000U; memcpy(p, &b, 4); res = 0xffffffffULL; }'
                  ' else { u32 m = (1U << r) - 1; res = (b & m) ? 0xffff : 0; b &= ~m; memcpy(p, &b, 4); } } rax = res; }')
    if shims:
        out.append('extern u64 rax, rcx, rdx, r8;')
    # ---- named import (Win32/CRT) の使用確認 → shim または fail-fast stub (レジスタグローバル ABI)
    body = '\n'.join(x for x in text if not x.startswith('declare '))
    used_names = sorted({n for n in re.findall(r'@([A-Za-z][\w]*)\(', body)
                         if not n.startswith(('function_', 'kh_', 'llvm', 'global_var'))})
    if used_names:
        out.append(HEAP_C)
        out.append('extern u64 rax, rcx, rdx, r8, r9;')
    for n in used_names:
        if n in IMP_SHIM:
            out.append('EMSCRIPTEN_KEEPALIVE u64 %s(void) { %s return rax; }' % (n, IMP_SHIM[n]))
        else:
            out.append('EMSCRIPTEN_KEEPALIVE u64 %s(void) { abort(); return 0; }   /* Win32 import: fail-fast (到達したら fuzz が検出) */' % n)
        nstub += 1
    for l in text:
        m = re.match(r'^declare (\S+) @function_([0-9a-f]+)\(([^)]*)\)', l)
        if m and m.group(2) in shims and m.group(2) not in defined:
            bd = SH[shims[m.group(2)]]
            out.append('EMSCRIPTEN_KEEPALIVE u64 function_%s(void) %s' % (m.group(2), bd if bd.startswith('{') else '{ %s return 0; }' % bd) if bd.startswith('{') else 'EMSCRIPTEN_KEEPALIVE u64 function_%s(void) { %s return 0; }' % (m.group(2), bd))
            nstub += 1
            continue
        if m and m.group(2) not in defined:
            ps = [p.strip().split()[0] for p in m.group(3).split(',') if p.strip()]
            r = m.group(1)
            args = ', '.join('%s a%d' % (CT.get(t, 'u64'), i) for i, t in enumerate(ps)) or 'void'
            out.append('EMSCRIPTEN_KEEPALIVE %s function_%s(%s) { abort(); %s}' % (CT.get(r, 'u64'), m.group(2), args, '' if r == 'void' else 'return 0; '))
            nstub += 1
    out.append('unsigned char kh_stack[65536] __attribute__((aligned(16), used));')
    open(stubs, 'w').write('\n'.join(out) + '\n')
    json.dump(sg, open(sigs, 'w'), indent=1)
    print('[stubs/sigs] defined %d, stubs %d' % (len(sg), nstub))


if __name__ == '__main__':
    main()
