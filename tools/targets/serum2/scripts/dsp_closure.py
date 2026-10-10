#!/usr/bin/env python3
"""RTTI vtable -> class methods; static call/addr-ref graph; DSP vs GUI closure sizing (MSVC x64 PE).
usage: dsp_closure.py <pe> <out.json>"""
import sys, re, json, struct, bisect, collections, multiprocessing as mp
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_OP_IMM, X86_REG_RIP

PATH = sys.argv[1]
pe = pefile.PE(PATH, fast_load=True)
IMG = pe.OPTIONAL_HEADER.ImageBase
S = {s.Name.rstrip(b'\0').decode(): s for s in pe.sections}
text, rdata, data = S['.text'], S['.rdata'], S['.data']
TB, TVA = text.get_data(), text.VirtualAddress
RB, RVA = rdata.get_data(), rdata.VirtualAddress
pd = S['.pdata'].get_data()
funcs = []
for i in range(0, len(pd) - 11, 12):
    b, e, u = struct.unpack_from('<III', pd, i)
    if b and TVA <= b < TVA + len(TB): funcs.append((b, e))
funcs.sort()
starts = [b for b, e in funcs]
def fidx(rva):
    i = bisect.bisect_right(starts, rva) - 1
    if i >= 0 and funcs[i][0] <= rva < funcs[i][1]: return i
    return -1

def demangle(n):
    body = n[4:-2]
    return '::'.join(reversed([p for p in body.split('@') if p]))

# ---- RTTI: type descriptors, COLs, vtables
def va_to_rva(v): return v - IMG
alldata = pe.get_memory_mapped_image()
classes = {}  # td_rva -> name
for m in re.finditer(rb'\.\?A[UV][A-Za-z0-9_@$?]{2,400}@@\x00', alldata):
    td = m.start() - 16
    if td > 0: classes[td] = m.group(0)[:-1].decode()
# COL scan: struct {u32 sig; u32 off; u32 cdoff; u32 td_rva; u32 chd_rva; u32 self_rva}
cols = {}
for off in range(RVA, RVA + len(RB) - 24, 4):
    sig, o, cd, td, chd, selfr = struct.unpack_from('<IIIIII', alldata, off)
    if sig == 1 and selfr == off and td in classes and o < 0x1000:
        cols.setdefault(td, []).append((off, o))
# vtable = qword slot referencing col va, next qwords are methods
col_by_va = {}
for td, lst in cols.items():
    for off, o in lst: col_by_va[IMG + off] = (td, o)
vtables = {}  # vtable_rva -> (name, offset, [method rvas])
for off in range(RVA, RVA + len(RB) - 8, 8):
    v = struct.unpack_from('<Q', alldata, off)[0]
    if v in col_by_va:
        td, o = col_by_va[v]
        ms = []
        p = off + 8
        while True:
            q = struct.unpack_from('<Q', alldata, p)[0]
            r = q - IMG
            if TVA <= r < TVA + len(TB) and fidx(r) >= 0 and funcs[fidx(r)][0] == r:
                ms.append(r); p += 8
            else: break
        vtables[off + 8] = (demangle(classes[td]), o, ms)

# ---- generic function-pointer tables from .reloc (DIR64)
pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_BASERELOC']])
slots = []
for blk in pe.DIRECTORY_ENTRY_BASERELOC:
    for e in blk.entries:
        if e.type == 10:  # DIR64
            slots.append(e.rva)
slots.sort()
fp_slot = {}
for r in slots:
    if r + 8 > len(alldata): continue
    v = struct.unpack_from('<Q', alldata, r)[0] - IMG
    if TVA <= v < TVA + len(TB):
        j = fidx(v)
        if j >= 0 and funcs[j][0] == v: fp_slot[r] = j
# runs of consecutive slots => tables
tbl_start = {}  # table start rva -> [func idx...]
for r in sorted(fp_slot):
    if (r - 8) in fp_slot and (r - 8) in tbl_start_member if False else False: pass
members = {}
cur = None
for r in sorted(fp_slot):
    if cur is not None and r == last + 8: members[cur].append(fp_slot[r])
    else: cur = r; members[cur] = [fp_slot[r]]
    last = r
# each slot address maps to the entries from that slot to the end of its run
slot2tail = {}
for st, lst in members.items():
    for k in range(len(lst)): slot2tail[st + 8 * k] = lst[k:]

slot_list = sorted(fp_slot)
WINDOW = 256
# ---- graph
def worker(rng):
    md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
    out = []
    for fi in rng:
        b, e = funcs[fi]
        code = TB[b - TVA:e - TVA]
        edges = set(); drefs = set()
        for i in md.disasm(code, IMG + b):
            m = i.mnemonic
            if m in ('call', 'jmp') or (m[0] == 'j'):
                ops = i.operands
                if ops and ops[0].type == X86_OP_IMM:
                    t = ops[0].imm - IMG
                    if TVA <= t < TVA + len(TB): edges.add(t)
            for o in i.operands:
                if o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP:
                    t = i.address + i.size + o.mem.disp - IMG
                    if TVA <= t < TVA + len(TB): edges.add(t)
                    else: drefs.add(t)
        out.append((fi, sorted(edges), sorted(drefs)))
    return out

if __name__ == '__main__':
    n = len(funcs); nw = 14
    chunks = [list(range(i, n, nw * 6)) for i in range(nw * 6)]
    with mp.Pool(nw) as p: res = p.map(worker, chunks)
    edges = [None] * n; drefs = [None] * n
    for r in res:
        for fi, e, d in r: edges[fi] = e; drefs[fi] = d
    vt_sorted = sorted(vtables)
    # per-function: referenced vtables (rip-relative ref exactly to vtable start)
    vt_starts = set(vtables)
    # adjacency in function indices
    adj = [set() for _ in range(n)]
    for fi in range(n):
        for t in edges[fi]:
            j = fidx(t)
            if j >= 0: adj[fi].add(j)
        for t in drefs[fi]:
            if t in vt_starts:
                for m in vtables[t][2]:
                    j = fidx(m)
                    if j >= 0: adj[fi].add(j)
            else:
                # data ref -> any fp slot within WINDOW bytes (struct-of-fnptr tables / vtable-less dispatch arrays)
                k = bisect.bisect_left(slot_list, t)
                while k < len(slot_list) and slot_list[k] < t + WINDOW:
                    adj[fi].add(fp_slot[slot_list[k]]); k += 1
    DSP = re.compile(r'^(SerumDSP|Oscillator|WarpOscillator|WTOsc|WTOscState|MultiSampleOsc|MultiSampleOscState|SampleOsc|SampleOscState|GranularOsc|GranularOscState|SpectralOsc|SpectralOscState|NoiseOsc|NoiseOscState|SubOsc|SubOscState|OscState|Voice|LFO|LFOState|Macro|MacroModSource|ModMatrix|ModSlot|ModLine|SkEnv|EnvState|MidiProcessor|PitchQuantizer|Arp|AlgoArp|PatternArp|ArpContext|ClipPlayer|MidiClip|XferFilter\w*|XferBode|XferChorus|XferComp|XferConv|XferDelay|XferDimE|XferDist|XferEQ|XferFX\w*|XferFlanger|XferHyper\w*|XferPhaser|XferReverb(::\w+)?|XferRandom|XferUtils|XferModule|XferModSource|XferFader|ZL\w+|PFFFTConvolver|libsfz::\w+|mu::\w+|InputNote|NoteExpressionVoice|XferLiveVoiceUser|XferFX)$')
    GUI = re.compile(r'^(VSTGUI::|XferVST3Editor|SerumEditor|SerumController|SerumSubController|Steinberg::Vst::VSTGUIEditor|PresetBrowser|PresetManager|.*Controller$|.*Display$|.*TemplateParams$|.*MenuData$|.*View$|.*Button$|.*DropTarget$)')
    NOISE = re.compile(r'^(Steinberg::|std::|nlohmann|IUnknown|type_info|I[A-Z]\w*$)')
    dsp_roots, gui_roots = set(), set()
    fam_bytes = collections.defaultdict(lambda: [0, 0, 0])  # class -> [vtables, methods, bytes]
    for v, (name, o, ms) in vtables.items():
        if DSP.match(name): tgt = dsp_roots
        elif GUI.match(name): tgt = gui_roots
        else: tgt = None
        for m in ms:
            j = fidx(m)
            if tgt is not None and j >= 0: tgt.add(j)
        fb = fam_bytes[name]; fb[0] += 1; fb[1] += len(ms)
        fb[2] += sum(funcs[fidx(m)][1] - funcs[fidx(m)][0] for m in set(ms) if fidx(m) >= 0)
    def closure(roots):
        seen = set(roots); st = list(roots)
        while st:
            x = st.pop()
            for y in adj[x]:
                if y not in seen: seen.add(y); st.append(y)
        return seen
    cd, cg = closure(dsp_roots), closure(gui_roots)
    sz = lambda s: sum(funcs[i][1] - funcs[i][0] for i in s)
    only_d, only_g, both = cd - cg, cg - cd, cd & cg
    reached = cd | cg
    summ = {
        'n_funcs': n, 'text_bytes_by_pdata': sz(range(n)),
        'rtti_vtables': len(vtables), 'rtti_classes': len(set(v[0] for v in vtables.values())),
        'dsp_root_funcs': len(dsp_roots), 'dsp_root_bytes': sz(dsp_roots),
        'gui_root_funcs': len(gui_roots), 'gui_root_bytes': sz(gui_roots),
        'dsp_closure_funcs': len(cd), 'dsp_closure_bytes': sz(cd),
        'gui_closure_funcs': len(cg), 'gui_closure_bytes': sz(cg),
        'dsp_only_funcs': len(only_d), 'dsp_only_bytes': sz(only_d),
        'gui_only_funcs': len(only_g), 'gui_only_bytes': sz(only_g),
        'shared_funcs': len(both), 'shared_bytes': sz(both),
        'fp_slots': len(fp_slot), 'fp_tables': len(members), 'unreached_funcs': n - len(reached), 'unreached_bytes': sz(set(range(n)) - reached),
    }
    # per-family DSP breakdown (roots only)
    fam = collections.defaultdict(lambda: [0, 0])
    def famof(nm):
        if re.match(r'XferFilter', nm): return 'filters'
        if re.match(r'Xfer(Bode|Chorus|Comp|Conv|Delay|DimE|Dist|EQ|Flanger|Hyper\w*|Phaser|Reverb\S*|FX\w*)$', nm) or nm.startswith('XferReverb'): return 'fx'
        if re.search(r'Osc(State)?$|^Oscillator$|^WarpOscillator$', nm): return 'oscillators'
        if re.match(r'(ZL|PFFFT)', nm): return 'convolution/fft'
        if re.match(r'(libsfz|mu::)', nm): return 'sfz/muparser'
        if re.match(r'(LFO|Macro|ModMatrix|ModSlot|ModLine|SkEnv|EnvState|XferModSource|XferModule)', nm): return 'mod'
        if re.match(r'(Arp|AlgoArp|PatternArp|ClipPlayer|MidiClip|MidiProcessor|PitchQuantizer|InputNote)', nm): return 'midi/arp/clip'
        if nm in ('SerumDSP', 'Voice', 'XferRandom', 'XferUtils', 'XferFader', 'NoteExpressionVoice', 'XferLiveVoiceUser'): return 'core/voice'
        return 'other'
    for nm, (nv, nm_, by) in fam_bytes.items():
        if DSP.match(nm):
            f = fam[famof(nm)]; f[0] += nm_; f[1] += by
    summ['dsp_root_families(methods,bytes)'] = {k: v for k, v in sorted(fam.items(), key=lambda x: -x[1][1])}
    topc = sorted(((nm, v[1], v[2]) for nm, v in fam_bytes.items() if DSP.match(nm)), key=lambda x: -x[2])[:30]
    summ['top_dsp_classes(name,methods,bytes)'] = topc
    topg = sorted(((nm, v[1], v[2]) for nm, v in fam_bytes.items() if not DSP.match(nm) and not NOISE.match(nm)), key=lambda x: -x[2])[:15]
    summ['top_other_classes(name,methods,bytes)'] = topg
    import pickle
    pickle.dump({'funcs': funcs, 'adj': [sorted(a) for a in adj], 'vtables': vtables, 'IMG': IMG, 'cd': cd, 'cg': cg}, open(sys.argv[2].replace('.json', '_graph.pkl'), 'wb'))
    json.dump({'summary': summ, 'dsp_only': sorted(IMG + funcs[i][0] for i in only_d)}, open(sys.argv[2], 'w'))
    print(json.dumps(summ, indent=1, ensure_ascii=False))
