#!/usr/bin/env python3
"""fw_cleanup.py — P0a 本体 IR の merge 後クリーンアップ (liftlib base.normalize の補完).

  python3 fw_cleanup.py IN.ll OUT.ll

* [W1] `global/constant [N x i8|i16] %wide-string` 等の未定義 named 定数参照 → zeroinitializer
       (RetDec artifact。liftlib base A5 は `constant` のみなので `global` も塞ぐ)
* [W2] define 済み function_* の declare を除去 (定義と署名が異なる declare が LLVM 検証で衝突するため。
       全 closure 内呼出しは実体定義を直接参照 or dispatch 経由で declare 不要)
* [W3] 空行整理
* [W4] declare 署名衝突 (同一 function_* に複数 declare) → call site 数が最多の署名を採用し,
       少数派 call site に 0 詰め (m11 sigfix の 0 pad 規約; 実測 3 関数 / 5 site)
"""
import re, sys


def main():
    src, dst = sys.argv[1], sys.argv[2]
    defines = set()
    with open(src, errors='replace') as f:
        for line in f:
            m = re.match(r'define \S+ @([\w.$_-]+)\(', line)
            if m:
                defines.add(m.group(1))
    lines = open(src, errors='replace').read().split('\n')
    # [W4] declare 署名衝突の解消 (define 無し function_* が対象)
    decls = {}
    for i, l in enumerate(lines):
        if l.startswith('declare '):
            m = re.match(r'declare \S+ @([\w.$_-]+)\(', l)
            if m and (m.group(1) not in defines or m.group(1).startswith('__asm_')):
                decls.setdefault(m.group(1), []).append(i)
    n4 = 0
    for nm, rows in decls.items():
        if len(rows) < 2:
            continue
        # 各 call の実引数個数を数え, 最多個数の署名を採用 (括弧 depth 考慮の分割)
        from collections import Counter

        def split_call_args(s):
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
            return [p.strip() for p in parts if p.strip()]

        cnt = Counter()
        for l in lines:
            if l is not None and 'call ' in l and '@' + nm + '(' in l:
                j = l.index('@' + nm + '(')
                depth, k = 0, j + len(nm) + 1
                for k in range(k, len(l)):
                    if l[k] == '(':
                        depth += 1
                    elif l[k] == ')':
                        depth -= 1
                        if depth == 0:
                            break
                args = split_call_args(l[j + len(nm) + 1 + 1:k])
                cnt[len(args)] += 1
        if not cnt:
            continue
        best_n = cnt.most_common(1)[0][0]
        kept_row = None
        for r in rows:
            sig = re.match(r'declare \S+ @[\w.$_-]+\(([^)]*)\)', lines[r]).group(1)
            k = len([a for a in sig.split(',') if a.strip()])
            if k == best_n:
                kept_row = r
                break
        if kept_row is None:
            continue
        kept_sig = re.match(r'declare \S+ @[\w.$_-]+\(([^)]*)\)', lines[kept_row]).group(1)
        kept_types = [a.strip().split(' ')[0] for a in kept_sig.split(',') if a.strip()]
        # 宣言を 1 本に絞る
        for r in rows:
            if r != kept_row:
                lines[r] = None
        # 少数派 call site を 0 詰め / 切詰め
        for i, l in enumerate(lines):
            if l is None or 'call ' not in l or '@' + nm + '(' not in l:
                continue
            j = l.index('@' + nm + '(')
            start = j + len(nm) + 1
            depth, k = 0, start
            for k in range(start, len(l)):
                if l[k] == '(':
                    depth += 1
                elif l[k] == ')':
                    depth -= 1
                    if depth == 0:
                        break
            args = split_call_args(l[start + 1:k])
            if len(args) == len(kept_types):
                continue
            tail = l[k + 1:]
            fixed_args = []
            for t, a in zip(kept_types, args):
                fixed_args.append(a)
            while len(fixed_args) < len(kept_types):
                t = kept_types[len(fixed_args)]
                fixed_args.append('i128 0' if t.startswith('i128') else ('ptr null' if 'ptr' in t or t.endswith('*') else ('%s 0' % t)))
            newl = l[:start + 1] + ', '.join(fixed_args) + ')' + tail
            lines[i] = newl
            n4 += 1
    lines = [l for l in lines if l is not None]
    # [W6] call されているが declare も define も無い関数の declare 生成 (call site の型から)
    have_decl = set()
    for l in lines:
        if l.startswith('declare '):
            m = re.match(r'declare \S+ @([\w.$_-]+)\(', l)
            if m:
                have_decl.add(m.group(1))
    from collections import Counter as _C
    sig_cnt = {}
    for l in lines:
        if 'call ' not in l or l.lstrip().startswith('declare'):
            continue
        m = re.match(r'\s*(?:%[\w.-]+ = )?call (\S+) @([\w.$_-]+)\(', l)
        if not m:
            continue
        nm6 = m.group(2)
        if nm6 in defines or nm6 in have_decl:
            continue
        j = l.index('@' + nm6 + '(')
        start = j + len(nm6) + 1
        depth, k = 0, start
        for k in range(start, len(l)):
            if l[k] == '(':
                depth += 1
            elif l[k] == ')':
                depth -= 1
                if depth == 0:
                    break
        inner = l[start + 1:k]
        parts, d2, last2 = [], 0, 0
        for i2, c2 in enumerate(inner):
            if c2 == '(':
                d2 += 1
            elif c2 == ')':
                d2 -= 1
            elif c2 == ',' and d2 == 0:
                parts.append(inner[last2:i2]); last2 = i2 + 1
        parts.append(inner[last2:])
        atys = []
        for p in parts:
            p = p.strip()
            am = re.match(r'^(i\d+\*|%[\w.$]+\*|i\d+|float|double|ptr|void)', p)
            atys.append(am.group(1) if am else 'i64')
        key = (m.group(1), tuple(atys))
        sig_cnt.setdefault(nm6, _C())[key] += 1
    n6 = 0
    decls_out = []
    for nm6, cc in sig_cnt.items():
        (retty, atys), _ = cc.most_common(1)[0]
        decls_out.append('declare %s @%s(%s) local_unnamed_addr' % (retty, nm6, ', '.join(atys)))
        n6 += 1
    if decls_out:
        # 最初の define 行の前に挿入
        for i, l in enumerate(lines):
            if l.startswith('define '):
                lines[i:i] = decls_out
                break
    out = []
    n1 = n2 = 0
    w1 = re.compile(r'^(?P<hd>@[\w.$-]+ = (?:local_unnamed_addr )?(?:internal )?(?:global|constant) \[[0-9]+ x i(?:8|16|32|64)\] )%(?:[\w.\-]+)\s*$')
    for line in lines:
        if '%wide-string' in line or w1.match(line):
            m = w1.match(line)
            if m:
                line = m.group('hd') + 'zeroinitializer\n'
                n1 += 1
        elif line.startswith('declare ') and '@function_' in line:
            m = re.match(r'declare \S+ @([\w.$_-]+)\(', line)
            if m and m.group(1) in defines:
                n2 += 1
                continue
        out.append(line)
    text = '\n'.join(out)
    text = re.sub(r'\n{3,}', '\n\n', text)
    open(dst, 'w').write(text)
    print('[cleanup] wide-string fixed %d / define-dup declares dropped %d / sig-conflict call sites padded %d / missing declares added %d' % (n1, n2, n4, n6))


if __name__ == '__main__':
    main()
