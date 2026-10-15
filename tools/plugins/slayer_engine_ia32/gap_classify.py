#!/usr/bin/env python3
"""gap_classify.py: lift 後の未被覆区間 (.text で被覆 0 の連続域) を 3 類に分類する (#2814 / 親 #1098)。

  (a) data-in-code : jt 表と半分以上重なる、または .text 内の reloc 値 (ポインタ) を 2 本以上含む
  (b) 関数          : 区間の先頭を指す直接 call/jmp/jcc がある、または関数 prologue (55 8b ec / 8b ff 55 8b ec / 83 ec / 81 ec) で始まる
  (c) 参照の無い区間 : 上記のどれでもない。 nop/int3/00 のみの区間 (padding) を含む

  python3 gap_classify.py <PE> <lift 出力 dir> [--md]   分類表を出す (--md で REPORT_APPENDIX_2814 用の Markdown)
  python3 gap_classify.py --json <gap_classes.json> --md  lift_text.py の 1 回目の分類結果から表だけ出す
  lift_text.py から classify() を使い、(b) の先頭を roots に加えて再 lift する。
"""
import collections, json, os, re, struct, sys

PAD = {0x90, 0xCC, 0x00}


def sweep(md, code, T0):
    """線形掃引 (CS_MODE_32)。 デコード不能の 1 バイトは飛ばして続ける (md.disasm の単独呼び出しは最初の不能で止まるため)。
    返り値は (VA, 長さ, insn) の列。 #4726: 旧実装は md.disasm(code, T0) の 1 回呼びで 0x1000a1a0 までしか見ていなかった。"""
    out, pos, n = [], 0, len(code)
    while pos < n:
        r = list(md.disasm(code[pos:pos + 16], T0 + pos, 1))
        if not r:
            pos += 1
            continue
        out.append((T0 + pos, r[0].size, r[0]))
        pos += r[0].size
    return out


def func_end(md, buf, va):
    """va から ret までを 1 本の関数として逆アセンブルできれば、ret の直後の VA を返す。 できなければ None。
    prologue は要求しない (#4726: 0x1000eab4 は mov ecx,[esp+4] で始まる)。 None になるのは次のいずれか:
    先頭が pad / 逆アセンブル不能で ret に届かない / ret の前に int3 がある / jmp・jcc が [va, ret 後) の外へ出る。"""
    from capstone.x86 import X86_OP_IMM
    if not buf or buf[0] in PAD:
        return None
    seen = []
    for ins in md.disasm(buf, va):
        if ins.mnemonic == 'int3':
            return None
        seen.append(ins)
        if ins.mnemonic in ('ret', 'retn'):
            end = ins.address + ins.size
            for i in seen:
                if (i.mnemonic == 'jmp' or i.mnemonic.startswith('j')) and i.operands and i.operands[0].type == X86_OP_IMM:
                    if not (va <= i.operands[0].imm < end):
                        return None
            return end
    return None


def selftest():
    """func_end の正例・負例。 規則を壊すと (例: 常に None・常に非 None) ここで落ちる。"""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32); md.detail = True
    body = bytes.fromhex('8b4c2404f7410406000000b801000000740f8b4424088b5424108902b803000000c3')
    cases = [
        ('prologue なし・ret で終わる関数 (0x1000eab4 と同形)', body, 0x1000eab4, 0x1000eab4 + len(body)),
        ('ret が無い (ret 前に尽きる)', body[:-1], 0x1000eab4, None),
        ('先頭が pad', b'\xcc' + body, 0x1000eab4, None),
        ('ret 前に int3', body[:4] + b'\xcc' + body[4:], 0x1000eab4, None),
        ('ret 後へ出る jmp', bytes.fromhex('e900010000c3'), 0x1000, None),
    ]
    bad = []
    for name, buf, va, want in cases:
        got = func_end(md, buf, va)
        if got != want:
            bad.append('%s: got %s want %s' % (name, got and hex(got), want and hex(want)))
    if bad:
        sys.exit('[selftest] FAIL\n  ' + '\n  '.join(bad))
    print('[selftest] PASS (%d 件: 関数の正例 1・負例 %d)' % (len(cases), len(cases) - 1))


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
    code = img[text.VirtualAddress:text.VirtualAddress + TS]
    calls = collections.defaultdict(list)
    heads = collections.defaultdict(list)
    for ins in md.disasm(code, T0):
        if (ins.mnemonic == 'call' or ins.mnemonic.startswith('j')) and ins.operands and ins.operands[0].type == X86_OP_IMM:
            t = ins.operands[0].imm
            if T0 <= t < T0 + TS and (t - T0) in where:
                n = where[t - T0]
                calls[n].append(ins.address)
                if t - T0 == gaps[n][0]:
                    heads[n].append(ins.address)
    cref = collections.defaultdict(list)   # 区間内を指す push 即値 (resync 掃引で全域を見る)。 SEH フレームの登録 (push <関数>) の形
    for va, size, ins in sweep(md, code, T0):
        if ins.mnemonic != 'push':
            continue
        for op in ins.operands:
            if op.type == X86_OP_IMM and T0 <= op.imm < T0 + TS and (op.imm - T0) in where:
                cref[where[op.imm - T0]].append((op.imm, va))
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
        k = 0
        while k < len(bs) and bs[k] in PAD:
            k += 1
        fbs = bs[k:]
        fva = T0 + a + k
        entries = sorted({t for t, _ in cref[n] if func_end(md, bytes(img[t - IMG:t - IMG + 512]), t) is not None})
        if set(bs) <= PAD:
            cls, why = 'c', 'padding (90/cc/00 のみ)'
        elif jt * 2 >= (b - a):
            cls, why = 'a', 'jt 表と重なる (%d/%d B)' % (jt, b - a)
        elif fbs[:3] == b'\x55\x8b\xec' or fbs[:5] == b'\x8b\xff\x55\x8b\xec' or fbs[:2] in (b'\x83\xec', b'\x81\xec'):
            cls = 'b'
            why = 'prologue %s (先頭 pad %d B の後)' % (fbs[:6].hex(' '), k)
        elif entries and not heads[n] and bs[0] in PAD:
            cls = 'b'
            why = 'コード側の即値が指す関数 %s (prologue なし・ret まで逆アセンブル可、区間先頭は pad)' % ','.join('0x%x' % x for x in entries[:3])
        elif len(relo[n]) >= 2:
            cls, why = 'a', '.text 内の reloc 値 %d 本 (ポインタ表とみなす)' % len(relo[n])
        elif heads[n] and bs[0] not in PAD:
            cls = 'b'
            why = '区間先頭への直接 call/jmp (参照元 %s)' % ','.join('0x%x' % x for x in heads[n][:3])
        else:
            cls = 'c'
            if heads[n]:
                why = '先頭が pad (先頭への参照あり)'
            elif calls[n]:
                why = '区間内の分岐のみ (先頭への参照なし)'
            else:
                why = '参照なし・prologue なし'
            why += (' (reloc %d 本)' % len(relo[n]) if relo[n] else '')
        rows.append(dict(va=T0 + a, fva=fva, size=b - a, cls=cls, why=why, jt=jt,
                         ncall=len(calls[n]), nhead=len(heads[n]), nreloc=len(relo[n]),
                         calls=['0x%x' % x for x in calls[n][:3]], relocs=['0x%x' % x for x in relo[n][:3]],
                         entries=entries if cls == 'b' else [], head=bs[:8].hex(' ')))
    return rows


def check_issue_gap(rows):
    """#4726 の回帰検査 (rows は classify() の結果)。 0x1000eab4 を含む区間は (b) で、0x1000eab4 を関数として指す。
    規則を壊すとここで落ちる。 lift_text.py が第 2 パスの前に呼ぶ。 空でなければ不合格の理由。"""
    hit = [r for r in rows if r['va'] <= 0x1000eab4 < r['va'] + r['size']]
    if len(hit) != 1:
        return '0x1000eab4 を含む区間が %d 個 (1 個のはず)' % len(hit)
    r = hit[0]
    if r['cls'] != 'b':
        return '0x1000eab4 の区間の分類が %s (b のはず)' % r['cls']
    if 0x1000eab4 not in r['entries']:
        return '0x1000eab4 が entries に無い: %s' % r['entries']
    return None


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
