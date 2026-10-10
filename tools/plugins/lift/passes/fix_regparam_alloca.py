#!/usr/bin/env python3
"""[P-R1] RetDec が引数レジスタを「未初期化ローカル alloca」と誤認する形の修復 (plugins 追加 pass)。

観測 (Fruity Balance mix kernel 0x5dee90, `mov r10,r9 ; movups xmm7,[r10]`):
    %r9 = alloca i64                       ; 一度も store されない
    %7  = bitcast ptr %r9 to ptr
    %8  = load i128, ptr %7                ; ← 本来は [arg4] (= r9 の指す先) からの 128bit load
→ MS x64 の第 N 整数引数レジスタ (rcx/rdx/r8/r9 = arg1..arg4) 名の alloca が store 無しで
  bitcast→load/store にのみ使われる場合, その ptr を `inttoptr i64 %argN to ptr` に置換する。

使い方: fix_regparam_alloca.py IN.ll OUT.ll [--report R.json]
"""
import re, sys, json

REG2ARG = {'rcx': 'arg1', 'rdx': 'arg2', 'r8': 'arg3', 'r9': 'arg4'}


def process(text):
    lines = text.split('\n')
    out = []
    fixed = []
    i = 0
    n = len(lines)
    # function ごとに処理
    start = None
    funcs = []
    for idx, l in enumerate(lines):
        if l.startswith('define '):
            start = idx
        elif l.startswith('}') and start is not None:
            funcs.append((start, idx))
            start = None
    repl = {}
    for (s, e) in funcs:
        body = lines[s:e + 1]
        hdr = body[0]
        args = re.findall(r'%(arg\d+)', hdr)
        for k, l in enumerate(body):
            m = re.match(r'^\s*%(rcx|rdx|r8|r9) = alloca (i64|i32)', l)
            if not m:
                continue
            reg = m.group(1)
            a = REG2ARG[reg]
            if a not in args:
                continue
            uses = [j for j, x in enumerate(body) if re.search(r'%' + reg + r'\b', x) and j != k]
            stored = any(re.search(r'store [^,]+, (?:ptr|i\d+\*) %' + reg + r'\b', body[j]) for j in uses)
            if stored:
                continue
            # 全 use が `%X = bitcast ptr %reg to ptr` (または i64* bitcast) のみ
            ok = True
            casts = []
            for j in uses:
                mm = re.match(r'^\s*(%[\w.]+) = bitcast (?:ptr|i64\*) %' + reg + r' to (?:ptr|i\d+\*)\s*$', body[j])
                if not mm:
                    ok = False
                    break
                casts.append((j, mm.group(1)))
            if not ok or not casts:
                continue
            # 置換: alloca 行を削除, bitcast を inttoptr に
            body[k] = ''
            for (j, name) in casts:
                body[j] = '  %s = inttoptr i64 %%%s to ptr' % (name, a)
            fixed.append({'func': re.search(r'@([\w.$]+)', hdr).group(1), 'reg': reg, 'arg': a, 'uses': len(casts)})
        lines[s:e + 1] = body
    return '\n'.join(lines), fixed


def main():
    inp, outp = sys.argv[1], sys.argv[2]
    text = open(inp).read()
    new, fixed = process(text)
    open(outp, 'w').write(new)
    print('[P-R1] regparam alloca → inttoptr(argN): %d 件 %s' % (len(fixed), json.dumps(fixed)), file=sys.stderr)
    if '--report' in sys.argv:
        json.dump(fixed, open(sys.argv[sys.argv.index('--report') + 1], 'w'), indent=1)


if __name__ == '__main__':
    main()
