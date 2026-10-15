#!/usr/bin/env python3
"""runtime_enum.py: lift 済み関数 (work/lift_text/ott_lifted.c) を走査し、 実行時の 3 論点の該当箇所を列挙する (#3128 PLG-G2-27)。

  python3 runtime_enum.py          列挙を表示し work/runtime_enum.json を書く (exit 0)

 (a) 間接 call (`call reg` / `call dword ptr [...]` のうち IAT 以外) → ott_dispatch 経由の call 先
 (b) AF を読む命令 (lahf・pushf/pushfd・daa・das・aaa・aas) と AF を書く sahf
 (c) fs:/gs: を含む命令 (TEB 参照) を、 読み/書き と offset で分類
入力: work/lift_text/ott_lifted.c (lift_text.py の出力) と work/lift_text/lift_meta.json。
関数ごとに「直接 call の閉包が import (IAT) を通るか」を出す (native 側で import 実装が要るかの判定)。
"""
import collections, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, 'work')
SRC = os.path.join(WORK, 'lift_text', 'ott_lifted.c')
IAT_LO, IAT_HI = 0x10013000, 0x10013400   # .idata の IAT slot (lift_meta の imports と iat_check.py で確認済み)

FN = re.compile(r'^void f_([0-9a-f]+)\(void\) \{$')
INS = re.compile(r'^  /\* ([0-9a-f]+): (.*?) \*/$')


def parse():
    fn = None
    ins = []   # (func, va, text)
    funcs = []
    for line in open(SRC):
        m = FN.match(line.rstrip('\n'))
        if m:
            fn = int(m.group(1), 16)
            funcs.append(fn)
            continue
        m = INS.match(line.rstrip('\n'))
        if m and fn is not None:
            ins.append((fn, int(m.group(1), 16), m.group(2).strip()))
    return funcs, ins


def xcheck_bytes(vas):
    """capstone の mnemonic と無関係に、 命令の先頭バイトだけで数える (別アルゴリズムの検算)。"""
    import pefile
    d = os.environ.get('FL_WIN64_DIR') or os.path.join(os.environ.get('RUNNER_TEMP', ''), 'fl-win64')
    pe = pefile.PE(os.path.join(d, 'extracted', 'block22434_PE.bin'))
    mem = pe.get_memory_mapped_image()
    base = pe.OPTIONAL_HEADER.ImageBase
    cnt = collections.Counter()
    for va in vas:
        b = mem[va - base:va - base + 16]
        i = 0
        while b[i] in (0x66, 0x67, 0xf0, 0xf2, 0xf3):
            i += 1
        op = b[i]
        if op == 0x9f: cnt['lahf 0x9f'] += 1
        elif op == 0x9c: cnt['pushf 0x9c'] += 1
        elif op in (0x27, 0x2f, 0x37, 0x3f): cnt['daa/das/aaa/aas'] += 1
        elif op == 0x9e: cnt['sahf 0x9e'] += 1
        elif op in (0x64, 0x65): cnt['seg fs/gs prefix'] += 1
        if op == 0xff and b[i + 1] >> 3 & 7 in (2, 3):
            cnt['call indirect 0xff/2'] += 1
    return dict(cnt)


def main():
    if not os.path.isfile(SRC):
        sys.exit('[runtime_enum] FAIL: %s が無い (lift_text.py を先に実行)' % SRC)
    funcs, ins = parse()
    fset = set(funcs)
    by_fn = collections.defaultdict(list)
    for f, va, t in ins:
        by_fn[f].append((va, t))
    sites = sorted(set((va, t) for _, va, t in ins))
    print('[enum] 関数 %d・命令の出現 %d (distinct VA %d)' % (len(funcs), len(ins), len({va for _, va, _ in ins})))

    # (a) 間接 call
    ind = []
    for f, va, t in ins:
        m = re.match(r'call (.*)$', t)
        if m and not m.group(1).startswith('0x'):
            tgt = m.group(1)
            iat = re.search(r'\[0x([0-9a-f]+)\]$', tgt)
            kind = 'iat' if iat and IAT_LO <= int(iat.group(1), 16) < IAT_HI else ('mem' if '[' in tgt else 'reg')
            ind.append((f, va, t, kind))
    kinds = collections.Counter(k for *_, k in ind)
    print('[a] 間接 call の出現 %d 件 (distinct VA %d): %s' % (len(ind), len({v for _, v, _, _ in ind}), dict(kinds)))
    print('[a] 間接 call を含む関数 %d (IAT 以外の mem/reg に限ると %d)' % (
        len({f for f, *_, k in ind}), len({f for f, _, _, k in ind if k != 'iat'})))

    # (b) AF
    af_read = [(f, va, t) for f, va, t in ins if re.match(r'(lahf|pushf|pushfd|daa|das|aaa|aas)\b', t)]
    sahf = [(f, va, t) for f, va, t in ins if t.startswith('sahf')]
    print('[b] AF を読む命令 %d 件 (lahf/pushf/pushfd/daa/das/aaa/aas)' % len(af_read))
    print('[b] sahf (AF を書くが runtime は反映しない) %d 件 (distinct VA %d)、含む関数 %d' % (
        len(sahf), len({v for _, v, _ in sahf}), len({f for f, _, _ in sahf})))

    # (c) fs:/gs:
    seg = [(f, va, t) for f, va, t in ins if re.search(r'\b(fs|gs):', t)]
    offs = collections.Counter()
    rw = collections.Counter()
    for f, va, t in seg:
        m = re.search(r'\b(fs|gs):\[(0x[0-9a-f]+|[0-9]+)\]', t)
        off = m.group(2) if m else '?'
        offs[(m.group(1) if m else '?', off)] += 1
        mn = t.split(' ', 1)[0]
        wr = bool(re.match(r'(mov|and|or|add|sub|xor|inc|dec|pop|stos)', mn)) and re.match(r'\S+ (dword|word|byte) ptr (fs|gs):', t) is not None
        rw['write' if wr else 'read'] += 1
    print('[c] fs:/gs: を含む命令 %d 件 (distinct VA %d)、含む関数 %d' % (
        len(seg), len({v for _, v, _ in seg}), len({f for f, _, _ in seg})))
    print('[c] 読み/書き %s' % dict(rw))
    print('[c] セグメント:offset の内訳 %s' % dict(sorted(offs.items())))
    for f, va, t in seg:
        print('[c]   %08x (fn %08x) %s' % (va, f, t))

    # 直接 call 閉包が IAT (import) を通るか
    direct = collections.defaultdict(set)
    for f, va, t in ins:
        m = re.match(r'(?:call|jmp) 0x([0-9a-f]+)$', t)
        if m and int(m.group(1), 16) in fset:
            direct[f].add(int(m.group(1), 16))
    imp_direct = {f for f, va, t in ins if re.match(r'call dword ptr \[0x([0-9a-f]+)\]$', t) and IAT_LO <= int(re.search(r'0x([0-9a-f]+)', t).group(1), 16) < IAT_HI}
    ind_mem = {f for f, *_, k in ind if k != 'iat'}
    def closure(f):
        seen, st = set(), [f]
        while st:
            g = st.pop()
            if g in seen:
                continue
            seen.add(g)
            st.extend(direct.get(g, ()))
        return seen
    pure = {f for f in funcs if not (closure(f) & imp_direct) and not (closure(f) & ind_mem)}
    print('[pure] 直接 call 閉包が IAT も間接 call も含まない関数 %d / %d' % (len(pure), len(funcs)))
    fs_fn = {f for f, *_ in seg}
    print('[c] fs: を含む関数のうち閉包が pure (native で単独実行しやすい) %d / %d: %s' % (
        len(fs_fn & pure), len(fs_fn), ' '.join('%08x' % f for f in sorted(fs_fn & pure))))
    xc = xcheck_bytes(sorted({va for _, va, _ in ins}))
    print('[xcheck] 命令の先頭バイト (接頭辞を除く) で数えた検算: %s' % xc)
    out = {'functions': len(funcs), 'insns': len(ins), 'xcheck': xc,
           'indirect_calls': [{'fn': '%x' % f, 'va': '%x' % v, 'text': t, 'kind': k} for f, v, t, k in ind],
           'af_readers': [{'fn': '%x' % f, 'va': '%x' % v, 'text': t} for f, v, t in af_read],
           'sahf': [{'fn': '%x' % f, 'va': '%x' % v} for f, v, t in sahf],
           'seg': [{'fn': '%x' % f, 'va': '%x' % v, 'text': t} for f, v, t in seg],
           'pure_functions': sorted('%x' % f for f in pure)}
    os.makedirs(WORK, exist_ok=True)
    json.dump(out, open(os.path.join(WORK, 'runtime_enum.json'), 'w'), indent=1)
    print('[enum] wrote %s' % os.path.join(WORK, 'runtime_enum.json'))


if __name__ == '__main__':
    main()
