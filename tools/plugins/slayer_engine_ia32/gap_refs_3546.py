#!/usr/bin/env python3
"""gap_refs_3546.py: (c) 中身あり区間の参照検査 (PLG-G2-28 #3546・REPORT_APPENDIX_3546.md §3)。

  FL_WIN64_DIR=<fl-win64 の展開先> python3 lift_text.py --no-emcc      # 先に lift 出力 (work/lift_text) を作る
  python3 gap_refs_3546.py <PE> <lift 出力 dir>

(c) のうち padding 以外の区間ごとに、次のどれかが区間内を指すかを調べる:
  R 生の 4 バイト値 (全ファイル位置・全セクション。 4 バイト単位の任意の位置)
  L .reloc の HIGHLOW 値 (位置は問わない)
  I .text 内の命令の即値・絶対変位 (mem の disp を含む)
  B 区間内の分岐のみ (区間外からの参照は無いが、区間内の分岐先が区間内にある)
全部無ければ「参照なし」。 I の中の間接 call ([reg+disp] で表を引く先) は検出できない (限界)。
"""
import collections, os, sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
from capstone.x86 import X86_OP_IMM, X86_OP_MEM

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gap_classify


def main():
    pe_path, out = sys.argv[1], sys.argv[2]
    env = gap_classify.load(pe_path, out)
    rows = gap_classify.classify(env)
    pe, IMG, T0, TS, text, img, md = (env[k] for k in ('pe', 'IMG', 'T0', 'TS', 'text', 'img', 'md'))
    targets = [r for r in rows if r['cls'] == 'c' and not r['why'].startswith('padding')]
    spans = [(r['va'], r['va'] + r['size']) for r in targets]

    def hit(v):
        return next((i for i, (a, b) in enumerate(spans) if a <= v < b), None)

    refs = collections.defaultdict(lambda: collections.defaultdict(list))
    # R: 全ファイル位置の 4 バイト値 (4 バイト単位の任意の位置)
    span_vas = set()
    for a, b in spans:
        span_vas.update(range(a, b))
    for i in range(0, len(img) - 3):
        v = int.from_bytes(img[i:i + 4], 'little')
        if v in span_vas:
            refs[hit(v)]['R'].append(IMG + i)
    # L: .reloc の HIGHLOW 値
    for b in pe.DIRECTORY_ENTRY_BASERELOC:
        for e in b.entries:
            if e.type != 3:
                continue
            v = int.from_bytes(img[e.rva:e.rva + 4], 'little')
            j = hit(v)
            if j is not None:
                refs[j]['L'].append(IMG + e.rva)
    # I: .text 内の命令の即値・絶対変位 (と分岐の参照元)
    code = img[text.VirtualAddress:text.VirtualAddress + TS]
    for ins in md.disasm(code, T0):
        for op in ins.operands:
            if op.type == X86_OP_IMM:
                t = op.imm
            elif op.type == X86_OP_MEM and op.mem.base == 0 and op.mem.index == 0:
                t = op.mem.disp
            else:
                continue
            j = hit(t)
            if j is not None:
                refs[j]['I'].append(ins.address)
    print('[gap_refs] (c) 中身あり %d 区間 (padding 除く)' % len(targets))
    cnt = collections.Counter()
    for j, r in enumerate(targets):
        a, b = spans[j]
        kinds = ''.join(sorted(refs[j].keys())) if refs[j] else '-'
        if not refs[j]:
            verdict = '参照なし'
        elif set(refs[j].keys()) == {'I'} and all(a <= x < b for x in refs[j]['I']):
            verdict = '区間内の分岐のみ'
        else:
            verdict = '参照あり (%s)' % kinds
        cnt[verdict] += 1
        shown = ' '.join('0x%x' % x for k in ('R', 'L', 'I') for x in refs[j].get(k, [])[:2]) or '-'
        print('0x%x %4d B  %-18s %s' % (a, b - a, verdict, shown))
    print('[gap_refs] ' + ', '.join('%s %d' % kv for kv in sorted(cnt.items())))



if __name__ == '__main__':
    main()
