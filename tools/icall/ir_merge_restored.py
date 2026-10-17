#!/usr/bin/env python3
"""ir_merge_restored.py — roundtrip.sh の CHUNKS=N が出した after.<i>.restored.ll を 1 本の IR に統合する (ICALL-97 #4290).
  python3 ir_merge_restored.py OUT.ll IN0.ll IN1.ll ...
  - define は chunk 間で重複したら止める (chunk は関数集合の分割なので本来重ならない)
  - declare は同名の define がある・既出のものを捨てる
  - 同名 global は先頭 chunk の定義を採る (cookie の i64/i32 違い等は fa_route_build の ir_fix_cookie が扱う)
  - metadata 番号 (!N) は chunk ごとに後ろへずらす (番号衝突で llvm-link が失敗するため)
  - uselistorder 指令は落とす (llvm-link が拒否する)
"""
import re, sys

MD_DEF = re.compile(r'^!(\d+) = ')
MD_REF = re.compile(r'(?<![\w"])!(\d+)\b')


def main():
    out, ins = sys.argv[1], sys.argv[2:]
    if not ins:
        sys.exit('usage: ir_merge_restored.py OUT.ll IN.ll ...')
    chunks = [open(p, errors='replace').read().split('\n') for p in ins]
    defined = set()
    for ls in chunks:
        for l in ls:
            m = re.match(r'^define [^@]*@([\w.$"-]+)\(', l)
            if m:
                if m.group(1) in defined:
                    sys.exit('duplicate define: ' + m.group(1))
                defined.add(m.group(1))
    head, body = [], []
    seen_top, seen_glob, seen_decl = set(), set(), set()
    meta_base = 0
    for ls in chunks:
        meta_max = -1
        for l in ls:
            m = MD_DEF.match(l)
            if m:
                meta_max = max(meta_max, int(m.group(1)))
        for l in ls:
            if re.match(r'^\s*uselistorder', l):
                continue
            if l.startswith(('source_filename', 'target datalayout', 'target triple')):
                key = l.split(' ')[0]
                if key not in seen_top:
                    seen_top.add(key)
                    head.append(l)
                continue
            m = re.match(r'^(%[\w.$"-]+) = type ', l)
            if m:
                if m.group(1) not in seen_top:
                    seen_top.add(m.group(1))
                    head.append(l)
                continue
            m = re.match(r'^(@[\w.$"-]+) = ', l)
            if m:
                if m.group(1) not in seen_glob:
                    seen_glob.add(m.group(1))
                    head.append(l)
                continue
            m = re.match(r'^declare [^@]*@([\w.$"-]+)\(', l)
            if m:
                if m.group(1) not in defined and m.group(1) not in seen_decl:
                    seen_decl.add(m.group(1))
                    head.append(l)
                continue
            if meta_base:
                l = MD_REF.sub(lambda x: '!%d' % (int(x.group(1)) + meta_base), l)
                l = MD_DEF.sub(lambda x: '!%d = ' % (int(x.group(1)) + meta_base), l)
            body.append(l)
        meta_base += meta_max + 1
    with open(out, 'w') as f:
        f.write('\n'.join(head + body) + '\n')
    print('[merge] chunks %d, defines %d, metadata ids %d' % (len(chunks), len(defined), meta_base))


if __name__ == '__main__':
    main()
