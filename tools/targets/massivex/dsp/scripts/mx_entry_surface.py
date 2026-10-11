#!/usr/bin/env python3
"""VST3 エントリ面 (export + MassiveX*/Steinberg::Vst vtable slot) の一覧と
x64c probe 用 entries.json を出す (MX-3 要件 1/3)。

- seeds = exports + RTTI vtable slot のうち .pdata begin であるもの
- 1-round closure = seeds の直接 call/jmp 先 (thunk 領域外) — 過小評価の下限
- 出力: <out>.json (サマリ), <out>_entries_x64c.json (x64c --entries 用 roots)

usage: mx_entry_surface.py <pe> <rtti_vtables.json> <out>
"""
import sys, json, re, struct, bisect, collections
import pefile, capstone

THUNK_LO, THUNK_HI = 0x396e000, 0x3970200
EXPORTS = {'GetPluginFactory': 0xa870, 'InitDll': 0xa850, 'ExitDll': 0xa860,
           'factoriesListGetter': 0x1188680}
FAMILY_EXACT = {
    'SingleComponentEffect', 'ComponentBase', 'EditControllerEx1', 'EditController',
    'IPluginBase', 'FObject', 'FUnknown', 'IDependent', 'Unit', 'ProgramList', 'Parameter',
    'Bus', 'AudioBus', 'EventBus', 'BusList', 'IPlugView', 'CPluginView', 'IConnectionPoint',
    'IAudioProcessor', 'IComponent', 'IEditController', 'IEditController2', 'IUnitInfo',
    'IAutomationState', 'IMidiMapping', 'IInfoListener', 'IProcessContextRequirements',
    'IParameterFinder',
}


def main(path, vtp, outp):
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(path, 'rb').read()
    t = [s for s in pe.sections if s.Characteristics & 0x20000000][0]
    pds = sorted([s for s in pe.sections if s.Name.rstrip(b'\0').decode() == '.pdata'],
                 key=lambda s: -s.Misc_VirtualSize)
    t_lo, t_hi = t.VirtualAddress, t.VirtualAddress + t.Misc_VirtualSize
    t_raw = t.PointerToRawData

    def off(r):
        return t_raw + (r - t_lo)

    raw = data[pds[0].PointerToRawData: pds[0].PointerToRawData + pds[0].Misc_VirtualSize]
    fsz = {}
    for i in range(0, len(raw) - 11, 12):
        st, e, _u = struct.unpack_from('<III', raw, i)
        if e > st and st and 0x1000 <= st < t_hi and e <= t_hi:
            fsz[st] = e - st
    begins = sorted(fsz)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    vt = json.load(open(vtp))
    fam = collections.defaultdict(set)
    slot_cls = {}
    for name, lst in vt.items():
        m = re.match(r'^\.\?(AV|AU)(.+?)@@(.*)$', name)
        if not m:
            continue
        short = [x for x in m.group(2).split('@') if x][-1]
        if short in FAMILY_EXACT or short.startswith('MassiveX') or short.startswith('MX'):
            for v in lst:
                for s in v['slots']:
                    r = int(s, 16) - base
                    if r in fsz:
                        fam[short].add(r)
                        slot_cls[r] = (short, v['vtable'])
    seeds = set(EXPORTS.values()) | set(x for v in fam.values() for x in v)

    one = set()
    for e in sorted(seeds):
        sz = fsz.get(e)
        if sz is None:
            continue
        try:
            for a, iz, mn, ops in md.disasm_lite(data[off(e):off(e) + sz], base + e):
                if mn in ('call', 'jmp') and ops.startswith('0x'):
                    tg = int(ops, 16) - base
                    if THUNK_LO <= tg < THUNK_HI:
                        continue
                    if t_lo <= tg < t_hi:
                        one.add(tg)
        except capstone.CsError:
            pass
    one |= seeds

    out = {'base': hex(base), 'pdata_funcs': len(fsz), 'pdata_bytes': sum(fsz.values()),
           'exports': {k: hex(base + v) for k, v in EXPORTS.items()},
           'family_classes': {k: len(v) for k, v in sorted(fam.items())},
           'family_slots_total': sum(len(v) for v in fam.values()),
           'seeds': len(seeds),
           'one_round_closure': len(one),
           'one_round_pdata': sum(1 for x in one if x in fsz),
           'one_round_bytes_pdata': sum(fsz[x] for x in one if x in fsz),
           'pct_of_pdata': round(100.0 * sum(1 for x in one if x in fsz) / len(fsz), 2)}
    json.dump(out, open(outp + '.json', 'w'), indent=1)
    json.dump({'roots': [hex(base + x) for x in sorted(seeds)]},
              open(outp + '_seeds_x64c.json', 'w'), indent=1)
    json.dump({'roots': [hex(base + x) for x in sorted(one)]},
              open(outp + '_one_x64c.json', 'w'), indent=1)
    json.dump({'cls_short': sorted(set(c for c, _ in slot_cls.values()))},
              open(outp + '_classes.json', 'w'), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3])
