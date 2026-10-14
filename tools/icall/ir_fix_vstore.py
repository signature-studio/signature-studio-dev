#!/usr/bin/env python3
"""ir_fix_vstore.py IN.ll OUT.ll — RetDec が xmm の「レジスタ→メモリ」store (vmovapd/vmovaps/vmovdqa/vmovdqu/vmovups/vmovupd/
   movaps/movapd/movdqa/movdqu/movups/movupd [mem], xmm) を **store でなく void helper 呼出し** に落とした箇所を store に戻す。

   症状 (ICALL-6 / #361): `vmovapd [rsp+0x40], xmm0` が
       %5 = load i128, i128* %0                       ; エントリで stack slot の「値」を 1 回 load
       call void @__asm_vmovapd.22(i128 %5, i128 %10) ; 第 1 引数 = 宛先の旧値, 第 2 引数 = 書込む値 (helper は何もしない)
   になり、同じ slot を読む後続の `vmovapd xmm1, [rsp+0x40]` は `call i128 @__asm_vmovapd(i128 %5)` = 旧値 (未初期化)。
   AVX/FMA3 版 CRT tan (1801a9be0) の大引数経路 (|x| >= 0.84 付近) が 1801aa0d6 で未初期化値を使い 42/600 になっていた。

   修復: 宛先値 %D が `load i128, i128* %P` (%P = 関数内の alloca) の場合だけ、%D 専用の alloca を新設し
       call void @__asm_X(i128 %D, i128 %S)  →  store i128 %S, i128* %vst.N
       %D の他の使用 (reload)                →  直前に `%vld.K = load i128, i128* %vst.N` を挿入して置換
   %P が alloca でない (グローバル/ポインタ) 場合は意味を決められないので触らず unresolved として数える。
   出力: JSON 1 行 {"vstore_fixed": N, "vstore_reloads": M, "vstore_unresolved": K, "unresolved_detail": [...]}。
   unresolved が非 0 でも exit 0 (対象 PE に該当があるだけで、修復済みの結果は有効; 件数は REPORT の台帳)。
   --direct (opt-in, #1025): 宛先 %D が alloca 以外のポインタ %P の load で、%D の使用が load と helper 呼出しの 2 箇所だけなら、
   helper 呼出しを `store i128 %S, i128* %P` に置き換える (movups [mem], xmm の宛先が self+N 等の引数由来のとき消えていた store)。
   既定 off: OTT/FA 経路は従来どおり (未検証の経路を巻き込まない)。"""
import json, re, sys
from collections import Counter

NAMES = r'(?:v?mov(?:aps|apd|dqa|dqu|ups|upd))'
DROP = re.compile(r'^(?P<i>\s*)call void @__asm_(?P<n>' + NAMES + r')(?:[.\w]*)\(i128 (?P<d>%[\w.]+), i128 (?P<s>%[\w.]+|-?\d+)\)(?P<md>, !insn\.addr !\d+)?[ \t]*$')
DROP_ANY = re.compile(r'^\s*call void @__asm_(?P<n>' + NAMES + r')(?:[.\w]*)\((?P<a>.*)\)(?:, !insn\.addr !\d+)?[ \t]*$')
LOAD = re.compile(r'^\s*(?P<d>%[\w.]+) = load i128, i128\* (?P<p>%[\w.]+)(?:, align \d+)?(?:, !insn\.addr !\d+)?[ \t]*$')
ALLOCA = re.compile(r'^\s*(?P<d>%[\w.]+) = alloca i128\b')


def fix_function(lines, st):
    allocas, loads = set(), {}
    last_alloca = -1
    for k, ln in enumerate(lines):
        m = ALLOCA.match(ln)
        if m:
            allocas.add(m.group('d'))
            last_alloca = k
            continue
        m = LOAD.match(ln)
        if m:
            loads[m.group('d')] = m.group('p')
    fix = {}   # %D -> new alloca
    direct = {}   # %D -> 宛先ポインタ (alloca 以外。%D の使用が load と helper 呼出しの 2 箇所だけなら store を直接置く)
    uses = Counter(t for ln in lines for t in re.findall(r'%[\w.]+', ln))
    for ln in lines:
        m = DROP.match(ln)
        if m:
            d = m.group('d')
            if d in loads and loads[d] in allocas:
                fix.setdefault(d, '%%vst.%d' % (st['n'] + len(fix)))
            elif d in loads and uses[d] == 2 and st['direct_on']:
                direct[d] = loads[d]
            else:
                st['unres'].append({'dst': d, 'line': ln.strip()[:120]})
            continue
        m = DROP_ANY.match(ln)
        if m:
            st['unres'].append({'dst': None, 'line': ln.strip()[:120]})
    if not fix and not direct:
        return lines
    # phi が %D を使うと挿入位置が決まらない → その %D は触らない
    for d in list(fix):
        pat = re.compile(r'\bphi\b.*' + re.escape(d) + r'(?![\w.])')
        if any(pat.search(ln) for ln in lines):
            st['unres'].append({'dst': d, 'line': 'used by phi'})
            del fix[d]
    st['n'] += len(fix)
    out = []
    for k, ln in enumerate(lines):
        m = DROP.match(ln)
        if m and m.group('d') in fix:
            out.append('%sstore i128 %s, i128* %s%s' % (m.group('i'), m.group('s'), fix[m.group('d')], m.group('md') or ''))
            st['fixed'] += 1
            continue
        if m and m.group('d') in direct:
            out.append('%sstore i128 %s, i128* %s%s' % (m.group('i'), m.group('s'), direct[m.group('d')], m.group('md') or ''))
            st['direct'] += 1
            continue
        m = LOAD.match(ln)
        if m and m.group('d') in fix:
            out.append(ln)   # 定義 (未使用になるが残す: 他の SSA 番号を変えない)
            continue
        for d, a in fix.items():
            if re.search(re.escape(d) + r'(?![\w.])', ln) and not ALLOCA.match(ln):
                st['reloads'] += 1
                tmp = '%%vld.%d' % st['r']
                st['r'] += 1
                indent = re.match(r'\s*', ln).group(0)
                out.append('%s%s = load i128, i128* %s' % (indent, tmp, a))
                ln = re.sub(re.escape(d) + r'(?![\w.])', tmp, ln)
        out.append(ln)
        if k == last_alloca:
            for a in fix.values():
                out.append('  %s = alloca i128' % a)
    if fix and last_alloca < 0:
        raise SystemExit('ir_fix_vstore: alloca 無し関数に修復対象 (想定外)')
    return out


def main():
    src, dst = [a for a in sys.argv[1:] if not a.startswith('--')][:2]
    lines = open(src, errors='replace').read().split('\n')
    st = {'n': 0, 'r': 0, 'fixed': 0, 'direct': 0, 'direct_on': '--direct' in sys.argv, 'reloads': 0, 'unres': []}
    out, i = [], 0
    while i < len(lines):
        if lines[i].startswith('define '):
            j = i
            while not lines[j].startswith('}'):
                j += 1
            out.extend(fix_function(lines[i:j], st))
            i = j
            continue
        out.append(lines[i])
        i += 1
    open(dst, 'w').write('\n'.join(out))
    print(json.dumps({'vstore_fixed': st['fixed'], 'vstore_direct': st['direct'], 'vstore_reloads': st['reloads'], 'vstore_unresolved': len(st['unres']), 'unresolved_detail': st['unres'][:20]}))


if __name__ == '__main__':
    main()
