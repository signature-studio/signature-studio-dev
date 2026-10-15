#!/usr/bin/env python3
# HeapAlloc のネガコン (#1116 受入条件 2): gen_stubs_sigs.py の HEAP_C (kh_heap_alloc) を
# ホスト x86_64 gcc で直接実行し、過大要求・領域超過が 0 を返すこと、先に確保したブロックと
# cursor が失敗で壊れないことを確認する。license 版 license/scripts/kh710_check.py の heap_cases と同等。
import os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.dirname(HERE)
OUT = os.path.join(SNAP, 'work', 'heap_negctrl')
os.makedirs(OUT, exist_ok=True)

gen = open(os.path.join(SNAP, 'lift', 'gen_stubs_sigs.py')).read()
heap_c = re.search(r"HEAP_C = r'''(.*?)'''", gen, re.S).group(1)
heap_c = heap_c.replace('(unsigned int)', '(uintptr_t)')

src = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
typedef unsigned long long u64;
typedef unsigned char u8;
#define CUR (*(u64*)(uintptr_t)0x04000100ULL)
''' + heap_c + r'''
static int fails = 0;
static void check(const char* name, int ok) {
    printf("%s %s\n", ok ? "PASS" : "FAIL", name);
    if (!ok) fails++;
}
int main(void) {
    if (mmap((void*)0x04000000ULL, 0x02200000ULL, PROT_READ | PROT_WRITE,
             MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0) == MAP_FAILED) { perror("mmap"); return 2; }
    memset((void*)0x05000000ULL, 0, 0x100000ULL + 0x10000ULL);
    CUR = 0;
    u64 p1 = kh_heap_alloc(100);
    check("basic_alloc", p1 != 0);
    for (u64 i = 0; i < 100; i++) ((u8*)(uintptr_t)p1)[i] = 0xAB;
    u64 cur0 = CUR;
    u64 big = kh_heap_alloc(0x200000);
    check("2MB_returns_0", big == 0);
    check("2MB_cursor_unchanged", CUR == cur0);
    u64 huge = kh_heap_alloc(0xFFFFFFFFFFFFFFF0ULL);
    check("huge_returns_0", huge == 0);
    check("huge_cursor_unchanged", CUR == cur0);
    u64 max = kh_heap_alloc(0x100000);
    check("1MB_ok_or_exhausted_0", max == 0 || max >= 0x05000000ULL);
    u64 over = kh_heap_alloc(0x100000);
    check("exhausted_returns_0", over == 0);
    int ok = 1;
    for (u64 i = 0; i < 100; i++) if (((u8*)(uintptr_t)p1)[i] != 0xAB) ok = 0;
    check("live_block_intact", ok);
    printf("RESULT %s\n", fails ? "FAIL" : "PASS");
    return fails != 0;
}
'''
c_path = os.path.join(OUT, 'heap_negctrl.c')
bin_path = os.path.join(OUT, 'heap_negctrl')
open(c_path, 'w').write(src)
subprocess.run(['cc', '-O1', '-Wall', '-Wno-unused', '-o', bin_path, c_path], check=True)
sys.exit(subprocess.run([bin_path]).returncode)
