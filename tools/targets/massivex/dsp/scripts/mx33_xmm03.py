#!/usr/bin/env python3
"""MX-33 (#3032) 受入 1: xmm0〜3 だけの入口 livein (pdata 始点 seeds の保留 17 件) を分類する。

判定定義 (REPORT_MX33.md §1):
  1. 対象 (f, k∈{0..3}): f の入口から k が定義されずに読まれる読み命令 (mx6_vectorcall.analyze の must-def で列挙)。
  2. 読み命令の幅で分類 (classify_read): S = scalar (下位 32/64 bit) / P = 128 bit (packed 証拠) / A = 曖昧。
  3. 後続追跡 (MX-37 #3774): A の読みのうち次の 2 つは CFG 上で後続の読みを追う。
     - 複写 (xmm_j ← xmm_k): 複写先 xmm_j の値を CFG 上で追う。S の読みは幅の証拠、P の読みは 128 bit の証拠。
       完全上書き (movaps 等の reg/mem 全幅書込) で追跡を止める。追跡できない書込・呼出境界は A。
     - merge (VEX 3 オペランドの cvtsi2* / scalar 算術): 入力 xmm_k の上位は宛先へ素通しされるので、宛先の後続の
       P 読みだけを証拠にする (下位は新しい値で上書きされるので S は証拠にしない)。
  4. 関数: いずれかの k の読みが P なら 128 bit 候補 / 全 k が S なら scalar / それ以外は判定不能。
  5. 独立再計算: CFG を使わない線形走査で、関数範囲内の P 読みの有無を数え、CFG の P ⊆ 線形 P を検査
     (構造上の上限確認にとどまる。同じ逆アセンブラと読み集合 effects() を使う)。

usage: mx33_xmm03.py <pe> <vectorcall.json> <out.json>
       mx33_xmm03.py --selftest
"""
import json
import re
import sys

import capstone
import pefile
from capstone import x86

from mx6_vectorcall import analyze, bits, effects, _regidx, XOR_IDIOM

MERGE_DEST = {'movss', 'movsd', 'movlps', 'movlpd', 'movhps', 'movhpd', 'movhlps', 'movlhps'}
BITWISE = {'andps', 'andnps', 'orps', 'xorps', 'andpd', 'andnpd', 'orpd', 'xorpd'}
FULLW = {'movaps', 'movapd', 'movups', 'movupd', 'movdqa', 'movdqu', 'movntps', 'movntpd', 'movntdq'}
SHUF = {'movddup', 'movsldup', 'movshdup', 'movhlps', 'movlhps'}
SCALAR_CVT = re.compile(r'cvtt?(ss|sd)2si')
SCALAR_CONSUME = re.compile(r'(add|sub|mul|div|min|max|cmp|fn?m(add|sub))')
COPY = {'movaps', 'movapd', 'movups', 'movupd', 'movdqa', 'movdqu'}
CALL_VOLATILE = range(6)  # xmm0-5: call の境界で引数として渡りうる


def base_mnem(ins):
    m = ins.mnemonic
    return m[1:] if m.startswith('v') else m


def classify_read(md, ins, k, literal_cvtsi2=False):
    """xmm_k の読み 1 件を (S|P|A, 理由) に分類する。規則は REPORT_MX33.md §1 の表と一致させる。
    literal_cvtsi2=True は仕様文言 (「cvtsi2ss 等」を scalar 読み) をそのまま使う感度用。"""
    b = base_mnem(ins)
    ops = ins.operands
    roles = [i for i, o in enumerate(ops) if o.type == x86.X86_OP_REG and _regidx(md, o.reg) == k]
    nreg = sum(1 for o in ops if o.type != x86.X86_OP_IMM)
    kept = 1 if nreg == 3 else 0
    dst_is_mem = bool(ops) and ops[0].type == x86.X86_OP_MEM
    if b in MERGE_DEST and kept in roles:
        return 'A', 'merge (保持される部分の素通し)'
    if b.startswith('cvtsi2') and not literal_cvtsi2:
        return 'A', 'cvtsi2 の xmm 入力は上位保持のみ (下位は GPR からの書込)'
    if nreg == 3 and 1 in roles and b.endswith(('ss', 'sd')) and not SCALAR_CONSUME.match(b) and not literal_cvtsi2:
        return 'A', '3 オペランド scalar の上位保持 (下位は別オペランドが使う)'
    if b in BITWISE:
        return 'A', 'bitwise ps/pd (scalar の符号・絶対値にも使われる)'
    if b == 'movlps':
        return 'A', 'movlps (下位 2 float の可能性)'
    if b in ('movhps', 'movhpd') and dst_is_mem:
        return 'P', 'high 64 bit 読み'
    if b in SHUF:
        return 'P', 'shuffle 族'
    if b in FULLW:
        return ('P', 'full-width store') if dst_is_mem else ('A', 'reg-reg 複写 (pass-through)')
    if b in ('movss', 'movsd', 'movlpd', 'movd', 'movq') or SCALAR_CVT.fullmatch(b) or b.endswith(('ss', 'sd')) \
            or (literal_cvtsi2 and b.startswith('cvtsi2')):
        return 'S', 'scalar (下位 32/64 bit)'
    if b.endswith(('ps', 'pd')):
        return 'P', 'packed 演算 (*ps/*pd)'
    if b.startswith('p'):
        return 'P', 'integer SIMD (p*)'
    return 'A', '未分類 (%s)' % b


def copy_pair(md, ins):
    """reg-reg 全幅複写 (xmm_dst ← xmm_src) なら (src, dst)、違えば None。"""
    if base_mnem(ins) not in COPY or len(ins.operands) != 2:
        return None
    d, s = ins.operands
    if d.type != x86.X86_OP_REG or s.type != x86.X86_OP_REG:
        return None
    dst, src = _regidx(md, d.reg), _regidx(md, s.reg)
    return (src, dst) if dst is not None and src is not None else None


def upper_flow_dst(md, ins, k):
    """merge の入力 xmm_k の上位が素通しされる宛先 (VEX 3 オペランドの cvtsi2* / scalar 上位保持)。該当しなければ None。"""
    b = base_mnem(ins)
    ops = ins.operands
    if len(ops) != 3 or ops[0].type != x86.X86_OP_REG or ops[1].type != x86.X86_OP_REG:
        return None
    if _regidx(md, ops[1].reg) != k:
        return None
    if not (b.startswith('cvtsi2') or (b.endswith(('ss', 'sd')) and not SCALAR_CONSUME.match(b))):
        return None
    return _regidx(md, ops[0].reg)


def full_kill(md, ins, t):
    """xmm_t を全幅で上書きする命令か (宛先が t の reg で全幅の書込)。"""
    ops = ins.operands
    if not ops or ops[0].type != x86.X86_OP_REG or _regidx(md, ops[0].reg) != t:
        return False
    b = base_mnem(ins)
    return b in FULLW or b in ('movd', 'movq') or ins.mnemonic in XOR_IDIOM


def follow(md, insns, succ, start, taint0, s_is_evidence, merge=False):
    """insns[start] の後続で taint0 (xmm レジスタ集合) の値を CFG 上で追う。
    P 読み → ('P', 理由)。s_is_evidence なら S 読み → 証拠。どちらでもなければ ('A', 理由)。
    追跡中に、taint の値を読む命令が曖昧 (A) なら A で止める。taint の部分書込 (読まない) は A。
    merge=True は merge の保持上位 (bit 127:64) の追跡。shuffle 族 (movddup 等) は下位 64 bit しか読まないため証拠にしない。"""
    stack = [(s, frozenset(taint0)) for s in succ[start]]
    seen = set()
    evid = False
    while stack:
        k, T = stack.pop()
        if (k, T) in seen or not T:
            continue
        seen.add((k, T))
        ins = insns[k]
        if ins.group(x86.X86_GRP_CALL) and any(t in CALL_VOLATILE for t in T):
            return 'A', 'call 境界で追跡中の値が引数として渡りうる'
        if ins.group(x86.X86_GRP_RET) and 0 in T:
            return 'A', 'ret で追跡中の値 (xmm0 戻り値) が呼出側へ渡る'
        if not succ[k] and not ins.group(x86.X86_GRP_RET) and ins.mnemonic not in ('int3', 'ud2') \
                and any(t in CALL_VOLATILE for t in T):
            return 'A', '関数外への jmp で追跡中の値が引数として渡りうる'
        rd, wr = effects(md, ins)
        if ins.mnemonic == 'vzeroupper':
            wr = 0
        cp = copy_pair(md, ins)
        hit = {t for t in T if rd >> t & 1}
        read_s = set()
        for t in hit:
            cls, why = classify_read(md, ins, t)
            if cls == 'P' and merge and why == 'shuffle 族':
                return 'A', 'merge 上位の読みが shuffle (下位 64 bit のみ読む): %s' % base_mnem(ins)
            if cls == 'P':
                return 'P', why
            if cls == 'S':
                read_s.add(t)
                evid = evid or s_is_evidence
                continue
            if cp is not None and cp[0] == t:
                continue
            return 'A', '追跡中の読みが曖昧: %s (%s)' % (base_mnem(ins), why)
        T2 = set(T)
        for t in T:
            if not (wr >> t & 1):
                continue
            if t in read_s:
                continue
            if full_kill(md, ins, t) and t not in hit:
                T2.discard(t)
                continue
            return 'A', '追跡中の値が部分書込で上書きされる: %s' % base_mnem(ins)
        if cp is not None and cp[0] in T:
            T2.add(cp[1])
        for s in succ[k]:
            stack.append((s, frozenset(T2)))
    if evid:
        return 'S', 'CFG 後続の読みが全て scalar'
    return 'A', 'CFG 後続に幅の証拠なし'


def classify_fn(md, r, literal_cvtsi2=False, bitwise_as_p=False):
    insns, succ = r['cfg']
    idx = {ins.address: i for i, ins in enumerate(insns)}
    reads = {}
    for ins, k in r['undef_reads03']:
        c, why = classify_read(md, ins, k, literal_cvtsi2)
        if bitwise_as_p and why.startswith('bitwise'):
            c = 'P'
        if c == 'A':
            cp = copy_pair(md, ins)
            up = upper_flow_dst(md, ins, k)
            if cp is not None and cp[0] == k:
                c, w = follow(md, insns, succ, idx[ins.address], {cp[1]}, True)
                why = '複写先の後続: %s' % w
            elif up is not None:
                c, w = follow(md, insns, succ, idx[ins.address], {up}, False, merge=True)
                why = ('merge 上位の後続 P 読み: %s' if c == 'P' else 'merge 上位の後続 (A): %s') % w
        reads.setdefault(k, []).append((ins, c, why))
    per_k = {}
    for k, lst in reads.items():
        cl = {c for _, c, _ in lst}
        per_k[k] = 'P' if 'P' in cl else ('S' if cl == {'S'} else 'A')
    return fn_class(per_k), per_k, reads


def fn_class(per_k_cls):
    if any(v == 'P' for v in per_k_cls.values()):
        return '128bit'
    if per_k_cls and all(v == 'S' for v in per_k_cls.values()):
        return 'scalar'
    return 'undetermined'


NC = [
    ('addss xmm0,xmm1; ret', 'f30f58c1c3', 'scalar'),
    ('addps xmm0,xmm1; ret', '0f58c1c3', '128bit'),
    ('movss [rsp+8],xmm0; ret', 'f30f11442408c3', 'scalar'),
    ('movaps [rsp+8],xmm0; ret', '0f29442408c3', '128bit'),
    ('movaps xmm1,xmm0; ret (reg-reg 複写のみ・後続なし)', '0f28c8c3', 'undetermined'),
    ('andps xmm0,xmm1; ret (bitwise → 判定不能)', '0f54c1c3', 'undetermined'),
    ('paddd xmm0,xmm1; ret (integer SIMD)', '660ffec1c3', '128bit'),
    ('movss xmm0,xmm1; ret (k0 は merge のみ・k1 は scalar)', 'f30f10c1c3', 'undetermined'),
    ('vcvtsi2ss xmm0,xmm0,eax; ret (VEX merge のみ)', 'c5fa2ac0c3', 'undetermined'),
    ('movaps xmm1,xmm0; addss xmm1,xmm2; ret (複写 → scalar 読み)', '0f28c8' + 'f30f58ca' + 'c3', 'scalar'),
    ('movaps xmm1,xmm0; addps xmm1,xmm2; ret (複写 → 128 bit 読み)', '0f28c8' + '0f58ca' + 'c3', '128bit'),
    ('movaps xmm1,xmm0; movaps xmm1,[rsp+8]; ret (複写先の全幅上書きで追跡停止)', '0f28c8' + '0f284c2408' + 'c3', 'undetermined'),
    ('vcvtsi2ss xmm0,xmm0,eax; addps xmm0,xmm1; ret (merge の上位 → 128 bit)', 'c5fa2ac0' + '0f58c1' + 'c3', '128bit'),
    ('vcvtsi2ss xmm0,xmm0,eax; addss xmm0,xmm1; ret (merge の後続 scalar は証拠にしない)', 'c5fa2ac0' + 'f30f58c1' + 'c3', 'undetermined'),
    ('vcvtsi2ss xmm0,xmm0,eax; movddup xmm0,xmm0; ret (merge 上位の shuffle は下位 64 bit のみ → 証拠にしない)', 'c5fa2ac0' + 'f20f12c0' + 'c3', 'undetermined'),
    ('vcvtsi2ss xmm0,xmm0,eax; vzeroupper; addps xmm0,xmm1; ret (vzeroupper は xmm 下位を消さない → 128 bit)', 'c5fa2ac0' + 'c5f877' + '0f58c1' + 'c3', '128bit'),
    ('movaps xmm1,xmm0; vzeroupper; addss xmm1,xmm2; ret (vzeroupper 後も複写の後続 scalar → scalar)', '0f28c8' + 'c5f877' + 'f30f58ca' + 'c3', 'scalar'),
]


def new_md():
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    return md


def selftest():
    md = new_md()
    ok = True
    for name, hx, want in NC:
        code = bytes.fromhex(hx)
        dis = '; '.join('%s %s' % (i.mnemonic, i.op_str) for i in md.disasm(code, 0x1000))
        r = analyze(md, code, 0x1000, 0x1000 + len(code), lambda a, n: None)
        got, per_k, _ = classify_fn(md, r)
        good = got == want
        ok &= good
        print('  %-56s [%s] got=%s want=%s %s' % (name, dis, got, want, 'PASS' if good else 'FAIL'))
    print('selftest %s (%d cases)' % ('PASS' if ok else 'FAIL', len(NC)))
    return ok


def main(pe_path, vc_p, out_p):
    if not selftest():
        return 1
    vc = json.load(open(vc_p))
    pe = pefile.PE(pe_path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(pe_path, 'rb').read()
    text = [s for s in pe.sections if s.Characteristics & 0x20000000][0]

    def off(r):
        return text.PointerToRawData + (r - text.VirtualAddress)

    def read_abs(va, n):
        try:
            return pe.get_data(va - base, n)
        except pefile.PEFormatError:
            return None

    md = new_md()

    def population(label):
        return [x for x in vc[label]['rows'] if x['pdata_begin'] and not x['livein45'] and x['livein0_3']]

    pop = population('seeds')
    one_pop = population('one_round')
    rows = []
    for x in pop:
        va, e = int(x['rva'], 16), int(x['end'], 16)
        code = data[off(va):off(va) + (e - va)]
        r = analyze(md, code, base + va, base + e, read_abs)
        assert r is not None and r['livein'] & 0x30 == 0 and r['livein'] & 0xF == int(
            sum(1 << k for k in x['livein0_3'])), x['rva']
        cls, per_k, reads = classify_fn(md, r)
        lin_p = set()
        lin_any = set()
        for ins in md.disasm(code, base + va):
            rd, _ = effects(md, ins)
            for k in range(4):
                if rd >> k & 1:
                    lin_any.add(k)
                    if classify_read(md, ins, k)[0] == 'P':
                        lin_p.add(k)
        rows.append({
            'rva': x['rva'], 'end': x['end'], 'insns': r['insns'], 'livein_k': bits(r['livein'] & 0xF),
            'per_k': {str(k): v for k, v in sorted(per_k.items())}, 'fn_class': cls,
            'fn_class_alt_bitwise_as_P': classify_fn(md, r, bitwise_as_p=True)[0],
            'fn_class_alt_literal_cvtsi2_as_S': classify_fn(md, r, literal_cvtsi2=True)[0],
            'reads': {str(k): [(hex(i.address), i.mnemonic, i.op_str, c, why) for i, c, why in lst]
                      for k, lst in sorted(reads.items())},
            'linear_P_k': sorted(lin_p), 'linear_any_read_k': sorted(lin_any),
        })
    cnt = {c: sum(1 for x in rows if x['fn_class'] == c) for c in ('scalar', '128bit', 'undetermined')}
    cnt_alt = {c: sum(1 for x in rows if x['fn_class_alt_bitwise_as_P'] == c) for c in ('scalar', '128bit', 'undetermined')}
    cnt_lit = {c: sum(1 for x in rows if x['fn_class_alt_literal_cvtsi2_as_S'] == c) for c in ('scalar', '128bit', 'undetermined')}
    lin_ok = all(x['linear_P_k'] for x in rows if x['fn_class'] == '128bit')
    lin_p_n = sum(1 for x in rows if x['linear_P_k'])
    one_same = {x['rva'] for x in one_pop} == {x['rva'] for x in pop}
    res = {'population': len(rows), 'population_one_round_pdata_begin': len(one_pop),
           'population_one_round_same_set': one_same, 'counts': cnt,
           'counts_alt_bitwise_as_P': cnt_alt, 'counts_alt_literal_cvtsi2_as_S': cnt_lit,
           'linear_P_functions': lin_p_n, 'containment_cfg_P_subset_linear_P': lin_ok,
           'rows': rows}
    json.dump(res, open(out_p, 'w'), indent=1, ensure_ascii=False)
    print('population=%d (one_round pdata begin %d, same set=%s)' % (len(rows), len(one_pop), one_same))
    print('counts: scalar=%d 128bit=%d undetermined=%d' % (cnt['scalar'], cnt['128bit'], cnt['undetermined']))
    print('sensitivity: bitwise→P %s | literal cvtsi2→S %s' % (cnt_alt, cnt_lit))
    print('linear P (any k in 0-3) functions=%d | containment CFG-P ⊆ linear-P: %s' % (lin_p_n, lin_ok))
    for x in rows:
        ev = '; '.join('xmm%s: %s' % (k, ', '.join('%s %s[%s]' % (a, m, c) for a, m, o, c, w in v))
                        for k, v in x['reads'].items())
        print('| %s | %s | %s | %s |' % (x['rva'], x['end'], x['fn_class'], ev))
    fail = len(rows) != 17 or not lin_ok or not one_same or sum(cnt.values()) != 17
    print('MX33 受入1 %s' % ('FAIL' if fail else 'PASS'))
    return 1 if fail else 0


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == '--selftest':
        sys.exit(0 if selftest() else 1)
    sys.exit(main(*sys.argv[1:4]))
