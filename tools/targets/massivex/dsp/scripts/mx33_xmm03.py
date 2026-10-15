#!/usr/bin/env python3
"""MX-33 (#3032) 受入 1: xmm0〜3 だけの入口 livein (pdata 始点 seeds の保留 17 件) を分類する。

判定定義 (REPORT_MX33.md §1):
  1. 対象 (f, k∈{0..3}): f の入口から k が定義されずに読まれる読み命令 (mx6_vectorcall.analyze の must-def で列挙)。
  2. 読み命令の幅で分類 (classify_read): S = scalar (下位 32/64 bit) / P = 128 bit (packed 証拠) / A = 曖昧。
  3. 関数: いずれかの k の読みが P なら 128bit 候補 / 全 k が S なら scalar / それ以外は判定不能。
  4. 独立再計算: CFG を使わない線形走査で、関数範囲内の P 読みの有無を数え、CFG の P ⊆ 線形 P を検査
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

from mx6_vectorcall import analyze, bits, effects, _regidx

MERGE_DEST = {'movss', 'movsd', 'movlps', 'movlpd', 'movhps', 'movhpd', 'movhlps', 'movlhps'}
BITWISE = {'andps', 'andnps', 'orps', 'xorps', 'andpd', 'andnpd', 'orpd', 'xorpd'}
FULLW = {'movaps', 'movapd', 'movups', 'movupd', 'movdqa', 'movdqu', 'movntps', 'movntpd', 'movntdq'}
SHUF = {'movddup', 'movsldup', 'movshdup', 'movhlps', 'movlhps'}
SCALAR_CVT = re.compile(r'cvtt?(ss|sd)2si')
SCALAR_CONSUME = re.compile(r'(add|sub|mul|div|min|max|cmp|fn?m(add|sub))')


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


def fn_class(per_k_cls):
    if any(v == 'P' for v in per_k_cls.values()):
        return '128bit'
    if per_k_cls and all(v == 'S' for v in per_k_cls.values()):
        return 'scalar'
    return 'undetermined'


def classify_fn(md, r, literal_cvtsi2=False, bitwise_as_p=False):
    reads = {}
    for ins, k in r['undef_reads03']:
        c, why = classify_read(md, ins, k, literal_cvtsi2)
        if bitwise_as_p and why.startswith('bitwise'):
            c = 'P'
        reads.setdefault(k, []).append((ins, c, why))
    per_k = {}
    for k, lst in reads.items():
        cl = {c for _, c, _ in lst}
        per_k[k] = 'P' if 'P' in cl else ('S' if cl == {'S'} else 'A')
    return fn_class(per_k), per_k, reads


NC = [
    ('addss xmm0,xmm1; ret', 'f30f58c1c3', 'scalar'),
    ('addps xmm0,xmm1; ret', '0f58c1c3', '128bit'),
    ('movss [rsp+8],xmm0; ret', 'f30f11442408c3', 'scalar'),
    ('movaps [rsp+8],xmm0; ret', '0f29442408c3', '128bit'),
    ('movaps xmm1,xmm0; ret (reg-reg 複写のみ)', '0f28c8c3', 'undetermined'),
    ('andps xmm0,xmm1; ret (bitwise → 判定不能)', '0f54c1c3', 'undetermined'),
    ('paddd xmm0,xmm1; ret (integer SIMD)', '660ffec1c3', '128bit'),
    ('movss xmm0,xmm1; ret (k0 は merge のみ・k1 は scalar)', 'f30f10c1c3', 'undetermined'),
    ('vcvtsi2ss xmm0,xmm0,eax; ret (VEX merge のみ)', 'c5fa2ac0c3', 'undetermined'),
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
