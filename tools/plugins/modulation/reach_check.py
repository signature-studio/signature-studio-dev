#!/usr/bin/env python3
"""閉包の取りこぼし監査: 閉包・frontier の外にある kernel 呼出関数が、閉包から direct call で到達できるか / 他から参照されているかを調べる。
  背景: plugin_closure.py の BFS は framework 共通ハッシュ (13 DLL 以上) の関数 (frontier) で止まる。 そのハッシュは call/jmp の rel32 をゼロ化して作るため、
        呼び先が DLL ごとに違う薄いラッパーも frontier 扱いになり、 その先の DLL 固有関数が閉包にも frontier にも入らない (レビュー指摘、 REPORT §3.1)。
  手順 (DLL ごと):
    A. `.pdata` 全関数 (チェーン unwind を除く) を capstone で線形逆アセンブルし、 call/jmp の即値で別の .pdata 関数の開始 VA を指す辺を集める (plugin_closure.py と同じ辺の定義)。
       あわせて即値・RIP 相対/絶対メモリ operand が関数開始 VA を指す参照、 データ上の 8 バイト VA ポインタ、 .pdata/.xdata 以外の 4 バイト RVA を数える。
    B. 閉包 ranges の関数群を根にして、 A の辺を frontier も越えて BFS (前向き) し、 到達集合と最短経路を得る。
    C. 検算 (別算法 + 別の辺抽出): `.text` を逆アセンブルせず E8 / E9 / EB のバイトパターンから rel32 / rel8 の呼出先を拾った辺 B' を作り (偽陽性を含む上位集合)、
       (1) A の辺が全て B' に含まれること、 (2) 各 target について B' の逆辺 (target から祖先を辿る) で閉包に届くか、 が A の前向き BFS の結果を含意すること、 を確かめる。
       A ⊄ B' (A が B' に無い辺を持つ) または A で到達するのに B' で到達しない target があれば、 測定が不正として exit 1。
    target = scan_dll (p0c/kernel_matrix.py。 framework を除外せず全 .pdata 関数を走査する) が kernel 呼出 site を見つけた関数のうち、 閉包にも frontier にも属さないもの。
    leak = 閉包から A で到達し、 閉包に属さず、 framework 共通ハッシュでもない関数 (= 閉包の定義が取りこぼしている DLL 固有関数)。
usage: reach_check.py [--gate] [--facts work/modulation/facts.json] [--blocks 18978,19144] [--out work/modulation/refs]
  既定: 表を出し、 検算 NG のときだけ exit 1。 leak があっても exit 0 のまま件数を出す (e2e は測定として使う)
  --gate: leak が 1 本でもあれば exit 1
前提: modulation_e2e.sh の closure_facts までを実行済み (work/closure, work/winfuncs, work/fw_hash_counts.json, work/kernel_table.json)。
出力: work/modulation/refs/<block>.json
"""
import argparse, bisect, collections, json, os, re, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, '..')
sys.path.insert(0, os.path.join(P, '..', 'shared'))
from paths import FL_WIN64_DIR  # noqa: E402

EXT = os.path.join(FL_WIN64_DIR, 'extracted')
WORK = os.path.join(P, 'work')
FWTHR = 13
MASK = (1 << 64) - 1


def reach_forward(edges, roots):
    """roots から edges ({src: {dst}}) を BFS。 戻り値 = {node: 親 (roots は None)}。"""
    par = {r: None for r in roots}
    q = collections.deque(sorted(roots))
    while q:
        u = q.popleft()
        for v in sorted(edges.get(u, ())):
            if v not in par:
                par[v] = u
                q.append(v)
    return par


def ancestors(edges, target):
    """target の祖先集合 (target 自身を含む)。 逆辺を作って辿る。"""
    rev = collections.defaultdict(set)
    for u, vs in edges.items():
        for v in vs:
            rev[v].add(u)
    seen = {target}
    st = [target]
    while st:
        u = st.pop()
        for p in rev.get(u, ()):
            if p not in seen:
                seen.add(p)
                st.append(p)
    return seen, rev


def leaks(edges, closure, is_framework):
    """closure から到達し、 closure に属さず、 framework でもない関数の集合。"""
    par = reach_forward(edges, closure)
    return {f for f in par if f not in closure and not is_framework(f)}, par


def crosscheck(edges_a, edges_b, closure, targets):
    """A ⊆ B' と、 A の前向き到達 ⇒ B' の逆向き到達 を確かめる。 戻り値 = (A にあって B' に無い辺, A で到達なのに B' で届かない target, B' でだけ届く target)。"""
    a_not_b = sorted((u, v) for u, vs in edges_a.items() for v in vs if v not in edges_b.get(u, ()))
    par = reach_forward(edges_a, closure)
    miss, extra = [], []
    for t in sorted(targets):
        fwd = t in par
        bwd = bool(ancestors(edges_b, t)[0] & closure)
        if fwd and not bwd:
            miss.append(t)
        if bwd and not fwd:
            extra.append(t)
    return a_not_b, miss, extra


def load_dll(block):
    import pefile
    pe = pefile.PE(os.path.join(EXT, 'block%05d_PE.bin' % block), fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    pd = next(s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata').get_data()
    funcs = {}
    for i in range(len(pd) // 12):
        b, e, u = struct.unpack_from('<III', pd, 12 * i)
        if b and not (u & 1):
            funcs[base + b] = base + e
    return pe, base, funcs


def disasm_edges(pe, base, funcs):
    """A: 線形逆アセンブル由来の辺と、 関数開始 VA への即値 / メモリ operand 参照の件数。"""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
    text = next(s for s in pe.sections if s.Name.startswith(b'.text'))
    tb, tva = text.get_data(), base + text.VirtualAddress
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    fset = set(funcs)
    edges = collections.defaultdict(set)
    sites = collections.defaultdict(list)
    refs = collections.defaultdict(collections.Counter)
    for f in sorted(funcs):
        e = funcs[f]
        for ins in md.disasm(tb[f - tva: e - tva], f):
            jc = ins.mnemonic in ('call', 'jmp')
            for o in ins.operands:
                if o.type == X86_OP_IMM:
                    t = o.imm & MASK
                    if t not in fset:
                        continue
                    if jc:
                        if t != f:
                            edges[f].add(t)
                            sites[t].append((f, ins.address, ins.bytes[0]))
                    else:
                        refs[t]['imm'] += 1
                elif o.type == X86_OP_MEM:
                    m = o.mem
                    if m.base == X86_REG_RIP:
                        t = (ins.address + ins.size + m.disp) & MASK
                        if t in fset:
                            refs[t]['rip'] += 1
                    elif m.base == 0 and m.index == 0 and (m.disp & MASK) in fset:
                        refs[m.disp & MASK]['abs'] += 1
    return edges, sites, refs


def raw_edges(pe, base, funcs):
    """B': E8 / E9 (rel32) / EB (rel8) のバイトパターンから拾った辺 (命令境界を見ないので偽陽性を含む上位集合)。"""
    text = next(s for s in pe.sections if s.Name.startswith(b'.text'))
    tb, tva = text.get_data(), base + text.VirtualAddress
    starts = sorted(funcs)
    fset = set(starts)
    edges = collections.defaultdict(set)
    sites = collections.defaultdict(list)
    for m in re.finditer(rb'(?=[\xe8\xe9\xeb])', tb):
        i = m.start()
        if tb[i] == 0xEB:
            if i + 2 > len(tb):
                continue
            t = tva + i + 2 + struct.unpack_from('<b', tb, i + 1)[0]
        else:
            if i + 5 > len(tb):
                continue
            t = tva + i + 5 + struct.unpack_from('<i', tb, i + 1)[0]
        if t not in fset:
            continue
        va = tva + i
        k = bisect.bisect_right(starts, va) - 1
        if k < 0 or va >= funcs[starts[k]] or starts[k] == t:
            continue
        edges[starts[k]].add(t)
        sites[t].append((starts[k], va))
    return edges, sites


def data_refs(pe, base, funcs):
    """データ上の 8 バイト VA ポインタ (全 section) と、 .pdata / .xdata 以外の 4 バイト RVA。 {関数 VA: [(section, VA)]}"""
    import numpy as np
    fva = np.array(sorted(funcs), dtype=np.uint64)
    frva = np.array(sorted(funcs), dtype=np.int64) - base
    p8, r4 = collections.defaultdict(list), collections.defaultdict(list)
    for s in pe.sections:
        nm = s.Name.rstrip(b'\0').decode('latin1')
        d = s.get_data()
        a = base + s.VirtualAddress
        n8 = len(d) // 8
        if n8:
            arr = np.frombuffer(d[:n8 * 8], dtype='<u8')
            for k in np.nonzero(np.isin(arr, fva))[0]:
                p8[int(arr[k])].append((nm, a + 8 * int(k)))
        if nm in ('.pdata', '.xdata'):
            continue
        n4 = len(d) // 4
        if n4:
            arr = np.frombuffer(d[:n4 * 4], dtype='<u4').astype(np.int64)
            for k in np.nonzero(np.isin(arr, frva))[0]:
                r4[base + int(arr[k])].append((nm, a + 4 * int(k)))
    return p8, r4


def kernel_targets(block, ranges, frontier):
    """scan_dll の kernel 呼出 site を持つ関数のうち、 閉包にも frontier にも属さないもの。 {関数 VA: [kernel 実装 VA(hex)]}"""
    sys.path.insert(0, os.path.join(P, 'p0c'))
    import kernel_matrix as KM
    _, r = KM.scan_dll(block)
    out = collections.defaultdict(list)
    for s in r.get('callsites', []):
        f = int(s['func'], 16)
        if any(a <= f < b for a, b in ranges) or f in frontier:
            continue
        out[f].append(s['kernel'])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--gate', action='store_true')
    ap.add_argument('--facts', default=os.path.join(WORK, 'modulation', 'facts.json'))
    ap.add_argument('--blocks', default='')
    ap.add_argument('--out', default=os.path.join(WORK, 'modulation', 'refs'))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    sys.path.insert(0, os.path.join(P, 'lift'))
    import plugin_closure as PC
    cnt = PC.fw_counts()
    if a.blocks:
        todo = [('block %s' % b, int(b)) for b in a.blocks.split(',')]
    else:
        todo = [(n, f['block']) for n, f in json.load(open(a.facts)).items()]

    print('| プラグイン | block | 閉包 / frontier 関数 | 辺 A / B\' (B\' のみ) | 閉包外 kernel 呼出関数 (site) | うち DLL 固有 (hash < 13 DLL) | うち閉包から direct call で到達 (site) | 到達しない関数の祖先の根: データ参照あり / なし | leak 関数 / B |')
    print('|---|--:|--:|--:|--:|--:|--:|--:|--:|')
    detail = []
    tot = collections.Counter()
    bad = 0
    for name, b in todo:
        c = json.load(open(os.path.join(WORK, 'closure', 'block%05d.json' % b)))
        ranges = [tuple(int(x, 16) for x in r.split('-')) for r in c['ranges']]
        closure = {r[0] for r in ranges}
        frontier = {int(x, 16) for x in c['frontier']}
        pe, base, funcs = load_dll(b)
        hmap = {x[0]: x[2] for x in json.load(open(os.path.join(WORK, 'winfuncs', 'block%05d.json' % b)))['funcs']}
        is_fw = lambda f: hmap.get(f - base) is not None and cnt.get(hmap[f - base], 0) >= FWTHR
        ea, sites_a, refs = disasm_edges(pe, base, funcs)
        eb, sites_b = raw_edges(pe, base, funcs)
        p8, r4 = data_refs(pe, base, funcs)
        kt = kernel_targets(b, ranges, frontier)
        lk, par = leaks(ea, closure, is_fw)
        a_not_b, miss, extra = crosscheck(ea, eb, closure, set(kt))
        nA, nB = sum(len(v) for v in ea.values()), sum(len(v) for v in eb.values())
        nBonly = nB - (nA - len(a_not_b))
        ok = not a_not_b and not miss
        bad += not ok

        def lab(f):
            return '0x%x[%s]' % (f, '閉包' if f in closure else 'frontier' if f in frontier else 'framework' if is_fw(f) else '固有')

        def path(t):
            p = []
            while t is not None:
                p.append(t)
                t = par[t]
            return ' → '.join(lab(x) for x in reversed(p))

        def ext(f):
            return len(p8.get(f, ())) + len(r4.get(f, ())) + sum(refs.get(f, {}).values())

        rows = []
        for f in sorted(kt):
            anc, rev = ancestors(ea, f)
            roots = sorted(x for x in anc if not rev.get(x))
            rows.append({'func': hex(f), 'bytes': funcs[f] - f, 'dll_specific': not is_fw(f), 'hash_dll_count': cnt.get(hmap.get(f - base), 0),
                         'kernel_sites': len(kt[f]), 'kernels': sorted(set(kt[f])), 'reachable_from_closure': f in par,
                         'path': path(f) if f in par else None,
                         'callers_disasm': len({x[0] for x in sites_a.get(f, ())}), 'callers_rawscan': len({x[0] for x in sites_b.get(f, ())}),
                         'ref_imm_rip_abs': dict(refs.get(f, {})), 'va_ptr': [(s, hex(v)) for s, v in p8.get(f, ())],
                         'rva4': [(s, hex(v)) for s, v in r4.get(f, ())],
                         'ancestors': len(anc), 'ancestors_in_closure': len(anc & closure),
                         'roots': len(roots), 'roots_with_ref': sum(1 for x in roots if ext(x))})
        reach = [r for r in rows if r['reachable_from_closure']]
        no = [r for r in rows if not r['reachable_from_closure']]
        sp = [r for r in rows if r['dll_specific']]
        rw = sum(r['roots_with_ref'] for r in no)
        rwo = sum(r['roots'] - r['roots_with_ref'] for r in no)
        lbytes = sum(funcs[f] - f for f in lk)
        print('| %s | %d | %d / %d | %d / %d (%d) | %d (%d) | %d | %d (%d) | %d / %d | %d / %d |' % (
            name, b, len(closure), len(frontier), nA, nB, nBonly, len(rows), sum(r['kernel_sites'] for r in rows), len(sp),
            len(reach), sum(r['kernel_sites'] for r in reach), rw, rwo, len(lk), lbytes))
        for k, v in (('A', nA), ('B', nB), ('leak', len(lk)), ('leak_bytes', lbytes), ('targets', len(rows)), ('sp', len(sp)), ('reach', len(reach)),
                     ('reach_sites', sum(r['kernel_sites'] for r in reach)), ('leak_dll', 1 if lk else 0), ('reach_dll', 1 if reach else 0)):
            tot[k] += v
        detail.append((name, b, rows, ok, a_not_b, miss, extra, sorted(lk), lab))
        json.dump({'block': b, 'closure_funcs': len(closure), 'frontier_funcs': len(frontier), 'edges_A': nA, 'edges_Braw': nB, 'edges_Braw_only': nBonly,
                   'leak_funcs': [{'func': hex(f), 'bytes': funcs[f] - f, 'path': path(f)} for f in sorted(lk)], 'leak_bytes': lbytes, 'targets': rows,
                   'crosscheck': {'A_not_in_B': [[hex(u), hex(v)] for u, v in a_not_b], 'fwd_reach_but_bwd_not': [hex(x) for x in miss],
                                  'bwd_reach_only': [hex(x) for x in extra]}},
                  open(os.path.join(a.out, '%d.json' % b), 'w'), indent=1)
    print('| 計 | | | %d / %d | %d | %d | %d (%d) | | %d / %d |' % (tot['A'], tot['B'], tot['targets'], tot['sp'], tot['reach'], tot['reach_sites'], tot['leak'], tot['leak_bytes']))
    print()
    for name, b, rows, ok, a_not_b, miss, extra, lkl, lab in detail:
        print('### %s (block %d) 検算 %s' % (name, b, 'OK' if ok else 'NG'))
        for u, v in a_not_b[:5]:
            print('  NG: A の辺 0x%x → 0x%x が B\' に無い' % (u, v))
        for t in miss[:5]:
            print('  NG: 0x%x は A の前向きで到達、 B\' の逆向きで届かない' % t)
        for t in extra[:5]:
            print('  info: 0x%x は B\' の逆向きでだけ届く (偽陽性候補の辺経由)' % t)
        for r in rows:
            if not (r['reachable_from_closure'] or r['callers_disasm']):
                continue
            print('  kernel 呼出関数 %s %d B (同一ハッシュ %d DLL) site %d  callers(disasm/raw)=%d/%d  参照(imm,rip,abs)=%s va_ptr=%d rva4=%d  祖先 %d (閉包内 %d) 根 %d (データ参照あり %d)' % (
                r['func'], r['bytes'], r['hash_dll_count'], r['kernel_sites'], r['callers_disasm'], r['callers_rawscan'], r['ref_imm_rip_abs'] or '{}',
                len(r['va_ptr']), len(r['rva4']), r['ancestors'], r['ancestors_in_closure'], r['roots'], r['roots_with_ref']))
            if r['path']:
                print('      経路: ' + r['path'])
        print('  (上記以外の kernel 呼出関数 %d 本: 呼出元なし かつ 閉包から到達しない)' % sum(1 for r in rows if not (r['reachable_from_closure'] or r['callers_disasm'])))
        print('  leak %d 関数: %s' % (len(lkl), ', '.join('0x%x' % f for f in lkl)))
    print('reach_check: 検算 %s (NG %d 本) / 閉包外の kernel 呼出関数 %d 本のうち閉包から direct call で到達 %d 本 (%d 本の殻)、 DLL 固有 (hash < %d DLL) %d 本 / leak (閉包から到達する閉包外の DLL 固有関数) のある殻 = %d/%d 本' % (
        'OK' if not bad else 'NG', bad, tot['targets'], tot['reach'], tot['reach_dll'], FWTHR, tot['sp'], tot['leak_dll'], len(todo)))
    sys.exit(1 if bad or (a.gate and tot['leak_dll']) else 0)


if __name__ == '__main__':
    main()
