#!/usr/bin/env python3
"""殻 (x64 レイアウト) ↔ Slayer_Engine.dll (ia32 レイアウト) の VST2 構造体 marshal 表 (#674 受入 3)。

  marshal.py         表を出力し、engine の実バイナリ (block22434) の AEffect 構築部と突き合わせる。 不一致で exit 1。
  marshal.py --nega  ネガコン (壊した入力・誤った期待は必ず FAIL)。 miss > 0 で exit 1。

素材: $FL_WIN64_DIR/extracted/block22434_PE.bin (既定 $RUNNER_TEMP/fl-win64)。 依存: capstone==5.0.7。
x64 側の期待値は tools/hostbridge/poc/vst2_abi.h (static_assert と同じ値) から取る。
"""
import argparse, os, re, shutil, struct, sys

try:
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    from capstone.x86 import X86_OP_MEM, X86_OP_IMM, X86_OP_REG
except ImportError:
    sys.exit('capstone が無い: uv pip install --python <python> capstone==5.0.7')

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, 'work')
EXPECT_CAPSTONE = '5.0.7'
EXPECT_SHA256 = '84b64c43cc6528401e1c4e84074785e100e8453c4db4c8322a5d5f608de724a9'
CTOR_RVA = 0x10E0          # AEffect 構築関数 (engine の AudioEffect ctor 相当)
CTOR_END = 0x1196          # ret 0xc まで
THIS_TO_AE = 0x20          # lea ebx,[edx+0x20] : AEffect は this+0x20 に埋め込まれる
MAGIC = 0x56737450         # 'VstP'

# AEffect のフィールド (VST SDK 順)。 (名前, 型のサイズ種別, 大きさ)  p = pointer
AEFFECT = [
    ('magic', 'i', 4), ('dispatcher', 'p', 0), ('process', 'p', 0), ('setParameter', 'p', 0),
    ('getParameter', 'p', 0), ('numPrograms', 'i', 4), ('numParams', 'i', 4), ('numInputs', 'i', 4),
    ('numOutputs', 'i', 4), ('flags', 'i', 4), ('resvd1', 'p', 0), ('resvd2', 'p', 0),
    ('initialDelay', 'i', 4), ('realQualities', 'i', 4), ('offQualities', 'i', 4), ('ioRatio', 'f', 4),
    ('object', 'p', 0), ('user', 'p', 0), ('uniqueID', 'i', 4), ('version', 'i', 4),
    ('processReplacing', 'p', 0), ('processDoubleReplacing', 'p', 0), ('future', 'b', 56),
]
# x64 の期待値: tools/hostbridge/poc/vst2_abi.h の _Static_assert と同じ (pad は C の自然整列で入る)
X64_EXPECT = {'dispatcher': 0x08, 'numPrograms': 0x28, 'flags': 0x38, 'resvd1': 0x40, 'ioRatio': 0x5C,
              'object': 0x60, 'uniqueID': 0x70, 'processReplacing': 0x78, 'size': 0xC0}
# x32 の期待値は engine の構築 store 列 (実測) と突き合わせる。 size のみ仕様 (SDK) から
X32_EXPECT = {'size': 0x90}


def layout(ptr):
    off, out = 0, {}
    for name, kind, n in AEFFECT:
        size = ptr if kind == 'p' else n
        align = size if kind in ('p', 'i', 'f') else 1
        off = (off + align - 1) // align * align
        out[name] = (off, size)
        off += size
    max_align = max(ptr, 4)
    total = (off + max_align - 1) // max_align * max_align
    return out, total


def events_layout(ptr):
    # VstEvents: int32 numEvents; (pointer) reserved; VstEvent* events[]
    numEvents = (0, 4)
    reserved = ((4 + ptr - 1) // ptr * ptr, ptr)
    events0 = (reserved[0] + ptr, ptr)
    return {'numEvents': numEvents, 'reserved': reserved, 'events[0]': events0}


VSTEVENT = {'type': (0, 4), 'byteSize': (4, 4), 'deltaFrames': (8, 4), 'flags': (12, 4), 'data[16]': (16, 16)}
ERECT = {'top': (0, 2), 'left': (2, 2), 'bottom': (4, 2), 'right': (6, 2)}


def load(path):
    data = open(path, 'rb').read()
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    opt = struct.unpack_from('<H', data, pe + 20)[0]
    vsz, va, _, rawp = struct.unpack_from('<IIII', data, pe + 24 + opt + 8)
    return data, va, data[rawp:rawp + vsz]


def engine_stores(text, va):
    """ctor 内の AEffect への store を (AE オフセット) -> ('imm', 値) | ('reg', 名前) で返す。
    レジスタに入った即値 (mov reg,imm / xor reg,reg) は線形に追跡し、store 時に即値へ解決する。
    追跡できなくなった reg (他の命令で書き換え・pop) は未知扱い。"""
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    st, const = {}, {}
    for ins in md.disasm(text[CTOR_RVA - va:CTOR_END - va], CTOR_RVA):
        if ins.mnemonic == 'lea' and ins.op_str == 'ebx, [edx + 0x20]':
            st['_lea_ok'] = True
        ops = ins.operands
        if ins.mnemonic == 'mov' and len(ops) == 2 and ops[0].type == X86_OP_REG and ops[1].type == X86_OP_IMM:
            const[ins.reg_name(ops[0].reg)] = ops[1].imm & 0xFFFFFFFF
            continue
        if ins.mnemonic == 'xor' and len(ops) == 2 and ops[0].type == X86_OP_REG and ops[1].type == X86_OP_REG \
                and ops[0].reg == ops[1].reg:
            const[ins.reg_name(ops[0].reg)] = 0
            continue
        if ins.mnemonic == 'mov' and len(ops) == 2 and ops[0].type == X86_OP_MEM and ops[0].mem.index == 0:
            dst, src = ops
            base = ins.reg_name(dst.mem.base) if dst.mem.base else ''
            if base == 'ebx':
                off = dst.mem.disp
            elif base == 'edx' and dst.mem.disp >= THIS_TO_AE:
                off = dst.mem.disp - THIS_TO_AE
            else:
                off = None
            if off is not None:
                if src.type == X86_OP_IMM:
                    st.setdefault(off, ('imm', src.imm & 0xFFFFFFFF))
                elif src.type == X86_OP_REG:
                    r = ins.reg_name(src.reg)
                    if r in const:
                        st.setdefault(off, ('imm', const[r]))
                    else:
                        st.setdefault(off, ('reg', r))
        # 上記以外で reg が書き換わる命令は追跡を打ち切る (pop / mov reg,mem など)
        if ops and ops[0].type == X86_OP_REG and ins.mnemonic not in ('cmp', 'test'):
            const.pop(ins.reg_name(ops[0].reg), None)
        if ins.mnemonic in ('pop',) and ops and ops[0].type == X86_OP_REG:
            const.pop(ins.reg_name(ops[0].reg), None)
    return st


def zero_fill_bytes(text, va):
    """ctor 内の `mov ecx, N` + `rep stosd` を探し、0 埋めされる AEffect 先頭からのバイト数 (N*4) を返す。
    `lea edi, [edx+0x20]` (AEffect 先頭) に対する埋め。 見つからなければ None。"""
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    insns = list(md.disasm(text[CTOR_RVA - va:CTOR_END - va], CTOR_RVA))
    for n, ins in enumerate(insns):
        if 'stosd' in ins.mnemonic or 'stosd' in ins.op_str:
            for back in reversed(insns[:n]):
                if back.mnemonic == 'mov' and back.op_str.startswith('ecx, '):
                    return int(back.op_str.split(', ')[1], 0) * 4
    return None


DISPATCH_RVA = 0x10001300   # guest switch (vtable slot+0x18)。 dispatcher 0x10001000 は全 opcode をここへ渡す
PROCESS_EVENTS = 25         # effProcessEvents
EDIT_GET_RECT = 13          # effEditGetRect
ROUTE_EXPECT = {'bound': 0x18, 'opcode25_default': True, 'default_returns_zero': True,
                'erect_child_loaded': True, 'erect_child_slot': 4}


def image_base(data):
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    return struct.unpack_from('<I', data, pe + 24 + 28)[0]


def file_off(data, addr):
    """VA -> ファイル上の位置。 範囲外は None。"""
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    opt = struct.unpack_from('<H', data, pe + 20)[0]
    nsec = struct.unpack_from('<H', data, pe + 6)[0]
    rva = addr - image_base(data)
    for k in range(nsec):
        o = pe + 24 + opt + 40 * k
        vs, sva, rs, rp = struct.unpack_from('<IIII', data, o + 8)
        if sva <= rva < sva + max(vs, rs):
            return rp + rva - sva
    return None


def route_facts(data, va, text):
    """effProcessEvents(25) / effEditGetRect(13) が guest 内でどこへ流れるかを静的に読む。 読めない欄は None。"""
    base = image_base(data) + va
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    f = {'bound': None, 'opcode25_default': None, 'default_returns_zero': None,
         'erect_child_loaded': None, 'erect_child_slot': None}
    entry = list(md.disasm(text[DISPATCH_RVA - base:DISPATCH_RVA - base + 0x20], DISPATCH_RVA))
    ci = next((i for i, x in enumerate(entry) if x.mnemonic == 'cmp' and x.op_str.startswith('eax, ')), None)
    if ci is None or ci + 1 >= len(entry) or entry[ci + 1].mnemonic != 'ja':
        return f
    bound = int(entry[ci].op_str.split(', ')[1], 0)
    default = int(entry[ci + 1].op_str, 0)
    f['bound'] = bound
    f['opcode25_default'] = PROCESS_EVENTS > bound
    dflt = list(md.disasm(text[default - base:default - base + 0x10], default))
    f['default_returns_zero'] = bool(dflt) and dflt[0].op_str == 'eax, esi' and \
        any(x.op_str == 'esi, esi' for x in entry)
    jm = [x for x in entry if x.mnemonic == 'jmp']
    m = re.search(r'\[eax\*4 \+ (0x[0-9a-f]+)\]', jm[0].op_str) if jm else None
    if not m:
        return f
    e = rdata_entry(data, int(m.group(1), 16) + 4 * EDIT_GET_RECT)
    if e is None:
        return f
    body = list(md.disasm(text[e - base:e - base + 0x30], e))
    idx = next((i for i, x in enumerate(body) if x.op_str == 'ecx, dword ptr [ecx + 8]'), None)
    f['erect_child_loaded'] = idx is not None
    if idx is not None:
        cm = next((x for x in body[idx:] if x.mnemonic == 'call'), None)
        sm = re.match(r'dword ptr \[eax \+ (0x[0-9a-f]+|\d+)\]$', cm.op_str) if cm else None
        f['erect_child_slot'] = int(sm.group(1), 0) if sm else None
    return f


def rdata_entry(data, addr):
    o = file_off(data, addr)
    return struct.unpack_from('<I', data, o)[0] if o is not None else None


def check_routes(f, expect):
    return ['route %s = %r, want %r' % (k, f.get(k), v) for k, v in expect.items() if f.get(k) != v]


def check(path, x32_size=0x90, magic_expect=MAGIC, ptr32=4, pin_sha=True, route_expect=None):
    """返り値: 失敗項目の list (空なら合格)。 表は stdout に出す。 pin_sha=False は値突合だけを試すネガコン用。"""
    fails = []
    data, va, text = load(path)
    import hashlib
    if pin_sha and hashlib.sha256(open(path, 'rb').read()).hexdigest() != EXPECT_SHA256:
        return ['input sha256 mismatch']
    import capstone
    if capstone.__version__ != EXPECT_CAPSTONE and not capstone.__version__.startswith(EXPECT_CAPSTONE):
        return ['capstone %s != %s' % (capstone.__version__, EXPECT_CAPSTONE)]

    L64, S64 = layout(8)
    L32, S32 = layout(ptr32)
    if S64 != 0xC0:
        fails.append('x64 sizeof %#x != 0xc0' % S64)
    for k, v in X64_EXPECT.items():
        if k == 'size':
            continue
        if L64[k][0] != v:
            fails.append('x64 %s @%#x != %#x' % (k, L64[k][0], v))
    if S32 != x32_size:
        fails.append('x32 sizeof %#x != %#x' % (S32, x32_size))

    st = engine_stores(text, va)
    if not st.pop('_lea_ok', False):
        fails.append('ctor lea ebx,[edx+0x20] not found (ctor RVA moved?)')
    print('## AEffect 構築 store 列 (engine %#x・this+0x20 = AEffect)' % (CTOR_RVA + va))
    names32 = {v[0]: k for k, v in L32.items()}
    for off in sorted(st):
        kind, val = st[off]
        name = names32.get(off, '(?)')
        shown = ('%#x' % val) if kind == 'imm' else val
        print('  AE+%#04x %-22s <- %s' % (off, name, shown))
    # 未 store の欄は ctor 冒頭の rep stosd (ecx=0x24 dword = 0x90 B) で 0 埋めされることを確認して許容する。
    # 0 埋め範囲が AEffect 全体を覆わない場合は未初期化欄があるため FAIL。
    zero_fill = zero_fill_bytes(text, va)
    if zero_fill is None or zero_fill < S32:
        fails.append('rep stosd zero-fill not found or < sizeof(AEffect) (%r)' % zero_fill)
    for name, (off, size) in L32.items():
        if off not in st and zero_fill is not None and off + size > zero_fill:
            fails.append('engine leaves %s (@%#x) uninitialized' % (name, off))
    # 値の突合 (engine の実値)
    want = {'magic': ('imm', magic_expect), 'numOutputs': ('imm', 2), 'version': ('imm', 1),
            'ioRatio': ('imm', 0x3F800000), 'uniqueID': ('imm', 0x4E6F4566), 'numInputs': ('imm', 1),
            'object': ('reg', 'edx'), 'flags': ('imm', 0),
            # 引数由来 (呼出し元が決める・即値でない)
            'numPrograms': ('reg', 'ebp'), 'numParams': ('reg', 'eax')}
    for name, exp in want.items():
        off = L32[name][0]
        got = st.get(off)
        if got != exp:
            fails.append('engine %s @%#x = %r, want %r' % (name, off, got, exp))
    # VstEvents / ERect の読取経路 (dispatcher → guest switch)。 静的に読めない欄は None として FAIL
    rf = route_facts(data, va, text)
    print('## effProcessEvents(25) / effEditGetRect(13) の経路 (guest switch %#x)' % DISPATCH_RVA)
    for k, v in rf.items():
        print('  %-20s = %r' % (k, v))
    fails += check_routes(rf, route_expect or ROUTE_EXPECT)
    print('## x32 オフセット (ptr=%d): size %#x' % (ptr32, S32))
    print('## x64 オフセット (ptr=8): size %#x' % S64)
    print('')
    print('| 欄 | x64 off/size (殻) | x32 off/size (engine) | 変換 |')
    print('|---|---|---|---|')
    for name, kind, _ in AEFFECT:
        o64, s64 = L64[name]
        o32, s32 = L32[name]
        conv = 'ポインタ: 8→4 B。 guest 空間の値として 32bit に詰め直す' if kind == 'p' else (
            'float: bit 同一 (f32)' if kind == 'f' else ('そのまま' if kind == 'i' else 'そのまま (不透明)'))
        print('| %s | %#04x / %d | %#04x / %d | %s |' % (name, o64, s64, o32, s32, conv))
    ev = events_layout(ptr32)
    ev64 = events_layout(8)
    print('')
    print('| VstEvents 欄 | x64 off/size | x32 off/size |')
    print('|---|---|---|')
    for k in ('numEvents', 'reserved', 'events[0]'):
        print('| %s | %#04x / %d | %#04x / %d |' % (k, ev64[k][0], ev64[k][1], ev[k][0], ev[k][1]))
    print('')
    print('VstEvent (ポインタを含まない・両 ABI 同一): ' + ', '.join('%s@%#x' % (k, v[0]) for k, v in VSTEVENT.items()))
    print('ERect (ポインタを含まない・両 ABI 同一): ' + ', '.join('%s@%d' % (k, v[0]) for k, v in ERECT.items()))
    return fails


def nega(path):
    """期待を壊した入力で必ず FAIL すること。 miss = 合格してしまった件数。"""
    os.makedirs(WORK, exist_ok=True)
    cases = []
    # N1: magic の即値を 1 bit 壊した複製 → 'magic' の値突合で FAIL
    d = open(path, 'rb').read()
    i = d.find(struct.pack('<I', MAGIC))
    p1 = os.path.join(WORK, 'nega_magic.bin')
    open(p1, 'wb').write(d[:i] + struct.pack('<I', MAGIC ^ 1) + d[i + 4:])
    cases.append(('N1 magic 1bit 破壊 (値突合)', p1, {'pin_sha': False}))
    # N2: x32 の sizeof 期待を 0xa0 に誤る → sizeof 突合で FAIL
    cases.append(('N2 x32 sizeof 期待を誤る', path, {'x32_size': 0xA0}))
    # N3: 期待 magic を誤る → 値突合で FAIL
    cases.append(('N3 期待 magic を誤る', path, {'magic_expect': MAGIC + 1}))
    # N4: effEditGetRect の子 vtable 参照スロットを誤る (期待 slot=5) → route 突合で FAIL
    cases.append(('N4 effEditGetRect の子 slot 期待を誤る', path,
                  {'route_expect': dict(ROUTE_EXPECT, erect_child_slot=5)}))
    # N5: effProcessEvents(25) が switch 内で処理される、と誤った期待 → route 突合で FAIL
    cases.append(('N5 opcode25 が default に落ちる、を誤った期待', path,
                  {'route_expect': dict(ROUTE_EXPECT, opcode25_default=False)}))
    miss = 0
    real = sys.stdout
    for label, p, kw in cases:
        sys.stdout = open(os.devnull, 'w')
        try:
            f = check(p, **kw)
        finally:
            sys.stdout.close()
            sys.stdout = real
        print('[nega %s] %s' % (label, 'FAIL (期待どおり)' if f else 'PASS (MISS)'))
        for x in f[:3]:
            print('    - ' + x)
        if not f:
            miss += 1
    print('nega: %d/%d miss' % (miss, len(cases)))
    return 1 if miss else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--nega', action='store_true')
    a = ap.parse_args()
    root = os.environ.get('FL_WIN64_DIR') or os.path.join(os.environ.get('RUNNER_TEMP', '/tmp'), 'fl-win64')
    path = os.path.join(root, 'extracted', 'block22434_PE.bin')
    if not os.path.exists(path):
        sys.exit('素材が無い: %s (oc_artifacts: fl-win64 が必要)' % path)
    if a.nega:
        return nega(path)
    fails = check(path)
    if fails:
        print('[marshal] FAIL')
        for x in fails:
            print('  - ' + x)
        return 1
    print('[marshal] OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
