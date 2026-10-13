#!/usr/bin/env python3
"""[P-S2] fistp qword の上位 dword store 欠落の復元 (opt-in, 関数指定; #982)。

機械語 `fistp qword [m]` は 64bit を 1 回 store するが、RetDec は下位 dword の store しか残さないことがある。
例 0x5de3e0 (機械語):
    fistp qword ptr [rbp+8]
    mov eax, dword ptr [rbp+0xc] ; mov dword ptr [rdx], eax   ; 上位 dword → [rdx]
    mov eax, dword ptr [rbp+8]   ; mov dword ptr [r8], eax    ; 下位 dword → [r8]
RetDec IR では [r8] (%arg3) への下位 store のみが残り、[rdx] (%arg2) の `inttoptr` は未使用になる。

本 pass は次の形の関数だけ対象にする (--func 指定が必須。対象外の関数は触らない):
    %X = fptosi ... to i64                     ; fistp の結果
    %L = trunc i64 %X to i32
    store i32 %L, ptr %P                       ; %P = inttoptr %argK (下位 dword)
    %H = inttoptr i64 %argJ to ptr             ; J != K, %H が未使用 (store が落ちた先)
該当すれば、下位 store の直後に
    %hs = lshr i64 %X, 32 ; %hh = trunc i64 %hs to i32 ; store i32 %hh, ptr %H
を挿入する。上の形が 1 関数に 1 つだけ成立するときのみ書き換える (曖昧なら何もしない)。

使い方: fix_fistp_hi_store.py IN.ll OUT.ll --func function_5de3e0 [--report r.json]
"""
import argparse, json, re

DEF = re.compile(r'^define ')
FPTOSI = re.compile(r'^\s*(%[\w.\-]+) = fptosi .* to i64\s*$')
TRUNC = re.compile(r'^\s*(%[\w.\-]+) = trunc i64 (%[\w.\-]+) to i32\s*$')
STORE32 = re.compile(r'^(\s*)store i32 (%[\w.\-]+), ptr (%[\w.\-]+)(.*)$')
INTPTR = re.compile(r'^\s*(%[\w.\-]+) = inttoptr i64 (%[\w.\-]+) to ptr\s*$')


TERM = re.compile(r'^\s*(br|ret|switch|unreachable|invoke|resume|indirectbr|callbr)\b')
LABEL = re.compile(r'^(\s*[\w.\-]+:|\d+:)')


def same_block(lines, a, b):
    """行 a の定義が行 b の使用より前にあり、間に基本ブロックの境界 (label / 終端命令) が無いこと。"""
    if not a < b:
        return False
    for l in lines[a + 1:b]:
        if LABEL.match(l) or TERM.match(l):
            return False
    return True


def fix_fn(lines):
    """関数本体 lines (define 〜 }) に対し (書換え後の lines, 状態) を返す。"""
    fpt = {}
    trunc = {}
    stores = []
    ptrs = {}
    for i, l in enumerate(lines):
        m = FPTOSI.match(l)
        if m:
            fpt[m.group(1)] = i
        m = TRUNC.match(l)
        if m and m.group(2) in fpt and same_block(lines, fpt[m.group(2)], i):
            trunc[m.group(1)] = (i, m.group(2))
        m = INTPTR.match(l)
        if m:
            ptrs[m.group(1)] = (i, m.group(2))
    uses = {}
    for l in lines:
        for t in re.findall(r'%[\w.\-]+', l):
            uses[t] = uses.get(t, 0) + 1
    for i, l in enumerate(lines):
        m = STORE32.match(l)
        if m and m.group(2) in trunc and same_block(lines, trunc[m.group(2)][0], i):
            stores.append((i, m))
    dead = [p for p in ptrs if uses.get(p, 0) == 1]
    cands = []
    for si, m in stores:
        ti, x = trunc[m.group(2)]
        ent = ptrs.get(m.group(3))
        if ent is None:
            continue
        for h in dead:
            # %H の定義が下位 store より前で同一 basic block 内 (支配違反の IR を出さない)
            if ptrs[h][1] != ent[1] and same_block(lines, ptrs[h][0], si):
                cands.append((si, x, h, m.group(1)))
    if len(cands) != 1:
        return None, len(cands)
    si, x, h, ind = cands[0]
    # 挿入する名前が関数内で未使用であることを確認 (衝突すると再定義になる)
    if uses.get('%fhi_s', 0) or uses.get('%fhi_v', 0):
        return None, 0
    out = list(lines)
    out[si] = lines[si] + '\n%s%%fhi_s = lshr i64 %s, 32\n%s%%fhi_v = trunc i64 %%fhi_s to i32\n%sstore i32 %%fhi_v, ptr %s' % (
        ind, x, ind, ind, h)
    return out, 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('inp')
    ap.add_argument('outp')
    ap.add_argument('--func', action='append', required=True)
    ap.add_argument('--report')
    a = ap.parse_args()
    src = open(a.inp).read().split('\n')
    targets = set(a.func)
    out = []
    rep = {}
    i = 0
    while i < len(src):
        if DEF.match(src[i]):
            j = i
            while not src[j].startswith('}'):
                j += 1
            name = re.search(r'@([\w.\-]+)\(', src[i]).group(1)
            body = src[i:j + 1]
            if name in targets:
                new, n = fix_fn(body)
                rep[name] = 'fixed' if new is not None else 'skipped (candidates=%d)' % n
                if new is not None:
                    body = new
            out.extend(body)
            i = j + 1
            continue
        out.append(src[i])
        i += 1
    missing = sorted(targets - set(rep))
    for f in missing:
        rep[f] = 'not found'
    open(a.outp, 'w').write('\n'.join(out))
    for f in sorted(rep):
        print('[P-S2] %s: %s' % (f, rep[f]))
    if a.report:
        json.dump(rep, open(a.report, 'w'), indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
