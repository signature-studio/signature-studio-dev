#!/usr/bin/env python3
"""Massive X.vst3 — VST3 エントリ起点 closure (再帰降下・ closure 内だけを解析)。

algo (規則 37 の独立再計算は mx_recount.py で別アルゴリズム):
  入口 = 直接 call/jmp の rel32 先。関数 = 入口のうち「自分より前の入口」以降、
       次の入口までの区間 (ただし自分の呼出しで伸びることはない = 過小評価の下限)。
  1. seeds = exports (GetPluginFactory/InitDll/ExitDll/factoriesListGetter)
              + MassiveX* / Steinberg::Vst* クラスの vtable slot (pdata begin であるもの)
  2. frontier を disasm し、call/jmp rel32 先で .text 内かつ thunk 領域外のものを新入口に追加
  3. 2 を繰り返す (入口が増えなくなるまで)
  4. 入口集合 = closure。サイズ = 入口数 / 担当バイト数 (正確な end は .pdata のものを優先)

thunk 領域 = RVA 0x396e000-0x3970200 (jmp [rip+IAT] スタブ列。capstone は
  `call qword ptr [rip+X]` を括弧付きで印字するので startswith('0x') では拾わない。
  ここは明示除外)。

MODE (第 4 引数・既定 linear):
  linear = 旧方式。入口から次の入口まで線形に disasm (jump table・文字列窓も code 扱い)。
  flow   = code/data 区別つき再帰降下 (MX-13)。入口から制御フローで到達する命令だけを code とする。
           fall-through・直接 jmp/jcc (関数内は追う)・直接 call (callee)・tail jmp。間接 jmp
           (jump table) の先は追わず、テーブル窓は decode しない (未解決件数 indirect_unres)。

usage: mx_closure.py <pe> <rtti_vtables.json> <out_prefix> [linear|flow]
"""
import sys, json, pickle, bisect, re, collections, struct
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
MAXFN = 0x8000


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

    # ---- seeds
    seeds = set(EXPORTS.values())
    vt = json.load(open(vtp))
    fam = collections.defaultdict(set)
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
    for v in fam.values():
        seeds |= v

    def flow(e, fb):
        work, ins, cs = [e], set(), set()
        nb = ni = un = 0
        while work:
            a = work.pop()
            try:
                for ea, iz, mn, ops in md.disasm_lite(data[off(a):off(a) + 4096], base + a):
                    r = ea - base
                    if r in ins or not (e <= r < fb):
                        break
                    ins.add(r)
                    nb += iz
                    ni += 1
                    if mn in ('ret', 'int3', 'ud2', 'hlt'):
                        break
                    if mn == 'call':
                        if ops.startswith('0x'):
                            tg = int(ops, 16) - base
                            if t_lo <= tg < t_hi and not (THUNK_LO <= tg < THUNK_HI):
                                cs.add(tg)
                        continue
                    if mn.startswith('j'):
                        if not ops.startswith('0x'):
                            un += 1
                        else:
                            tg = int(ops, 16) - base
                            if e <= tg < fb:
                                work.append(tg)
                            elif t_lo <= tg < t_hi and not (THUNK_LO <= tg < THUNK_HI):
                                cs.add(tg)
                        if mn == 'jmp':
                            break
            except capstone.CsError:
                pass
        return cs, nb, ni, un

    # ---- recursive descent over entry points only
    entries = set(seeds)
    callees = {}
    rounds = 0
    rlog = []
    while True:
        rounds += 1
        new = set()
        st = collections.Counter()
        sl = sorted(entries)
        for e in sl:
            if e in callees:
                continue
            # 自分の区間 = [e, 次の既知入口) (ただし .pdata end を優先)
            i = bisect.bisect_right(sl, e)
            nxt = sl[i] if i < len(sl) else t_hi
            end = fsz.get(e)
            if end is None:
                j = bisect.bisect_right(begins, e) - 1
                if j >= 0 and e < begins[j] + fsz[begins[j]]:
                    end = begins[j] + fsz[begins[j]]
                else:
                    end = nxt
            else:
                end = e + end
            if end > nxt:
                end = nxt
            sz = min(end - e, MAXFN)
            if sz <= 0:
                callees[e] = []
                continue
            st['linear'] += sz
            if MODE == 'flow':
                cs, nb, ni, un = flow(e, e + sz)
                st['reached'] += nb
                st['insn'] += ni
                st['unres'] += un
                callees[e] = sorted(cs)
                new |= {tg for tg in cs if tg not in entries}
                continue
            cs = set()
            try:
                for a, iz, mn, ops in md.disasm_lite(data[off(e):off(e) + sz], base + e):
                    if mn in ('call', 'jmp') and ops.startswith('0x'):
                        tg = int(ops, 16) - base
                        if THUNK_LO <= tg < THUNK_HI:
                            continue
                        if t_lo <= tg < t_hi:
                            cs.add(tg)
                            if tg not in entries:
                                new.add(tg)
            except capstone.CsError:
                pass
            callees[e] = sorted(cs)
        before = len(entries)
        entries |= new
        rlog.append({'round': rounds, 'entries': len(entries), 'added': len(entries) - before,
                     'linear_bytes': st['linear'], 'reached_bytes': st['reached'],
                     'reached_insns': st['insn'], 'indirect_unres': st['unres']})
        sys.stderr.write('round %d entries %d (+%d) %s\n' % (rounds, len(entries), len(entries) - before, rlog[-1]))
        if len(entries) == before:
            break

    # ---- per-root closure (BFS)
    def reach(rs):
        seen, stk = set(), list(rs)
        while stk:
            f = stk.pop()
            if f in seen:
                continue
            seen.add(f)
            stk.extend(callees.get(f, ()))
        return seen

    out = {'pe': path, 'mode': MODE, 'rounds_log': rlog,
           'base': hex(base), 'image_size': hex(pe.OPTIONAL_HEADER.SizeOfImage),
           'pdata_funcs': len(fsz), 'pdata_bytes': sum(fsz.values()), 'text_size': t.Misc_VirtualSize,
           'n_family_slots': sum(len(v) for v in fam.values()),
           'family_classes': {k: len(v) for k, v in sorted(fam.items())},
           'roots': {}, 'per_class': {}}
    for name, r in EXPORTS.items():
        s = reach([r])
        out['roots'][name] = {'roots': 1, 'closure_funcs': len(s),
                              'closure_pdata': sum(1 for x in s if x in fsz)}
    s = reach(sorted(seeds))
    out['roots']['VST3-entry-surface(all)'] = {
        'roots': len(seeds), 'closure_funcs': len(s),
        'closure_pdata': sum(1 for x in s if x in fsz),
        'closure_pct_of_pdata': round(100.0 * sum(1 for x in s if x in fsz) / len(fsz), 2)}
    for k in sorted(fam):
        s = reach(sorted(fam[k]))
        out['per_class'][k] = {'slots': len(fam[k]), 'closure_funcs': len(s)}
    out['closure_total'] = {'funcs': len(entries),
                            'pdata_funcs': sum(1 for x in entries if x in fsz),
                            'bytes_pdata': sum(fsz[x] for x in entries if x in fsz),
                            'pct_pdata': round(100.0 * sum(1 for x in entries if x in fsz) / len(fsz), 2)}
    json.dump(out, open(outp + '.json', 'w'), indent=1)
    pickle.dump({'entries': sorted(entries), 'callees': callees, 'fsz': fsz, 'base': base,
                 'seeds': sorted(seeds), 'fam': {k: sorted(v) for k, v in fam.items()},
                 'EXPORTS': EXPORTS},
                open(outp + '_sets.pkl', 'wb'), protocol=4)
    json.dump({'roots': [hex(base + x) for x in sorted(entries)]},
              open(outp + '_x64c_entries.json', 'w'), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    MODE = sys.argv[4] if len(sys.argv) > 4 else 'linear'
    assert MODE in ('linear', 'flow'), MODE
    main(sys.argv[1], sys.argv[2], sys.argv[3])
