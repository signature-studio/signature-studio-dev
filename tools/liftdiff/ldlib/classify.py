"""不一致の原因類型の自動分類。

入力: 1 関数の比較結果 (cases[]) + 機械語静的解析 (pe.Analyzer) + IR 静的特徴 (irtool.ir_features)。
出力: タグ列 (信頼度付き)。タグ一覧は docs/FORMAT.md §4。
"""

PRIORITY = ['load_dropped', 'short_global', 'spill_slot_deref', 'callsite_arg_drop', 'icall_drop', 'arg_drop', 'xmm_arg_drop', 'simd_int_semantics', 'xmm_result', 'unresolved_callee', 'unlifted_callee', 'zero_init_drop', 'fp_flag_unreflected', 'import_arg_diff',
            'rep_string_helper', 'simd_helper', 'ret_only', 'callee_divergence', 'wasm_trap', 'memory_semantics', 'other']


def trap_kind(msg):
    m = (msg or '').lower()
    if m.startswith('timeout'):
        return 'hang'
    if 'out of bounds' in m:
        return 'oob'
    if 'unreachable' in m:
        return 'unreachable'
    if 'signature' in m:
        return 'indirect_sig'
    if 'divide' in m or 'integer overflow' in m:
        return 'arith'
    if 'stack' in m:
        return 'stack_overflow'
    return 'other'


def classify(rec, mach, irf, sig, route='ir'):
    """rec: _run_one の結果 (cases)。mach/irf: 静的特徴 (None 可)。route: 'ir'=RetDec 系 (既定) / 'clift'=C 転写 (x64c)。
    戻り: [(tag, confidence, evidence)]。clift では IR 由来の類型 (lift 産物に IR が無い) を抑止し、
    x64c 由来の類型を追加する (docs/FORMAT.md §4)。"""
    tags = []

    def add(tag, conf, ev):
        if not any(t[0] == tag for t in tags):
            tags.append((tag, conf, ev))

    bad = [c for c in rec.get('cases', []) if c['outcome'] in ('diff', 'wasm_trap')]
    if not bad:
        return tags
    np_sig = len(sig['params']) if sig else 0
    fp_sig = sum(1 for t in (sig['params'] if sig else []) if t in ('float', 'double'))
    int_sig = np_sig - fp_sig
    diffs = {}
    for c in bad:
        for k, v in c.get('diffs', {}).items():
            diffs.setdefault(k, v)
    for c in bad:
        for m in c.get('diffs', {}).get('mem', {}).get('first', []):
            try:
                o = int(m['o'], 16)
                vw = int(m['wasm'], 16) if not m['wasm'].startswith('unch') else None
                vn = int(m['native'], 16) if not m['native'].startswith('unch') else None
            except Exception:
                continue
            if vw is None or vn is None or m['r'] != 'image':
                continue
            for sh in (0, 32):
                v = (vw >> sh) & 0xffffffff
                if v and abs(v - (o + sh // 8)) <= 16 and v != (vn >> sh) & 0xffffffff:
                    add('load_dropped', 'high', 'wasm wrote its own global address (rva %#x%+d) where native wrote %s: a global load was dropped and the address used as the value' % (o + sh // 8, v - (o + sh // 8), m['native']))
    if irf and irf.get('regslot_deref', 0) > 0 and ('mem' in diffs or 'ret' in diffs):
        add('spill_slot_deref', 'medium', 'IR dereferences the spill alloca of a register (bitcast ptr %%reg) %d times: the memory operand [reg] reads the stack slot, not the pointer it holds' % irf['regslot_deref'])
    if mach and irf is not None:
        if (mach['icall'] + mach['ijmp']) > 0 and irf['icalls'] == 0:
            trace = diffs.get('trace', {})
            ev = 'machine indirect call/jmp=%d, IR indirect call=0' % (mach['icall'] + mach['ijmp'])
            if trace.get('kind') in ('native_extra_entry', 'entry_va') or diffs.get('calls', {}).get('kind') == 'native_extra_call':
                add('icall_drop', 'high', ev + '; native trace has callee entries missing in wasm (%s)' % trace.get('kind', 'calls'))
            else:
                add('icall_drop', 'medium', ev)
    # 引数脱落: 静的 arity と IR 署名、または trace の entry_arg 差分
    if mach:
        need_gpr = mach['arity_gpr']
        stk = mach['stack_args']
        need_total = max(need_gpr, (max(stk) + 5) if stk else 0)
        if need_total > np_sig and (fp_sig == 0 or need_total > np_sig):
            add('arg_drop', 'high' if bad else 'medium', 'machine uses %d arg slots (gpr=%d, stack=%s), IR signature has %d' % (need_total, need_gpr, stk, np_sig))
        if mach['arity_x'] > fp_sig:
            # win64 の xmm 引数は位置 N = xmm N。読む slot が全て IR 署名の同じ位置で float/double なら脱落ではない
            # (fix_xmm_args.py のように slot の隙間を i64 で埋める署名では、fp 引数の個数 < arity_x になる)
            slots = mach.get('xmm_slots')
            ptypes = sig['params'] if sig else []
            if not (slots and all(i < len(ptypes) and ptypes[i] in ('float', 'double') for i in slots)):
                add('xmm_arg_drop', 'medium', 'machine reads xmm0..%d, IR fp params=%d' % (mach['arity_x'] - 1, fp_sig))
    t = diffs.get('trace')
    if irf and irf.get('short_global_loads', 0) > 0 and ('mem' in diffs or 'ret' in diffs or 'trace' in diffs):
        add('short_global', 'medium', 'IR loads %d wider value(s) than the declared size of a global (e.g. 20xf32 default table declared as [8 x i8])' % irf['short_global_loads'])
    if t and t.get('kind') == 'entry_arg':
        try:
            if int(t['wasm'], 16) == 0 and int(t['native'], 16) != 0:
                add('callsite_arg_drop', 'high', 'callee %s arg%d: native=%s but wasm passes 0 (call site lost the argument; zero-padded)' % (t['va'], t['pos'], t['native']))
        except Exception:
            pass
    if t and t.get('kind') == 'entry_arg':
        pos = t.get('pos')
        add('callee_divergence', 'medium', 'callee %s arg%d native=%s wasm=%s' % (t['va'], pos, t['native'], t['wasm']))
    elif t and t.get('kind') in ('native_extra_entry', 'entry_va', 'wasm_extra_entry'):
        add('callee_divergence', 'medium', 'trace %s at #%s' % (t['kind'], t.get('index')))
    c = diffs.get('calls')
    if c:
        if c.get('kind') == 'call_arg':
            add('import_arg_diff', 'high', 'import %s arg%d native=%s wasm=%s' % (c['name'], c['arg'], c['native'], c['wasm']))
        elif c.get('kind') in ('native_extra_call', 'wasm_extra_call', 'call_name'):
            add('import_call_seq', 'medium', '%s at #%d' % (c['kind'], c['index']))
    for cs in bad:
        w = cs.get('_w', {})
        for cl in w.get('calls', []):
            if cl['n'].startswith('function_'):
                add('unresolved_callee', 'high', 'wasm called undefined %s' % cl['n'])
        if cs.get('wasm_uninit_dependent'):
            add('zero_init_drop', 'high', 'wasm result depends on uninitialised stack fill (0x00 vs 0xa5) while native is deterministic')
    if mach and route == 'ir' and mach['fpcmp'] > 0:
        add('fp_flag_unreflected', 'medium' if irf and irf['fcmp'] == 0 else 'low',
            'machine has %d comis/ucomis; IR fcmp=%d (comis lowered via __asm helper without CPU-flag semantics)' % (mach['fpcmp'], irf['fcmp'] if irf else -1))
    if mach and route == 'ir' and mach['repstr'] > 0:
        add('rep_string_helper', 'low', 'machine has %d rep movs/stos' % mach['repstr'])
    if route == 'clift':
        # x64c 固有の類型 (C 転写 route)。既存類型のうち lift 産物に IR が無いため出せないものは
        # irf=None で自動抑止され、さらに静的特徴のみの低確信度タグは route='ir' のみに限定した。
        d = diffs.get('ret') or {}
        if 'xmm0' in diffs or (('native_x0' in d or 'wasm_x0' in d) and not diffs.get('mem')):
            add('xmm_result', 'medium', 'xmm0 (x0) return differs while memory writes agree: FP/MMX/SIMD result semantics (cvt/pack/saturate/round) diverge')
        if mach and mach.get('simdint', 0) > 0 and ('mem' in diffs or 'ret' in diffs):
            add('simd_int_semantics', 'medium', 'machine has %d packed-int (MMX/SSE2) ops and results differ: packed byte/word semantics (saturation, packus/pmulhuw, MMX XMM-non-alias)' % mach['simdint'])
        nul = 0
        uva = None
        for cs in bad:
            w = cs.get('_w', {}) or {}
            k = int(w.get('unlifted', 0) or 0)
            if k:
                nul += k
                uva = w.get('unlifted_va')
        if nul:
            add('unlifted_callee', 'high', 'wasm ret-0-continued over %d indirect call(s) to VAs outside the x64c lift closure (last %s); native executed the real callee' % (nul, uva))
    if irf and irf['asm_calls'] > 0 and not tags:
        add('simd_helper', 'low', 'IR calls %d __asm_* helper(s)' % irf['asm_calls'])
    if 'ret' in diffs and not ('mem' in diffs or 'calls' in diffs or 'trace' in diffs) and not tags:
        add('ret_only', 'low', 'only return value differs (void-like function may leave rax undefined)')
    if 'mem' in diffs and not tags:
        add('memory_semantics', 'medium', 'native/wasm memory write sets differ (first: %s)' % (diffs['mem']['first'][0] if diffs['mem'].get('first') else ''))
    for cs in bad:
        if cs['outcome'] == 'wasm_trap':
            add('wasm_trap', 'high', '%s: %s' % (trap_kind(cs.get('wasm_detail')), (cs.get('wasm_detail') or '')[:160]))
    if not tags:
        add('other', 'low', 'unclassified diff: %s' % ','.join(sorted(diffs)))
    return tags


def verdict(rec):
    cs = rec.get('cases', [])
    if any(c['outcome'] in ('diff', 'wasm_trap') for c in cs):
        return 'mismatch'
    if any(c['outcome'] == 'equal' for c in cs):
        return 'match'
    return 'unexec'


def unexec_reason(rec):
    cs = rec.get('cases', [])
    if not cs:
        return rec.get('reason', 'no_cases')
    st = [c['outcome'] for c in cs]
    if any(s == 'hang' for s in st):
        return 'hang'
    if any(s == 'wasm_timeout_native_long' for s in st):
        return 'wasm_timeout_native_long'
    nat = [c.get('native_status') for c in cs]
    # 全 case で native が落ちた → 原因分類 (fault addr から)
    faults = [c.get('fault') for c in cs if c.get('fault')]
    low = sum(1 for f in faults if int(f['addr'], 16) < 0x10000)
    if any(n == 'timeout' for n in nat):
        return 'native_timeout'
    if any(n == 'sigill' for n in nat):
        return 'native_sigill'
    if faults and low == len(faults):
        return 'native_null_deref_all_patterns'
    return 'native_fault_all_patterns'
