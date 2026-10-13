#!/usr/bin/env python3
# HeapAlloc の同型性試験 (#1116): gen_stubs_sigs.py の HEAP_C の kh_heap_alloc と
# harness/scen_khmath.h の n_HeapAlloc を、同じ要求列で 2 round 実行して戻り値・cursor を比べる。
# 両方のソースを読んで抽出するため、どちらかを直すと試験も追従する。ホスト x86_64 (gcc, ms_abi) 前提。
import os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.dirname(HERE)
OUT = os.path.join(SNAP, 'work', 'heap_diff')
os.makedirs(OUT, exist_ok=True)

gen = open(os.path.join(SNAP, 'lift', 'gen_stubs_sigs.py')).read()
heap_c = re.search(r"HEAP_C = r'''(.*?)'''", gen, re.S).group(1)
heap_c = heap_c.replace('(unsigned int)', '(uintptr_t)')

khm = open(os.path.join(HERE, 'scen_khmath.h')).read()
m = re.search(r'u64 __attribute__\(\(ms_abi\)\) n_HeapAlloc\(.*?\n\}\n', khm, re.S)
if not m:
    sys.exit('n_HeapAlloc が scen_khmath.h に見つからない')
native_alloc = m.group(0)

src = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <sys/mman.h>
typedef unsigned long long u64;
typedef unsigned int u32;
#define CUR (*(u64*)(uintptr_t)0x04000100ULL)
''' + heap_c + '\n' + native_alloc + r'''
int main(void) {
    if (mmap((void*)0x04000000ULL, 0x02200000ULL, PROT_READ | PROT_WRITE,
             MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0) == MAP_FAILED) { perror("mmap"); return 2; }
    u64 reqs[] = {0, 1, 15, 17, 0x100000, 0x100001, ~0ULL, 0xF0000, 0x100000, 0x100000,
                  0x100000, 0x100000, 0x100000, 16, 0, 0x80000};
    int n = (int)(sizeof reqs / sizeof reqs[0]), total = 0, mism = 0;
    for (int round = 0; round < 2; round++) {
        memset((void*)0x05000000ULL, 0, 0x100000ULL + 0x10000ULL);
        CUR = 0;
        for (int i = 0; i < n; i++) {
            u64 s0 = CUR;
            u64 r1 = kh_heap_alloc(reqs[i]); u64 c1 = CUR;
            CUR = s0;
            u64 r2 = n_HeapAlloc(0, 0, reqs[i]); u64 c2 = CUR;
            CUR = c1;
            total++;
            if (r1 != r2 || c1 != c2) {
                mism++;
                printf("mismatch round=%d req=%llx heap=%llx native=%llx cur=%llx/%llx\n",
                       round, reqs[i], r1, r2, c1, c2);
            }
        }
    }
    printf("total=%d mismatches=%d\n", total, mism);
    return mism != 0;
}
'''
c_path = os.path.join(OUT, 'heap_alloc_diff.c')
bin_path = os.path.join(OUT, 'heap_alloc_diff')
open(c_path, 'w').write(src)
subprocess.run(['cc', '-O0', '-Wall', '-Wno-unused', '-o', bin_path, c_path], check=True)
sys.exit(subprocess.run([bin_path]).returncode)
