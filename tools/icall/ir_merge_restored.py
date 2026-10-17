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
ASM_DECL = re.compile(r'^declare (\S+) @(__asm_[\w.$-]+)\((.*?)\)')
ASM_RENAME_BASE = 9000  # 改名 suffix。base_of() (m11_simd2.py) は末尾の __数字 を落とすので、base 名 (movss 等) は変わらない


def asm_rename(chunks):
    # ICALL-126 (#6140): chunk ごとに __asm_* の declare 署名が違う名前 (例: __asm_movss.3 は chunk 0・2 が i64(i128)、chunk 1 が i128(i32))
    # は、統合 IR で先頭 chunk の宣言だけが残り、後続 chunk の call が型不一致になる。LLVM の wasm backend はその call を unreachable の thunk にする。
    # 署名が食い違う名前だけを、chunk ごとに一意な名前 (__asm_<name>__<9000+i>) へ付け替える。declare と call の両方を直す。
    sig = {}
    for ls in chunks:
        for l in ls:
            m = ASM_DECL.match(l)
            if m:
                sig.setdefault(m.group(2), set()).add((m.group(1), m.group(3)))
    conflict = {n for n, s in sig.items() if len(s) > 1}
    if not conflict:
        return chunks, 0
    out = []
    for i, ls in enumerate(chunks):
        if i == 0:
            out.append(ls)
            continue
        pat = re.compile(r'@(' + '|'.join(re.escape(n) for n in sorted(conflict, key=len, reverse=True)) + r')(?![\w.$-])')
        out.append([pat.sub(lambda m: '@%s__%d' % (m.group(1), ASM_RENAME_BASE + i), l) for l in ls])
    return out, len(conflict)


def main():
    out, ins = sys.argv[1], sys.argv[2:]
    if not ins:
        sys.exit('usage: ir_merge_restored.py OUT.ll IN.ll ...')
    chunks = [open(p, errors='replace').read().split('\n') for p in ins]
    chunks, n_renamed = asm_rename(chunks)
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
