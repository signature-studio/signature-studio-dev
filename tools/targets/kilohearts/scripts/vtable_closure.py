#!/usr/bin/env python3
"""ホスト (Snap Heap / Multipass / Phase Plant) の closure を vtable 経由の間接 call で再計算する (KH-19, #782).

規則 (over-approximation, 不動点まで反復):
  1. 初期集合 before = roots (<ns>::*Dsp / *MasterDsp / *DspModel の vtable slot) からの直接 call/jmp 閉包。
  2. 集合内の各関数を逆アセンブルし間接 call を分類する:
       vtable : call [reg+disp] / call [reg] → 候補 = 同 ns の全 class の vtable の slot (disp/8 番目)
       iat    : call [rip+..] で参照先が import address table (IAT) の slot → 外部 DLL 関数、解決不要 (別計上)
       rip_data: call [rip+..] で参照先が IAT 以外 (関数ポインタ変数等) → 下記 3 の規則で解決を試みる
       その他 : call reg / call [idx*s+..] 等 → 解決せず未解決として計上
  3. rip_data の解決 (#849): 参照先 slot S を次で分類する (メモリイメージ・全 .text 走査):
       static_fn     : S の初期値 (8 byte) が関数先頭 (res に存在) を指し、かつ .text に S への store (mov [rip+S], x) が無く、
                       S のアドレスを取る lea も無い → 確定。初期値の関数を候補に加える。
       runtime_store : .text に S への store がある → 初期値が実行時に変わり得るため未確定。
       addr_taken    : S のアドレスを lea で取る → 未確定 (間接的な書き換えの可能性)。
       null_unused   : 初期値 0 かつ store / lea 無し → 呼ばれないはずの slot (未使用として計上)。
       nonfunc_init  : 初期値が関数先頭でない (非 0) → 未確定。
  4. 候補を閉包に加え、増分が無くなるまで繰り返す。after = 不動点 (vtable のみ)。
     after_rip = 不動点 (vtable + 確定 rip_data)。
  4'. CFG/XFG dispatch (#849): load config の GuardCFDispatch/XFGDispatch slot を call [rip+..] で呼ぶ site は、呼び先が
       直前の rax。同一関数内を逆向きに追い (rax_source)、`mov rax, [R+d]` なら vtable slot d/8 と同じ規則、
       `lea rax, [rip+F]` で F が関数先頭なら F を候補にする。after_cfg (= 不動点) は after / after_rip とは別に出す。
  ※ 候補は同 ns の vtable に限る (他 ns・boost/Skia の仮想関数は対象外 = 過小評価の余地あり、REPORT に明記)。
  ※ store 走査は res に含まれる関数 (sweep 済み) のみ。res 外の関数が S に書く可能性は残る (REPORT に明記)。
usage: vtable_closure.py <HeartCore.core_64> <work/callgraph.pkl> <work/rtti_vtables.json> <ns> <all|nogui> <out.json>
"""
import sys, json, pickle, re, collections

import pefile
import capstone


def ns_of(cls):
    rest = cls[4:]
    rest = rest[:-2] if rest.endswith('@@') else rest
    if '?' in rest or '$' in rest:
        return None, None
    parts = [p for p in rest.split('@') if p]
    if len(parts) != 2:
        return None, None
    return parts[0], parts[1]


GUI = re.compile(r'(Editor|Controller|Ui|UI|View|Gui|Skia)')


def vtable_slots(vt, ns, mode):
    """ns の vtable を slot 番号 (0 始まり) ごとに集める。
    mode=all: ns の全 class (上限側) / mode=nogui: GUI 名 (Editor/Controller/UI) を除く (下限側)。"""
    slots = collections.defaultdict(set)
    for cls, lst in vt.items():
        name, cns = ns_of(cls)
        if cns != ns or (mode == 'nogui' and GUI.search(name or '')):
            continue
        for v in lst:
            for k, s in enumerate(v['slots']):
                slots[k].add(int(s, 16))
    return slots


RIP_REF = re.compile(r'\[rip ([+-]) (0x[0-9a-f]+|[0-9]+)\]')
RIP_STORE = re.compile(r'^(?:\w+ ptr )?\[rip ([+-]) (0x[0-9a-f]+|[0-9]+)\], ')


def iat_slots(pe, base):
    """import address table の各 slot の VA (IMAGE_IMPORT_DESCRIPTOR.FirstThunk から import 数ぶん)。"""
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
    slots = set()
    for entry in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
        first = base + entry.struct.FirstThunk
        for k in range(len(entry.imports)):
            slots.add(first + 8 * k)
    return slots


def rip_target(insn):
    m = RIP_REF.search(insn.op_str)
    if not m:
        return None
    d = int(m.group(2), 16) if m.group(2).startswith('0x') else int(m.group(2))
    return insn.address + insn.size + (-d if m.group(1) == '-' else d)


def classify_call(insn, iat):
    ops = insn.op_str
    if ops.startswith('0x'):
        return ('direct', None)
    if re.fullmatch(r'r[a-z0-9]+', ops):
        return ('reg', None)
    if 'rip' in ops:
        tgt = rip_target(insn)
        return ('iat', None) if tgt in iat else ('rip_data', tgt)
    m = re.fullmatch(r'qword ptr \[(r[a-z0-9]+)(?: \+ (0x[0-9a-f]+|[0-9]+))?\]', ops)
    if m:
        d = m.group(2)
        return ('vtable', 0 if d is None else int(d, 16) if d.startswith('0x') else int(d))
    if '+' in ops and ops.count('+') >= 2 or '*' in ops:
        return ('indexed', None)
    return ('other', None)


def slot_facts(pe, base, res, md, t, data, slot_vas):
    """rip_data の参照先 slot ごとに store / lea の有無 (全 res 関数の .text 走査) と初期値を集める。"""
    stored, leaed = set(), set()
    for f in res:
        size = res[f]['size']
        off = f - t.VirtualAddress
        for i in md.disasm(data[off:off + size], base + f):
            if i.mnemonic not in ('mov', 'lea') or 'rip' not in i.op_str:
                continue
            tgt = rip_target(i)
            if tgt not in slot_vas:
                continue
            if i.mnemonic == 'lea':
                leaed.add(tgt)
            elif RIP_STORE.search(i.op_str):
                stored.add(tgt)
    return stored, leaed


def is_trampoline(pe, base, data, t, md, fn, iat):
    """先頭命令が jmp reg / jmp [rip+非IAT] なら、実際の呼び先が静的に決まらない thunk (未確定)。"""
    off = fn - t.VirtualAddress
    first = next(md.disasm(data[off:off + 16], base + fn), None)
    if first is None or first.mnemonic != 'jmp':
        return False
    if re.fullmatch(r'r[a-z0-9]+', first.op_str):
        return True
    return 'rip' in first.op_str and rip_target(first) not in iat


def cfg_dispatch_slots(pe):
    """load config の GuardCFDispatchFunctionPointer / GuardXFGDispatchFunctionPointer (#849)。
    これらの slot を call [rip+..] で呼ぶ間接 call は、呼び先が直前の rax に入る (thunk は jmp rax)。"""
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_LOAD_CONFIG']])
    lc = getattr(pe, 'DIRECTORY_ENTRY_LOAD_CONFIG', None)
    if lc is None:
        return set()
    return {getattr(lc.struct, n) for n in ('GuardCFDispatchFunctionPointer', 'GuardXFGDispatchFunctionPointer')
            if getattr(lc.struct, n, 0)}


def is_cfg_call(insn, cfg_slots):
    return 'rip' in insn.op_str and rip_target(insn) in cfg_slots


RAX_NAMES = {'rax', 'eax', 'ax', 'al', 'ah'}
MEM_BASE_DISP = re.compile(r'qword ptr \[(r[a-z0-9]+)(?: \+ (0x[0-9a-f]+|[0-9]+))?\]')
IMPLICIT_RAX_WRITE = {'cdqe', 'cwde', 'cbw', 'lahf', 'xlat', 'cmpxchg', 'cmpxchg8b', 'cmpxchg16b',
                      'lods', 'lodsb', 'lodsw', 'lodsd', 'lodsq', 'cpuid', 'rdtsc', 'rdtscp', 'xgetbv', 'syscall'}
ONE_OP_RAX_WRITE = {'mul', 'imul', 'div', 'idiv'}


def writes_rax_implicitly(w, ops):
    """オペランドに rax 族を明示せずに rax を書く命令 (cdqe・1 オペランドの mul/div・xchg/xadd の rax 相手 等)。"""
    if w.mnemonic in IMPLICIT_RAX_WRITE:
        return True
    if w.mnemonic in ONE_OP_RAX_WRITE and len(ops) == 1:
        return True
    return w.mnemonic in ('xchg', 'xadd') and any(o in RAX_NAMES for o in ops)


def rax_source(ins, idx, base, res):
    """guard 経由の call (ins[idx]) の直前で rax に入った値の出所を、同一関数内を逆向きに追う (#849)。
    戻り値 (kind, arg): vtable_cfg (arg=disp, `mov rax, [R+disp]`、R は rip 以外) / lea_fn (arg=VA, 関数先頭) / lea_nonfn /
    rip_load (arg=参照先 VA) / reg_copy / other_write:<mn> (暗黙の書き込みを含む) / call_ret / label_barrier / block_end / unresolved。
    分岐先 (label) を跨ぐ場合は、経路が一意でないため label_barrier とする。"""
    labels = {int(i.op_str, 16) for i in ins if i.mnemonic.startswith('j') and i.op_str.startswith('0x')}
    if ins[idx].address in labels:
        return 'label_barrier', None
    k = idx - 1
    while k >= 0:
        if ins[k + 1].address in labels:
            return 'label_barrier', None
        w = ins[k]
        if w.mnemonic == 'call':
            return 'call_ret', None
        if w.mnemonic in ('ret', 'jmp'):
            return 'block_end', None
        ops = [o.strip() for o in w.op_str.split(',')] if w.op_str else []
        if writes_rax_implicitly(w, ops):
            return 'other_write:' + w.mnemonic, None
        first = ops[0] if ops else ''
        if first in RAX_NAMES and w.mnemonic not in ('cmp', 'test'):
            src = w.op_str.split(',', 1)[1].strip() if ',' in w.op_str else ''
            m = MEM_BASE_DISP.fullmatch(src)
            if w.mnemonic == 'mov' and m and m.group(1) != 'rip':
                d = m.group(2)
                return 'vtable_cfg', (0 if d is None else int(d, 16) if d.startswith('0x') else int(d))
            if w.mnemonic == 'lea' and 'rip' in src:
                t = rip_target(w)
                return ('lea_fn' if t - base in res else 'lea_nonfn'), t
            if w.mnemonic == 'mov' and 'rip' in src:
                return 'rip_load', rip_target(w)
            if w.mnemonic == 'mov' and re.fullmatch(r'r[a-z0-9]+', src):
                return 'reg_copy', None
            return 'other_write:' + w.mnemonic, None
        k -= 1
    return 'unresolved', None


def read_slot(mem, base, va):
    """VA の 8 byte 初期値 (メモリイメージ上)。範囲外なら None。"""
    off = va - base
    if off < 0 or off + 8 > len(mem):
        return None
    return int.from_bytes(mem[off:off + 8], 'little')


def main(corep, cgp, vtp, ns, mode, outp):
    pe = pefile.PE(corep, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    t = pe.sections[0]
    data = t.get_data()
    res = pickle.load(open(cgp, 'rb'))['res']
    vt = json.load(open(vtp))
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    iat = iat_slots(pe, base)

    roots = set()
    for cls, lst in vt.items():
        name, cns = ns_of(cls)
        if cns != ns or not re.search(r'(MasterDsp|Dsp|DspModel)$', name or ''):
            continue
        for v in lst:
            for s in v['slots']:
                roots.add(int(s, 16) - base)
    roots = {r for r in roots if r in res}
    slots = vtable_slots(vt, ns, mode)

    def direct_closure(seed):
        seen, st = set(), list(seed)
        while st:
            f = st.pop()
            if f in seen or f not in res:
                continue
            seen.add(f)
            st.extend(res[f]['calls'])
            st.extend(res[f]['jmps'])
        return seen

    sites = {}

    def sites_of(f):
        if f not in sites:
            size = res[f]['size']
            off = f - t.VirtualAddress
            sites[f] = [classify_call(i, iat) for i in md.disasm(data[off:off + size], base + f) if i.mnemonic == 'call']
        return sites[f]

    cfg_slots = cfg_dispatch_slots(pe)
    cfg_cache = {}

    def cfg_of(f):
        """f 内の guard 経由 call (参照先が cfg_slots) の rax 出所。"""
        if f not in cfg_cache:
            size = res[f]['size']
            off = f - t.VirtualAddress
            ins = list(md.disasm(data[off:off + size], base + f))
            cfg_cache[f] = [rax_source(ins, k, base, res) for k, i in enumerate(ins)
                            if i.mnemonic == 'call' and is_cfg_call(i, cfg_slots)]
        return cfg_cache[f]

    def fixpoint(seed, rip_targets, use_cfg=False):
        cur = set(seed)
        done_expand = set()
        while True:
            added = set()
            for f in list(cur):
                if f in done_expand:
                    continue
                done_expand.add(f)
                for kind, disp in sites_of(f):
                    if kind == 'vtable':
                        for tgt in slots.get(disp // 8, ()):
                            if tgt - base in res and tgt - base not in cur:
                                added.add(tgt - base)
                    elif kind == 'rip_data' and disp in rip_targets:
                        fn = rip_targets[disp]
                        if fn not in cur:
                            added.add(fn)
                if use_cfg:
                    for rk, arg in cfg_of(f):
                        if rk == 'vtable_cfg':
                            for tgt in slots.get(arg // 8, ()):
                                if tgt - base in res and tgt - base not in cur:
                                    added.add(tgt - base)
                        elif rk == 'lea_fn' and arg - base not in cur:
                            added.add(arg - base)
            if not added:
                break
            cur |= direct_closure(added)
        return cur

    before = direct_closure(roots)
    cur = fixpoint(before, {})

    unresolved = collections.Counter()
    vt_sites = 0
    iat_sites = 0
    rip_slots = set()
    for f in cur:
        for kind, d in sites_of(f):
            if kind == 'vtable':
                vt_sites += 1
            elif kind == 'iat':
                iat_sites += 1
            elif kind == 'rip_data':
                rip_slots.add(d)
            elif kind != 'direct':
                unresolved[kind] += 1

    # rip_data の解決 (#849): 参照先 slot を分類する
    stored, leaed = slot_facts(pe, base, res, md, t, data, rip_slots)
    mem = pe.get_memory_mapped_image()
    rip_class = collections.Counter()
    rip_resolved = {}
    slot_detail = {}
    for va in sorted(rip_slots):
        init = read_slot(mem, base, va)
        if va in stored:
            k = 'runtime_store'
        elif va in leaed:
            k = 'addr_taken'
        elif init is None:
            k = 'unreadable'
        elif init == 0:
            k = 'null_unused'
        elif init - base in res and is_trampoline(pe, base, data, t, md, init - base, iat):
            k = 'trampoline'
        elif init - base in res:
            k = 'static_fn'
            rip_resolved[va] = init - base
        else:
            k = 'nonfunc_init'
        rip_class[k] += 1
        slot_detail[hex(va)] = k

    cur_rip = fixpoint(before, rip_resolved)
    rip_call_sites = sum(1 for f in cur for kind, _ in sites_of(f) if kind == 'rip_data')

    # CFG/XFG dispatch 経由の call (#849): rax の出所で分類し、vtable 形 / lea 関数先頭だけを閉包に加える
    cur_cfg = fixpoint(before, rip_resolved, use_cfg=True)
    cfg_res = collections.Counter()
    for f in cur_cfg:
        for rk, _ in cfg_of(f):
            cfg_res[rk] += 1

    def bytes_of(s):
        return sum(res[f]['size'] for f in s)

    result = dict(
        ns=ns, mode=mode, roots=len(roots), candidate_slots=sum(len(v) for v in slots.values()),
        before_funcs=len(before), before_bytes=bytes_of(before),
        after_funcs=len(cur), after_bytes=bytes_of(cur),
        after_rip_funcs=len(cur_rip), after_rip_bytes=bytes_of(cur_rip),
        after_cfg_funcs=len(cur_cfg), after_cfg_bytes=bytes_of(cur_cfg),
        vtable_sites=vt_sites, iat_sites=iat_sites, unresolved=dict(unresolved),
        rip_data_call_sites=rip_call_sites, rip_data_slots=len(rip_slots), rip_data_slot_class=dict(rip_class),
        rip_data_resolved_slots=len(rip_resolved),
        cfg_dispatch_slots=sorted(hex(s) for s in cfg_slots), cfg_call_sites=sum(cfg_res.values()),
        cfg_call_resolution=dict(cfg_res),
        rip_data_slot_detail=slot_detail,
    )
    json.dump(result, open(outp, 'w'), indent=1)
    print(json.dumps({k: v for k, v in result.items() if k != 'rip_data_slot_detail'}))


if __name__ == '__main__':
    main(*sys.argv[1:7])
