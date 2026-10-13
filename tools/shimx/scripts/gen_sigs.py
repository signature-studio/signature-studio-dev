#!/usr/bin/env python3
"""shimx 公開関数の LLVM 署名表 data/sigs.json を生成する (sig_normalize.py の正本入力)。

  gen_sigs.py [--out data/sigs.json] [--check]

src/*.c を 1 本ずつ `emcc -S -emit-llvm` して外部リンケージの `define` から戻り値型と引数型を拾う。
--check : 生成結果が既存の data/sigs.json と一致しなければ exit 1 (shimx 側の署名変更の取りこぼし検出)。
"""
import argparse, glob, json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
FLAGS = ['-S', '-emit-llvm', '-O0', '-w', '-Wno-error=int-conversion', '-Wno-implicit-function-declaration',
         '-fno-strict-aliasing', '-pthread']
DEF = re.compile(r'^define\s+(?P<pre>[^@\n]*?)@(?P<name>[\w.$-]+)\((?P<args>.*?)\)\s*(?:#\d+|local_unnamed_addr|\{)', re.M)
ATTRS = {'noundef', 'zeroext', 'signext', 'nonnull', 'nocapture', 'readonly', 'writeonly', 'readnone', 'inreg', 'returned',
         'noalias', 'nofree', 'nest'}
SKIP_LINK = {'internal', 'private'}


def split_args(a):
    out, depth, cur = [], 0, ''
    for ch in a:
        if ch in '<[{(':
            depth += 1
        elif ch in '>]})':
            depth -= 1
        if ch == ',' and depth == 0:
            out.append(cur.strip()); cur = ''
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def ptype(p):
    """引数 1 個から型だけを取り出す ('ptr noundef %1' → 'ptr', 'ptr byval(%struct.X) align 4 %1' → 'ptr')"""
    p = p.strip()
    if p == '...':
        return '...'
    return p.split()[0]


def parse_defs(text):
    out = {}
    for m in DEF.finditer(text):
        toks = m.group('pre').split()
        if any(t in SKIP_LINK for t in toks):
            continue
        ret = [t for t in toks if t not in ATTRS and t not in ('dso_local', 'hidden', 'weak', 'weak_odr', 'linkonce_odr',
                                                              'protected', 'default', 'internal', 'private', 'external', 'fastcc', 'ccc')]
        if not ret:
            continue
        out[m.group('name')] = {'ret': ret[-1], 'params': [ptype(p) for p in split_args(m.group('args'))]}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'data', 'sigs.json'))
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    sigs = {}
    with tempfile.TemporaryDirectory() as td:
        for f in sorted(glob.glob(os.path.join(ROOT, 'src', '*.c'))):
            o = os.path.join(td, os.path.basename(f) + '.ll')
            r = subprocess.run(['emcc'] + FLAGS + [f, '-o', o], capture_output=True, text=True)
            if r.returncode != 0:
                print('gen_sigs: emcc 失敗 %s\n%s' % (f, r.stderr[-800:]), file=sys.stderr)
                return 1
            for n, s in parse_defs(open(o).read()).items():
                sigs.setdefault(n, s)
    doc = json.dumps({k: sigs[k] for k in sorted(sigs)}, indent=0, sort_keys=True) + '\n'
    if a.check:
        cur = open(a.out).read() if os.path.exists(a.out) else ''
        if cur != doc:
            print('gen_sigs: %s が shimx ソースと不一致 (python3 scripts/gen_sigs.py で再生成)' % a.out, file=sys.stderr)
            return 1
        print('gen_sigs: %s 一致 (%d 関数)' % (a.out, len(sigs)))
        return 0
    open(a.out, 'w').write(doc)
    print('gen_sigs: %d 関数 -> %s' % (len(sigs), a.out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
