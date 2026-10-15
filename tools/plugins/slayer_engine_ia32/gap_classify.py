#!/usr/bin/env python3
"""gap_classify.py: lift 後の未被覆区間 (.text で被覆 0 の連続域) を 3 類に分類する (#2814 / 親 #1098)。

  (a) data-in-code : jt 表と半分以上重なる、または .text 内の reloc 値 (ポインタ) を 2 本以上含む
  (b) 関数          : 直接 call/jmp の先頭になる、または関数 prologue (55 8b ec / 8b ff 55 8b ec / 83 ec / 81 ec) で始まる
  (c) 参照の無い区間 : 上記のどれでもない。 nop/int3/00 のみの区間 (padding) を含む

  python3 gap_classify.py <PE> <lift 出力 dir> [--md]   分類表を出す (--md で REPORT_APPENDIX_2814 用の Markdown)
  python3 gap_classify.py --json <gap_classes.json> --md  lift_text.py の 1 回目の分類結果から表だけ出す
  lift_text.py から classify() を使い、(b) の先頭を roots に加えて再 lift する。
"""
import collections, json, os, re, struct, sys

PAD = {0x90, 0xCC, 0x00}


def load(pe_path, out):
    import pefile
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    pe = pefile.PE(pe_path)
    IMG = pe.OPTIONAL_HEADER.ImageBase
    text = pe.sections[0]
    T0 = IMG + text.VirtualAddress
    TS = text.Misc_VirtualSize
    img = pe.get_memory_mapped_image()
    md = Cs(CS_ARCH_X86, CS_MODE_32); md.detail = True
    src = open(os.path.join(out, 'ott_lifted.c')).read()
    vas = sorted(set(int(m.group(1), 16) for m in re.finditer(r'/\* ([0-9a-f]+): ', src)))
    cov = bytearray(TS)
    for va in vas:
        ins = next(md.disasm(img[va - IMG:va - IMG + 16], va, 1))
        for k in range(ins.size):
            if va - T0 + k < TS:
                cov[va - T0 + k] = 1
    meta = json.load(open(os.path.join(out, 'lift_meta.json')))
    return dict(pe=pe, IMG=IMG, T0=T0, TS=TS, text=text, img=img, md=md, cov=cov, meta=meta)


def regions(cov):
    gaps, i, TS = [], 0, len(cov)
    while i < TS:
        if cov[i]:
            i += 1
            continue
        j = i
        while j < TS and not cov[j]:
            j += 1
        gaps.append((i, j))
        i = j
    return gaps


def classify(env):
    """未被覆区間ごとの分類 (list of dict)。 VA は絶対値。"""
    from capstone.x86 import X86_OP_IMM
    pe, IMG, T0, TS, text, img, md, cov, meta = (env[k] for k in ('pe', 'IMG', 'T0', 'TS', 'text', 'img', 'md', 'cov', 'meta'))
    jtm = bytearray(TS)
    for s, sz in meta['jt_ranges']:
        for k in range(max(s - T0, 0), min(s - T0 + sz, TS)):
            jtm[k] = 1
    gaps = regions(cov)
    where = {}
    for n, (a, b) in enumerate(gaps):
        for k in range(a, b):
            where[k] = n
    calls = collections.defaultdict(list)
    code = img[text.VirtualAddress:text.VirtualAddress + TS]
    for ins in md.disasm(code, T0):
        if (ins.mnemonic == 'call' or ins.mnemonic.startswith('j')) and ins.operands and ins.operands[0].type == X86_OP_IMM:
            t = ins.operands[0].imm
            if T0 <= t < T0 + TS and (t - T0) in where:
                calls[where[t - T0]].append(ins.address)
    relo = collections.defaultdict(list)
    for b in pe.DIRECTORY_ENTRY_BASERELOC:
        for e in b.entries:
            off = e.rva - text.VirtualAddress
            if e.type != 3 or not (0 <= off < TS) or jtm[off]:
                continue
            v = struct.unpack_from('<I', img, e.rva)[0]
            if T0 <= v < T0 + TS and (v - T0) in where:
                relo[where[v - T0]].append(IMG + e.rva)
    rows = []
    for n, (a, b) in enumerate(gaps):
        bs = bytes(img[text.VirtualAddress + a:text.VirtualAddress + b])
        jt = sum(jtm[a:b])
        head = bs[:2]
        if set(bs) <= PAD:
            cls, why = 'c', 'padding (90/cc/00 のみ)'
        elif jt * 2 >= (b - a):
            cls, why = 'a', 'jt 表と重なる (%d/%d B)' % (jt, b - a)
        elif len(relo[n]) >= 2:
            cls, why = 'a', '.text 内の reloc 値 %d 本 (ポインタ表とみなす)' % len(relo[n])
        elif (calls[n] and bs[0] not in PAD) or bs[:3] == b'\x55\x8b\xec' or bs[:5] == b'\x8b\xff\x55\x8b\xec' or bs[:2] in (b'\x83\xec', b'\x81\xec'):
            cls = 'b'
            if calls[n]:
                why = '直接 call/jmp の先 (参照元 %s)' % ','.join('0x%x' % x for x in calls[n][:3])
            else:
                why = 'prologue %s' % bs[:6].hex(' ')
        else:
            cls = 'c'
            why = '参照なし・prologue なし' + (' (reloc %d 本)' % len(relo[n]) if relo[n] else '')
        rows.append(dict(va=T0 + a, size=b - a, cls=cls, why=why, jt=jt,
                         ncall=len(calls[n]), nreloc=len(relo[n]),
                         calls=['0x%x' % x for x in calls[n][:3]], relocs=['0x%x' % x for x in relo[n][:3]],
                         head=bs[:8].hex(' ')))
    return rows


def main():
    if '--json' in sys.argv:   # lift_text.py が書いた gap_classes.json から表だけ出す
        rows = json.load(open(sys.argv[sys.argv.index('--json') + 1]))
    else:
        rows = classify(load(sys.argv[1], sys.argv[2]))
    tot = collections.Counter(); byte = collections.Counter()
    for r in rows:
        tot[r['cls']] += 1; byte[r['cls']] += r['size']
    print('[classify] (a) %d 区間 %d B / (b) %d 区間 %d B / (c) %d 区間 %d B (うち padding %d 区間)' % (
        tot['a'], byte['a'], tot['b'], byte['b'], tot['c'], byte['c'], sum(1 for r in rows if r['why'].startswith('padding'))))
    if '--md' in sys.argv:
        print('| # | VA | B | 分類 | 根拠 | 参照元 (call/jmp) | 参照元 (reloc) | 先頭 8 B |')
        print('|---:|---|---:|:---:|---|---|---|---|')
        for i, r in enumerate(rows):
            print('| %d | 0x%x | %d | %s | %s | %s | %s | `%s` |' % (i, r['va'], r['size'], r['cls'], r['why'],
                  ' '.join(r['calls']) or '-', ' '.join(r['relocs']) or '-', r['head']))
    return rows


if __name__ == '__main__':
    main()
