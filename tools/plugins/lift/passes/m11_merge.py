#!/usr/bin/env python3
# M11 #3b: chunk .ll マージ (複数 RetDec lift の統合). IR 全体を行ベースで走査し
# define 毎に最長 define を登録, global/declare/type は重複除去で連結.
# 使い方: python3 m11_merge.py work/bootN.lift.ll ... -o work/boot_all.ll
import sys, re


def main():
    infiles, out = [], None
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == '-o':
            out = sys.argv[i + 1]
            i += 2
        else:
            infiles.append(sys.argv[i])
            i += 1
    defines = {}
    declares = []
    decls_seen = set()
    globals_seen = {}
    types = []
    types_seen = set()
    header = []
    others = []
    dpat = re.compile(r'^declare \S+ @')
    gpat = re.compile(r'^@([\w.$-]+) = ')
    tpat = re.compile(r'^%([\w.$-]+) = type ')

    for f in infiles:
        lines = open(f).read().split('\n')
        n = len(lines)
        i = 0
        while i < n:
            l = lines[i]
            if l.startswith('define ') and '@' in l:
                nm = '_' if False else re.sub(r'^define \S+ @([\w.$_-]+).*$', r'\1', l)
                m = re.match(r'^define \S+ @([\w.$_-]+)', l)
                if not m:
                    i += 1
                    continue
                nm = m.group(1)
                buf = [l]
                i += 1
                while i < n and not lines[i].startswith('}'):
                    buf.append(lines[i])
                    i += 1
                if i < n:
                    buf.append(lines[i])
                    i += 1
                if nm not in defines:
                    defines[nm] = buf
                continue
            m = dpat.match(l)
            if m and l not in decls_seen:
                decls_seen.add(l)
                declares.append(l)
                i += 1
                continue
            m = gpat.match(l)
            if m:
                const = re.match(r'^@[\w.$-]+ = (?:local_unnamed_addr )?(?:\w[\w\s]*\b)?(?:constant|global)', l)
                if m.group(1) not in globals_seen and re.match(r'^@[\w.$-]+ = ', l):
                    globals_seen[m.group(1)] = l
                    # 1 行グローバル ([N x i8] c"..." / scalar のみ; 配列 expressive ケースは mood)
                    j = l
                    if re.search(r'\] c"', j):
                        # 1 行パス (その行全体が c"...")
                        pass
                    # 行読進め (通常 1 行)
                    i += 1
                    continue
            m = tpat.match(l)
            if m:
                if l not in types_seen:
                    types_seen.add(l)
                    types.append(l)
                i += 1
                continue
            if l.startswith('source_filename') or l.startswith('target ') or l.startswith('; Function') or l.startswith('attributes '):
                if l.startswith('source_filename') or l.startswith('target ') and l not in header:
                    header.append(l)
                i += 1
                continue
            if others is not None and l.startswith('@') is False and l.startswith('%') is False and l.strip():
                if l not in header and not l.startswith('attributes'):
                    others.append(l)
            i += 1

    with open(out, 'w') as f:
        f.write('source_filename = "m11"\n')
        f.write('target datalayout = "e-m:e-p:32:32-p10:8:8-p20:8:8-i64:64-i128:128-f128:64-n32:64-S128-ni:1:10:20"\n')
        for h in header:
            if h.startswith('source_filename') or h.startswith('target '):
                continue
            f.write(h + '\n')
        for t in types:
            f.write(t + '\n')
        f.write('\n')
        for gv in sorted(globals_seen.values()):
            f.write(gv + '\n')
        f.write('\n')
        cnt = 0
        for nm in sorted(defines):
            f.write('\n'.join(defines[nm]) + '\n\n')
            cnt += 1
        for d in declares:
            f.write(d + '\n')
    print('[merge] defines: %d / globals: %d / declares: %d / %s -> %s'
          % (cnt, len(globals_seen), len(declares), ' '.join(infiles), out))


if __name__ == '__main__':
    main()
