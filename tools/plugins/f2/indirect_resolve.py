#!/usr/bin/env python3
"""#1305 (PLG-F3-7): waiver 4 site の閉包 (raise_reach_frontier の W 起点 BFS) に現れる間接 call 23 件の呼出し先を解決する。

解決の段階:
  (A) `call [rip+slot]`: slot の 8 byte を PE ファイルから読む。IAT なら import 名、.pdata 関数なら関数 VA、
      0 なら「ファイル上は未初期化 (実行時に格納される)」として未解決と数える。
  (B) `call [reg+disp]` / `call reg` / `call [rcx]` 等: 呼出し元関数内で、そのレジスタへの直前の代入を
      逆向きに 1 段だけ追う (`mov reg, [rip+slot]` / `lea reg, [rip+X]` / `mov reg, imm` / `mov reg, [reg2+disp]`)。
      追えないものは「解決不能 (理由付き)」として数える。
  判定: 解決先が trap 命令 (div/idiv/int/ud2) または例外 API (RaiseException 系) を含むかを
      raise_reach_frontier と同じ規則で BFS して見る。

出力: work/f2/indirect_resolve_<block>.json と標準出力。
使い方: python3 tools/plugins/f2/indirect_resolve.py <block>
"""
import json, os, sys, struct, bisect, argparse
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import FL_WIN64_DIR
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_RIP

W = os.path.join(HERE, '..', 'work')
RAISE_NAMES = ('RaiseException', 'RtlRaiseException', 'CxxThrowException', '_RaiseExcept', 'RaiseFloatException')
TRAP = ('div', 'idiv', 'int', 'int3', 'ud2', 'into')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('block', type=int)
    a = ap.parse_args()
    block = a.block
    pe = pefile.PE(os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % block), fast_load=True)
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

    def read_q(va):
        b = pe.get_data(va - base, 8)
        return struct.unpack('<Q', b)[0] if b and len(b) == 8 else None

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True

    wv = json.load(open(os.path.join(HERE, 'icall_gate_waivers.json')))
    roots = sorted({int(w['function'], 16) for w in wv if int(w['block']) == block})
    # raise_reach_frontier と同じ BFS (同じ辺・同じ境界) で、関数ごとの間接 call を集める
    seen = set(roots)
    queue = list(roots)
    parent = {r: None for r in roots}
    order = []
    sites = []   # (func, ins)
    direct_unres = set()
    while queue:
        f = queue.pop()
        order.append(f)
        end = funcs.get(f)
        if end is None:
            continue
        code = pe.get_data(f - base, end - f)
        insns = list(md.disasm(code, f))
        for idx, ins in enumerate(insns):
            if ins.mnemonic not in ('call', 'jmp') or not ins.operands:
                continue
            o = ins.operands[0]
            if o.type == X86_OP_IMM:
                t = o.imm
                if func_of(t) is None:
                    if not (t in iat or (pe.get_data(t - base, 2) or b'')[:2] == b'\xff\x25'):
                        direct_unres.add(t)
                elif t != f:
                    g = func_of(t)
                    if g not in seen:
                        seen.add(g)
                        parent[g] = f
                        queue.append(g)
            elif o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP:
                tgt = ins.address + ins.size + o.mem.disp
                if tgt not in iat:
                    sites.append((f, insns, idx))
            else:
                sites.append((f, insns, idx))

    def back_def(insns, idx, reg_name):
        # 直前の代入を逆向きに 1 段だけ追う
        for j in range(idx - 1, max(-1, idx - 40), -1):
            p = insns[j]
            if p.mnemonic in ('call', 'ret', 'jmp') and j != idx:
                return ('barrier', hex(p.address), p.mnemonic)
            if p.mnemonic in ('mov', 'lea', 'movabs') and len(p.operands) == 2:
                d = p.operands[0]
                if d.type == X86_OP_REG and md.reg_name(d.reg) == reg_name:
                    s = p.operands[1]
                    if s.type == X86_OP_IMM:
                        return ('imm', hex(s.imm), hex(p.address))
                    if s.type == X86_OP_MEM and s.mem.base == X86_REG_RIP:
                        slot = p.address + p.size + s.mem.disp
                        return ('rip_mem' if p.mnemonic == 'mov' else 'rip_lea', hex(slot), hex(p.address))
                    if s.type == X86_OP_MEM:
                        return ('mem', md.reg_name(s.mem.base) if s.mem.base else '-', s.mem.disp, hex(p.address), p.mnemonic)
                    return ('other', p.op_str, hex(p.address))
            # 同じレジスタを書く別命令 (add/sub/xor 等) は解決不能として止める
            if p.operands and p.operands[0].type == X86_OP_REG and md.reg_name(p.operands[0].reg) == reg_name:
                return ('clobber', p.mnemonic, hex(p.address))
        return ('none', '', '')

    # (A') slot が .bss 等でファイル上 0 の場合は、PE 全体の .text から slot への store (mov [slot], X) を集める
    need = set()
    for f, insns, idx in sites:
        o = insns[idx].operands[0]
        if o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP:
            slot = insns[idx].address + insns[idx].size + o.mem.disp
            if iat.get(slot) is None:
                need.add(slot)
        elif o.type == X86_OP_REG:
            d = back_def(insns, idx, md.reg_name(o.reg))
            if d[0] == 'rip_mem' and iat.get(int(d[1], 16)) is None:
                need.add(int(d[1], 16))
    # 線形スイープは data 混在で途中停止するため、.pdata の関数単位で逆アセンブルする
    stores = {s: [] for s in need}
    loads = {s: [] for s in need}
    for fs in starts:
        fins = list(md.disasm(pe.get_data(fs - base, funcs[fs] - fs), fs))
        for k, ins in enumerate(fins):
            for o in ins.operands:
                if o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP:
                    t = ins.address + ins.size + o.mem.disp
                    if t in need:
                        if ins.mnemonic == 'mov' and ins.operands[0].type == X86_OP_MEM:
                            src = ins.operands[1]
                            if src.type == X86_OP_IMM:
                                tag = ('imm', hex(src.imm))
                                dfn = None
                            elif src.type == X86_OP_REG:
                                tag = ('reg', md.reg_name(src.reg))
                                dfn = back_def(fins, k, md.reg_name(src.reg))
                            else:
                                tag = ('mem', ins.op_str)
                                dfn = None
                            stores[t].append([hex(ins.address), tag, dfn])
                        else:
                            loads[t].append(hex(ins.address))
    # store 元が lea/mov の rip 参照なら関数 VA まで解く
    def store_value(dfn):
        if not dfn:
            return None
        if dfn[0] == 'rip_lea':
            return int(dfn[1], 16)
        return None

    # 格納値が IAT thunk (`jmp [rip+slot]` で RaiseException 等) を指す slot を raise 候補として記録する
    def thunk_name(va):
        b = pe.get_data(va - base, 6) if va - base >= 0 else b''
        if b[:2] != b'\xff\x25':
            return None
        return iat.get(va + 6 + struct.unpack('<i', b[2:6])[0])

    raise_slots = {}
    for s_, lst in stores.items():
        for st_ in lst:
            if st_[2] and st_[2][0] == 'rip_lea':
                th = thunk_name(int(st_[2][1], 16))
                if th and any(k in th[1] for k in RAISE_NAMES):
                    raise_slots.setdefault(s_, []).append([st_[0], '%s!%s' % th])

    # slot の番地が .data/.rdata の qword として現れる箇所 (間接書込みの足がかり候補)
    data_ptr = {s_: [] for s_ in need}
    for sec in pe.sections:
        if sec.Name.rstrip(b'\0') in (b'.data', b'.rdata'):
            d_ = sec.get_data()
            sva = base + sec.VirtualAddress
            for k in range(0, len(d_) - 7, 8):
                v_ = struct.unpack_from('<Q', d_, k)[0]
                if v_ in data_ptr:
                    data_ptr[v_].append(hex(sva + k))

    def resolve_slot(row, slot):
        v = read_q(slot)
        row['slot'] = hex(slot)
        row['slot_value_in_file'] = hex(v) if v is not None else None
        st = stores.get(slot, [])
        row['stores'] = st
        vals = set()
        for s_ in st:
            if s_[1][0] == 'imm':
                vals.add(s_[1][1])
            elif s_[2] and s_[2][0] == 'rip_lea':
                vals.add(hex(int(s_[2][1], 16)))
        if v is not None and v != 0 and v in iat:
            row['resolved'] = 'import %s!%s' % iat[v]
        elif v is not None and v != 0 and func_of(v) is not None:
            row['resolved'] = 'function %s' % hex(v)
        elif st:
            row['resolved'] = 'runtime store x%d; values %s' % (len(st), sorted(vals) or 'not literal')
        else:
            row['resolved'] = 'no store found'
            row['data_ptr_to_slot'] = data_ptr.get(slot, [])

    rows = []
    for f, insns, idx in sites:
        ins = insns[idx]
        o = ins.operands[0]
        row = {'func': hex(f), 'site': hex(ins.address), 'asm': '%s %s' % (ins.mnemonic, ins.op_str)}
        if o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP:
            resolve_slot(row, ins.address + ins.size + o.mem.disp)
        elif o.type == X86_OP_REG:
            row['def'] = back_def(insns, idx, md.reg_name(o.reg))
            if row['def'][0] == 'rip_mem':
                row['via_reg_slot'] = row['def'][1]
                resolve_slot(row, int(row['def'][1], 16))
        elif o.type == X86_OP_MEM:
            reg = md.reg_name(o.mem.base) if o.mem.base else None
            row['def'] = back_def(insns, idx, reg) if reg else ('abs', hex(o.mem.disp))
            row['disp'] = o.mem.disp
        if row.get('slot') and int(row['slot'], 16) in raise_slots:
            row['raise_store'] = raise_slots[int(row['slot'], 16)]
        rows.append(row)

    def path_of(f):
        p = []
        while f is not None:
            p.append(hex(f))
            f = parent.get(f)
        return list(reversed(p))

    raise_reach = []
    for r in rows:
        if r.get('raise_store'):
            raise_reach.append({'site': r['site'], 'func': r['func'], 'api': r['raise_store'][0][1],
                                'path_from_root': path_of(int(r['func'], 16))})
    cls = {'raise_via_slot': 0, 'resolved_in_file': 0, 'resolved_runtime_store': 0,
           'slot_no_store': 0, 'object_or_register_based': 0}
    for r in rows:
        if r.get('raise_store'):
            cls['raise_via_slot'] += 1
        elif r.get('slot'):
            res_ = r.get('resolved', '')
            if res_.startswith('import') or res_.startswith('function'):
                cls['resolved_in_file'] += 1
            elif res_.startswith('runtime store'):
                cls['resolved_runtime_store'] += 1
            else:
                cls['slot_no_store'] += 1
        else:
            cls['object_or_register_based'] += 1

    res = {'block': block, 'roots': [hex(r) for r in roots], 'visited_funcs': len(order),
           'indirect_sites': len(rows), 'unresolved_direct_targets': sorted(hex(x) for x in direct_unres),
           'raise_slots': {hex(k): v for k, v in raise_slots.items()},
           'classification': cls, 'raise_reach': raise_reach,
           'rows': rows}
    os.makedirs(os.path.join(W, 'f2'), exist_ok=True)
    json.dump(res, open(os.path.join(W, 'f2', 'indirect_resolve_%d.json' % block), 'w'), ensure_ascii=False, indent=1)
    print('block %d: visited=%d indirect_sites=%d' % (block, len(order), len(rows)))
    for r in rows:
        print(json.dumps(r, ensure_ascii=False))


if __name__ == '__main__':
    main()
