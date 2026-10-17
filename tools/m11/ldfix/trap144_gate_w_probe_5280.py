#!/usr/bin/env python3
"""trap144_gate_w_probe_5280.py: global 18787504 (0x11EACB0・call site B の分岐値) へ書く store を採る IR 変種を作る (#5280 受入 1・診断用)。
  使い方: python3 trap144_gate_w_probe_5280.py <in.ll> <out.ll> <sites.json>
  in.ll は prod fix の IR (prod_order_3608.sh h_nor8b fix ... が作る work/p3608/h_nor8b/prod.ll) を想定する。
  記録: 全 store の宛先が [G-7, G+7] に入ったら、CNT を +1 し、RING[(cnt & 63)] に
    +0 site id・+8 宛先アドレス・+16 格納値 (i64 化)・+24 宛先の幅に依らず 1 (予備) を書く。
    一致しない store は SCRATCH へ書く (select で宛先を切替。元の分岐・phi は変えない)。
  読み方は trap114_w_read_5280.mjs。記録領域は guest 線形メモリの 0x11FFA000 以降 (既存 probe の 0x11FF8000〜0x11FFF000 と重ならない)。
  制限: 宛先の先頭アドレスだけで判定する (G-7〜G+7 に始まる store の全てを拾う。幅の大きい store は範囲内に始まれば拾う)。"""
import json, re, sys

G = 18825444
LO = G - 7
CNT = 0x11FFA000
RING = 0x11FFA100
SCRATCH = 0x11FFB000
MASK = (1 << 64) - 1
STORE_RE = re.compile(r'^(\s*)store (\S+) (.*), ptr (.*?)(, align \d+)?$')
CONST = ('null', 'undef', 'poison', 'zeroinitializer')


def as_i64(name, ty, val, out):
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
        '%s%%%s_d = sub i64 %%%s_pa, %d' % (indent, p, p, LO),
        '%s%%%s_h = icmp ule i64 %%%s_d, 14' % (indent, p, p),
        '%s%%%s_c = load i64, ptr inttoptr (i64 %d to ptr), align 8' % (indent, p, CNT),
        '%s%%%s_ci = and i64 %%%s_c, 63' % (indent, p, p),
        '%s%%%s_o = shl i64 %%%s_ci, 5' % (indent, p, p),
        '%s%%%s_rb = add i64 %%%s_o, %d' % (indent, p, p, RING),
        '%s%%%s_rp = inttoptr i64 %%%s_rb to ptr' % (indent, p, p),
        '%s%%%s_sel = select i1 %%%s_h, ptr %%%s_rp, ptr inttoptr (i64 %d to ptr)' % (indent, p, p, p, SCRATCH),
        '%s%%%s_cn = add i64 %%%s_c, 1' % (indent, p, p),
        '%s%%%s_inc = zext i1 %%%s_h to i64' % (indent, p, p),
        '%s%%%s_cnn = add i64 %%%s_c, %%%s_inc' % (indent, p, p, p),
        '%s%%%s_cs = select i1 %%%s_h, i64 %%%s_cnn, i64 %%%s_c' % (indent, p, p, p, p),
    ]
    v = as_i64(p + '_v', ty, val, out)
    out += [
        '%sstore i64 %%%s_cs, ptr inttoptr (i64 %d to ptr), align 8' % (indent, p, CNT),
        '%sstore i64 %d, ptr %%%s_sel, align 8' % (indent, sid, p),
        '%s%%%s_p8 = getelementptr i8, ptr %%%s_sel, i64 8' % (indent, p, p),
        '%sstore i64 %%%s_pa, ptr %%%s_p8, align 8' % (indent, p, p),
        '%s%%%s_p16 = getelementptr i8, ptr %%%s_sel, i64 16' % (indent, p, p),
        '%sstore i64 %s, ptr %%%s_p16, align 8' % (indent, v, p),
    ]
    return out


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
    open(dst, 'w').write('\n'.join(lines))
    json.dump({'stores': sites, 'g': G, 'cnt': hex(CNT), 'ring': hex(RING)}, open(sites_path, 'w'), ensure_ascii=False)
    print('[trap144_gate_w_probe_5280] stores watched %d -> %s' % (len(sites), dst))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3])
