#!/usr/bin/env python3
"""lb_reloc.py — 既に 0x30000000+RVA へ V-shift 済みの RetDec chain 成果 (m6〜m10 の最終 IR / C ランタイム) を、
任意の LB_BASE へ「リテラル単位で」再配置する (V-shift の第 2 段; 元の 0x180000000→0x30000000 shift は ir6_shift.py が済ませている).
   ll  : @global_var_<hex> 名 と `i64 <10進>` 直値 (OLD..OLD+SPAN) を (NEW-OLD) だけ移動. 範囲外は不変.
   c   : 16進リテラル 0x30xxxxxx[u|ul|ull] (OLD..OLD+SPAN) を移動. 特例: (a) m8_rt の上限 0x36000000ull → LB_MAXMEM,
         (b) m10_boot の固定 scratch 0x35e00000 → 静的配列.
   共通: --prefix P で `function_<VA>` / `global_var_<VA>` (識別子単位) に P_ を付与 (@function_ / C 識別子 / EXPORTED_FUNCTIONS 内 _function_).
監査: 置換した全リテラルを --report JSON に (種別, 旧, 新, 行文脈) で出力. i64 直値は範囲内 37 件で全て address と手確認済 (REPORT.md).
usage: lb_reloc.py ll IN OUT --new HEX [--old 0x30000000] [--prefix P] [--report R.json]
       lb_reloc.py c  IN OUT --new HEX [--maxmem HEX] [--prefix P] [--report R.json]
       lb_reloc.py exports 'STRING' --prefix P
"""
import sys, re, json, argparse
from collections import Counter

OLD_DEFAULT = 0x30000000
SPAN = 0x310000   # PE image 0x308000 + 余裕

def prefixer(prefix):
    if not prefix: return lambda s: s
    rx = re.compile(r'(?<![A-Za-z0-9_])(function|global_var)_([0-9a-fA-F]{5,10})\b')
    return lambda s: rx.sub(lambda m: '%s_%s_%s' % (prefix, m.group(1), m.group(2)), s)

def reloc_ll(text, old, new, report, prefix):
    delta = new - old
    def rn(m):
        v = int(m.group(1), 16)
        if old <= v < old + SPAN:
            report.append(dict(kind='ll-name', old=hex(v), new=hex(v + delta))); return '@global_var_%x' % (v + delta)
        return m.group(0)
    text = re.sub(r'@global_var_([0-9a-fA-F]{8})\b', rn, text)
    def rv(m):
        v = int(m.group(1))
        if old <= v < old + SPAN:
            ls = text.rfind('\n', 0, m.start()) + 1; le = text.find('\n', m.end())
            report.append(dict(kind='ll-i64', old=hex(v), new=hex(v + delta), ctx=text[ls:le].strip()[:100])); return 'i64 %d' % (v + delta)
        return m.group(0)
    text = re.sub(r'\bi64 (\d{9,10})\b', rv, text)
    return prefixer(prefix)(text)

def reloc_c(text, old, new, maxmem, report, prefix):
    delta = new - old
    if '#define MSCR ((volatile uint32_t *)0x35e00000)' in text:
        text = text.replace('#define MSCR ((volatile uint32_t *)0x35e00000)',
                            'static volatile uint32_t lb_mscr[4096];\n#define MSCR (lb_mscr)')
        report.append(dict(kind='c-scratch', old='0x35e00000', new='static lb_mscr[4096]'))
    def rep(m):
        lit, suf = m.group(1), m.group(2)
        v = int(lit, 16)
        if lit.lower() == '0x36000000' and suf.lower() == 'ull':   # m8_ptr_ok の上限
            report.append(dict(kind='c-limit', old=lit + suf, new='0x%xull' % maxmem)); return '0x%xull' % maxmem
        if old <= v < old + SPAN:
            report.append(dict(kind='c-addr', old=lit + suf, new='0x%x%s' % (v + delta, suf)))
            return '0x%x%s' % (v + delta, suf)
        return m.group(0)
    text = re.sub(r'\b(0[xX][0-9a-fA-F]{8})([uUlL]*)\b', rep, text)
    return prefixer(prefix)(text)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode'); ap.add_argument('inp'); ap.add_argument('out', nargs='?')
    ap.add_argument('--new', default='0x10000'); ap.add_argument('--old', default=hex(OLD_DEFAULT))
    ap.add_argument('--maxmem', default='0x4000000'); ap.add_argument('--prefix', default='')
    ap.add_argument('--report')
    a = ap.parse_args()
    old, new, maxmem = int(a.old, 0), int(a.new, 0), int(a.maxmem, 0)
    rep = []
    if a.mode == 'exports':
        print(re.sub(r'(?<![A-Za-z0-9])_(function)_([0-9a-fA-F]{5,10})\b', lambda m: '_%s_%s_%s' % (a.prefix, m.group(1), m.group(2)), a.inp)); return
    text = open(a.inp).read()
    res = reloc_ll(text, old, new, rep, a.prefix) if a.mode == 'll' else reloc_c(text, old, new, maxmem, rep, a.prefix)
    open(a.out, 'w').write(res)
    if a.report: json.dump(rep, open(a.report, 'w'), indent=0)
    print('[lb_reloc %s] %s: %s' % (a.mode, a.inp.split('/')[-1], dict(Counter(r['kind'] for r in rep))))

if __name__ == '__main__':
    main()
