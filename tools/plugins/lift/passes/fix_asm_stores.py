#!/usr/bin/env python3
"""[P-S1c] 64bit 部分 store (movlps/movlpd/movsd/movss 系) の store 復元 (plugins 追加 pass)。

ir5_patch [S1a] は i128 の movups/movaps/movdqa store しか復元しない。RetDec は
    %old = load i64, ptr %p            ; 書込前の値 (store 先の旧値)
    call void @__asm_movlps__2(i64 %old, i128 %val)    ; movlps [mem], xmm  (下位 64bit を store)
の形で出力する (関数 .2 overload = 戻り void の store 形)。これを
    %lo = trunc i128 %val to i64 ; store i64 %lo, ptr %p
へ置換する。movhps/movhpd は上位 64bit (lshr 64)。
使い方: fix_asm_stores.py IN.ll OUT.ll
"""
import re, sys

PAT = re.compile(r'^(\s*)call void @__asm_(movlps|movlpd|movhps|movhpd|movsd|movq)(?:__\d+|\.\d+)?\(i64 (%[\w.\-]+), i128 (%[\w.\-]+)\)(?:,? ?!?[\w.\- ]*)?\s*$')
PAT32 = re.compile(r'^(\s*)call void @__asm_(movss|movd)(?:__\d+|\.\d+)?\(i32 (%[\w.\-]+), i128 (%[\w.\-]+)\)(?:,? ?!?[\w.\- ]*)?\s*$')


SX_CALL = re.compile(r'^(\s*)(%[\w.\-]+) = call i64 @__asm_(movaps|movups|movdqa|movdqu|movapd|movupd)(?:__\d+|\.\d+)?\(i128 (%[\w.\-]+)\)\s*$')


def fix_trunc_stores(lines):
    """関数単位 (SSA 名は関数ごとに独立) に _fix_trunc_stores_fn を適用"""
    n = 0
    start = None
    for i, l in enumerate(lines):
        if l.startswith('define '):
            start = i
        elif l.startswith('}') and start is not None:
            seg = lines[start:i + 1]
            n += _fix_trunc_stores_fn(seg)
            lines[start:i + 1] = seg
            start = None
    return n


def _fix_trunc_stores_fn(lines):
    """[P-S1d] `%a = call i64 @__asm_movaps__3(i128 %v)` + `%b = sext i64 %a to i128` + `store i128 %b, ptr %p`
    (RetDec の 128bit store 形; 戻り i64 経由で上位 64bit が符号拡張に化ける) → `store i128 %v, ptr %p`"""
    n = 0
    calls = {}
    for i, l in enumerate(lines):
        m = SX_CALL.match(l)
        if m:
            calls[m.group(2)] = (i, m.group(4), m.group(1))
    sext = {}
    for i, l in enumerate(lines):
        m = re.match(r'^\s*(%[\w.\-]+) = (?:sext|zext) i64 (%[\w.\-]+) to i128\s*$', l)
        if m and m.group(2) in calls:
            sext[m.group(1)] = (i, m.group(2))
    for i, l in enumerate(lines):
        m = re.match(r'^(\s*)store i128 (%[\w.\-]+), ptr (%[\w.\-]+)(.*)$', l)
        if m and m.group(2) in sext:
            ci, v, _ = calls[sext[m.group(2)][1]]
            si = sext[m.group(2)][0]
            lines[i] = '%sstore i128 %s, ptr %s%s' % (m.group(1), v, m.group(3), m.group(4))
            lines[ci] = ''
            lines[si] = ''
            n += 1
    return n


def main():
    inp, outp = sys.argv[1], sys.argv[2]
    lines = open(inp).read().split('\n')
    n1d = fix_trunc_stores(lines)
    print('[P-S1d] 128bit store (i64 経由 sext) 復元 %d 件' % n1d, file=sys.stderr)
    # %reg → load 元 ptr (関数内で最近の定義を採用; SSA なので一意)
    loads = {}
    out = []
    n = 0
    miss = 0
    uid = 0
    for l in lines:
        if l.startswith('define '):
            loads = {}
        ml = re.match(r'^\s*(%[\w.\-]+) = load (i64|i32), ptr (%[\w.\-]+)', l)
        if ml:
            loads[ml.group(1)] = (ml.group(2), ml.group(3))
        m = PAT.match(l)
        m32 = PAT32.match(l) if not m else None
        mm = m or m32
        if mm:
            ind, op, old, val = mm.group(1), mm.group(2), mm.group(3), mm.group(4)
            ty = 'i64' if m else 'i32'
            ent = loads.get(old)
            if ent and ent[0] == ty:
                uid += 1
                if op in ('movhps', 'movhpd'):
                    out.append('%s%%s1c_sh%d = lshr i128 %s, 64' % (ind, uid, val))
                    out.append('%s%%s1c_lo%d = trunc i128 %%s1c_sh%d to i64' % (ind, uid, uid))
                else:
                    out.append('%s%%s1c_lo%d = trunc i128 %s to %s' % (ind, uid, val, ty))
                out.append('%sstore %s %%s1c_lo%d, ptr %s' % (ind, ty, uid, ent[1]))
                n += 1
                continue
            miss += 1
        out.append(l)
    open(outp, 'w').write('\n'.join(out))
    print('[P-S1c] partial store 復元 %d 件 (未解決 %d)' % (n, miss), file=sys.stderr)


if __name__ == '__main__':
    main()
