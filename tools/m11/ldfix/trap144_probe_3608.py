#!/usr/bin/env python3
"""trap144_probe_3608.py: trap 144・149 の引き金を採るための IR 変種を作る (#3608 受入 1・診断用)。
 使い方: python3 trap144_probe_3608.py <in.ll> <out.ll> <sites.json>
   in.ll は prod fix の IR (prod_order_3608.sh h_nor8b fix ... が作る work/p3608/h_nor8b/prod.ll) を想定する。
 記録 1 (entry 引数): ENTRY の 5 関数の entry で hit 回数と引数を書く。slot = ENTRY_BASE + k*ESLOT:
   +0 hit 回数 / +8*a 引数 a (ptr は ptrtoint、iN は zext・trunc で i64 化)。
 記録 2 (書込み元): 全 store の宛先が WATCH_A (0x10aa13f0) か WATCH_B (0x10aa1418) と一致したら、
   W_REC の +0 に宛先アドレス・+8 に site id・+16 に格納値 (i64 化) を書く (最後の一致が残る)。
   不一致の store は SCRATCH へ書く (select で宛先を切替。元の分岐・phi は変えない)。
   site id の一覧 (元 IR の関数名・行番号・store 命令) は sites.json に出す。
 読み方は trap144_read_3608.mjs。記録領域は guest 線形メモリの 0x11FF8000 以降 (既存 probe の 0x11FFF000 以降と重ならない)。
 制限: 一致判定は store の先頭アドレスだけで見る (0x10aa13f0 を含む幅の store が 1 byte 前から書く場合は見逃す)。"""
import json, re, sys

WATCH_A = 0x10AA13F0
WATCH_B = 0x10AA1418
W_REC = 0x11FF8000
SCRATCH = 0x11FF8100
ENTRY_BASE = 0x11FF9000
ESLOT = 64
ENTRY = [
    'function_44aeb0',
    'function_44f040',
    'function_653660',
    'function_412e40',
    'function_6539e0',
]
MASK = (1 << 64) - 1
STORE_RE = re.compile(r'^(\s*)store (\S+) (.*), ptr (.*?)(, align \d+)?$')
CONST = ('null', 'undef', 'poison', 'zeroinitializer')


def as_i64(name, ty, val, out):
    """ty の値 val を i64 にする命令を out に足し、オペランド (名前または即値) を返す。"""
    if ty == 'ptr':
        if val in CONST:
            return '0'
        out.append('  %%%s = ptrtoint ptr %s to i64' % (name, val))
        return '%' + name
    if not re.match(r'^i\d+$', ty):
        return '0'
    n = int(ty[1:])
    if val == 'true':
        return '1'
    if val in ('false',) + CONST:
        return '0'
    if re.match(r'^-?\d+$', val):
        return str(int(val) & MASK)
    if n == 64:
        return val
    out.append('  %%%s = %s %s %s to i64' % (name, 'zext' if n < 64 else 'trunc', ty, val))
    return '%' + name


def watch(k, indent, ty, val, addr, sid):
    p = 'tw%d' % k
    out = [
        '%s%%%s_pa = ptrtoint ptr %s to i64' % (indent, p, addr),
        '%s%%%s_ha = icmp eq i64 %%%s_pa, %d' % (indent, p, p, WATCH_A),
        '%s%%%s_hb = icmp eq i64 %%%s_pa, %d' % (indent, p, p, WATCH_B),
        '%s%%%s_h = or i1 %%%s_ha, %%%s_hb' % (indent, p, p, p),
        '%s%%%s_d = select i1 %%%s_h, ptr inttoptr (i64 %d to ptr), ptr inttoptr (i64 %d to ptr)' % (indent, p, p, W_REC, SCRATCH),
    ]
    v = as_i64(p + '_v', ty, val, out)
    out += [
        '%sstore i64 %%%s_pa, ptr %%%s_d, align 8' % (indent, p, p),
        '%s%%%s_d8 = getelementptr i8, ptr %%%s_d, i64 8' % (indent, p, p),
        '%sstore i64 %d, ptr %%%s_d8, align 8' % (indent, sid, p),
        '%s%%%s_d16 = getelementptr i8, ptr %%%s_d, i64 16' % (indent, p, p),
        '%sstore i64 %s, ptr %%%s_d16, align 8' % (indent, v, p),
    ]
    return out


def entry_probe(lines, k, fname):
    i = next(j for j, l in enumerate(lines) if re.match(r'^define .*@%s\(' % re.escape(fname), l))
    args = [a.strip() for a in re.search(r'@%s\((.*?)\)' % re.escape(fname), lines[i]).group(1).split(',') if a.strip()]
    j = i + 1
    while lines[j].strip() == '' or lines[j].lstrip().startswith(';'):
        j += 1
    if not re.match(r'^[A-Za-z0-9_.$-]+:', lines[j]):
        j = i
    base = ENTRY_BASE + k * ESLOT
    ins = [
        '  %%tp%d_b = inttoptr i64 %d to ptr' % (k, base),
        '  %%tp%d_h = load i64, ptr %%tp%d_b, align 8' % (k, k),
        '  %%tp%d_h1 = add i64 %%tp%d_h, 1' % (k, k),
        '  store i64 %%tp%d_h1, ptr %%tp%d_b, align 8' % (k, k),
    ]
    for a, arg in enumerate(args, 1):
        parts = arg.split()
        out = []
        v = as_i64('tp%d_a%d' % (k, a), parts[0], parts[-1], out)
        ins += out
        ins.append('  %%tp%d_p%d = getelementptr i8, ptr %%tp%d_b, i64 %d' % (k, a, k, 8 * a))
        ins.append('  store i64 %s, ptr %%tp%d_p%d, align 8' % (v, k, a))
    lines[j + 1:j + 1] = ins
    return {'fn': fname, 'base': hex(base), 'args': args}


def main(src, dst, sites_path):
    raw = open(src, errors='replace').read().split('\n')
    fn_at = []
    cur = None
    for l in raw:
        m = re.match(r'^define .*@([\w.$-]+)\(', l)
        if m:
            cur = m.group(1)
        elif l == '}':
            cur = None
        fn_at.append(cur)
    sites = []
    lines = []
    for n, l in enumerate(raw):
        m = STORE_RE.match(l)
        if m:
            sid = len(sites) + 1
            indent, ty, val, addr = m.group(1), m.group(2), m.group(3), m.group(4).strip()
            sites.append({'sid': sid, 'fn': fn_at[n], 'line': n + 1, 'store': l.strip()[:240]})
            lines += watch(sid, indent, ty, val, addr, sid)
        lines.append(l)
    entries = [entry_probe(lines, k, f) for k, f in enumerate(ENTRY)]
    open(dst, 'w').write('\n'.join(lines))
    json.dump({'stores': sites, 'entries': entries, 'watch_a': hex(WATCH_A), 'watch_b': hex(WATCH_B),
               'w_rec': hex(W_REC), 'entry_base': hex(ENTRY_BASE), 'eslot': ESLOT},
              open(sites_path, 'w'), ensure_ascii=False)
    print('[trap144_probe_3608] entries %d, stores watched %d -> %s' % (len(entries), len(sites), dst))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3])
