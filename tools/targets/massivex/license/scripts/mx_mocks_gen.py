#!/usr/bin/env python3
"""mx_mocks_gen.py — run_all.ll の declare から wasm シグネチャ完全一致の mock C を生成する。

背景: emcc (wasm32) では LLVM ポインタ = i32 に lowering されるため、C 側で
uint64_t (i64) を受ける mock とシグネチャが不一致になる (wasm-ld warning → 実行時 ABI 崩れ)。
本スクリプトは declare の型をそのまま wasm lowering 後の C 型へ写像し、
挙動付き mock (判定系・allocator・string 系) を名前表で注入する。

usage: mx_mocks_gen.py <run_all.ll> <out_mocks_gen.c>
"""
import re
import sys

# i128 → C 型
TYMAP = {
    'i1': 'uint8_t', 'i8': 'uint8_t', 'i16': 'uint16_t', 'i32': 'uint32_t',
    'i64': 'uint64_t', 'i128': 'unsigned __int128', 'i8*': 'uint32_t',
    'i16*': 'uint32_t', 'i32*': 'uint32_t', 'i64*': 'uint32_t',
    'i128*': 'uint32_t', 'ptr': 'uint32_t', 'void': 'void',
}

# 挙動付き mock (本体は GENERATOR が埋め込む)。キーは LLVM 名。
BEHAVIOR = {
    'function_1807182f6': 'return mc_ras_enabled;',
    'function_180718400': 'return mc_sysid_check1;',
    'function_180718b4b': 'return mc_final_ok;',
    'function_18129f8da': 'return mc_sysid_cmp;',
    'function_1812a01fa': 'return mc_fb1;',
    'function_1812a04e1': 'return mc_fb2;',
    'function_1812a11b0': 'return mc_strfmt;',
    'function_180b7cc89': 'return mc_add_rc;',
    'function_180bafa56': 'return mx_alloc(p0);',
    'function_181a527b8': 'return mx_alloc(p0);',
    'function_180bb005f': 'return mx_alloc(p0);',
    'function_180bafdef': 'return mx_alloc(p0);',
    'function_180bb0017': 'return mx_alloc(p0);',
    'function_180bb0466': 'return mx_alloc(p0);',
    'function_180bb067c': 'return mx_alloc(p0);',
    'function_180bafffd': 'return mx_alloc(p0);',
    'function_18073a526': 'if (p1) *(uint32_t *)(uintptr_t)p1 = 0x1111; return 0;',
    'function_18074b6ce': 'return 0x2222;',
    'unknown_17f6fdc73': 'return mc_serial_eq;',
    'function_180bc327d': 'if (p2) mx_sso_set((void *)(uintptr_t)p2, "1H0LR-SSPXD-FUZ81-PKS4D"); return mc_lookup_rc;',
    'function_180bc382d': 'if (p2) *(uint32_t *)(uintptr_t)p2 = 0x9000; return mc_lookup_rc;',
    'unknown_17f6fe144': 'if (p1) mx_sub_fill((void *)(uintptr_t)p1); return 0;',
    'function_18396fb60': 'if (p0 && p1 && p2) memcpy((void *)(uintptr_t)p0, (const void *)(uintptr_t)p1, (size_t)(p2 & 0xffffffff)); return p0;',
    'function_18396fb60_5': 'if (p0 && p1 && p2) memcpy((void *)(uintptr_t)p0, (const void *)(uintptr_t)p1, (size_t)(p2 & 0xffffffff)); return p0;',
    'function_18396fc40': 'if (p0 && p1 && p2) memcpy((void *)(uintptr_t)p0, (const void *)(uintptr_t)p1, (size_t)(p2 & 0xffffffff)); return p0;',
    '__readgsqword': 'mx_tls_init(); return mx_tls_page[(p0 & 0xfff) >> 3];',
    '__asm_movups': 'return p0;',
    '__asm_xorps': 'return p0;',
    '__asm_movaps': 'return (uint64_t)p0;',
    '__asm_movups.1': 'return;',
}

ALLOC_RET_ZERO_OK = True


def param_types(retty, params):
    """declare の引数型列 → C 型列 (空なら [])"""
    out = []
    for p in params:
        p = p.strip()
        if not p:
            continue
        ty = p.split()[0]
        if ty not in TYMAP:
            raise SystemExit('unknown param type: %r in %s' % (p, params))
        out.append(TYMAP[ty])
    return out


def c_ident(name):
    return re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name) is not None


def main():
    ll, out = sys.argv[1], sys.argv[2]
    decls = []
    for l in open(ll):
        if not l.startswith('declare'):
            continue
        m = re.match(r'declare (\S+) (@[\w.0-9]+)\(([^)]*)\)', l.strip())
        if not m:
            continue
        retty, name, params = m.group(1), m.group(2).lstrip('@'), m.group(3)
        if not c_ident(name):
            continue   # ドット付き名 (@__asm_movups.1 等) は mocks_extra.ll で定義
        decls.append((retty, name, [p for p in params.split(',')]))

    with open(out, 'w') as f:
        f.write('/* 自動生成: mx_mocks_gen.py — 編集しない (mx_mocks_gen.py を修正) */\n')
        f.write('#include <stdint.h>\n#include <stdlib.h>\n#include <string.h>\n')
        f.write('''
typedef unsigned __int128 u128;
uint64_t mc_ras_enabled = 1, mc_sysid_check1 = 0, mc_final_ok = 0, mc_sysid_cmp = 1;
uint64_t mc_fb1 = 1, mc_fb2 = 1, mc_lookup_rc = 0, mc_serial_eq = 0;
uint64_t mc_prod_has = 0, mc_prod_type = 0, mc_add_rc = 1, mc_strfmt = 0;
uint32_t g_tls = 0x7ff00000;
unsigned __int128 mx_harness_str0 = 1;

static uint32_t mx_alloc(uint32_t n) {
    void *p = calloc(1, n ? n : 16);
    return (uint32_t)(uintptr_t)p;
}
/* TLS モデル: gs_base = mx_tls_page。gs:[0x58] → TEB 相当 (page 内) を指す。
   IR 側は rcx=readgsqword(0x58) → [rcx+slot*8] → [ptr+0xe0] の二重 indirect を張る。 */
static uint64_t mx_tls_page[0x200];
static int mx_tls_ready = 0;
static void mx_tls_init(void) {
    if (mx_tls_ready) return;
    for (int i = 0; i < 0x200; i++) mx_tls_page[i] = (uint64_t)(uintptr_t)&mx_tls_page[0x100];
    mx_tls_ready = 1;
}
static void mx_sso_set(void *p, const char *s) {
    size_t n = strlen(s);
    memset(p, 0, 0x20);
    if (n < 16) {
        memcpy(p, s, n);
        *(uint32_t *)((char *)p + 0x10) = (uint32_t)n;
        *(uint32_t *)((char *)p + 0x18) = 15;
    } else {
        char *h = (char *)malloc(n + 1);
        memcpy(h, s, n + 1);
        *(uint32_t *)p = (uint32_t)(uintptr_t)h;
        *(uint32_t *)((char *)p + 0x10) = (uint32_t)n;
        *(uint32_t *)((char *)p + 0x18) = (uint32_t)n;
    }
}
static void mx_sub_fill(void *p) {
    mx_sso_set(p, mc_prod_has ? "premium" : "");
    *(uint32_t *)((char *)p + 0x28) = (uint32_t)mc_prod_type;
    *((uint8_t *)p + 0x30) = (uint8_t)mc_prod_has;   /* has: machine は [rbp+0x60] = base+0x30 を読む */
}
''')
        for retty, name, params in decls:
            tys = param_types(retty, params)
            rt = TYMAP.get(retty)
            if rt is None:
                raise SystemExit('unknown return type: %r (%s)' % (retty, name))
            args = ', '.join('%s p%d' % (t, i) for i, t in enumerate(tys))
            f.write('%s %s(%s) {\n' % (rt, name, args))
            body = BEHAVIOR.get(name, 'return 0;')
            if retty == 'void':
                body = body.replace('return 0;', 'return;').replace('return p0;', 'return;').replace('return p0; ', '')
            f.write('  %s\n}\n' % body)
    print('mx_mocks_gen: %d declares -> %s' % (len(decls), out))


if __name__ == '__main__':
    main()
