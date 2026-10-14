#!/usr/bin/env python3
"""lift_text.py: Slayer_Engine.dll (block22434) の .text を ia32 x64c で lift する (#1098)。

  python3 lift_text.py          roots 作成 → x64c (--arch ia32 --closure 999) → emcc -c → 被覆の実測 (work/ に出力)

関数境界の決め方 (根拠は REPORT_APPENDIX_1098.md §1):
  R1 export (main = 0x10007ca0)。
  R2 .rdata / .data の .reloc 絶対 dword (vtable・関数ポインタ表) のうち、値が .text を指すもの (243 本)。
  R3 .text 内の命令の即値 (mov/push/lea) のうち、値が .text を指すもの (10 本)。
  R4 直接 call 先は x64c の closure (再帰降下) で追加。 jump table は jmp の表から読む。
  .text 内の reloc 箇所のうち jump table 以外の値 (86 本) は roots に入れない (入れると data を命令として読む: REPORT_APPENDIX_1098.md §3)。
素材: $FL_WIN64_DIR/extracted/block22434_PE.bin (既定 $RUNNER_TEMP/fl-win64)。 依存: capstone==5.0.7・pefile・emcc (emsdk)。
"""
import json, os, re, struct, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..', '..'))
X64C = os.path.join(ROOT, 'tools', 'ott', 'lift', 'x64c.py')
RT = os.path.join(ROOT, 'tools', 'ott', 'rt')
WORK = os.path.join(HERE, 'work')
EXPORT_MAIN = 0x10007CA0


def pe_path():
    d = os.environ.get('FL_WIN64_DIR') or os.path.join(os.environ.get('RUNNER_TEMP', ''), 'fl-win64')
    p = os.path.join(d, 'extracted', 'block22434_PE.bin')
    if not os.path.isfile(p):
        sys.exit('[lift_text] FAIL: %s が無い (素材 fl-win64 を展開すること)' % p)
    return p


def main():
    import pefile
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    from capstone.x86 import X86_OP_IMM
    pth = pe_path()
    os.makedirs(WORK, exist_ok=True)
    pe = pefile.PE(pth)
    IMG = pe.OPTIONAL_HEADER.ImageBase
    text = pe.sections[0]
    T0 = IMG + text.VirtualAddress
    T1 = T0 + text.Misc_VirtualSize
    img = pe.get_memory_mapped_image()
    roots = {EXPORT_MAIN}
    data_t, imm_t = set(), set()
    for b in pe.DIRECTORY_ENTRY_BASERELOC:
        for e in b.entries:
            if e.type != 3:
                continue
            va = IMG + e.rva
            if T0 <= va < T1:
                continue
            v = struct.unpack_from('<I', img, e.rva)[0]
            if T0 <= v < T1:
                data_t.add(v)
    md = Cs(CS_ARCH_X86, CS_MODE_32); md.detail = True
    code = img[text.VirtualAddress:text.VirtualAddress + text.Misc_VirtualSize]
    for ins in md.disasm(code, T0):
        if ins.mnemonic in ('mov', 'push', 'lea'):
            for op in ins.operands:
                if op.type == X86_OP_IMM and T0 <= op.imm < T1:
                    imm_t.add(op.imm)
    roots |= data_t | imm_t
    ej = os.path.join(WORK, 'entries_text.json')
    json.dump({'roots': sorted(roots), 'calltgt': []}, open(ej, 'w'))
    print('[roots] export 1 + .rdata/.data の .text 向き絶対ポインタ %d (distinct) + code 即値 %d (distinct) = %d' % (len(data_t), len(imm_t), len(roots)))
    out = os.path.join(WORK, 'lift_text')
    r = subprocess.run([sys.executable, X64C, '--pe', pth, '--entries', ej, '--out', out, '--closure', '999', '--arch', 'ia32'],
                       capture_output=True, text=True)
    print(r.stdout.strip()); print(r.stderr.strip()[-400:])
    if r.returncode != 0:
        sys.exit('[lift_text] FAIL: x64c rc %d' % r.returncode)
    cc = ['emcc', '-c', '-O1', '-w', '-I', RT, os.path.join(out, 'ott_lifted.c'), '-o', os.path.join(out, 'ott_lifted.o')]
    r2 = subprocess.run(cc, capture_output=True, text=True)
    print('[emcc -c] rc %d, object %d B' % (r2.returncode, os.path.getsize(os.path.join(out, 'ott_lifted.o')) if r2.returncode == 0 else 0))
    if r2.returncode != 0:
        print(r2.stderr[-800:]); sys.exit('[lift_text] FAIL: emcc -c')
    src = open(os.path.join(out, 'ott_lifted.c')).read()
    vas = sorted(set(int(m.group(1), 16) for m in re.finditer(r'/\* ([0-9a-f]+): ', src)))
    cov = bytearray(text.Misc_VirtualSize)
    for va in vas:
        ins = next(md.disasm(img[va - IMG:va - IMG + 16], va, 1), None)
        if ins is None:
            sys.exit('[lift_text] FAIL: 命令の起点 0x%x が生バイトで decode できない' % va)
        for k in range(ins.size):
            if va - T0 + k < len(cov):
                cov[va - T0 + k] = 1
    meta = json.load(open(os.path.join(out, 'lift_meta.json')))
    print('[coverage] 命令の起点 %d、被覆 %d / %d B (%.2f%%)、未被覆 %d B' % (
        len(vas), sum(cov), len(cov), 100.0 * sum(cov) / len(cov), len(cov) - sum(cov)))
    print('[unsup] 非 x87 = %s' % {k: v for k, v in meta['unsup'].items() if not k.startswith('f')})
    print('[summary] functions %d, insns %d, unlifted callees %d, jump tables %d' % (
        len(meta['functions']), meta['ninsn'], sum(meta['unlifted_callees'].values()), len(meta['jt_ranges'])))
    gap_stats(pe, img, IMG, T0, text, cov, md, meta)


def gap_stats(pe, img, IMG, T0, text, cov, md, meta):
    """未被覆区間の内訳 (REPORT_APPENDIX_1098.md §3)。 定義: 区間 = cov==0 の連続域。 jt 表 = lift_meta の jt_ranges。
    reloc 値 = .text 内の HIGHLOW のうち、位置と値が共に jt の外で、値が .text を指すもの。 直接分岐 = 線形掃引 (CS_MODE_32) の call/jmp/jcc の rel 先。"""
    from capstone.x86 import X86_OP_IMM
    TS = len(cov)
    jtm = bytearray(TS)
    for s, sz in meta['jt_ranges']:
        for k in range(max(s - T0, 0), min(s - T0 + sz, TS)):
            jtm[k] = 1
    gaps, i = [], 0
    while i < TS:
        if cov[i]:
            i += 1
            continue
        j = i
        while j < TS and not cov[j]:
            j += 1
        gaps.append((i, j))
        i = j
    def gap_of(off):
        return next((g for g in gaps if g[0] <= off < g[1]), None)
    R = set()
    nreloc = 0
    for b in pe.DIRECTORY_ENTRY_BASERELOC:
        for e in b.entries:
            off = e.rva - text.VirtualAddress
            if e.type != 3 or not (0 <= off < TS) or jtm[off]:
                continue
            v = struct.unpack_from('<I', img, e.rva)[0]
            if T0 <= v < T0 + TS and not jtm[v - T0]:
                nreloc += 1
                g = gap_of(v - T0)
                if g:
                    R.add(g)
    D = set()
    ndir = 0
    code = img[text.VirtualAddress:text.VirtualAddress + TS]
    for ins in md.disasm(code, T0):
        if (ins.mnemonic == 'call' or ins.mnemonic.startswith('j')) and ins.operands and ins.operands[0].type == X86_OP_IMM:
            t = ins.operands[0].imm
            if T0 <= t < T0 + TS:
                g = gap_of(t - T0)
                if g:
                    D.add(g)
                    ndir += 1
    jt_bytes = sum(min(s - T0 + sz, TS) - max(s - T0, 0) for s, sz in meta['jt_ranges'] if s - T0 < TS)
    jt_gap = sum(sum(1 for k in range(max(s - T0, 0), min(s - T0 + sz, TS)) if not cov[k]) for s, sz in meta['jt_ranges'])
    jt_gap_uniq = sum(1 for k in range(TS) if jtm[k] and not cov[k])
    big = max(gaps, key=lambda g: g[1] - g[0])
    print('[gap] 未被覆区間 %d 個 (計 %d B)。 最大 0x%x〜0x%x (%d B)' % (
        len(gaps), sum(b - a for a, b in gaps), big[0] + T0, big[1] + T0, big[1] - big[0]))
    print('[gap] jt 表 %d 本 (計 %d B) のうち未被覆域 %d B (区間ごとの和。 表どうしの重なりを除いた一意バイトは %d B)' % (
        len(meta['jt_ranges']), jt_bytes, jt_gap, jt_gap_uniq))
    print('[gap] reloc (jt の外・値が .text) %d 本のうち、未被覆域の値を含む区間 %d 個' % (nreloc, len(R)))
    print('[gap] 直接 call/jmp/jcc の先を含む区間 %d 個 (%d 本)' % (len(D), ndir))
    rest = [g for g in gaps if g not in R and g not in D]
    print('[gap] 上記のどちらも含まない区間 %d 個 (%d B)' % (len(rest), sum(b - a for a, b in rest)))


if __name__ == '__main__':
    main()
