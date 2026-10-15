#!/usr/bin/env python3
"""ld175_site_link.py — #3753 (LD-175) spill 宛 UNDETERMINED site の機械語 ↔ IR のブロック単位の結線。

site ごとに次を出す (根拠行):
  機械語: site の直前が `mov rA,[rip+X]` → `mov eA,[rA]` (セル → ポインタ → 値の 2 段) か。セル K = X 参照先 - 0x400000 の内容 (ポインタ)。
          slot [rbp+d] の site 以後の読み (所属ブロック = 直前の dec_label_pc_ ラベル)
  IR    : site と同じブロックにある `load i32, ptr inttoptr (i64 K)` (セルの 1 段読み) の値 %q。
          %q の forward slice (演算・ext・`.reg2mem` の store → reload を 4 段まで) の使用ブロック
判定: 機械語 2 段 かつ IR 1 段 で、機械語の消費ブロックが IR の使用ブロックに全て含まれる → TRUE_DROP 候補。
      含まれない消費ブロックがあれば UNDETERMINED (判定根拠が足りない)。
  注意: forward slice は over-approximation (使用ブロックを多めに数える) なので、包含の成立だけを根拠にしない。
        判定の根拠は表示される行を目視で突き合わせて書く (REPORT_3753.md)。

使い方: python3 ld175_site_link.py       環境変数: M11_WORK (既定 tools/m11/work)
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '../../..'))
sys.path.insert(0, HERE)
from ldmach_img import ImageMachine  # noqa: E402

SITES = [  # (関数, site, 判定候補の出所)
    (0x128c320, 0x128d495),
    (0x1280530, 0x1284dab),
    (0xdcdde0, 0xdcdeee),
    (0xc343f0, 0xc3460e),
    (0x128f9e0, 0x12900c4),
]
MEM_RBP = re.compile(r'\[rbp \+ (0x[0-9a-f]+)\]')


def main():
    w = os.environ.get('M11_WORK', os.path.join(REPO, 'tools/m11/work'))
    mach = ImageMachine(os.path.join(w, 'm11_image.bin'), os.path.join(w, 'boot*.drc.config.json'))
    ll = open(os.path.join(w, 'boot_final3.ll')).read().splitlines()
    summary = []
    for fn, site in SITES:
        size = mach.fns[fn][1]
        ins = list(mach.cs.disasm(mach.read(fn - mach.base, size), fn, size))
        idx = {x.address: i for i, x in enumerate(ins)}
        i = idx[site]
        s = ins[i]
        print('### function_%x site %x: %s %s' % (fn, site, s.mnemonic, s.op_str))
        a, b = ins[i - 2], ins[i - 1]
        m0 = re.match(r'(\w+), qword ptr \[rip \+ (0x[0-9a-f]+)\]$', a.op_str)
        m1 = re.match(r'(\w+), (?:dword|qword) ptr \[(\w+)\]$', b.op_str)
        two = bool(m0 and m1 and m1.group(2) == m0.group(1))
        cell = a.address + a.size + int(m0.group(2), 16) if m0 else None
        k = cell - mach.base if cell else None
        print('  M 2 段 deref (%x %s / %x %s): %s' % (a.address, a.op_str, b.address, b.op_str, 'あり' if two else 'なし'))
        if cell:
            print('  M セル %x (IR K=%d) の内容 %x (ポインタ)' % (cell, k, int.from_bytes(mach.read(k, 8), 'little')))
        md = MEM_RBP.search(s.op_str)
        d = int(md.group(1), 16) if md else None
        # IR 側の関数本体
        st = next(n for n, l in enumerate(ll) if l.startswith('define weak i64 @function_%x(' % fn))
        en = next(n for n in range(st, len(ll)) if ll[n] == '}')
        body = ll[st:en]
        labels = [(int(m.group(1), 16), n) for n, l in enumerate(body) for m in [re.match(r'dec_label_pc_([0-9a-f]+):', l)] if m]

        def blk_of_addr(addr):
            best = None
            for la, n in labels:
                if la <= addr:
                    best = la
            return best

        def blk_of_line(n):
            best = None
            for la, ln in labels:
                if ln <= n:
                    best = la
            return best

        if d is not None:
            reads = []
            for y in ins[i + 1:]:
                mm = MEM_RBP.search(y.op_str)
                if mm and int(mm.group(1), 16) == d and not re.match(r'\w+ ptr \[rbp', y.op_str):
                    reads.append(y.address)
            mreads = sorted({blk_of_addr(x) for x in reads})
            print('  M slot [rbp+%x] の site 以後の読み %d 箇所 / ブロック %s' % (d, len(reads), ' '.join('%x' % x for x in mreads)))
        else:
            mreads = []
        # IR: site のブロックの 1 段セル読み
        sb = blk_of_addr(site)
        start_n = next(n for la, n in labels if la == sb) if sb is not None else 0
        q = None
        for n in range(start_n, len(body)):
            if n > start_n and body[n].startswith('dec_label_pc_'):
                break
            mq = re.match(r'\s+(%[\w.\-]+) = load (i\d+), ptr inttoptr \(i64 ' + str(k) + r' to ptr\)', body[n])
            if mq:
                q = mq.group(1)
                print('  IR ブロック %x の 1 段セル読み: 行 %d `%s`' % (sb, st + n + 1, body[n].strip()))
                break
        if q is None:
            print('  IR: site のブロックにセルの 1 段読みが無い')
            summary.append((site, 'UNDETERMINED', 'IR に 1 段読みが無い'))
            continue
        derived = {q}
        for _ in range(4):
            for l in body:
                mdef = re.match(r'\s+(%[\w.\-]+) = (.*)', l)
                if mdef and mdef.group(1) not in derived and any(re.search(re.escape(v) + r'(?![\w.\-])', mdef.group(2)) for v in derived):
                    derived.add(mdef.group(1))
                mst = re.match(r'\s+store \S+ (%[\w.\-]+), ptr (%[\w.\-]+)\.reg2mem$', l)
                if mst and mst.group(1) in derived:
                    for l2 in body:
                        mr = re.match(r'\s+(%[\w.\-]+) = load \S+, ptr (%[\w.\-]+\.reg2mem)$', l2)
                        if mr and mr.group(2) == mst.group(2) + '.reg2mem':
                            derived.add(mr.group(1))
        uses = set()
        for n, l in enumerate(body):
            for v in derived:
                if re.search(re.escape(v) + r'(?![\w.\-])', l) and not re.match(r'\s+' + re.escape(v) + ' = ', l):
                    uses.add(blk_of_line(n))
                    break
        ir_blocks = sorted(x for x in uses if x is not None)
        print('  IR %s の forward slice (%d 値) の使用ブロック: %s' % (q, len(derived), ' '.join('%x' % x for x in ir_blocks)))
        miss = [x for x in mreads if x not in ir_blocks]
        ok = two and bool(mreads) and not miss
        print('  判定: 機械語 2 段=%s / IR 1 段 / 機械語の消費ブロックが IR に無い: %s -> %s' % (
            two, ' '.join('%x' % x for x in miss) or 'なし', 'TRUE_DROP 候補' if ok else 'UNDETERMINED'))
        summary.append((site, 'TRUE_DROP 候補' if ok else 'UNDETERMINED', ' '.join('%x' % x for x in miss) or '-'))
        print()
    print('[ld175] summary')
    for site, v, note in summary:
        print('  %x\t%s\t未対応ブロック %s' % (int(site, 16) if isinstance(site, str) else site, v, note))
    return 0


if __name__ == '__main__':
    sys.exit(main())
