#!/usr/bin/env python3
# KH-150 (#5326): Ladder (ksla) の process (slot 14) と間接 call 先 (slot 15・20) が読む self / ctx のフィールドを
# 機械語のメモリオペランドから集計する。直線走査 + レジスタ由来追跡 (簡易・分岐は無視)。
#   usage: python3 scripts/ladder_layout_census.py <HeartCore.core_64> [out.json]
# 役割: 'self' = 関数に入った時の rcx (this) 由来 / 'ctx' = rdx (ctx) 由来 / 'ctx.model' = [ctx+0x3188] 由来。
import json, sys
import capstone
from capstone.x86 import X86_OP_MEM, X86_REG_RIP

PE = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else None
CTX_MODEL = 0x3188
# (名前, 関数 VA, 終端 VA (排他), 入口の this / ctx / 5 番目以降の役割)
RANGES = [
    ('process slot14', 0x1804d9930, 0x1804d9b9c, {'rcx': 'self', 'rdx': 'ctx'}),
    ('slot15',         0x1804d9820, 0x1804d98b0, {'rcx': 'self', 'rdx': 'ctx'}),
    ('slot20',         0x1804d9ba0, 0x1804db990, {'rcx': 'self', 'rdx': 'ctx'}),
]
# x64 の 64bit 汎用レジスタ 16 本の 32/16/8bit 別名を 64bit 名に寄せる
ALIAS = {}
for full, names in {
    'rax': ['eax', 'ax', 'al'], 'rbx': ['ebx', 'bx', 'bl'], 'rcx': ['ecx', 'cx', 'cl'], 'rdx': ['edx', 'dx', 'dl'],
    'rsi': ['esi', 'si', 'sil'], 'rdi': ['edi', 'di', 'dil'], 'rbp': ['ebp', 'bp', 'bpl'], 'rsp': ['esp', 'sp', 'spl'],
    **{f'r{i}': [f'r{i}d', f'r{i}w', f'r{i}b'] for i in range(8, 16)},
}.items():
    ALIAS[full] = full
    for n in names:
        ALIAS[n] = full
for i in range(8, 16):
    ALIAS[f'r{i}'] = f'r{i}'


def width_of(insn, op_size):
    # 命令のメモリ幅 (バイト)。movss/movd/movaps 等の幅は mnemonic と op_size で決める
    m = insn.mnemonic
    if m in ('movss', 'addss', 'mulss', 'subss', 'minss', 'maxss', 'divss', 'cvtss2sd'):
        return 4
    if m in ('movsd', 'addsd', 'mulsd'):
        return 8
    if m in ('movaps', 'movups', 'movdqa', 'movdqu', 'movapd') or m.startswith('movups'):
        return 16
    if m in ('movd',):
        return 4
    if m in ('movq',):
        return 8
    if m in ('movshdup', 'movsldup'):
        return 16
    if m.startswith('mov') and op_size:
        return op_size
    return op_size or 0


def kind_of(width, insn):
    m = insn.mnemonic
    if m.endswith('ss') or m in ('movss', 'movd'):
        return 'f32' if m.endswith('ss') or m == 'movss' else 'i32'
    if m in ('movsd', 'addsd', 'mulsd'):
        return 'f64'
    if width == 16:
        return 'v128'
    return {1: 'u8', 2: 'u16', 4: 'i32', 8: 'i64'}.get(width, '?')


def census(md, code, base_va, lo, hi, roles):
    regmap = {}  # reg64 -> (role, extra) ; role = 'self' | 'ctx' | 'ctx.model'
    for k, v in roles.items():
        regmap[ALIAS[k]] = (v, None)
    rows = {}
    for insn in md.disasm(code, base_va):
        if insn.address >= hi:
            break
        if insn.address < lo:
            continue
        # 1) 追跡: mov reg, [base+disp] で base が ctx なら reg を ctx.model にする
        ops = insn.operands
        if insn.mnemonic == 'mov' and len(ops) == 2 and ops[0].type == 1 and ops[1].type == X86_OP_MEM:
            m = ops[1].mem
            base = ALIAS.get(insn.reg_name(m.base), '') if m.base else ''
            if base in regmap and regmap[base][0] == 'ctx' and m.disp == CTX_MODEL:
                regmap[ALIAS[insn.reg_name(ops[0].reg)]] = ('ctx.model', None)
                continue
        # 2) メモリ参照を記録
        for op in ops:
            if op.type != X86_OP_MEM:
                continue
            m = op.mem
            if m.base == X86_REG_RIP or not m.base:
                continue
            base = ALIAS.get(insn.reg_name(m.base), '')
            if base not in regmap:
                continue
            role = regmap[base][0]
            if role == 'ctx' and m.disp == CTX_MODEL:
                continue  # 参照そのものは上の追跡で扱う
            disp = m.disp
            if m.index:
                disp = None  # 添字付き (配列) は個別オフセットにできない
            w = width_of(insn, op.size)
            key = (role, disp)
            r = rows.setdefault(key, {'role': role, 'off': disp, 'width': w, 'kinds': set(), 'insns': []})
            r['kinds'].add(kind_of(w, insn))
            r['width'] = max(r['width'], w)
            if len(r['insns']) < 3:
                r['insns'].append('%x %s %s' % (insn.address, insn.mnemonic, insn.op_str))
            is_write = op is ops[0] and insn.mnemonic not in ('cmp', 'test', 'ucomiss', 'comiss', 'ucomisd', 'comisd', 'bt')
            r.setdefault('acc', set()).add('write' if is_write else 'read')
        # 3) レジスタの追跡: 単純な複写 (mov reg, reg) は別名を伝播、それ以外でレジスタが上書きされたら追跡を止める
        if ops and ops[0].type == 1:
            dst = ALIAS.get(insn.reg_name(ops[0].reg), '')
            if insn.mnemonic == 'mov' and len(ops) == 2 and ops[1].type == 1 and ALIAS.get(insn.reg_name(ops[1].reg), '') in regmap:
                regmap[dst] = regmap[ALIAS[insn.reg_name(ops[1].reg)]]
            elif dst in regmap and insn.mnemonic not in ('cmp', 'test'):
                del regmap[dst]
    out = []
    for key in sorted(rows, key=lambda k: (k[0], -1 if k[1] is None else k[1])):
        r = rows[key]
        r['kinds'] = sorted(r['kinds'])
        r['access'] = '/'.join(sorted(r.pop('acc', set())))
        out.append(r)
    return out


def main():
    with open(PE, 'rb') as f:
        data = f.read()
    # PE の .text は ImageBase 0x180000000・RVA で読む (x64c の --img と同じ)。ファイル offset は RVA から求める
    import struct
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    nsec = struct.unpack_from('<H', data, pe + 6)[0]
    optsz = struct.unpack_from('<H', data, pe + 20)[0]
    sec0 = pe + 24 + optsz
    secs = []
    for i in range(nsec):
        o = sec0 + 40 * i
        vsz, va, rawsz, rawptr = struct.unpack_from('<IIII', data, o + 8)
        secs.append((va, max(vsz, rawsz), rawptr, rawsz))
    IMG = 0x180000000

    def read(va, n):
        rva = va - IMG
        for sva, ssz, raw, rsz in secs:
            if sva <= rva < sva + ssz:
                off = raw + (rva - sva)
                return data[off:off + n]
        raise RuntimeError('VA not mapped: %x' % va)

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    result = {}
    for name, lo, hi, roles in RANGES:
        code = read(lo, hi - lo)
        rows = census(md, code, lo, lo, hi, roles)
        result[name] = rows
        print('== %s  [%x, %x)' % (name, lo, hi))
        for r in rows:
            print('  %-10s off=%-8s width=%-3s kinds=%-12s access=%-5s e.g. %s' % (
                r['role'], '?' if r['off'] is None else hex(r['off']), r['width'], ','.join(r['kinds']),
                r.get('access', '-'), ' | '.join(r['insns'][:2])))
    if OUT:
        json.dump(result, open(OUT, 'w'), indent=1)


if __name__ == '__main__':
    main()
