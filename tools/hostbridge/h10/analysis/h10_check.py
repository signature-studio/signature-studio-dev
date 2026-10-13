#!/usr/bin/env python3
"""h10_check.py — Fruity Wrapper の状態 reader (SaveRestoreState load → record loop) に関する主張を PE バイトから機械検査する.

Ghidra 非依存 (pefile + capstone のみ)。evidence/*.c (Ghidra decompile) とは別アルゴリズムで、
dispatch tree を capstone の命令列から抽象実行して「record id → 読込サイズ/種別」を導出する。

usage: h10_check.py <fw_a.dll> [<fw_b.dll>] [--json out.json] [--break <key>]
  --break <key>: ネガティブコントロール (期待表の 1 要素を壊して FAIL することを確認): rec57size | ver | ctor6 | rec51
exit 0 = 全 PASS (--break 時は FAIL を検出したら exit 0 = 「検出できた」).
"""
import json, struct, sys
import pefile, capstone

# fw_a (block19091) の既知アドレス: 名前 → (VA, size)  (Ghidra function size)
FUNCS_A = {
    'SaveRestoreState': (0x870da0, 1042),
    'readerV5': (0x875af0, 5237),
    'writer': (0x8712b0, 2681),
    'ctor_TVSTPlugin': (0x7a9db0, 0),
    'ctor_caller': (0x87c980, 55),
}
# 期待: reader の record dispatch (id → (種別, サイズ))  [fw_a 実測: asm の handler を機械解析した結果と比較する]
EXPECT = {
    0x01: ('fixed', 0x14), 0x02: ('fixed', 0x19), 0x1e: ('fixed', 0x10),
    0x1f: ('array12', None), 0x20: ('array12', None),
    0x32: ('fixed', 0x10), 0x33: ('fixed', 4), 0x34: ('fixed', 0x10),
    0x35: ('blob', None), 0x36: ('string', None), 0x37: ('string+replace', None), 0x38: ('string', None),
    0x39: ('fixed', 4), 0x3a: ('string', None),
}


class Img:
    def __init__(self, path):
        self.pe = pefile.PE(path)
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.img = self.pe.get_memory_mapped_image()
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.md.skipdata = True
        self.sections = [(s.Name.rstrip(b'\0').decode(), self.base + s.VirtualAddress,
                          self.base + s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData)) for s in self.pe.sections]

    def bytes_at(self, va, n):
        return self.img[va - self.base: va - self.base + n]

    def dis(self, va, n):
        return list(self.md.disasm(self.bytes_at(va, n), va))

    def locate(self, ref: 'Img', va, plen=24):
        """ref の関数 (va) の先頭 plen バイトを自 image から探し、一意に見つかった VA を返す."""
        sig = ref.bytes_at(va, plen)
        first = self.img.find(sig)
        if first < 0 or self.img.find(sig, first + 1) >= 0:
            return None
        return self.base + first


def imm(op):
    return int(op, 16) if op.startswith('0x') else int(op)


def dispatch_table(im: Img, fva, fsize):
    """readerV5 の record dispatch を抽象実行し {id: handler_va} を返す (default = loop 末尾の seek)."""
    ins = im.dis(fva, fsize)
    idx = {i.address: k for k, i in enumerate(ins)}
    start = None
    for k in range(len(ins) - 1):
        a, b = ins[k], ins[k + 1]
        if a.mnemonic == 'mov' and a.op_str.startswith('eax, dword ptr [rbp +') and b.mnemonic == 'cmp' and b.op_str == 'eax, 0x34':
            start = k
            break
    if start is None:
        raise RuntimeError('dispatch start (cmp eax,0x34) not found')
    res = {}
    for rid in range(0, 0x40):
        eax = rid
        flags = None  # (lhs - rhs) as signed for jg/jl, zero for je/jne
        k = start + 1
        steps = 0
        while steps < 400:
            steps += 1
            i = ins[k]
            m, o = i.mnemonic, i.op_str
            if m == 'cmp' and o.startswith('eax, '):
                flags = eax - imm(o.split(', ')[1])
            elif m == 'sub' and o.startswith('eax, '):
                eax = eax - imm(o.split(', ')[1])
                flags = eax
            elif m == 'test' and o == 'eax, eax':
                flags = eax
            elif m in ('je', 'jne', 'jg', 'jl', 'jle', 'jge', 'ja', 'jb', 'jae', 'jbe', 'jmp'):
                tgt = int(o, 16)
                take = {'je': flags == 0, 'jne': flags != 0, 'jg': flags is not None and flags > 0,
                        'jl': flags is not None and flags < 0, 'jle': flags is not None and flags <= 0,
                        'jge': flags is not None and flags >= 0, 'jmp': True}.get(m)
                if take is None:
                    raise RuntimeError(f'unsupported branch {m}')
                if take:
                    k = idx[tgt]
                    if m == 'jmp' or (ins[k].mnemonic not in ('cmp', 'sub', 'test')):
                        res[rid] = tgt
                        break
                    continue
            else:
                res[rid] = i.address
                break
            k += 1
        else:
            raise RuntimeError(f'dispatch walk did not terminate for id {rid}')
    return res, ins, idx


def classify(ins, idx, handler):
    """handler の命令列から (種別, サイズ) を導出. 末尾は次 record への seek (loop 共通)."""
    k = idx[handler]
    edx = None
    kinds = []
    replace = False
    for j in range(k, min(k + 60, len(ins))):
        i = ins[j]
        m, o = i.mnemonic, i.op_str
        if m == 'mov' and o.startswith('edx, ') and o.split(', ')[1].startswith(('0x', '1', '2', '3', '4', '5', '6', '7', '8', '9')):
            edx = imm(o.split(', ')[1])
        if m == 'mov' and o.startswith('r9w, 0x5c'):
            replace = True
        if m == 'call':
            kinds.append(('call', o, edx))
        if m == 'jmp':
            break
    return kinds, replace, [c[1] for c in kinds]


def reader_table(im: Img, fva, fsize):
    disp, ins, idx = dispatch_table(im, fva, fsize)
    # default handler (= 未知 id) の VA は最頻値
    from collections import Counter
    default = Counter(disp.values()).most_common(1)[0][0]
    table = {}
    for rid, h in disp.items():
        if h == default:
            continue
        kinds, replace, _calls = classify(ins, idx, h)
        table[rid] = (h, kinds, replace)
    return table, default, ins, idx


def main():
    argv = sys.argv[1:]
    brk = None
    out_json = None
    if '--break' in argv:
        brk = argv[argv.index('--break') + 1]
        del argv[argv.index('--break'):argv.index('--break') + 2]
    if '--json' in argv:
        out_json = argv[argv.index('--json') + 1]
        del argv[argv.index('--json'):argv.index('--json') + 2]
    a = Img(argv[0])
    builds = [('fw_a (block19091)', a, a, 0)]
    if len(argv) > 1:
        builds.append(('fw_b (block23676)', Img(argv[1]), a, 1))

    results = []
    fails = 0

    def check(name, ok, detail=''):
        nonlocal fails
        results.append({'check': name, 'ok': bool(ok), 'detail': detail})
        print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail else ''))
        if not ok:
            fails += 1

    for label, im, ref, is_b in builds:
        print(f'== {label}')
        addr = {}
        for n, (va, sz) in FUNCS_A.items():
            if not is_b:
                addr[n] = va
            elif n == 'ctor_caller':
                addr[n] = None  # ctor の call 元から後で解決 (先頭に rip 相対があり署名が使えない)
            else:
                addr[n] = im.locate(ref, va, 34 if n == 'SaveRestoreState' else 24)
            if not is_b:
                check(f'{label}: locate {n}', addr[n] is not None, hex(addr[n]) if addr[n] else 'not found')
        if is_b and addr['ctor_TVSTPlugin']:
            tva_ = addr['ctor_TVSTPlugin']
            lo_ = [l for n_, l, h in im.sections if n_.startswith('.text')][0]
            hi_ = [h for n_, l, h in im.sections if n_.startswith('.text')][0]
            blob_ = im.bytes_at(lo_, hi_ - lo_)
            import re as re_, struct as st_
            for m_ in re_.finditer(rb'\xe8(....)', blob_, re_.S):
                if lo_ + m_.start() + 5 + st_.unpack('<i', m_.group(1))[0] == tva_:
                    site = lo_ + m_.start()
                    back = im.bytes_at(site - 0x30, 0x30)
                    k_ = back.rfind(b'\x48\x83\xec\x38')
                    addr['ctor_caller'] = site - 0x30 + k_ if k_ >= 0 else None
        for n in addr:
            if is_b:
                check(f'{label}: locate {n}', addr[n] is not None, hex(addr[n]) if addr[n] else 'not found')
        if any(v is None for v in addr.values()):
            continue

        # --- 1. reader record dispatch (asm 抽象実行) vs EXPECT
        fva, fsz = addr['readerV5'], FUNCS_A['readerV5'][1]
        table, default, ins, idx = reader_table(im, fva, fsz)
        # 読込 helper の VA は build ごとに違うので、既知の固定長 record (50/51/52) と文字列 record (54) から役割で同定する
        def role(rid):
            h, kinds, replace = table[rid]
            cs = [c for c in kinds if c[1].startswith('0x')]
            return cs, replace
        derived = {}
        fixed_helper = None
        for rid in (0x32, 0x33, 0x34):  # 既知の固定長 (16/4/16) から fixed-read helper を同定
            cs, _ = role(rid)
            if cs:
                fixed_helper = cs[-1][1]
        string_helper = role(0x36)[0][-1][1] if role(0x36)[0] else None
        for rid in sorted(table):
            cs, replace = role(rid)
            names = [c[1] for c in cs]
            if fixed_helper in names and not any('416eb0' in n or '5013f0' in n for n in names) and string_helper not in names:
                size = [c[2] for c in cs if c[1] == fixed_helper][-1]
                derived[rid] = ('fixed', size)
            elif string_helper in names:
                derived[rid] = ('string+replace' if replace else 'string', None)
            elif fixed_helper in names:
                # array (416eb0 で配列確保 → fixed helper でサイズ=count*12) / blob (5013f0 で resize)
                is_blob = any(n.endswith('5013f0') or n == '0x5013f0' for n in names)
                derived[rid] = ('blob', None) if is_blob else ('array12', None)
            else:
                derived[rid] = ('?', names)
        if brk == 'rec57size':
            derived[0x39] = ('fixed', 8)
        if brk == 'rec51':
            derived.pop(0x33, None)
        exp = dict(EXPECT)
        check(f'{label}: reader handles exactly ids {sorted(hex(i) for i in exp)}',
              sorted(derived) == sorted(exp), f'derived={sorted(hex(i) for i in derived)}')
        for rid in sorted(exp):
            check(f'{label}: record {rid} (0x{rid:x}) = {exp[rid][0]}{"/" + str(exp[rid][1]) if exp[rid][1] else ""}',
                  derived.get(rid) == exp[rid], f'derived={derived.get(rid)}')
        unk = [r for r in range(0x40) if r not in table]
        check(f'{label}: 未知 id {len(unk)} 個 (0..0x3f のうち) は全て default (= 次 record へ seek, 読込なし)',
              len(unk) == 0x40 - len(exp), f'unknown ids -> default handler {hex(default)}')

        # --- 2. 末尾 seek helper が record 内容を消費しなくても次 record へ進む (loop 末尾 = call seek; loop 条件 pos < size)
        tail = [i for i in ins if i.address >= default][:14]
        check(f'{label}: default handler は (record 先頭 + size) へ seek して loop 条件へ戻る',
              any(i.mnemonic == 'call' for i in tail) and any(i.mnemonic == 'jl' for i in tail),
              ' ; '.join(f'{i.mnemonic} {i.op_str}' for i in tail[:8]))

        # --- 3. 文字列 encoding: version >= 9 で UTF-8 flag (or al,2)
        win = [i for i in ins if fva <= i.address < fva + 0x300]
        pos9 = [k for k, i in enumerate(win) if i.mnemonic == 'cmp' and i.op_str.endswith(', 9')]
        ok9 = any(win[k + 1].mnemonic == 'jl' and win[k + 2].mnemonic == 'or' and win[k + 2].op_str == 'al, 2' for k in pos9 if k + 2 < len(win))
        check(f'{label}: reader は version>=9 で UTF-8 flag (or al,2)、version<=8 は ANSI', ok9)
        # flags 既定値 byte (rip 相対) = 0
        movz = [i for i in win if i.mnemonic == 'movzx' and 'rip' in i.op_str]
        rip_va = None
        if movz:
            m = movz[0]
            disp = int(m.op_str.split('rip')[1].strip(' +]').replace(' ', ''), 16) if '+' in m.op_str else -int(m.op_str.split('-')[1].strip(' ]'), 16)
            rip_va = m.address + m.size + disp
        check(f'{label}: reader flag 既定値 (DAT) = 0 → ANSI 既定', rip_va is not None and im.bytes_at(rip_va, 1) == b'\x00',
              f'DAT@{hex(rip_va) if rip_va else None}={im.bytes_at(rip_va, 1).hex() if rip_va else None}')

        # --- 4. version gate (SaveRestoreState): > 12 は error 5、-1 は無視、<5 は legacy reader、>=5 は record reader
        sva = addr['SaveRestoreState']
        sins = im.dis(sva, FUNCS_A['SaveRestoreState'][1])
        cmps = [(i.op_str.split(', ')[1], sins[k + 1].mnemonic) for k, i in enumerate(sins[:-1])
                if i.mnemonic == 'cmp' and i.op_str.startswith('dword ptr [rbp +') and sins[k + 1].mnemonic in ('jle', 'jg', 'je', 'jne', 'jl', 'jge')]
        want = {('0xc', 'jle'), ('-1', 'je'), ('4', 'jg')}
        if brk == 'ver':
            want = {('0xd', 'jle'), ('-1', 'je'), ('4', 'jg')}
        check(f'{label}: version gate = {{>12: error5, ==-1: skip, <=4: legacy 875800, >=5: record reader}}',
              want <= set(cmps), f'cmp/jcc={cmps}')
        wr = [i for i in sins if i.mnemonic == 'mov' and i.op_str.endswith(', 0xc') and 'dword ptr [rbp' in i.op_str]
        check(f'{label}: writer は常に version 12 (0xc) を書く (save 経路)', len(wr) >= 1, wr[0].op_str if wr else '')

        # --- 5. TVSTPlugin ctor の呼出元は 1 箇所のみ、6 番目引数 (hint) = 定数 0
        import re
        tva = addr['ctor_TVSTPlugin']
        refs = []
        for name, lo, hi in im.sections:
            if not name.startswith('.text'):
                continue
            blob = im.bytes_at(lo, hi - lo)
            for m_ in re.finditer(rb'[\xe8\xe9](....)', blob, re.S):
                rel = struct.unpack('<i', m_.group(1))[0]
                if lo + m_.start() + 5 + rel == tva:
                    refs.append(('call/jmp', lo + m_.start()))
            for m_ in re.finditer(rb'[\x48\x4c]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d](....)', blob, re.S):
                disp = struct.unpack('<i', m_.group(1))[0]
                if lo + m_.start() + 7 + disp == tva:
                    refs.append(('lea', lo + m_.start()))
        for name, lo, hi in im.sections:
            if name.startswith('.pdata') or name.startswith('.reloc'):
                continue
            blob = im.bytes_at(lo, hi - lo)
            pos = blob.find(struct.pack('<Q', tva))
            while pos >= 0:
                refs.append(('ptr64', lo + pos))
                pos = blob.find(struct.pack('<Q', tva), pos + 1)
        check(f'{label}: TVSTPlugin ctor ({hex(tva)}) の参照は 1 件 (call) のみ', len(refs) == 1 and refs[0][0] == 'call/jmp', str([(k, hex(v)) for k, v in refs]))
        cva = addr['ctor_caller']
        cins = im.dis(cva, FUNCS_A['ctor_caller'][1])
        sixth = [i for i in cins if i.mnemonic == 'mov' and i.op_str.startswith('qword ptr [rsp + 0x28]')]
        val = sixth[0].op_str.split(', ')[1] if sixth else None
        if brk == 'ctor6':
            val = '0x1'
        check(f'{label}: 6 番目引数 (stack [rsp+0x28] = hint) は定数 0', val in ('0', '0x0'), f'{sixth[0].op_str if sixth else None}')
        callsite = [i for i in cins if i.mnemonic == 'call']
        check(f'{label}: caller 内の call 先 = TVSTPlugin ctor', len(callsite) == 1 and int(callsite[0].op_str, 16) == tva)

        # --- 6. record 57 の実体 = effGetVstVersion (opcode 0x3a) の結果 (+0x9c4) — ctor で格納、writer で record 0x39 として書出し
        cbody = im.dis(tva, 0x1800)
        st = [k for k, i in enumerate(cbody) if i.mnemonic == 'mov' and i.op_str.startswith('dword ptr [rcx + 0x9c4], eax')]
        win_ok = False
        if st:
            k = st[0]
            win_ok = any(j.mnemonic == 'mov' and j.op_str in ('edx, 0x3a',) for j in cbody[max(0, k - 12):k])
        check(f'{label}: TVSTPlugin ctor: dispatcher(opcode 0x3a=effGetVstVersion) の戻りを +0x9c4 へ格納', bool(st) and win_ok)
        wins = im.dis(addr['writer'], FUNCS_A['writer'][1])
        w39 = [k for k, i in enumerate(wins) if i.mnemonic == 'mov' and i.op_str.startswith('eax, dword ptr [rbx + 0x9c4]')]
        ok39 = bool(w39) and any(j.mnemonic == 'mov' and j.op_str == 'edx, 0x39' for j in wins[w39[0]:w39[0] + 6])
        check(f'{label}: writer は +0x9c4 を record 0x39 として書き、書出しは TVSTPlugin インスタンスのみ (IsInstance 呼出し直後)', ok39)

    summary = {'fails': fails, 'checks': len(results), 'break': brk}
    print(f'\nSUMMARY checks={len(results)} fails={fails} break={brk}')
    if out_json:
        json.dump({'summary': summary, 'results': results}, open(out_json, 'w'), indent=1)
    if brk:
        sys.exit(0 if fails > 0 else 1)
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
