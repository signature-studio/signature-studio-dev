#!/usr/bin/env python3
"""#1305 (PLG-F3-7): waiver の各 root (関数) から、例外を送出する関数へ直接 call/jmp で届くかを root ごとに判定する。

  送出関数 (raise 関数) = 次のどちらかを含む関数:
    (i)  `call [rip+slot]` で slot が `kernel32!RaiseException` 等 (RAISE_NAMES) の IAT thunk を指すもの
         (slot の store 先 `mov [slot], rax` の rax が `lea rax,[rip+X]` で thunk X を指すものを PE 全体から集める)
    (ii) IAT の RaiseException 系を直接 call/jmp するもの (raise_reach_frontier.py と同じ判定)
  辺: 直接 call/jmp (rel32) のみ。間接 call は辺にしない (indirect_resolve.py で別に解決する)。
  出力: root ごとに (届くか / 最短経路 / 届く raise 関数 / 到達した関数数)。

使い方: python3 tools/plugins/f2/raise_root_reach.py <block>
"""
import json, os, sys, struct, bisect, argparse
from collections import deque
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import FL_WIN64_DIR
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_RIP

RAISE_NAMES = ('RaiseException', 'RtlRaiseException', 'CxxThrowException', 'RaiseFloatException')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('block', type=int)
    a = ap.parse_args()
    pe = pefile.PE(os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % a.block), fast_load=True)
    pe.parse_data_directories()
    base = pe.OPTIONAL_HEADER.ImageBase
    iat = {}
    for d in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
        for i in d.imports:
            if i.address:
                iat[i.address] = (d.dll.decode(errors='replace'), (i.name or b'?').decode(errors='replace'))
    pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0].get_data()
    funcs = {}
    for i in range(len(pd) // 12):
        b, e, u = struct.unpack_from('<III', pd, 12 * i)
        if b and not (u & 1):
            funcs[base + b] = base + e
    starts = sorted(funcs)

    def func_of(va):
        k = bisect.bisect_right(starts, va) - 1
        if k >= 0 and starts[k] <= va < funcs[starts[k]]:
            return starts[k]
        return None

    def thunk_name(va):
        b = pe.get_data(va - base, 6)
        if b[:2] != b'\xff\x25':
            return None
        return iat.get(va + 6 + struct.unpack('<i', b[2:6])[0])

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    disasm = {}
    for fs in starts:
        disasm[fs] = list(md.disasm(pe.get_data(fs - base, funcs[fs] - fs), fs))

    # (i) slot への store を PE 全体から集め、格納値が raise thunk のものを raise slot とする
    slot_val = {}
    for fs in starts:
        ins_l = disasm[fs]
        for ins in ins_l:
            if ins.mnemonic != 'mov' or len(ins.operands) != 2:
                continue
            d, s = ins.operands
            if d.type != X86_OP_MEM or d.mem.base != X86_REG_RIP or s.type != X86_OP_REG:
                continue
            slot = ins.address + ins.size + d.mem.disp
            # 同関数内で s.reg を直前に lea rax,[rip+X] で作ったものを探す
            for prev in reversed(ins_l[:ins_l.index(ins)]):
                if prev.mnemonic == 'lea' and len(prev.operands) == 2 and prev.operands[0].type == X86_OP_REG \
                        and prev.operands[0].reg == s.reg and prev.operands[1].type == X86_OP_MEM \
                        and prev.operands[1].mem.base == X86_REG_RIP:
                    tgt = prev.address + prev.size + prev.operands[1].mem.disp
                    slot_val.setdefault(slot, []).append((hex(ins.address), hex(tgt)))
                    break
                if prev.operands and prev.operands[0].type == X86_OP_REG and prev.operands[0].reg == s.reg:
                    break
    raise_slots = set()
    raise_slot_names = {}
    for slot, lst in slot_val.items():
        for store_va, tgt in lst:
            th = thunk_name(int(tgt, 16))
            if th and any(k in th[1] for k in RAISE_NAMES):
                raise_slots.add(slot)
                raise_slot_names.setdefault(hex(slot), []).append([store_va, '%s!%s' % th])

    # raise 関数: (i) raise slot への間接 call を持つ / (ii) IAT raise を直接参照する
    raise_fn = {}
    for fs in starts:
        for ins in disasm[fs]:
            if ins.mnemonic not in ('call', 'jmp') or not ins.operands:
                continue
            o = ins.operands[0]
            if o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP:
                t = ins.address + ins.size + o.mem.disp
                if t in iat and any(k in iat[t][1] for k in RAISE_NAMES):
                    raise_fn.setdefault(fs, []).append(['iat', hex(ins.address), '%s!%s' % iat[t]])
                elif t in raise_slots:
                    raise_fn.setdefault(fs, []).append(['slot', hex(ins.address), hex(t)])

    # 各 root から直接 call/jmp の BFS。raise 関数に届くかを判定
    wv = json.load(open(os.path.join(HERE, 'icall_gate_waivers.json')))
    roots = sorted({int(w['function'], 16) for w in wv if int(w['block']) == a.block})
    out = {'block': a.block, 'raise_slots': {k: v for k, v in raise_slot_names.items()}, 'raise_functions': {hex(k): v for k, v in raise_fn.items()}, 'roots': {}}
    for r in roots:
        par = {r: None}
        q = deque([r])
        hit = None
        while q:
            f = q.popleft()
            if f in raise_fn and hit is None:
                hit = f
            for ins in disasm.get(f, []):
                if ins.mnemonic in ('call', 'jmp') and ins.operands and ins.operands[0].type == X86_OP_IMM:
                    g = func_of(ins.operands[0].imm)
                    if g is not None and g != f and g not in par:
                        par[g] = (f, hex(ins.address))
                        q.append(g)
        path = None
        if hit is not None:
            path = []
            c = hit
            while c is not None:
                p = par[c]
                path.append([hex(c), p[1] if p else None])
                c = p[0] if p else None
            path.reverse()
        out['roots'][hex(r)] = {'reached_funcs': len(par), 'reaches_raise': hit is not None,
                                'raise_func': hex(hit) if hit is not None else None,
                                'path': path, 'raise_detail': raise_fn.get(hit) if hit is not None else None}
    os.makedirs(os.path.join(HERE, '..', 'work', 'f2'), exist_ok=True)
    json.dump(out, open(os.path.join(HERE, '..', 'work', 'f2', 'raise_root_reach_%d.json' % a.block), 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
