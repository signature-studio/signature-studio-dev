#!/usr/bin/env python3
"""[P-T2] 定義済み関数の `i32` 仮引数がポインタとして使われる形 (E3) の修復 (plugins 追加 pass; #1485)。

観測 (BooBass_Eng 21202 `function_180049450(i64 %arg1, i32 %arg2)`): 本体は `inttoptr i64 %arg2 to ptr` で
ポインタとして読むが、仮引数が i32 のため clang が "'%argN' defined with type 'i32' but expected 'i64'" で拒否する。
ネイティブは第 2 引数レジスタ (rdx) の 64bit 全体をポインタとして使うため、`i64` 化して上位ビットを保つ。

使い方: fix_i32_ptr_arg.py IN.ll OUT.ll --func function_180049450 [--report R.json]
  --func は複数可。対象の関数が module に無ければ何もしない。

変換規則 (--func の関数 F だけを対象にする。他の関数の署名には触れない):
  - F の define: 本体で `inttoptr i64 %argN to ptr` として使われる `i32 %argN` 仮引数を `i64 %argN` にする。
    本体の `icmp eq|ne i32 %argN, C` は `i64` 比較に揃える (C は 0..2^31-1 のみ。値が i32/i64 で一致する範囲)。
    それ以外の使い方 (算術・trunc・store 等) が残るなら失敗する。
  - F の declare / call の該当位置の実引数 (`i32 X`):
    - 0..2^31-1 の整数定数 C → `i64 C`
    - `%V = trunc i64 %W to i32` で定義された %V → `%i3x.N = add i64 %W, 0` を call の直前に挿入し、それを渡す
      (同値の 0 拡張でなく上位 32bit を保つ。%V の定義は変えない: 他の i32 使用を壊さないため)
      定義の探索は同一関数内を全行対象に行う (距離制限なし)。
    - それ以外 (仮引数・load 結果など) → 失敗。`i64` 化すると定義と型が合わず不正 IR になるため。
  - 失敗時は出力を書かず、理由を stderr に出して非 0 終了する (lift_ranges.sh は set -e で止まる)。
  - 成功時は分類 (const / trunc / decl) の件数を stderr に出す。--report で呼出ごとの JSON も書く。"""
import re, sys, json

I32_MAX = 2 ** 31 - 1


class PassError(Exception):
    pass


def _close(s, open_idx):
    depth = 0
    for i in range(open_idx, len(s)):
        if s[i] == '(':
            depth += 1
        elif s[i] == ')':
            depth -= 1
            if depth == 0:
                return i
    raise PassError('対応する ")" が無い: %s' % s.strip())


def _split(s):
    parts, depth, cur = [], 0, ''
    for ch in s:
        if ch in '([{<':
            depth += 1
        elif ch in ')]}>':
            depth -= 1
        if ch == ',' and depth == 0:
            parts.append(cur.strip())
            cur = ''
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts


def _fn_end(lines, idx):
    for e in range(idx, len(lines)):
        if lines[e].startswith('}'):
            return e
    raise PassError('関数の終端 "}" が無い (line %d)' % (idx + 1))


def _fn_start(lines, j):
    for s in range(j, -1, -1):
        if lines[s].startswith('define '):
            return s
    raise PassError('呼出 (line %d) を含む define が無い' % (j + 1))


def _trunc_src(lines, j, v, fstart):
    pat = re.compile(r'^\s*' + re.escape(v) + r' = trunc i64 (%\S+) to i32\s*$')
    for q in range(j - 1, fstart - 1, -1):
        m = pat.match(lines[q])
        if m:
            return m.group(1)
    return None


def _icmp_const(v, ctx):
    c = int(v)
    if not 0 <= c <= I32_MAX:
        raise PassError('icmp の定数 %s は i32/i64 で値が一致しない (%s)' % (v, ctx.strip()))
    return ''


def process(text, fn):
    lines = text.split('\n')
    at = '@' + fn
    defs = [i for i, l in enumerate(lines)
            if l.startswith('define ') and re.search(re.escape(at) + r'\(', l)]
    if not defs:
        return text, [{'func': fn, 'defined': False}]
    if len(defs) != 1:
        raise PassError('%s の define が %d 件 (1 件を要求)' % (fn, len(defs)))
    idx = defs[0]
    dl = lines[idx]
    op = dl.index(at + '(') + len(at)
    cl = _close(dl, op)
    args = _split(dl[op + 1:cl])
    bidx = _fn_end(lines, idx)
    body = lines[idx + 1:bidx + 1]

    targets = []
    for k, a in enumerate(args):
        t = a.split()
        if len(t) >= 2 and t[0] == 'i32' and t[1].startswith('%'):
            nm = t[1]
            if any(re.search(r'inttoptr i64 ' + re.escape(nm) + r' to ptr', b) for b in body):
                targets.append((k, nm))
    if not targets:
        return text, [{'func': fn, 'defined': True, 'args': []}]

    names = [nm for _, nm in targets]
    for nm in names:
        for b in body:
            s = re.sub(r'inttoptr i64 ' + re.escape(nm) + r' to ptr', '', b)
            s = re.sub(r'icmp (eq|ne) i32 ' + re.escape(nm) + r', (-?\d+)(?![\w.])',
                       lambda m: _icmp_const(m.group(2), b), s)
            if re.search(re.escape(nm) + r'(?![\w.$])', s):
                raise PassError('本体で %s が inttoptr / icmp 以外に使われる (%s)' % (nm, b.strip()))

    out = list(lines)
    for j in range(idx + 1, bidx + 1):
        l = out[j]
        for nm in names:
            l = re.sub(r'icmp (eq|ne) i32 (' + re.escape(nm) + r'), ', r'icmp \1 i64 \2, ', l)
        out[j] = l

    new_args = list(args)
    for k, _ in targets:
        new_args[k] = 'i64' + args[k][3:]
    out[idx] = dl[:op + 1] + ', '.join(new_args) + dl[cl:]

    report = [{'func': fn, 'defined': True, 'args': names}]
    inserts = {}
    used = set(re.findall(r'%[-\w.$]+', text))
    n = 0
    for j, l in enumerate(lines):
        if j == idx or not re.search(re.escape(at) + r'(?![\w.$])', l):
            continue
        if l.count(at + '(') != 1:
            raise PassError('%s の参照形が未対応 (line %d): %s' % (fn, j + 1, l.strip()))
        op = l.index(at + '(') + len(at)
        cl = _close(l, op)
        parts = _split(l[op + 1:cl])
        is_decl = re.match(r'^declare\b', l) is not None
        is_call = re.search(r'\bcall\b[^@]*' + re.escape(at) + r'\($', l[:op + 1]) is not None
        if not (is_decl or is_call):
            raise PassError('%s の非 call / 非 declare 参照 (line %d): %s' % (fn, j + 1, l.strip()))
        new_parts = list(parts)
        kinds = []
        for k, nm in targets:
            if k >= len(parts):
                raise PassError('%s の引数数が足りない (line %d): %s' % (fn, j + 1, l.strip()))
            p = parts[k]
            if is_decl:
                if not re.match(r'^i32\b', p):
                    raise PassError('declare の %d 番目が i32 でない (line %d): %s' % (k, j + 1, l.strip()))
                new_parts[k] = 'i64' + p[3:]
                kinds.append('decl')
                continue
            if not p.startswith('i32 '):
                raise PassError('呼出の %d 番目が i32 でない (line %d): %s' % (k, j + 1, l.strip()))
            v = p[4:].strip()
            if re.fullmatch(r'-?\d+', v):
                c = int(v)
                if not 0 <= c <= I32_MAX:
                    raise PassError('呼出の定数 %s は範囲外 (line %d)' % (v, j + 1))
                new_parts[k] = 'i64 %d' % c
                kinds.append('const')
            elif re.fullmatch(r'%[-\w.$]+', v):
                src = _trunc_src(lines, j, v, _fn_start(lines, j))
                if src is None:
                    raise PassError('呼出の実引数 %s が trunc 定義でも定数でもない (line %d): %s' % (v, j + 1, l.strip()))
                while True:
                    n += 1
                    name = '%%i3x.%d' % n
                    if name not in used:
                        break
                used.add(name)
                indent = re.match(r'\s*', l).group(0)
                inserts.setdefault(j, []).append('%s%s = add i64 %s, 0' % (indent, name, src))
                new_parts[k] = 'i64 ' + name
                kinds.append('trunc')
            else:
                raise PassError('呼出の実引数 %s が未対応の形 (line %d): %s' % (v, j + 1, l.strip()))
        out[j] = l[:op + 1] + ', '.join(new_parts) + l[cl:]
        for kd in kinds:
            report.append({'func': fn, 'line': j + 1, 'kind': kd})

    final = []
    for j, l in enumerate(out):
        final.extend(inserts.get(j, []))
        final.append(l)
    return '\n'.join(final), report


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
    report = []
    try:
        for fn in funcs:
            text, r = process(text, fn)
            report += r
    except PassError as e:
        print('[P-T2] FAIL: %s (出力は書かない)' % e, file=sys.stderr)
        sys.exit(1)
    open(outp, 'w').write(text)
    counts = {}
    for r in report:
        if 'kind' in r:
            counts[r['kind']] = counts.get(r['kind'], 0) + 1
    print('[P-T2] i32 ptr-arg → i64: 分類 %s' % json.dumps(counts, sort_keys=True), file=sys.stderr)
    if rep:
        json.dump(report, open(rep, 'w'), indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
