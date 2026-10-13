#!/usr/bin/env python3
"""SR-4 step 1: lift 対象 (WT osc / WarpOscillator / XferFilterSVF / XferFilterLadder / Voice core) の関数表と静的 closure の lift 前提分類。
usage: sr4_survey.py <Serum2_win64.vst3> <outdir>
出力: <outdir>/sr4_funcs.tsv (関数ごと)・<outdir>/sr4_summary.json (集計)
RTTI vtable 抽出は dsp_closure.py を import して再利用 (モジュール先頭部のみ実行される)。
closure は直接 call/jmp の静的辺のみ (間接 call は辺を張らず `indirect_calls` として数える。vtable/fp 表経由は含めない)。
vtable の method スロットは .text を指す限り全て読む: dsp_closure.py の vtable 抽出は .pdata 関数先頭でない slot で打ち切るため
XferFilter* は 1 method しか見えないが、実際は .pdata 外の leaf 関数 (`gap` 関数) が並ぶ。gap 関数の末尾は ret/jmp + 0xCC パディングで推定。"""
import sys, os, json, struct, collections
HERE = os.path.dirname(os.path.abspath(__file__))
PATH, OUT = sys.argv[1], sys.argv[2]
sys.argv = ['dsp_closure.py', PATH, os.devnull]
sys.path.insert(0, HERE)
import dsp_closure as dc
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_OP_IMM, X86_REG_RIP

IMG, TB, TVA, funcs, fidx, ALLD = dc.IMG, dc.TB, dc.TVA, dc.funcs, dc.fidx, dc.alldata
TEND = TVA + len(TB)
VOICE_LO, VOICE_HI = 0x18007e700, 0x1800861f3
GROUPS = collections.OrderedDict([
    ('wt_osc', ['WTOsc', 'WarpOscillator', 'Oscillator', 'WTOscState']),
    ('filter', ['XferFilterSVF', 'XferFilterLadder']),
    ('voice', ['Voice']),
])
cut = {}
with open(os.path.join(HERE, '..', 'out', 'sr3_cut_table.tsv')) as fh:
    next(fh)
    for ln in fh:
        va, _by, lib, _tag = ln.rstrip('\n').split('\t')
        cut[int(va, 16)] = lib

rdata_lo, rdata_hi = dc.RVA, dc.RVA + len(dc.RB)
md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
pd_start = {b: e for b, e in funcs}
gap_funcs = {}


def gap_extent(b):
    code = TB[b - TVA:min(b - TVA + 0x4000, len(TB))]
    last = b
    for i in md.disasm(code, IMG + b):
        last = i.address + i.size - IMG
        nxt = last - TVA
        if i.mnemonic in ('ret', 'jmp') and (nxt >= len(TB) or TB[nxt] in (0xCC, 0x90)):
            if i.mnemonic == 'ret' or not (i.operands and i.operands[0].type == X86_OP_IMM and b <= i.operands[0].imm - IMG < last):
                return last
    return last


def resolve(rva):
    """rva が関数先頭なら (end_rva)。.pdata 関数の途中は None。.pdata 外の .text は gap 関数として登録。"""
    if not (TVA <= rva < TEND): return None
    j = fidx(rva)
    if j >= 0: return funcs[j][1] if funcs[j][0] == rva else None
    if rva not in gap_funcs: gap_funcs[rva] = gap_extent(rva)
    return gap_funcs[rva]


def scan(fk):
    b, e = fk
    code = TB[b - TVA:e - TVA]
    r = dict(insn=0, dcall=set(), iat=0, icall=0, packed=0, avx=0, x87=0, scalar_fp=0, mn=collections.Counter())
    for i in md.disasm(code, IMG + b):
        m = i.mnemonic
        r['insn'] += 1
        r['mn'][m] += 1
        if m.startswith('v'): r['avx'] += 1
        if m[0] == 'f' and m != 'fxsave': r['x87'] += 1
        if m.endswith(('ps', 'pd')) and m[0] in 'admnoxpscu' and not m.endswith(('ss', 'sd')): r['packed'] += 1
        if m.endswith(('ss', 'sd')) and m not in ('movss', 'movsd'): r['scalar_fp'] += 1
        if m == 'call' or m[0] == 'j':
            ops = i.operands
            if ops and ops[0].type == X86_OP_IMM:
                t = ops[0].imm - IMG
                if m == 'call' or not (b <= t < e): r['dcall'].add(t)
            elif m == 'call':
                o = ops[0]
                if o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP:
                    t = i.address + i.size + o.mem.disp - IMG
                    if rdata_lo <= t < rdata_hi + 0x400000 and not (TVA <= t < TEND): r['iat'] += 1
                    else: r['icall'] += 1
                else:
                    r['icall'] += 1
    return r


cache = {}
def info(fk):
    if fk not in cache: cache[fk] = scan(fk)
    return cache[fk]


by_class = collections.defaultdict(list)
for v, (name, off, ms) in dc.vtables.items():
    by_class[name].append((v, off, ms))
# vtable が存在するはずのクラス (無ければ RTTI 抽出の壊れ/別バイナリとして exit 2。SR4_REQUIRE_EXTRA=Name,.. はネガコン用)
REQUIRED = ['WTOsc', 'XferFilterSVF', 'XferFilterLadder', 'Voice'] + [x for x in os.environ.get('SR4_REQUIRE_EXTRA', '').split(',') if x]
missing = [n for n in REQUIRED if n not in by_class]
if missing:
    print('FAIL: RTTI vtable not found for required classes:', missing, file=sys.stderr)
    sys.exit(2)


def vtable_slots(v):
    out = []; p = v
    while p + 8 <= len(ALLD):
        q = struct.unpack_from('<Q', ALLD, p)[0] - IMG
        if not (TVA <= q < TEND): break
        out.append(q); p += 8
    return out


roots = collections.OrderedDict()
vt_rows = []
for g, names in GROUPS.items():
    rs = set()
    for n in names:
        for (v, off, ms) in by_class.get(n, []):
            sl = vtable_slots(v)
            vt_rows.append((g, n, v + IMG, off, len(ms), len(sl)))
            for m in sl:
                e = resolve(m)
                if e: rs.add((m, e))
    roots[g] = rs
voice_core = {(b, e) for (b, e) in funcs if VOICE_LO <= IMG + b and IMG + e <= VOICE_HI + 1}
voice_core_overlap = {(b, e) for (b, e) in funcs if IMG + b <= VOICE_HI and IMG + e > VOICE_LO}
roots['voice'] |= voice_core

closures = {}
for g, rs in roots.items():
    seen = set(rs); st = list(rs)
    while st:
        x = st.pop()
        for t in info(x)['dcall']:
            e = resolve(t)
            if e and (t, e) not in seen:
                seen.add((t, e)); st.append((t, e))
    closures[g] = seen


def cls(fk):
    r = info(fk); va = IMG + fk[0]
    if va in cut: return 'oss:' + cut[va]
    if r['iat']: return 'iat'
    if r['avx']: return 'avx'
    if r['icall']: return 'icall'
    return 'closed'


os.makedirs(OUT, exist_ok=True)
allf = set().union(*closures.values())
with open(os.path.join(OUT, 'sr4_funcs.tsv'), 'w') as fh:
    fh.write('func_va\tbytes\tkind\tclosure_groups\troot_groups\tclass\tinsn\tdirect_callees\tiat_calls\tindirect_calls\tpacked\tavx\tx87\tscalar_fp\n')
    for fk in sorted(allf):
        b, e = fk; r = info(fk)
        fh.write('0x%x\t%d\t%s\t%s\t%s\t%s\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\n' % (
            IMG + b, e - b, 'pdata' if b in pd_start else 'gap', ','.join(g for g in GROUPS if fk in closures[g]),
            ','.join(g for g in GROUPS if fk in roots[g]), cls(fk), r['insn'], len(r['dcall']), r['iat'], r['icall'],
            r['packed'], r['avx'], r['x87'], r['scalar_fp']))


def summarize(S):
    c = collections.Counter(cls(i).split(':')[0] for i in S)
    cb = collections.Counter()
    for i in S: cb[cls(i).split(':')[0]] += i[1] - i[0]
    mn = collections.Counter()
    for i in S: mn.update(info(i)['mn'])
    return dict(funcs=len(S), gap_funcs=sum(1 for i in S if i[0] not in pd_start), bytes=sum(e - b for (b, e) in S),
                class_funcs=dict(c), class_bytes=dict(cb), insn=sum(info(i)['insn'] for i in S),
                iat_calls=sum(info(i)['iat'] for i in S), indirect_calls=sum(info(i)['icall'] for i in S),
                packed=sum(info(i)['packed'] for i in S), avx=sum(info(i)['avx'] for i in S),
                x87=sum(info(i)['x87'] for i in S), scalar_fp=sum(info(i)['scalar_fp'] for i in S))


summary = dict(
    image=os.path.basename(PATH), image_base=hex(IMG),
    vtables=[dict(group=g, cls=n, vtable_va=hex(v), this_off=o, methods_pdata_only=k, slots_text=sl) for (g, n, v, o, k, sl) in vt_rows],
    voice_core_range=[hex(VOICE_LO), hex(VOICE_HI)],
    voice_core_funcs_inside=len(voice_core), voice_core_funcs_overlapping=len(voice_core_overlap),
    voice_core_bytes_inside=sum(e - b for (b, e) in voice_core),
    roots={g: summarize(s) for g, s in roots.items()},
    closure={g: summarize(s) for g, s in closures.items()},
    closure_union=summarize(allf),
    root_funcs={g: ['0x%x' % (IMG + b) for (b, e) in sorted(rs)] for g, rs in roots.items()},
)
for g, rs in roots.items():
    if not rs:
        print('FAIL: empty root set for group', g, file=sys.stderr); sys.exit(2)
json.dump(summary, open(os.path.join(OUT, 'sr4_summary.json'), 'w'), indent=1, sort_keys=True)
print(json.dumps({k: summary[k] for k in ('voice_core_funcs_inside', 'voice_core_funcs_overlapping', 'voice_core_bytes_inside')}))
for g in GROUPS:
    print(g, 'roots', summary['roots'][g]['funcs'], summary['roots'][g]['bytes'], 'closure', summary['closure'][g]['funcs'], summary['closure'][g]['bytes'], summary['closure'][g]['class_funcs'])
print('union', summary['closure_union']['funcs'], summary['closure_union']['bytes'], summary['closure_union']['class_funcs'])
