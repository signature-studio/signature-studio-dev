#!/usr/bin/env python3
"""Carve EQ (ksge) closure の IAT 呼出 site を実測する (KH-18 / #781)。

入力: work/callgraph.pkl (callgraph.py), work/closures_sets.pkl (closures.py), work/rtti_vtables.json (rtti_walk.py),
      HeartCore.core_64 (PE)。closure = closures_sets の sets['graphiceq'] (infra 除外後の到達集合)。
出力: stdout に IAT site の表 (関数 VA / 呼出 VA / import 名 / 直前の引数準備 / 直後の戻り値利用 / 到達 root 数)、
      work/carve_iat_sites.json に同内容。

usage: carve_iat_census.py HeartCore.core_64 work/callgraph.pkl work/closures_sets.pkl work/rtti_vtables.json [out.json]
"""
import sys, json, pickle, re, collections
import pefile
import capstone
from capstone import CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_REG_RIP

NS = 'graphiceq'
PROCESS_ROOT = 0x37d210  # GraphicEqDsp の vtable slot 14 (Gain の process 0x1804b0380 と同 slot。RVA は base 相対)


def call_path(root, tgt, res):
    prev = {root: None}
    q = collections.deque([root])
    while q:
        f = q.popleft()
        if f == tgt:
            break
        for n in res[f]['calls'] + res[f]['jmps']:
            if n in res and n not in prev:
                prev[n] = f
                q.append(n)
    if tgt not in prev:
        return None
    p, c = [], tgt
    while c is not None:
        p.append(f'{c:#x}')
        c = prev[c]
    return list(reversed(p))


def import_map(pe, base):
    m = {}
    for ent in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
        dll = ent.dll.decode(errors='replace')
        for i, imp in enumerate(ent.imports):
            name = imp.name.decode(errors='replace') if imp.name else f'ord{imp.ordinal}'
            m[base + ent.struct.FirstThunk + i * 8] = f'{dll}!{name}'
    return m


def fmt(ins):
    return f'{ins.address:x}: {ins.mnemonic} {ins.op_str}'


def main(core, cgp, setp, vtp, out):
    pe = pefile.PE(core, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(core, 'rb').read()
    imps = import_map(pe, base)
    cg = pickle.load(open(cgp, 'rb'))
    res = cg['res']
    funcs = pickle.load(open(setp, 'rb'))['sets'][NS]
    fset = set(funcs)
    md = capstone.Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True

    def reach(rs):
        seen, st = set(), list(rs)
        while st:
            f = st.pop()
            if f in seen or f not in res:
                continue
            seen.add(f)
            st.extend(res[f]['calls'])
            st.extend(res[f]['jmps'])
        return seen

    # vtable JSON から GraphicEqDsp の slot 7・13・14 を引き、固定 VA (PROCESS_ROOT 等) と照合する
    vt = json.load(open(vtp))
    gslots = [int(s, 16) - base for s in vt['.?AVGraphicEqDsp@graphiceq@@'][0]['slots']]
    if gslots[14] != PROCESS_ROOT:
        sys.exit(f'PROCESS_ROOT mismatch: vtable slot14={gslots[14]:#x} != {PROCESS_ROOT:#x}')
    print(f'vtable check ok: GraphicEqDsp slot7={gslots[7]:#x} slot13={gslots[13]:#x} slot14={gslots[14]:#x}')
    proc_all = reach([gslots[14]])

    # 関数ごとに [rip+disp] call/jmp を集める (closure 本体と process 直接 closure の infra 側)
    def scan(fs):
        found = []
        for f in sorted(fs):
            size = res[f]['size']
            off = pe.get_offset_from_rva(f)
            code = data[off:off + size]
            ins = list(md.disasm(code, base + f))
            for k, i in enumerate(ins):
                if i.mnemonic not in ('call', 'jmp'):
                    continue
                if '[rip' not in i.op_str:
                    continue
                tgt_slot = i.address + i.size + i.disp
                name = imps.get(tgt_slot)
                if name is None:
                    continue
                before = [fmt(x) for x in ins[max(0, k - 6):k]]
                after = [fmt(x) for x in ins[k + 1:k + 4]]
                found.append(dict(func=f'{f:#x}', site=f'{i.address:#x}', kind=i.mnemonic, slot=f'{tgt_slot:#x}',
                                  import_name=name, before=before, after=after))
        return found

    sites = scan(funcs)
    proc_iat = scan(proc_all - fset)

    # 各 site の関数が到達する root (vtable slot) の数と class 名
    roots = collections.defaultdict(list)
    for k, lst in vt.items():
        rest = k[4:]
        rest = rest[:-2] if rest.endswith('@@') else rest
        if '?' in rest or '$' in rest:
            continue
        parts = [p for p in rest.split('@') if p]
        if len(parts) != 2 or parts[-1] != NS:
            continue
        if not re.search(r'(MasterDsp|Dsp|DspModel)$', parts[0]):
            continue
        for v in lst:
            for s in v['slots']:
                roots[parts[0]].append(int(s, 16) - base)

    reach_by_root = {}
    for cls, rs in roots.items():
        for r in set(rs):
            reach_by_root[(cls, r)] = reach([r]) & fset
    proc = proc_all & fset
    for s in sites:
        f = int(s['func'], 16)
        hit = sorted({f'{c}@{r:#x}' for (c, r), st in reach_by_root.items() if f in st})
        s['reached_by_roots'] = len(hit)
        s['root_examples'] = hit[:3]
        s['path'] = call_path(int(hit[0].split('@')[1], 16), f, res) if hit else None

    summary = collections.Counter(s['import_name'] for s in sites)
    print(f'closure funcs={len(funcs)} IAT call sites={len(sites)}')
    print(f'process root {PROCESS_ROOT:#x}: direct closure {len(proc_all)} funcs (unique 集合内 {len(proc)}), '
          f'IAT sites in unique = {sum(1 for s in sites if int(s["func"], 16) in proc)}, '
          f'IAT sites in infra side ({len(proc_all - fset)} funcs) = {len(proc_iat)}')
    for name, n in summary.most_common():
        print(f'  {n:2d}  {name}')
    for n, s in enumerate(sites, 1):
        print(f"[{n:02d}] func {s['func']} site {s['site']} {s['kind']} -> {s['import_name']} (slot {s['slot']}) roots={s['root_examples']}")
        if s['path']:
            print(f"      path {' -> '.join(s['path'])}")
        for b in s['before']:
            print(f'      < {b}')
        print(f"      > {' | '.join(s['after'])}")
    json.dump(dict(closure_funcs=len(funcs), sites=sites, process_iat_infra=proc_iat), open(out, 'w'), indent=1, ensure_ascii=False)


if __name__ == '__main__':
    a = sys.argv[1:]
    main(a[0], a[1], a[2], a[3], a[4] if len(a) > 4 else 'work/carve_iat_sites.json')
