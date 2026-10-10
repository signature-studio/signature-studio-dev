#!/usr/bin/env python3
"""fw_cefix.py — m5 ir5_patch A9L 挿入命令の型補完 + LLVM 21 で廃止された constexpr の命令化 (hoist).

(1) ソース型欠落: A9L の `zext (i32 <ce> to i64)` 命令化がソース型を落とす → 同一関数内の定義から補完。
(2) 第二項の型重複: `add i32 0, i32 %ceA` (binop の第2項に型 token) → 除去。
(3) inttoptr 幅不一致: `inttoptr i64 %ce(i32) to ptr` → zext 挿入。
(4) 廃止 constexpr の hoist: select / 算術 (add/sub/...) / trunc 系の constexpr を
    「使用行の直前への命令挿入」で置換 (LLVM 21 は select・算術 constexpr を廃止)。
    対象: 命令行の operand 中に出現する select (...) / 算術 (...) / trunc (ty %v to ..) 等。
    inttoptr/ptrtoint/getelementptr のみの木 (数値と @global のみ) は合法のためそのまま残す。

  python3 fw_cefix.py IN.ll OUT.ll
"""
import re, sys

BINOPS = ('add', 'sub', 'mul', 'and', 'or', 'xor', 'shl', 'lshr', 'ashr', 'srem', 'urem', 'sdiv', 'udiv')
HOIST_OPS = ('select', 'trunc', 'zext', 'sext', 'fptrunc', 'fpext', 'sitofp', 'uitofp',
             'fptosi', 'fptoui', 'icmp', 'fcmp') + BINOPS
LEGAL = ('inttoptr', 'ptrtoint', 'getelementptr', 'bitcast')


PRED = ('slt', 'sgt', 'sle', 'sge', 'eq', 'ne', 'ult', 'ugt', 'ule', 'uge',
        'oeq', 'one', 'olt', 'ogt', 'ole', 'oge', 'ord', 'uno', 'ueq', 'une')


def find_groups(s, start=0):
    """(head_word, word_start_idx, open_idx, close_idx, mid_text) の列。head 込みで置換できるように開始位置も返す。"""
    out = []
    i = start
    n = len(s)
    while i < n:
        if s[i] == '(':
            depth = 1
            j = i + 1
            while j < n and depth:
                if s[j] == '(':
                    depth += 1
                elif s[j] == ')':
                    depth -= 1
                j += 1
            m = re.search(r'([A-Za-z][A-Za-z0-9_.]+)\s*$', s[start:i])
            head = m.group(1) if m else ''
            wstart = m.start() if m else i
            if head in PRED:
                m2 = re.search(r'([A-Za-z][A-Za-z0-9_.]+)\s*$', s[start:wstart])
                if m2:
                    head = m2.group(1)
                    wstart = m2.start()
            mid = s[wstart + len(head):i].strip()
            out.append((head, wstart, i, j, mid))
            i += 1        # 内部の入れ子 group も列挙する (call 引数内の select 等のため)
        else:
            i += 1
    return out


def split_args(s):
    """top-level コンマ分割 (括弧内は無視)"""
    parts, depth, last = [], 0, 0
    for i, c in enumerate(s):
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        elif c == ',' and depth == 0:
            parts.append(s[last:i])
            last = i + 1
    parts.append(s[last:])
    return [p.strip() for p in parts]


def has_value_ref(s):
    return re.search(r'%[\w.-]+', s) is not None


class Hoister:
    def __init__(self, uid):
        self.uid = uid

    def expr_type(self, text):
        """式 text の LLVM 型を推定 (hoist 判定と命令生成用)"""
        t = text.strip()
        m = re.match(r'^(i\d+|ptr|float|double|half|bf16)\b', t)
        if m:
            return m.group(1)
        m = re.match(r'^([\w%][\w.$*-]*)', t)
        return m.group(1) if m else 'i64'

    def hoist(self, line, indent, emitted):
        """line 内の hoist 対象 constexpr を命令列へ。返値: 置換後の line。
        emitted に本文より前に挿入すべき命令行を積む。"""
        changed = True
        while changed:
            changed = False
            for head, wstart, oi, ci, mid in find_groups(line):
                if head not in HOIST_OPS:
                    continue
                body = line[oi + 1:ci - 1]
                nm = '%%cenh%d' % self.uid()
                if head in ('icmp', 'fcmp'):
                    args = split_args(body)
                    if len(args) != 2:
                        continue
                    ty = self.expr_type(args[0])
                    a1 = re.sub(r'^(i\d+|ptr|float|double|half|bf16)\s+', '', args[0].strip())
                    a2 = re.sub(r'^(i\d+|ptr|float|double|half|bf16)\s+', '', args[1].strip())
                    tmpl = '%s%s = %s %s %s %s, %s' % (indent, nm, head, mid, ty, a1, a2)
                elif head == 'select':
                    args = split_args(body)
                    if len(args) != 3:
                        continue
                    # select (i1 C, T A, T B) — C/T は既に値化済みのはず
                    tmpl = '%s%s = select %s, %s, %s' % (indent, nm, args[0].strip(), args[1].strip(), args[2].strip())
                elif head in ('trunc', 'zext', 'sext', 'fptrunc', 'fpext', 'sitofp', 'uitofp', 'fptosi', 'fptoui'):
                    m = re.match(r'^(.*\S)\s+to\s+([\w]+)$', body)
                    if not m:
                        continue
                    src, toty = m.group(1).strip(), m.group(2)
                    tmpl = '%s%s = %s %s to %s' % (indent, nm, head, src, toty)
                elif head in BINOPS:
                    args = split_args(body)
                    if len(args) != 2:
                        continue
                    ty = self.expr_type(args[0])
                    a1 = re.sub(r'^(i\d+|ptr|float|double|half|bf16)\s+', '', args[0].strip())
                    a2 = re.sub(r'^(i\d+|ptr|float|double|half|bf16)\s+', '', args[1].strip())
                    tmpl = '%s%s = %s %s %s, %s' % (indent, nm, head, ty, a1, a2)
                else:
                    continue
                # 引数内に残る hoist 対象を先に展開 (入れ子 select 等)
                sub = []
                tmpl = self.hoist(tmpl, indent, sub)
                emitted.extend(sub)
                emitted.append(tmpl)
                line = line[:wstart] + nm + line[ci:]
                changed = True
                break
        return line


def main():
    src, dst = sys.argv[1], sys.argv[2]
    lines = open(src, errors='replace').read().split('\n')
    types = {}
    fn = ''
    counters = [0]
    nfix1 = nfix2 = nfix3 = nfix4 = 0
    ce = re.compile(r'^\s*(%[\w.-]+) = (\S+)(?:\s+(.*))?$')
    pat = re.compile(r'^(\s*)(%[\w.-]+) = (zext|sext|trunc) (%[\w.-]+) to (\S+)$')
    bpat = re.compile(r'^(\s*(?:%[\w.-]+ = )?)' + r'(add|sub|mul|and|or|xor|shl|lshr|ashr|srem|urem|sdiv|udiv)' +
                      r' ((?:nuw |nsw |exact )*)(i\d+|ptr|float|double|half|bf16) ([^,]+), (i\d+|ptr|float|double|half|bf16) ([^,\s].*?)(\s*,.*)?$')
    itp = re.compile(r'^(\s*)((?:%[\w.-]+) = )inttoptr i64 (%[\w.-]+) to ptr(\s*(?:,.*)?)$')

    def uid():
        counters[0] += 1
        return counters[0]

    H = Hoister(uid)
    out = []
    for l in lines:
        if l.startswith('define '):
            types = {}
            mfn = re.search(r'@function_([0-9a-f]+)', l)
            fn = mfn.group(1) if mfn else 'x'
            out.append(l)
            continue
        # ---- (3) inttoptr 幅不一致
        m = itp.match(l)
        if m:
            ind, dstv, srcv, tail = m.groups()
            sty = types.get(srcv)
            if sty and sty not in ('i64', 'ptr'):
                nn = '%%cew%d_%s' % (nfix3, fn)
                out.append('%s%s = zext %s %s to i64' % (ind, nn, sty, srcv))
                types[nn] = 'i64'
                l = '%s%sinttoptr i64 %s to ptr%s' % (ind, dstv, nn, tail)
                nfix3 += 1
            if dstv:
                types[dstv.strip().rstrip('=')] = 'ptr'
            out.append(l)
            continue
        # ---- (1) zext/sext/trunc のソース型補完
        m = pat.match(l)
        if m:
            ind, dstv, op, srcv, toty = m.groups()
            sty = types.get(srcv)
            if sty:
                l = '%s%s = %s %s %s to %s' % (ind, dstv, op, sty, srcv, toty)
                types[dstv] = toty
                nfix1 += 1
        else:
            # ---- (2) binop 第2項の型重複除去
            m = bpat.match(l)
            if m:
                head, op, flags, ty1, op1, ty2, op2, tail = m.groups()
                l = '%s%s %s%s %s, %s%s' % (head, op, flags, ty1, op1, op2, tail or '')
                mm = re.match(r'^(%[\w.-]+) = ', head.strip())
                if mm:
                    types[mm.group(1)] = ty1
                nfix2 += 1
        # ---- (4) 廃止 constexpr の hoist (全命令行)
        if l.startswith(('  ', '\t')) and not l.startswith('declare') and not l.startswith('}'):
            ind = l[:len(l) - len(l.lstrip())]
            emitted = []
            newl = H.hoist(l.strip(), ind, emitted)
            if emitted:
                out.extend(emitted)
                l = newl
                nfix4 += 1
        # 型記録
        m = ce.match(l)
        if m:
            name, op, rest = m.group(1), m.group(2), m.group(3) or ''
            ty = None
            if op in ('zext', 'sext', 'trunc', 'fptrunc', 'fpext', 'sitofp', 'uitofp', 'fptosi', 'fptoui', 'ptrtoint'):
                mm = re.search(r' to ([\w]+)$', rest)
                ty = mm.group(1) if mm else None
            elif op in ('icmp', 'fcmp'):
                ty = 'i1'
            elif op == 'select':
                mm = re.search(r',\s*(i\d+|ptr|float|double)\s', rest)
                ty = mm.group(1) if mm else None
            elif op == 'inttoptr':
                ty = 'ptr'
            elif op == 'load':
                mm = re.match(r'([\w*]+)', rest)
                ty = mm.group(1) if mm else None
            elif op in BINOPS:
                mm = re.match(r'((?:nuw |nsw |exact )*)([\w]+)\s', rest)
                ty = mm.group(2) if mm else None
            if ty:
                types[name] = ty
        out.append(l)
    # ---- (5) operand 位置の inttoptr (i64 %local to T) → 命令化 (constexpr に local 値は使えない)
    itp5 = re.compile(r'(?<!= )inttoptr \(i64 (%[\w.-]+) to ([\w*]+)\)')
    nfix5 = 0
    out2 = []
    for l in out:
        if l.startswith(('define', 'declare', '}', '@')) or 'inttoptr (i64 %' not in l:
            out2.append(l)
            continue
        ind = l[:len(l) - len(l.lstrip())]
        # 行頭の自家 inttoptr 命令定義は触らない
        pre5 = []
        while True:
            m5 = itp5.search(l)
            if not m5:
                break
            nn = '%%cew%d_%s' % (nfix5, fn)
            pre5.append('%s%s = inttoptr i64 %s to ptr' % (ind, nn, m5.group(1)))
            l = l[:m5.start()] + nn + l[m5.end():]
            nfix5 += 1
        out2.extend(pre5)
        out2.append(l)
    open(dst, 'w').write('\n'.join(out2))
    print('[cefix] srctype %d / binop2nd %d / inttoptr %d / hoisted %d / operand-inttoptr %d' % (nfix1, nfix2, nfix3, nfix4, nfix5))


if __name__ == '__main__':
    main()
