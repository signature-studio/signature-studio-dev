#!/usr/bin/env python3
"""gap_enum.py: 未被覆 .text 区間 (lift 済み命令が被覆しない連続域) の fs:/gs: 命令と AF を読む命令を数える (#3128 PLG-G2-27)。

  python3 gap_enum.py          区間の先頭から逐次 decode し、 該当命令と区間の分類 (gap_classes.json) を表示する (exit 0)

区間ごとに先頭から decode するため、 データを命令として読む誤りを含みうる (下限ではなく候補)。
区間の分類は gap_classify.classify() で最終 lift (pass 2) の区間に対して行う。 分類 (a) は誤ることがある
(REPORT_APPENDIX_3128.md §5)。 本スクリプトは分類で除外せず、 全候補を分類つきで出す。
入力: work/lift_text/ott_lifted.c と lift_meta.json (lift_text.py の出力)、 $FL_WIN64_DIR/extracted/block22434_PE.bin。
"""
import collections, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, 'work')
sys.path.insert(0, HERE)
import gap_classify

AF_READ = re.compile(r'(lahf|pushf|pushfd|daa|das|aaa|aas)\b')


def main():
    d = os.environ.get('FL_WIN64_DIR') or os.path.join(os.environ.get('RUNNER_TEMP', ''), 'fl-win64')
    pth = os.path.join(d, 'extracted', 'block22434_PE.bin')
    out = os.path.join(WORK, 'lift_text')
    if not os.path.isfile(pth) or not os.path.isfile(os.path.join(out, 'ott_lifted.c')):
        sys.exit('[gap_enum] FAIL: %s と %s が要る (素材を展開し lift_text.py を先に実行)' % (pth, out))
    env = gap_classify.load(pth, out)
    T0, TS, img, md, cov, text = env['T0'], env['TS'], env['img'], env['md'], env['cov'], env['text']
    cls = {r['va']: r['cls'] for r in gap_classify.classify(env)}
    gaps = gap_classify.regions(cov)
    code = bytes(img[text.VirtualAddress:text.VirtualAddress + TS])
    seg, af = [], []
    for a, b in gaps:
        region = T0 + a
        off = a
        while off < b:
            ins = next(md.disasm(code[off:off + 16], T0 + off, 1), None)
            if ins is None:
                off += 1
                continue
            row = (ins.address, ('%s %s' % (ins.mnemonic, ins.op_str)).strip(), region, b - a, cls[region])
            if re.search(r'\b(fs|gs):', ins.op_str):
                seg.append(row)
            if AF_READ.match(ins.mnemonic):
                af.append(row)
            off += ins.size
    print('[gap] 未被覆区間 %d 個 (計 %d B)' % (len(gaps), sum(b - a for a, b in gaps)))
    print('[gap] fs:/gs: を含む命令 %d 件 (区間分類 %s)' % (len(seg), dict(collections.Counter(r[4] for r in seg))))
    print('[gap] AF を読む命令 %d 件 (区間分類 %s)' % (len(af), dict(collections.Counter(r[4] for r in af))))
    for kind, rows in (('fs', seg), ('af', af)):
        for va, t, region, size, c in rows:
            print('[gap:%s] %08x %s (区間 %08x +%d B, 分類 %s)' % (kind, va, t, region, size, c))


if __name__ == '__main__':
    main()
