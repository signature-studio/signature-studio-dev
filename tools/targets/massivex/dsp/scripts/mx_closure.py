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

ENTRY (第 5 引数・既定 any): any = 新入口を制限しない (従来)。pdata = 新入口を .pdata begin に限る (MX-25)。
  pdata_call = (MX-29・flow 専用) 新入口は (a) .pdata begin、または (b) 直接 call rel32 の目標で
           .text 内・thunk 外・文字列窓の外、かつ入口から最初の ret / jmp まで (最大 32 命令) を
           不正命令なしでデコードできるもの。jmp / jcc の目標は (a) の場合だけ入口にする。
           文字列窓 (印字可能 ASCII 8 字以上 + NUL、または UTF-16LE 8 字以上 + U+0000。
           .pdata 関数と重なるものは窓にしない) は flow の code から除外する。

usage: mx_closure.py <pe> <rtti_vtables.json> <out_prefix> [linear|flow] [any|pdata|pdata_call]
"""
import sys, json, pickle, bisect, re, collections, struct
import pefile, capstone

THUNK_LO, THUNK_HI = 0x396e000, 0x3970200
UNDOC = {'fstpnce'}  # D9 D8+i (FSTP1、未文書化の別名)。SDM の命令表に無いため、先頭ブロックの判定で不正扱い
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
LOCKABLE = {'adc', 'add', 'and', 'btc', 'btr', 'bts', 'cmpxchg', 'cmpxchg8b', 'cmpxchg16b', 'dec', 'inc',
            'neg', 'not', 'or', 'sbb', 'sub', 'xadd', 'xchg', 'xor'}
LEGACY_PFX = {0x66, 0x67, 0x2e, 0x36, 0x3e, 0x26, 0x64, 0x65, 0xf2, 0xf3}


def insn_sdm_ok(raw, mn, ops):
    # SDM の LOCK 規則と REX 規則。raw = 命令のバイト列、mn/ops = capstone の出力 (disasm_lite)。
    #   REX: SDM Vol.2 2.2.1 (p.2-8)。REX は直後が opcode (または 0F) でないと無視される。REX の後の F0 は REX を無視するだけで #UD ではない。
    #   LOCK: ロック可能命令・宛先 (Intel 形の先頭オペランド) がメモリ・REP (F2/F3) と併用しない。
    #         HLE 形 (xacquire / xrelease) は F2 / F3 を使うので、その形だけ許す。
    lock, rep = False, []
    for b in raw:
        if b == 0xf0:
            lock = True
        elif 0x40 <= b <= 0x4f:
            continue
        elif b in LEGACY_PFX:
            if b in (0xf2, 0xf3):
                rep.append(b)
        else:
            break
    if not lock:
        return True
    toks = mn.split()
    if 'lock' not in toks or toks[-1] not in LOCKABLE or '[' not in ops.split(',')[0]:
        return False
    if len(rep) > 1:
        return False
    if rep:
        hle = 'xacquire' if rep[0] == 0xf2 else 'xrelease'
        return hle in toks
    return True


def block_ok(md, chunk, va):
    # 入口から最初の ret / jmp まで (最大 32 命令) を不正命令なしでデコードできるか。
    # capstone は不正命令で出力を止めるので、ret / jmp に達せず止まったら不正。
    n = 0
    try:
        for ea, iz, mn, ops in md.disasm_lite(chunk, va):
            if mn in UNDOC:
                return False
            if not insn_sdm_ok(chunk[ea - va:ea - va + iz], mn, ops):
                return False
            n += 1
            if 'ret' in mn.split() or 'jmp' in mn.split() or n >= 32:
                return True
    except capstone.CsError:
        return False
    return False


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

    def pd_overlap(s, e):
        i = bisect.bisect_right(begins, s) - 1
        if i >= 0 and begins[i] + fsz[begins[i]] > s:
            return True
        j = bisect.bisect_left(begins, s)
        return j < len(begins) and begins[j] < e

    # ---- 文字列窓 (MX-29): 印字可能 ASCII (\t\r\n と 0x20-0x7e) 8 字以上 + NUL、
    #      または UTF-16LE の同文字 8 字以上 + U+0000。.pdata 関数と重なるものは窓にしない。
    PRN = rb'\t\r\n\x20-\x7e'
    tx = data[t_raw: t_raw + t.Misc_VirtualSize]
    raw_w = sorted((m.start(), m.end()) for pat in (rb'[%s]{8,}\x00' % PRN,
                                                    rb'(?:[%s]\x00){8,}\x00\x00' % PRN)
                   for m in re.finditer(pat, tx))
    mrg = []
    for s, e in raw_w:
        if mrg and s <= mrg[-1][1]:
            mrg[-1][1] = max(mrg[-1][1], e)
        else:
            mrg.append([s, e])
    WINS = []
    n_pd_drop = 0
    for s, e in mrg:
        if pd_overlap(t_lo + s, t_lo + e):
            n_pd_drop += 1
        else:
            WINS.append((t_lo + s, t_lo + e))
    WS = [w[0] for w in WINS]
    WIN_ON = ENTRY == 'pdata_call'

    def inwin(r):
        i = bisect.bisect_right(WS, r) - 1
        return i if i >= 0 and r < WINS[i][1] else -1

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
        work, ins, cs, cl = [e], set(), set(), set()
        nb = ni = un = 0
        wh = set()
        while work:
            a = work.pop()
            try:
                for ea, iz, mn, ops in md.disasm_lite(data[off(a):off(a) + 4096], base + a):
                    r = ea - base
                    if r in ins or not (e <= r < fb):
                        break
                    if WIN_ON and inwin(r) >= 0:
                        wh.add(inwin(r))
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
                                cl.add(tg)
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
        return cs, cl, nb, ni, un, wh

    LEAF = {}

    def leaf_ok(tg):
        if tg not in LEAF:
            if inwin(tg) >= 0:
                LEAF[tg] = 'win'
            else:
                LEAF[tg] = 'ok' if block_ok(md, data[off(tg):off(tg) + 480], base + tg) else 'bad'
        return LEAF[tg] == 'ok'

    # ---- recursive descent over entry points only
    def admit(tg, call):
        # any: 従来どおり (既定)。pdata: 新入口は .pdata 関数先頭 (begin) に限る (MX-25)。
        # pdata_call: begin、または直接 call の目標で leaf_ok のもの (MX-29)。
        if ENTRY == 'any' or tg in fsz:
            return True
        if ENTRY == 'pdata' or not call:
            return False
        return leaf_ok(tg)
    entries = set(seeds)
    callees = {}
    callall = {}
    WH = set()
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
                cs, cl, nb, ni, un, wh = flow(e, e + sz)
                st['reached'] += nb
                st['insn'] += ni
                st['unres'] += un
                WH.update(wh)
                callall[e] = sorted(cl)
                callees[e] = sorted(tg for tg in cs if admit(tg, tg in cl))
                new |= {tg for tg in callees[e] if tg not in entries}
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
                            if tg not in entries and admit(tg, True):
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

    out = {'pe': path, 'mode': MODE, 'entry': ENTRY, 'rounds_log': rlog,
           'string_windows': {
               'raw_matches': len(raw_w), 'merged': len(mrg), 'pdata_overlap_dropped': n_pd_drop,
               'kept': len(WINS), 'kept_bytes': sum(e - s for s, e in WINS),
               'flow_hit_windows': len(WH),
               'top20_by_len': [[hex(s), e - s] for s, e in sorted(WINS, key=lambda w: -(w[1] - w[0]))[:20]]},
           'leaf': dict(collections.Counter(LEAF.values())),
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
                 'EXPORTS': EXPORTS, 'callall': callall, 'windows': WINS, 'entry': ENTRY},
                open(outp + '_sets.pkl', 'wb'), protocol=4)
    json.dump({'roots': [hex(base + x) for x in sorted(entries)]},
              open(outp + '_x64c_entries.json', 'w'), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    MODE = sys.argv[4] if len(sys.argv) > 4 else 'linear'
    ENTRY = sys.argv[5] if len(sys.argv) > 5 else 'any'
    assert MODE in ('linear', 'flow'), MODE
    assert ENTRY in ('any', 'pdata', 'pdata_call'), ENTRY
    assert ENTRY != 'pdata_call' or MODE == 'flow', 'pdata_call は flow 専用'
    main(sys.argv[1], sys.argv[2], sys.argv[3])
