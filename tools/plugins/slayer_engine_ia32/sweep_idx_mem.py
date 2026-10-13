#!/usr/bin/env python3
"""block22434 (engine) の .text 全域を ia32 で掃引し、添字スケール 4 の memory operand を数える (#894 §9.5)。

  python3 sweep_idx_mem.py            # 既定: $RUNNER_TEMP/fl-win64/extracted/block22434_PE.bin
  python3 sweep_idx_mem.py --dll PATH # 対象 PE を指定

掃引: 各位置で 1 命令を decode し、成功なら命令長だけ進む。失敗 (undecodable) は 1 バイト飛ばす。
これにより .text の途中で止まらず、全 VirtualSize を被覆する。
入力の sha256・capstone の版は measure.py の固定値で検証し、不一致は exit 1。
"""
import argparse, collections, hashlib, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from measure import EXPECT_SHA256, EXPECT_CAPSTONE, EXPECT_TEXT_VSIZE, parse_pe, fl_dir  # noqa: E402

try:
    import capstone
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    from capstone import x86 as cx
except ImportError:
    sys.exit('capstone が無い: uv pip install --python <python> capstone==5.0.7')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dll', help='対象 PE (既定: $RUNNER_TEMP/fl-win64/extracted/block22434_PE.bin)')
    ap.add_argument('--ctx', type=int, default=0, help='*4+8 の各件の前後 N 命令を逆アセンブルして出す')
    args = ap.parse_args()
    if capstone.__version__ != EXPECT_CAPSTONE:
        sys.exit('[pin] FAIL capstone=%s (期待 %s)' % (capstone.__version__, EXPECT_CAPSTONE))
    path = args.dll or os.path.join(fl_dir(), 'extracted', 'block22434_PE.bin')
    data = open(path, 'rb').read()
    sha = hashlib.sha256(data).hexdigest()
    if sha != EXPECT_SHA256:
        sys.exit('[input] FAIL sha256=%s (期待 %s)' % (sha, EXPECT_SHA256))

    pe = parse_pe(data)
    text = pe['text']
    if text['vsize'] != EXPECT_TEXT_VSIZE:
        sys.exit('[pe] FAIL .text VirtualSize=%d' % text['vsize'])
    base = (pe['ibase'] or 0) + text['va']
    code = data[text['rawptr']:text['rawptr'] + text['vsize']]

    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True

    total = len(code)
    undec = 0
    ok = 0
    covered = 0
    idx4 = 0          # 添字スケール 4 の memory operand 総数
    idx4_insn = 0     # そのうち 1 つ以上を含む命令数
    d8 = []           # (address, 命令テキスト) 変位 8 かつ 添字 *4
    idx4_disp = collections.Counter()
    idx4_pair = collections.Counter()  # (base, index) の組
    idx4_x87 = 0

    seq = []          # 全命令の列 (--ctx 用)
    pos = 0
    while pos < total:
        r = list(md.disasm(bytes(code[pos:pos + 15]), base + pos, 1))
        if not r:
            undec += 1
            pos += 1
            continue
        ins = r[0]
        ok += 1
        covered += ins.size
        seq.append(ins)
        hit = False
        for op in ins.operands:
            if op.type != cx.X86_OP_MEM:
                continue
            m = op.mem
            if m.index != 0 and m.scale == 4:
                idx4 += 1
                hit = True
                idx4_disp[m.disp] += 1
                if ins.mnemonic.startswith('f'):
                    idx4_x87 += 1
                idx4_pair[(ins.reg_name(m.base) if m.base else '-', ins.reg_name(m.index))] += 1
                if m.disp == 8:
                    d8.append((len(seq) - 1, '%s %s' % (ins.mnemonic, ins.op_str)))
        if hit:
            idx4_insn += 1
        pos += ins.size

    print('[input] file=%s sha256=%s' % (path, sha))
    print('[pe] .text VirtualSize=%d file_off=0x%x' % (text['vsize'], text['rawptr']))
    print('[sweep] capstone=%s insn_ok=%d bytes_by_insn=%d undecodable_bytes=%d covered=%d / %d' % (
        capstone.__version__, ok, covered, undec, covered + undec, total))
    print('[idx*4] memory operands=%d (insns=%d) disp top=%s' % (
        idx4, idx4_insn, ' '.join('%d=%d' % kv for kv in idx4_disp.most_common(10))))
    print('[idx*4] x87(f*)=%d top (base,index)=%s' % (
        idx4_x87, ' '.join('[%s+%s*4]=%d' % (b, i, v) for (b, i), v in idx4_pair.most_common(8))))
    print('[idx*4+8] count=%d' % len(d8))
    for i, t in d8:
        a = seq[i].address
        print('  0x%x  %s' % (a, t))
        if args.ctx:
            for ins in seq[max(0, i - args.ctx):i + args.ctx + 1]:
                mark = '>' if ins.address == a else ' '
                print('    %s 0x%x  %-24s %s %s' % (mark, ins.address, ins.bytes.hex(), ins.mnemonic, ins.op_str))


if __name__ == '__main__':
    main()
