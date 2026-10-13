#!/usr/bin/env python3
"""PLG-G1 (#206) synth-simple + drum-synth 13 本 (Delphi 殻 12 block)の lift 前提を実測する (lift 自体は lift/batch_lift.sh)。

  1. DSP 閉包の規模 (work/closure/block*.json; lift/plugin_closure.py の出力)
  2. 閉包 (= plugin 固有関数) が発行する Dispatcher ID / host vtable slot (inventory/host_calls.py の scan を再利用)
  3. 閉包が呼ぶ SIMD kernel 表の変数・実装 (p0c/kernel_matrix.py の scan_dll を再利用; framework 非所属関数のみ走査)
  4. 付随する C++ DLL (engine 6 本 + MiniSynth 単体) の外形 (work/g1/cpp_facts.json)
出力: work/g1/facts.json と stdout の Markdown 表。
usage: closure_facts.py
"""
import os, sys, json, collections, struct

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, '..')
sys.path.insert(0, os.path.join(P, 'inventory'))
sys.path.insert(0, os.path.join(P, 'p0c'))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import FL_WIN64_DIR  # noqa: E402
import pefile  # noqa: E402
import host_calls  # noqa: E402
import kernel_matrix as KM  # noqa: E402
from common import PLUGINS, engines  # noqa: E402

EXT = os.path.join(FL_WIN64_DIR, 'extracted')
WORK = os.path.join(P, 'work')
OUTD = os.path.join(WORK, 'g1')

def closure_info(block):
    c = json.load(open(os.path.join(WORK, 'closure', 'block%05d.json' % block)))
    rs = []
    for r in c['ranges']:
        a, b = r.split('-')
        rs.append((int(a, 16), int(b, 16)))
    return c, rs


def host_facts(block, ranges):
    fn = 'block%05d_PE.bin' % block
    _, res = host_calls.scan(fn)
    pe = pefile.PE(os.path.join(EXT, fn), fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase

    def inside(rva):
        va = base + rva
        return any(a <= va < b for a, b in ranges)
    ids = collections.Counter()
    slots = collections.Counter()
    for rva, disp, ident in res:
        if not inside(rva):
            continue
        slots[disp] += 1
        if disp == 0:
            ids['dyn' if ident is None else ident] += 1
    hs = json.load(open(os.path.join(P, 'framework', 'hostshim', 'hs_ids.json')))['ids']
    imm = {k: v for k, v in ids.items() if k != 'dyn'}
    uncovered = {str(k): v for k, v in sorted(imm.items()) if str(k) not in hs}
    return {'ids': {str(k): v for k, v in sorted(ids.items(), key=lambda x: -x[1])},
            'slot_disps': {hex(k): v for k, v in sorted(slots.items())},
            'sites': sum(slots.values()), 'disp0_sites': sum(ids.values()),
            'imm_id_sites': sum(imm.values()), 'dyn_id_sites': ids.get('dyn', 0),
            'ids_not_in_hs_ids': uncovered}


def kernel_facts(block, ranges):
    _, r = KM.scan_dll(block)
    if not r.get('init_found'):
        return {'init_found': False}
    kmap = r.get('kernel_va_map', {})
    inv = {v: k for k, v in kmap.items() if v}
    used = collections.Counter()
    for dva, c in r.get('kernels_used', {}).items():
        used[inv.get(dva, dva)] += c
    cs = r.get('callsites', [])
    fr = {int(x, 16) for x in json.load(open(os.path.join(WORK, 'closure', 'block%05d.json' % block)))['frontier']}
    in_clo, in_fr = [], []
    for s in cs:
        fva = int(s['func'], 16)
        if any(a <= fva < b for a, b in ranges):
            in_clo.append(s)
        elif fva in fr:
            in_fr.append(s)
    norm = lambda s: inv.get(s['kernel'], s['kernel'])
    return {'init_found': True, 'callsites_dll_unique_scan': len(cs),
            'callsites_in_closure': len(in_clo), 'callsites_in_frontier': len(in_fr),
            'kernels_in_closure': dict(sorted(collections.Counter(norm(s) for s in in_clo).items())),
            'kernels_in_dll_scan': dict(sorted(used.items())), 'n_kernels_dll_scan': len(used),
            'ret_used_in_closure': sum(1 for s in in_clo if s.get('ret_used'))}


def engine_facts(block):
    fn = 'block%05d_PE.bin' % block
    pe = pefile.PE(os.path.join(EXT, fn))
    exp = []
    if hasattr(pe, 'DIRECTORY_ENTRY_EXPORT'):
        exp = [(e.name.decode() if e.name else '#%d' % e.ordinal) for e in pe.DIRECTORY_ENTRY_EXPORT.symbols]
    imp = collections.OrderedDict()
    if hasattr(pe, 'DIRECTORY_ENTRY_IMPORT'):
        for d in pe.DIRECTORY_ENTRY_IMPORT:
            imp[d.dll.decode()] = len(d.imports)
    pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
    pdata = pd.get_data()[:pd.Misc_VirtualSize]
    nf = nb = 0
    for i in range(len(pdata) // 12):
        b, e, u = struct.unpack_from('<III', pdata, 12 * i)
        if b and not (u & 1):
            nf += 1
            nb += e - b
    text = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
    return {'size': os.path.getsize(os.path.join(EXT, fn)), 'text_bytes': text.Misc_VirtualSize,
            'pdata_funcs': nf, 'pdata_bytes': nb, 'exports': exp[:20], 'n_exports': len(exp), 'imports': imp}


def main():
    os.makedirs(OUTD, exist_ok=True)
    out, cache = {}, {}
    for name, blk, _ in PLUGINS:
        if blk is None:
            continue
        if blk not in cache:      # Wasp / Wasp XT は同一 block (同一 PE)
            c, rs = closure_info(blk)
            f = {'block': blk, 'closure_funcs': c['unique_funcs'], 'closure_bytes': c['unique_bytes'],
                 'frontier_funcs': c['framework_frontier_funcs'], 'frontier_bytes': c['framework_frontier_bytes'],
                 'vcall': c['indirect_vcall'], 'ptr_or_vt0': c['indirect_ptr_or_vt0'], 'iat_calls': c['iat_calls'],
                 'entries': c['entries']}
            f['host'] = host_facts(blk, rs)
            f['kernel'] = kernel_facts(blk, rs)
            cache[blk] = f
        out[name] = cache[blk]
        print('done', name, file=sys.stderr)
    json.dump(out, open(os.path.join(OUTD, 'facts.json'), 'w'), indent=1, ensure_ascii=False)
    cpp = {str(b): engine_facts(b) for b in engines()}
    json.dump(cpp, open(os.path.join(OUTD, 'cpp_facts.json'), 'w'), indent=1, ensure_ascii=False)
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == '__main__':
    main()
