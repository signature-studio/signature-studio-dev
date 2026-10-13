#!/usr/bin/env python3
"""[P-T2] 定義済み関数の `i32` 仮引数がポインタとして使われる形 (E3) の修復 (plugins 追加 pass; #1485)。

観測 (BooBass_Eng 21202 `function_180049450(i64 %arg1, i32 %arg2)`): 本体は `inttoptr i64 %arg2 to ptr` で
ポインタとして読むが、仮引数が i32 のため clang が "'%argN' defined with type 'i32' but expected 'i64'" で拒否する。
ネイティブは第 2 引数レジスタ (rdx) の 64bit 全体をポインタとして使うため、呼出側の `trunc i64 %W to i32` は
上位 32bit を捨ててネイティブと不一致になる。よって:
  - define / declare の `i32 %argN` 仮引数 → `i64` (本体の `icmp eq i32 %argN, C` も `i64` に揃える)
  - module 内 call site の `i32 %V` 実引数 → 定義元が `%V = trunc i64 %W to i32` なら `%V = add i64 %W, 0` (上位ビットを保つ)
    それ以外 (`i32 0` 等の定数) → `i64 0` (値は同じ)
  - 対象は「本体で `inttoptr i64 %argN` として使われる i32 仮引数」を持つ関数のみ (`--func` で指定。既定は空)
  - 他の関数の `i32` 署名には触れない (呼出元の署名を変えると範囲が広がるため、`function_180056120` のような
    外側の `i32` 署名は別途扱う)
使い方: fix_i32_ptr_arg.py IN.ll OUT.ll --func function_180049450 [--report R.json]"""
import re, sys, json


def process(text, funcs):
    lines = text.split('\n')
    report = []
    for fn in funcs:
        ddef = re.compile(r'^define (\S+) @' + re.escape(fn) + r'\((.*?)\)(.*)$')
        idx = None
        for i, l in enumerate(lines):
            m = ddef.match(l)
            if m:
                idx = i
                break
        if idx is None:
            continue
        m = ddef.match(lines[idx])
        args = [a.strip() for a in m.group(2).split(',') if a.strip()]
        pos = []
        for k, a in enumerate(args):
            t = a.split()
            if len(t) == 2 and t[0] == 'i32' and t[1].startswith('%arg'):
                pos.append((k, t[1]))
        if not pos:
            continue
        # 本体が inttoptr i64 %argN として使うものだけ対象にする
        end = idx
        while end < len(lines) and not lines[end].startswith('}'):
            end += 1
        body = lines[idx:end + 1]
        ptr_args = [(k, nm) for (k, nm) in pos
                    if any(re.search(r'inttoptr i64 ' + re.escape(nm) + r' to ptr', b) for b in body)]
        if not ptr_args:
            continue
        names = {nm for (_, nm) in ptr_args}
        new_args = []
        for k, a in enumerate(args):
            if any(k == kk for kk, _ in ptr_args):
                new_args.append('i64 ' + a.split()[1])
            else:
                new_args.append(a)
        lines[idx] = 'define %s @%s(%s)%s' % (m.group(1), fn, ', '.join(new_args), m.group(3))
        for j in range(idx + 1, end + 1):
            for nm in names:
                lines[j] = re.sub(r'icmp (eq|ne) i32 ' + re.escape(nm) + r', ', r'icmp \1 i64 ' + nm + ', ', lines[j])
        # 呼出側: call i64 @fn(..., i32 X) の i32 実引数を i64 にする
        call = re.compile(r'(call \S+ @' + re.escape(fn) + r'\()(.*)\)')
        for j, l in enumerate(lines):
            if j == idx or not call.search(l):
                continue
            cm = call.search(l)
            parts = [p.strip() for p in cm.group(2).split(',')]
            changed = False
            for k, _ in ptr_args:
                if k >= len(parts):
                    continue
                p = parts[k]
                if p.startswith('i32 '):
                    v = p[4:].strip()
                    if re.match(r'^-?\d+$', v):
                        parts[k] = 'i64 ' + v
                    else:
                        parts[k] = 'i64 ' + v
                        # 定義元が trunc i64 %W to i32 なら同値の add に置換して上位ビットを保つ
                        for q in range(j - 1, max(0, j - 12), -1):
                            dm = re.match(r'^(\s*)' + re.escape(v) + r' = trunc i64 (%\S+) to i32\s*$', lines[q])
                            if dm:
                                lines[q] = '%s%s = add i64 %s, 0' % (dm.group(1), v, dm.group(2))
                                break
                            if lines[q].startswith('define'):
                                break
                    changed = True
            if changed:
                lines[j] = l[:cm.start(2)] + ', '.join(parts) + ')' + l[cm.end():]
                report.append({'func': fn, 'line': j + 1, 'call': True})
        report.append({'func': fn, 'args': sorted(names), 'define': True})
    return '\n'.join(lines), report


def main():
    argv = sys.argv[1:]
    funcs = []
    rep = None
    while '--func' in argv:
        i = argv.index('--func')
        funcs.append(argv[i + 1])
        del argv[i:i + 2]
    if '--report' in argv:
        i = argv.index('--report')
        rep = argv[i + 1]
        del argv[i:i + 2]
    inp, outp = argv[0], argv[1]
    text = open(inp).read()
    new, report = process(text, funcs)
    open(outp, 'w').write(new)
    print('[P-T2] i32 ptr-arg → i64: %d 件 %s' % (len(report), json.dumps(report)), file=sys.stderr)
    if rep:
        json.dump(report, open(rep, 'w'), indent=1)


if __name__ == '__main__':
    main()
