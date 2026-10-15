#!/usr/bin/env python3
# watch_ir_942.py: boot_final3.ll に観測フック m11_wh(id, addr) を差し込む (#942 受入 2・診断専用)。
# 対象は通常 boot で unit 17 の trap 直前 (WATCH_ADDR の 8B が 0x100000000 になる区間) の呼出し連鎖:
#   function_455790 → function_44bb70 → function_446400 → function_447860 → function_446370 → GetLocaleInfoW
# フックは watch_shim_942.c の m11_wh (固定アドレス 0x11FFF000 のリングに (id, *addr) を記録) を呼ぶ。
# 読み出しは watch_slot_942.mjs。
# 使い方: WATCH_ADDR=0x10aa10b8 python3 tools/m11/ldfix/watch_ir_942.py <in.ll> <out.ll>
import os, re, sys

src, dst = sys.argv[1], sys.argv[2]
ADDR = int(os.environ.get('WATCH_ADDR', '0x10aa10b8'), 16)
lines = open(src, errors='replace').read().split('\n')

# 関数ごとの観測点: entry (ラベル直後) と 各 call の直前/直後
ENTRY = {'455790': 90, '44bb70': 190, '44bae0': 180, '44ba50': 300, '446400': 1, '447860': 3, '446370': 10}
# 関数内の行パターンの直前 (before) / 直後 (after) に hook を入れる
LINE_HOOK = {'44ba50': [(r'call i1 @GetCPInfo', 'after', 301), (r'^  ret i64', 'before', 302)]}
CHAIN = {'455790': 100, '44bb70': 200, '446400': 0, '447860': 0}  # call 直後に base+k を入れる関数
BEFORE = {('446400', 'function_447860'): 2}  # (caller, callee) の直前
AFTER_CALLEE = {'447860': {'function_415610': 4, 'function_410b10': 5, 'function_410820': 6, 'function_417fc0': 7}}


def hook(n):
    return '  call void @m11_wh(i64 %d, i64 %d)' % (n, ADDR)


out = list(lines[:2]) + ['declare void @m11_wh(i64, i64)']
fn = None
k_in = {}
hit = set()
for ln in lines[2:]:
    m = re.match(r'^define .*@(\w+)\(', ln)
    if m:
        fn = m.group(1)[len('function_'):] if m.group(1).startswith('function_') else None
        k_in[fn] = 0
    if fn in ENTRY and re.match(r'^dec_label_pc_%s:' % fn, ln):
        out.append(ln)
        out.append(hook(ENTRY[fn]))
        hit.add(fn)
        continue
    mc = re.search(r'call \S+ @function_([0-9a-f]+)\(', ln)
    if fn is not None and mc and (fn in CHAIN or fn in AFTER_CALLEE):
        callee = 'function_' + mc.group(1)
        if (fn, callee) in BEFORE:
            out.append(hook(BEFORE[(fn, callee)]))
        out.append(ln)
        if fn in CHAIN and CHAIN[fn]:
            k_in[fn] += 1
            out.append(hook(CHAIN[fn] + k_in[fn]))
            hit.add(fn + '_call%d' % k_in[fn])
        elif fn in AFTER_CALLEE and callee in AFTER_CALLEE[fn]:
            out.append(hook(AFTER_CALLEE[fn][callee]))
            hit.add(fn + ':' + callee)
        continue
    if fn in LINE_HOOK:
        hooked = False
        for pat, where, hid in LINE_HOOK[fn]:
            if re.search(pat, ln):
                if where == 'before':
                    out.append(hook(hid))
                out.append(ln)
                if where == 'after':
                    out.append(hook(hid))
                hooked = True
                break
        if hooked:
            continue
    out.append(ln)
open(dst, 'w').write('\n'.join(out))
print('[watch_ir_942] hooks: entry=%s chain_calls=%d after_callee=%d' % (
    sorted(x for x in hit if '_call' not in x and ':' not in x),
    sum(1 for x in hit if '_call' in x), sum(1 for x in hit if ':' in x)))
