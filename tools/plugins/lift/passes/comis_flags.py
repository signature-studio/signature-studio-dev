#!/usr/bin/env python3
"""非 VEX comis/ucomis (comiss/comisd/ucomiss/ucomisd、サフィックス __N 付きを含む) の flag を IR に反映する ([PLG-F3-34] #3242).

RetDec の reg2mem 形の関数では flag が slot (`%cf.0.reg2mem` / `%zf.0.reg2mem` / `%pf.0.reg2mem` の alloca i1) に
store/load で載る。 comis は flag を更新しないので、呼出しの後に fcmp で flag を計算して slot へ store する:
  CF = fcmp ult (a < b または unordered)   ZF = fcmp ueq (a == b または unordered)   PF = fcmp uno
  (x86 SDM: 順序付き比較で unordered は ZF=PF=CF=1、 a<b は CF=1、 a==b は ZF=1、 a>b は全 0)
反映した呼出しは削除する (helper を呼ぶ必要が無くなる)。 slot が無い関数 (flag が SSA 定数のまま流れる関数) は
反映できないので呼出しを残す。 残った呼出しは m11_simd2.py が `unimpl` として出す (silent の stub にしない)。
使い方: python3 comis_flags.py in.ll out.ll [--report out.json]
"""
import json, re, sys
from collections import Counter

CALL_RE = re.compile(r'^(\s*)call void @__asm_(u?comis[sd])(?:__\d+)?\(i128 ([^,]+), (i128|i64|i32) ([^,)]+)\)\s*$')
DECL_RE = re.compile(r'^declare void @__asm_(u?comis[sd](?:__\d+)?)\(.*\) local_unnamed_addr\s*$', re.M)
SLOT_RE = re.compile(r'^\s*%(cf|zf|pf)\.0\.reg2mem = alloca i1\b', re.M)
FLAG_USE_RE = re.compile(r'%(pf)\.0\.reload\b')
HIST = Counter()
_n = [0]


def reflect(body, sym, ind, a, bty, b, slots):
    _n[0] += 1
    n = _n[0]
    ftype, iw = ('float', 'i32') if sym.endswith('s') else ('double', 'i64')
    if bty not in ('i128', iw):
        return None
    t = 'cfl%d' % n
    out = ['%s%%%s_a = trunc i128 %s to %s' % (ind, t, a, iw),
           '%s%%%s_fa = bitcast %s %%%s_a to %s' % (ind, t, iw, t, ftype)]
    if bty == 'i128':
        out += ['%s%%%s_bt = trunc i128 %s to %s' % (ind, t, b, iw),
                '%s%%%s_fb = bitcast %s %%%s_bt to %s' % (ind, t, iw, t, ftype)]
    else:
        out += ['%s%%%s_fb = bitcast %s %s to %s' % (ind, t, iw, b, ftype)]
    fa, fb = '%%%s_fa' % t, '%%%s_fb' % t
    out += ['%s%%%s_cf = fcmp ult %s %s, %s' % (ind, t, ftype, fa, fb),
            '%s%%%s_zf = fcmp ueq %s %s, %s' % (ind, t, ftype, fa, fb)]
    out += ['%sstore i1 %%%s_cf, ptr %%cf.0.reg2mem' % (ind, t),
            '%sstore i1 %%%s_zf, ptr %%zf.0.reg2mem' % (ind, t)]
    if 'pf' in slots:
        out += ['%s%%%s_pf = fcmp uno %s %s, %s' % (ind, t, ftype, fa, fb),
                '%sstore i1 %%%s_pf, ptr %%pf.0.reg2mem' % (ind, t)]
    return out


def do_function(fbody):
    slots = set(SLOT_RE.findall(fbody))
    lines = fbody.split('\n')
    sites = [i for i, l in enumerate(lines) if 'call void @__asm_' in l and 'comis' in l]
    if not sites:
        return fbody, 0
    reason = None
    if not {'cf', 'zf'} <= slots:
        reason = 'partial_slot' if slots & {'cf', 'zf'} else 'no_flag_slot'
    elif FLAG_USE_RE.search(fbody) and 'pf' not in slots:
        reason = 'pf_read_without_slot'
    repl = {}
    for i in sites:
        m = CALL_RE.match(lines[i])
        if not m:
            HIST['kept:vex_out_of_scope' if '__asm_v' in lines[i] else 'kept:unparsed'] += 1
            continue
        ind, sym, a, bty, b = m.groups()
        if reason:
            HIST['kept:' + reason] += 1
            continue
        new = reflect(fbody, sym, ind, a.strip(), bty, b.strip(), slots)
        if new is None:
            HIST['kept:width_mismatch'] += 1
            continue
        repl[i] = new
        HIST['reflected:' + sym] += 1
    res = []
    for i, l in enumerate(lines):
        if i in repl:
            res += repl[i]
        else:
            res.append(l)
    return '\n'.join(res), len(repl)


def main():
    src, dst = sys.argv[1], sys.argv[2]
    rep = sys.argv[sys.argv.index('--report') + 1] if '--report' in sys.argv else None
    with open(src) as f:
        parts = re.split(r'\n(?=define )', f.read())
    total = 0
    for k, p in enumerate(parts):
        if p.startswith('define '):
            parts[k], c = do_function(p)
            total += c
    s = '\n'.join(parts)
    # 反映で呼出しが消えた symbol の宣言を消す (m11_simd2 が unimpl と数えないため)
    removed = []
    for m in DECL_RE.finditer(s):
        sym = m.group(1)
        if not re.search(r'call void @__asm_%s\(' % re.escape(sym), s):
            removed.append(sym)
    if removed:
        s = re.sub(r'^declare void @__asm_(%s)\(.*\) local_unnamed_addr\s*\n' % '|'.join(re.escape(x) for x in removed),
                   '', s, flags=re.M)
    with open(dst, 'w') as f:
        f.write(s)
    summary = {'reflected_sites': total, 'removed_decls': removed, 'hist': dict(HIST)}
    if rep:
        with open(rep, 'w') as f:
            json.dump(summary, f, indent=1, ensure_ascii=False)
    print('[comis_flags] reflected %d sites; removed decls %d; %s' % (total, len(removed), dict(HIST)))


if __name__ == '__main__':
    main()
