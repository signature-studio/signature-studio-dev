#!/usr/bin/env python3
"""非共通 total2 外の関数 (outside) を参照の種類で分類し、到達しうる根を足した閉包 total3 を作る (#667)。 lift/plugin_closure.py は変更しない。

  closure_unreached.py [--out-dir DIR]    前提: closure_lea.py 実行済み (work/sampler/lea.json・lea/*.ranges.txt) + `source sampler/env.sh`

定義 (closure_indirect.py / closure_lea.py と同じ語彙):
  nonfw   = 非共通関数 (closure_indirect.Pe.nonfw)。 total2 = closure_lea.lea_fixpoint の閉包 (#627)。 outside = nonfw − total2
  (a) RVA32 表   = outside の開始 RVA が、非実行 (IMAGE_SCN_MEM_EXECUTE 0x20000000 が立たない) 初期化済み (0x40) 節に、節先頭から 4 バイト整列の LE u32 として載る (.pdata 除外)
  (b) 命令内即値 = nonfw の本体を capstone で復号し、call/jmp 以外の IMM オペランド値 v が 開始 VA (v = base+RVA: imm_va) または 開始 RVA (v = RVA: imm_rva) に等しい
                 (b_all = 参照元が nonfw の任意の本体、 b_live = 参照元が total2 内の本体)
  (c) call/jmp   = outside 関数からの call/jmp rel32 の先 (outside の呼び元のみ)。 (a)(b) に該当するものを除く
  (c-lea)        = outside 関数からの lea [rip+X] の先 (outside の参照元のみ)。 (a)(b)(c) に該当するものを除く
  (d) 参照なし   = 上記のいずれも無い (排他・優先順位 (a)>(b)>(c)>(c-lea))。 (d) 参照なし の字義 (a)(b)(c) のいずれも無い は別行で併記
  根 (AC2)       = (a) ∪ (b_live)。 (b_all のうち参照元が total2 外だけのものは根にしない: 参照元 (死んだ関数) が到達した時だけ BFS で入る)
  total3         = total2 ∪ 根 から、辺 = call/jmp rel32 ∪ lea [rip+X] ∪ 命令内即値 (imm_va ∪ imm_rva) で BFS した閉包 (辺が全部入っているので 1 回で固定点)
  上界 (参考)    = total2 ∪ (a) ∪ (b_all) から同じ BFS。 字義どおり根 = (a)∪(b) の場合の値
検査 (全て満たさなければ exit 1):
  U1 (i)   別算法: 4 バイト LE 値 (RVA32) を非実行初期化済み節の全オフセットで、即値の VA 下位 32 bit / RVA を nonfw 本体の全オフセットで検索。 capstone 版の集合が byte 走査版の部分集合
  U2 (ii)  固定点の独立検証: total3 の全関数について call/jmp・lea・即値の先が非共通なら total3 に入っている。 根 (a) ∪ (b_live) ⊆ total3
  U3 (iii) total2 ⊆ total3 ⊆ nonfw。 total2 は lea.json (#627) の値と一致
  U4 (iv)  排他合計 (a)+(b)+(c)+(c-lea)+(d) = outside
  U5 (v)   8 バイト VA の dataref (既存の root 定義) を持つ outside 関数が 0 件
出力: work/sampler/unr/block<B>.ranges.txt (total3 の ranges、lift 入力) / work/sampler/unr.json / stdout の表
"""
import argparse, json, os, sys, time

import numpy as np
from capstone import CS_GRP_CALL, CS_GRP_JUMP, CS_OP_IMM

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import closure_indirect as CI  # noqa: E402
import closure_lea as CL  # noqa: E402
import targets  # noqa: E402

WORK = CI.WORK
MASK64 = (1 << 64) - 1
MEM_EXEC, CNT_INIT = 0x20000000, 0x40
U32 = '<u4'


def nonexec_init_sections(pe):
    out = []
    for s in pe.sections:
        ch = s.Characteristics
        if s.Name.rstrip(b'\0') == b'.pdata' or (ch & MEM_EXEC) or not (ch & CNT_INIT):
            continue
        out.append(s.get_data()[:s.Misc_VirtualSize])
    return out


def u32_hits(d, values, shifts):
    """d の 4 バイト LE 値のうち values (np.array of u32) に等しいものの集合。 shifts=(0,) は 4 バイト整列のみ、(0,1,2,3) は全オフセット"""
    hits = set()
    for s in shifts:
        n = (len(d) - s) // 4
        if n <= 0:
            continue
        arr = np.frombuffer(d[s:s + 4 * n], dtype=U32)
        hits.update(arr[np.isin(arr, values)].tolist())
    return hits


def imm_capstone(x, f, starts):
    """call/jmp 以外の命令の IMM オペランドのうち、非共通開始 VA (imm_va) / 非共通開始 RVA (imm_rva) に等しい値の先 (RVA) の 2 集合"""
    va, rv = set(), set()
    for ins in x.md.disasm(x.body(f), x.base + f):
        if ins.group(CS_GRP_CALL) or ins.group(CS_GRP_JUMP):
            continue
        for op in ins.operands:
            if op.type == CS_OP_IMM:
                v = op.imm & MASK64
                if v - x.base in starts:
                    va.add(v - x.base)
                if v in starts:
                    rv.add(v)
    return va, rv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out-dir', default=os.path.join(WORK, 'sampler'))
    ap.add_argument('--lea-json', default=os.path.join(WORK, 'sampler', 'lea.json'))
    a = ap.parse_args()
    cnt = json.load(open(os.path.join(WORK, 'fw_hash_counts.json')))
    lea = json.load(open(a.lea_json))
    os.makedirs(os.path.join(a.out_dir, 'unr'), exist_ok=True)
    out, bad = {}, []
    t_start = time.time()
    for name, blk, _ in targets.SHELLS:
        x = CI.Pe(blk, cnt)
        clo = json.load(open(os.path.join(WORK, 'closure', 'block%05d.json' % blk)))
        entries = [int(v, 16) - x.base for v in clo['entries'].values()]
        calls = lambda f: x.edges(f)[0]
        base, _ = x.bfs(entries, calls)
        cand = sorted(x.nonfw - base)
        roots0 = x.dataref()(cand) if cand else set()
        total, _ = x.bfs(list(base) + sorted(roots0), calls)
        total2, _, _ = CL.lea_fixpoint(x, total, calls)
        nonfw = x.nonfw
        outside = nonfw - total2
        rva_arr = np.array(sorted(nonfw), dtype=U32)
        assert all(x.base + r < 2 ** 32 for r in nonfw), 'VA が 32 bit を超える'
        low = {(x.base + r): r for r in nonfw}
        low_arr = np.array(sorted(v & 0xffffffff for v in low), dtype=U32)
        low_map = {v & 0xffffffff: r for v, r in low.items()}
        secs = nonexec_init_sections(x.pe)

        A_cap = set().union(*(u32_hits(d, rva_arr, (0,)) for d in secs)) if secs else set()
        A_bs = set().union(*(u32_hits(d, rva_arr, (0, 1, 2, 3)) for d in secs)) if secs else set()
        IMM = {f: imm_capstone(x, f, nonfw) for f in nonfw}
        B_va_cap = set().union(*(IMM[f][0] for f in nonfw)) if nonfw else set()
        B_rva_cap = set().union(*(IMM[f][1] for f in nonfw)) if nonfw else set()
        B_va_bs, B_rva_bs = set(), set()
        for f in nonfw:
            b = x.body(f)
            B_va_bs |= {low_map[v] for v in u32_hits(b, low_arr, (0, 1, 2, 3))}
            B_rva_bs |= u32_hits(b, rva_arr, (0, 1, 2, 3))
        c1 = A_cap <= A_bs and B_va_cap <= B_va_bs and B_rva_cap <= B_rva_bs

        A = A_cap & outside
        B_all = (B_va_cap | B_rva_cap) & outside
        B_va = B_va_cap & outside
        B_rva = B_rva_cap & outside
        B_live = {t for f in total2 for t in (IMM[f][0] | IMM[f][1])} & outside
        C = set()
        CLEA = set()
        for g in outside:
            C |= {t for t in x.edges(g)[0] if t in outside}
            CLEA |= {t for t in x.edges(g)[1] if t in outside}
        ex_a = A
        ex_b = B_all - A
        ex_c = C - A - B_all
        ex_cl = CLEA - A - B_all - C
        ex_d = outside - A - B_all - C - CLEA
        d_lit = outside - A - B_all - C
        c4 = len(ex_a) + len(ex_b) + len(ex_c) + len(ex_cl) + len(ex_d) == len(outside)
        c5 = len(x.dataref()(sorted(outside))) == 0 if outside else True

        roots = A | B_live
        x.pe.parse_data_directories(directories=[0])
        ed = getattr(x.pe, 'DIRECTORY_ENTRY_EXPORT', None)
        exp = {s.address for s in ed.symbols if s.address} if ed else set()

        def edge3(f):
            i = IMM.get(f, (set(), set()))
            return x.edges(f)[0] | x.edges(f)[1] | i[0] | i[1]

        total3, _ = x.bfs(sorted(total2 | roots), edge3)
        literal, _ = x.bfs(sorted(total2 | A | B_all), edge3)
        miss = 0
        for f in total3:
            i = IMM.get(f, (set(), set()))
            for t in x.edges(f)[0] | x.edges(f)[1] | i[0] | i[1]:
                if t in nonfw and t not in total3:
                    miss += 1
        root_miss = len(roots - total3)
        c2 = miss == 0 and root_miss == 0
        c3 = total2 <= total3 <= nonfw and (len(total2), x.size(total2)) == (lea[name]['total2_funcs'], lea[name]['total2_bytes'])
        for tag, ok in (('U1 byte 走査の部分集合', c1), ('U2 固定点 (漏れ %d・根の漏れ %d)' % (miss, root_miss), c2),
                        ('U3 total2 ⊆ total3 ⊆ 非共通・total2 が lea.json と一致', c3), ('U4 排他合計 = outside', c4),
                        ('U5 outside の 8 バイト VA dataref 0', c5)):
            if not ok:
                bad.append('%s: %s' % (name, tag))
        open(os.path.join(a.out_dir, 'unr', 'block%05d.ranges.txt' % blk), 'w').write(','.join(x.ranges(total3)))
        cls = lambda s: {'funcs': len(s), 'bytes': x.size(s)}
        out[name] = {
            'block': blk, 'nonfw': cls(nonfw), 'total2': cls(total2), 'outside': cls(outside),
            'excl': {'a': cls(ex_a), 'b': cls(ex_b), 'c': cls(ex_c), 'c_lea': cls(ex_cl), 'd': cls(ex_d)},
            'nonexcl': {'a': cls(A), 'b': cls(B_all), 'b_va': cls(B_va), 'b_rva': cls(B_rva), 'c': cls(C), 'c_lea': cls(CLEA),
                        'd_literal': cls(d_lit)},
            'b_live': cls(B_live), 'roots': cls(roots), 'a_bytescan': len(A_bs), 'b_bytescan_va': len(B_va_bs), 'b_bytescan_rva': len(B_rva_bs),
            'total3': cls(total3), 'increment': {'funcs': len(total3) - len(total2), 'bytes': x.size(total3) - x.size(total2)},
            'literal_upper': cls(literal), 'remaining': cls(nonfw - total3),
            'checks': {'U1': c1, 'U2': c2, 'U3': c3, 'U4': c4, 'U5': c5},
            'export': {'total2': len(exp & total2), 'outside': len(exp & outside), 'd': len(exp & ex_d)}, 'nonfw_bytes_total': x.size(nonfw),
        }
        json.dump({'nonfw': sorted(nonfw), 'total2': sorted(total2), 'outside': sorted(outside), 'd': sorted(ex_d)},
                  open(os.path.join(a.out_dir, 'unr', 'block%05d.sets.json' % blk), 'w'))
        o = out[name]
        print('%s: total3 %d / %d (total2 %d/%d, +%d/%d) 上界 %d / %d 根 %d (b_live %d / b_all %d) U1-U5 %s export∩total2/outside/(d) %d/%d/%d' % (
            name, len(total3), x.size(total3), len(total2), x.size(total2), o['increment']['funcs'], o['increment']['bytes'],
            len(literal), x.size(literal), len(roots), len(B_live), len(B_all), 'PASS' if all(o['checks'].values()) else 'FAIL',
            o['export']['total2'], o['export']['outside'], o['export']['d']))
    fmt = lambda d: '%s / %s' % (format(d['funcs'], ','), format(d['bytes'], ','))
    print('\n| プラグイン | 非共通 関数 / B | total2 関数 / B | outside 関数 / B | (a) RVA32 排他 | (b) 即値 排他 | (c) call/jmp 排他 | (c-lea) 排他 | (d) 参照なし 排他 |')
    print('|---|--:|--:|--:|--:|--:|--:|--:|--:|')
    for name, _, _ in targets.SHELLS:
        o = out[name]
        print('| %s | %s | %s | %s | %s | %s | %s | %s | **%s** |' % (
            name, fmt(o['nonfw']), fmt(o['total2']), fmt(o['outside']), fmt(o['excl']['a']), fmt(o['excl']['b']),
            fmt(o['excl']['c']), fmt(o['excl']['c_lea']), fmt(o['excl']['d'])))
    print('\n| プラグイン | (a) 非排他 | (b) 非排他 (va / rva) | (c) 非排他 | (c-lea) 非排他 | (a)(b)(c) いずれも無い | b_live (根) | 根 | total3 / total2 からの増分 | 上界 (字義の根) | 未到達 (非共通 − total3) |')
    print('|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|')
    for name, _, _ in targets.SHELLS:
        o = out[name]
        print('| %s | %s | %s / %s | %s | %s | %s | %s | %s | %s (+%s) | %s | %s |' % (
            name, fmt(o['nonexcl']['a']), format(o['nonexcl']['b_va']['funcs'], ','), format(o['nonexcl']['b_rva']['funcs'], ','),
            fmt(o['nonexcl']['c']), fmt(o['nonexcl']['c_lea']), fmt(o['nonexcl']['d_literal']), fmt(o['b_live']), fmt(o['roots']),
            fmt(o['total3']), format(o['increment']['funcs'], ','), fmt(o['literal_upper']), fmt(o['remaining'])))
    keys = ('nonfw', 'total2', 'outside', 'total3', 'remaining')
    tot = {k: {s: sum(out[n][k][s] for n, _, _ in targets.SHELLS) for s in ('funcs', 'bytes')} for k in keys}
    print('\n計: total2 %s / outside %s / total3 %s / 未到達 %s' % (fmt(tot['total2']), fmt(tot['outside']), fmt(tot['total3']), fmt(tot['remaining'])))
    out['_sum'] = tot
    json.dump(out, open(os.path.join(a.out_dir, 'unr.json'), 'w'), indent=1)
    for b in bad:
        print('FAIL', b, file=sys.stderr)
    print('closure_unreached: %s (%.1f s)' % ('FAIL %d' % len(bad) if bad else 'PASS 5 checks x %d plugins' % len(targets.SHELLS), time.time() - t_start))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
