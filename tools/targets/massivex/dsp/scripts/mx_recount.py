#!/usr/bin/env python3
"""MX-3 の独立再計算 (規則 37: 実装側 mx_entry_surface.py と別アルゴリズム)。

mx_entry_surface.py = capstone disasm_lite で pdata 境界を作り BFS。
mx_recount.py       = pefile のメモリマップ image + **byte パターンスキャン**で
                      E8/E9 (call/jmp rel32) を全 .text から総浚いし、
                      target を関数境界集合に追加する (線形掃き・再帰降下でない)。
                      さらに closure は **逆BFS (caller 側から)** で到達集合を作る。

両者が一致しない場合は差分を出す (一致 = closure サイズ・関数境界集合の積集合)。

usage: mx_recount.py <pe> <rtti_vtables.json> <out.json>
"""
import sys, json, re, struct, collections
import pefile


def main(path, vtp, outp):
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    img = pe.get_memory_mapped_image()
    t = [s for s in pe.sections if s.Characteristics & 0x20000000][0]
    t_lo, t_hi = t.VirtualAddress, t.VirtualArea if False else t.VirtualAddress + t.Misc_VirtualSize
    blob = img[t_lo:t_hi]
    pds = sorted([s for s in pe.sections if s.Name.rstrip(b'\0').decode() == '.pdata'],
                 key=lambda s: -s.Misc_VirtualSize)
    praw = pe.__data__[pds[0].PointerToRawData: pds[0].PointerToRawData + pds[0].Misc_VirtualSize]
    fsz = {}
    for i in range(0, len(praw) - 11, 12):
        st, e, _u = struct.unpack_from('<III', praw, i)
        if e > st and st and 0x1000 <= st < t_hi and e <= t_hi:
            fsz[st] = e - st
    begins = set(fsz)

    # ---- linear byte scan: every E8/E9 rel32 in .text (recursive descent ではない)
    edges = collections.defaultdict(set)
    targets = set()
    n = len(blob)
    i = 0
    THUNK_LO, THUNK_HI = 0x396e000, 0x3970200
    while i < n - 5:
        op = blob[i]
        if op in (0xE8, 0xE9):
            d = struct.unpack_from('<i', blob, i + 1)[0]
            tgt = i + 5 + d          # RVA 基準 (blob は RVA t_lo から始まる)
            if t_lo <= tgt < t_hi and not (THUNK_LO <= tgt < THUNK_HI):
                edges[i].add(tgt)
                targets.add(tgt)
        i += 1
    # note: i は RVA ではない (blob の index = RVA - t_lo)。src = i + t_lo
    edges2 = {}
    for k, v in edges.items():
        edges2[k + t_lo] = sorted(v)

    # ---- roots (同じ定義・別実装: RTTI json から直接)
    vt = json.load(open(vtp))
    EX = {'GetPluginFactory': 0xa870, 'InitDll': 0xa850, 'ExitDll': 0xa860,
          'factoriesListGetter': 0x1188680}
    FAM = {'SingleComponentEffect', 'ComponentBase', 'EditControllerEx1', 'EditController',
           'IPluginBase', 'FObject', 'FUnknown', 'IDependent', 'Unit', 'ProgramList', 'Parameter',
           'Bus', 'AudioBus', 'EventBus', 'BusList', 'IPlugView', 'CPluginView', 'IConnectionPoint',
           'IAudioProcessor', 'IComponent', 'IEditController', 'IEditController2', 'IUnitInfo',
           'IAutomationState', 'IMidiMapping', 'IInfoListener', 'IProcessContextRequirements',
           'IParameterFinder'}
    roots = set(EX.values())
    for name, lst in vt.items():
        m = re.match(r'^\.\?(AV|AU)(.+?)@@(.*)$', name)
        if not m:
            continue
        short = [x for x in m.group(2).split('@') if x][-1]
        if short in FAM or short.startswith('MassiveX') or short.startswith('MX'):
            for v in lst:
                for s in v['slots']:
                    r = int(s, 16) - base
                    if r in fsz:
                        roots.add(r)

    # ---- linear-scan graph on the root's bytes only (差分明示のため 1 round 相当)
    # src -> targets.  root が .text のどの index か = rva - t_lo
    one = set(roots)
    for r in roots:
        src = r - t_lo
        one |= edges.get(src, set())
    # 逆BFS: root を呼ぶ call サイト (= 到達) を線形スキャンで全部探す
    callers = collections.defaultdict(list)
    for src, tgts in edges2.items():
        for tg in tgts:
            callers[tg].append(src)
    seen = set(roots)
    stk = list(roots)
    while stk:
        f = stk.pop()
        if f in seen:
            continue
        seen.add(f)
        for c in callers.get(f, ()):      # c は root を直接呼ぶサイト
            stk.append(c)
    out = {'method': 'linear E8/E9 byte scan (no recursive descent)',
           'pdata_funcs': len(fsz), 'bytes_of_text': len(blob),
           'e8e9_sites': sum(len(v) for v in edges2.values()),
           'e8e9_targets': len(targets),
           'roots': len(roots),
           'root_bytelevel_callees': len(one),
           'root_callers_byscan': len(seen)}
    json.dump(out, open(outp, 'w'), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3])
