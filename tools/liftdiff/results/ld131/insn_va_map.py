#!/usr/bin/env python3
"""LD-131 (#2801): x64c の C 出力 (命令ごとの `/* <VA>: <命令> */` 注記) から命令単位の VA 表を作る (stdlib のみ)。

  python3 tools/liftdiff/results/ld131/insn_va_map.py <ott_lifted.c> [--fn 1801c5e84,1801c0b6c] [--out insn_map.tsv]

出力は TSV (列: fn va insn kind target)。fn・va は 9 桁の 16 進 (例 1801c0b6f)。
  kind = jcc (条件分岐・target は分岐先 VA) / jmp (無条件分岐・target は分岐先 VA)
         / call (直接呼出し・target は呼出し先 VA) / call-imp (import 呼出し・target は import 名)
         / call-unlifted (未 lift の呼出し・target は VA) / 空 (それ以外)
"""
import argparse
import re
import sys

VA_RE = re.compile(r'^\s*/\* ([0-9a-f]{6,}): (.*?) \*/\s*$')
FN_RE = re.compile(r'^void f_([0-9a-f]+)\(void\) \{\s*$')
JCC_RE = re.compile(r'if \(CC_\w+\) goto L_([0-9a-f]+);')
JMP_RE = re.compile(r'\bgoto L_([0-9a-f]+);')
CALL_RE = re.compile(r'\bf_([0-9a-f]+)\(\);')
IMP_RE = re.compile(r'\bimp_(\w+)\(\);')
UNL_RE = re.compile(r'ott_unlifted\(0x([0-9a-f]+)ULL\);')
# x64c の guest 番地は VA - IMAGE_BASE + GUEST_BASE (OTT の ImageBase 0x180000000)。未 lift の呼出し先だけ VA に戻す。
IMAGE_BASE = 0x180000000
GUEST_BASE = 0x30000000


def classify(stmt):
    for kind, rx in (('jcc', JCC_RE), ('jmp', JMP_RE), ('call-imp', IMP_RE), ('call', CALL_RE), ('call-unlifted', UNL_RE)):
        m = rx.search(stmt)
        if m:
            target = m.group(1)
            if kind == 'call-unlifted':
                target = '%x' % (int(target, 16) - GUEST_BASE + IMAGE_BASE)
            return kind, target
    return '', ''


def parse(lines):
    rows = []
    fn = None
    cur = None
    for line in lines:
        m = FN_RE.match(line)
        if m:
            fn, cur = m.group(1), None
            continue
        if fn is None:
            continue
        m = VA_RE.match(line)
        if m:
            cur = {'fn': fn, 'va': m.group(1), 'insn': m.group(2), 'stmt': ''}
            rows.append(cur)
            continue
        if cur is not None:
            cur['stmt'] += line.strip() + ' '
    for r in rows:
        r['kind'], r['target'] = classify(r.pop('stmt'))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('c_file')
    ap.add_argument('--fn', default='', help='関数 VA (9 桁 16 進)。カンマ区切り。省略時は全関数')
    ap.add_argument('--out', default='', help='TSV の出力先 (省略時は標準出力)')
    a = ap.parse_args()
    with open(a.c_file, encoding='utf-8') as f:
        rows = parse(f.read().splitlines())
    if a.fn:
        want = set(a.fn.split(','))
        rows = [r for r in rows if r['fn'] in want]
    out = open(a.out, 'w', encoding='utf-8') if a.out else sys.stdout
    out.write('fn\tva\tinsn\tkind\ttarget\n')
    for r in rows:
        out.write('\t'.join((r['fn'], r['va'], r['insn'], r['kind'], r['target'])) + '\n')
    if a.out:
        out.close()
    print('rows=%d fns=%d' % (len(rows), len({r['fn'] for r in rows})), file=sys.stderr)


if __name__ == '__main__':
    main()
