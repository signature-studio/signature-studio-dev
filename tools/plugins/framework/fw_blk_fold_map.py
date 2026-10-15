#!/usr/bin/env python3
"""fw_blk_fold_map.py — #3121 受入 1: 修正前 IR の `ptrtoint ([2 x i8]* @1 to i32)` の出どころを分類する.

  python3 fw_blk_fold_map.py OLD.ll NEW_CHUNK.ll... [--csv OUT.csv]
  python3 fw_blk_fold_map.py --selftest

OLD = 修正前の stage-1 (fw6.restored.ll・BLK 配置の前)、NEW = 修正後の chunk 復元 IR (fw0〜fw7.restored.ll)。
chunk ごとに `!N` の metadata 定義が別なので、NEW は chunk 単位で読んで (関数, insn.addr) を合わせる
(merge 済み fw_all.restored.ll は metadata 定義を含まないので使えない)。
同じ `(関数名, !insn.addr)` の命令を NEW で見て分類する (両方とも元 VA 体系の IR):
  BLK     命令自体が BLK 読みか、入力を SSA で遡ると BLK 読みに届く。BLK 読み =
          load のアドレス、または getelementptr の基底が BLK 領域 [BLK, BLK+0x280) の整数 / `@global_var_8a10xx`。
          store は値オペランドだけを遡る (書込み先は読みではない)。call は引数だけを遡る (引数の整数は読みではない)。
  NOBLK   遡った全経路が BLK 読みに届かず、関数引数・呼出し結果にも当たらない
  UNK     呼出し結果・関数引数・遡り上限・直前の store の無いスタック読みで判定不能
  MISS    NEW に同じ (関数名, insn.addr) の命令が無い
  NOADDR  !insn.addr の無い行 (後段の LLVM 変換で増えた行)。直前の insn.addr を引き継いで同じ分類にする
"""
import csv
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict

BLK = 0x8A1000
BLK_END = BLK + 0x280
TARGET = 'ptrtoint ([2 x i8]* @1 to i32)'
RE_DEF = re.compile(r'^define .*?@(function_[0-9a-f]+)\(')
RE_META = re.compile(r'^!(\d+) = !\{i64 (\d+)\}\s*$')
RE_INSN = re.compile(r'!insn\.addr !(\d+)')
RE_REF = re.compile(r'!\d+')
RE_TOK = re.compile(r'%[-\w.$]+')
RE_LABEL = re.compile(r'^([\w.$-]+):')
RE_DEFN = re.compile(r'^\s*(%[-\w.$]+) = ')
RE_OP = re.compile(r'^(?:(?:tail|musttail|notail) )?([a-z][\w.]*)\s*(.*)$', re.S)
RE_BRLABEL = re.compile(r'label %[-\w.$]+')
RE_INBOUNDS = re.compile(r'^inbounds\s+')
RE_INT = re.compile(r'(?<![\w.%@$])(\d{7,})(?![\w.])')
RE_GLOBAL = re.compile(r'@global_var_([0-9a-f]+)\b')
DEPTH = 14
CALLS = ('call', 'invoke')


def split_top(s):
    out, depth, cur = [], 0, ''
    for ch in s:
        if ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth -= 1
        if ch == ',' and depth == 0:
            out.append(cur.strip())
            cur = ''
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def body_of(text):
    m = RE_DEFN.match(text)
    return text[m.end():] if m else text.strip()


def opcode(text):
    m = RE_OP.match(body_of(text))
    return (m.group(1), m.group(2)) if m else ('', '')


def blk_addr(text):
    body = RE_REF.sub('', text)
    for m in RE_INT.finditer(body):
        if BLK <= int(m.group(1)) < BLK_END:
            return True
    for m in RE_GLOBAL.finditer(body):
        if BLK <= int(m.group(1), 16) < BLK_END:
            return True
    return False


def blk_read(text):
    """命令自体が BLK 領域を読むか (load のアドレス・getelementptr の基底)."""
    op, rest = opcode(text)
    if op == 'load':
        return blk_addr(rest)
    if op == 'getelementptr':
        for part in split_top(RE_INBOUNDS.sub('', rest)):
            if '*' in part:
                return blk_addr(part)
    return False


def value_toks(d, text):
    return [t for t in RE_TOK.findall(RE_BRLABEL.sub('', text)) if t not in d['labels']]


def scan(path, index=None):
    """(func, addr) -> [(line_no, text, block)] と、TARGET を含む行を返す。index を渡すと def / store / label も集める."""
    meta = {}
    lines = []
    with open(path, encoding='utf-8', errors='replace') as f:
        for no, line in enumerate(f, 1):
            line = line.rstrip('\n')
            if line.startswith('!'):
                m = RE_META.match(line)
                if m:
                    meta[m.group(1)] = int(m.group(2))
            lines.append((no, line))
    func = None
    last = None
    block = None
    by_key = defaultdict(list)
    target_rows = []
    for no, line in lines:
        m = RE_DEF.match(line)
        if m:
            func = m.group(1)
            last = None
            block = None
            if index is not None:
                index.setdefault(func, {'def': {}, 'store': defaultdict(list), 'at': {}, 'labels': set()})
            continue
        ml = RE_LABEL.match(line)
        if ml and func is not None:
            block = ml.group(1)
            if index is not None:
                index[func]['labels'].add('%' + block)
            continue
        if not line.startswith(' ') or func is None:
            continue
        m = RE_INSN.search(line)
        addr = meta.get(m.group(1)) if m else None
        if index is not None:
            d = index[func]
            md = RE_DEFN.match(line)
            if md:
                d['def'][md.group(1)] = line
                d['at'][md.group(1)] = (no, block)
            op, rest = opcode(line)
            if op == 'store':
                parts = split_top(rest)
                ptr = RE_TOK.findall(parts[1]) if len(parts) > 1 else []
                if ptr:
                    d['store'][ptr[-1]].append((no, block, RE_TOK.findall(parts[0])))
        if addr is not None:
            last = addr
            by_key[(func, addr)].append((no, line, block))
        if TARGET in line:
            target_rows.append((no, func, addr if addr is not None else last, line, addr is None))
    return by_key, target_rows


def combine(rs):
    if 'BLK' in rs:
        return 'BLK'
    if 'UNK' in rs:
        return 'UNK'
    return 'NOBLK'


def fold(index, func, names, depth, memo, active):
    if not names:
        return 'NOBLK'
    return combine([trace(index, func, n, depth, memo, active) for n in names])


def trace(index, func, name, depth, memo, active):
    """値 name の流れを SSA で遡り 'BLK' / 'NOBLK' / 'UNK' を返す."""
    if name in memo:
        return memo[name]
    if name in active:
        return 'NOBLK'
    d = index.get(func)
    if d is None or depth <= 0:
        return 'UNK'
    text = d['def'].get(name)
    if text is None:
        return 'UNK'
    if opcode(text)[0] in CALLS:
        return 'UNK'
    active.add(name)
    r = inst_class(index, func, text, d['at'][name], depth - 1, memo, active)
    active.discard(name)
    memo[name] = r
    return r


def inst_class(index, func, text, at, depth, memo, active):
    """命令 text の入力を遡って 'BLK' / 'NOBLK' / 'UNK' を返す. at = (行番号, ブロック) は store の転送に使う."""
    if blk_read(text):
        return 'BLK'
    d = index[func]
    op, rest = opcode(text)
    if op == 'store':
        parts = split_top(rest)
        return fold(index, func, value_toks(d, parts[0]) if parts else [], depth, memo, active)
    if op == 'load':
        toks = value_toks(d, rest)
        if not toks:
            return 'NOBLK'
        addr = fold(index, func, toks, depth, memo, active)
        if addr == 'BLK':
            return 'BLK'
        prior = [st for st in d['store'].get(toks[-1], []) if st[1] == at[1] and st[0] < at[0]]
        if not prior:
            return 'UNK'
        return combine([addr, fold(index, func, prior[-1][2], depth, memo, active)])
    return fold(index, func, value_toks(d, rest), depth, memo, active)


def classify(index, func, addr, new_by_key):
    hits = new_by_key.get((func, addr))
    if not hits:
        return 'MISS', ''
    rs = [inst_class(index, func, text, (no, block), DEPTH, {}, set()) for no, text, block in hits]
    cls = combine(rs)
    ref = next(no for (no, _, _), r in zip(hits, rs) if r == cls)
    return cls, str(ref)


SELFTEST_IR = '''\
define i32 @function_a000(i32 %p0) {
entry:
  %a = add i32 0, 5
  %v = add i32 %a, 1
  store i32 %v, i32* inttoptr (i64 9048064 to i32*), !insn.addr !1001
  ret i32 0
}

define i32 @function_a001(i32 %p0) {
entry:
  %s = alloca i32
  %r = load i32, i32* inttoptr (i64 9048064 to i32*)
  %w = add i32 %r, 1, !insn.addr !1004
  store i32 %w, i32* %s, !insn.addr !1005
  %t = load i32, i32* %s, !insn.addr !1006
  ret i32 %t
}

define i32 @function_a002(i32 %p0) {
entry:
  %x = load i64, i64* @global_var_8a1018, !insn.addr !1002
  call void @g(i32 9048064), !insn.addr !1007
  %c = call i32 @g2()
  %d = add i32 %c, 1, !insn.addr !1008
  %p = getelementptr i8, i8* inttoptr (i64 9048068 to i8*), i64 4, !insn.addr !1009
  %pv = load i8, i8* %p, !insn.addr !1010
  %s2 = alloca i8
  %q = getelementptr i8, i8* %s2, i64 9048068, !insn.addr !1011
  %s3 = alloca i32
  %z = load i32, i32* %s3, !insn.addr !1012
  %v2 = load i32, i32* inttoptr (i64 4194304 to i32*)
  store i32 %v2, i32* inttoptr (i64 9048064 to i32*), !insn.addr !1015
  ret i32 0
}

define i32 @function_a003(i32 %p0) {
entry:
  %a = add i32 0, 5
  %c1 = icmp eq i32 %a, 0
  br i1 %c1, label %L1, label %L2, !insn.addr !1013
L1:
  ret i32 1
L2:
  ret i32 2
}

!1001 = !{i64 1001}
!1002 = !{i64 1002}
!1004 = !{i64 1004}
!1005 = !{i64 1005}
!1006 = !{i64 1006}
!1007 = !{i64 1007}
!1008 = !{i64 1008}
!1009 = !{i64 1009}
!1010 = !{i64 1010}
!1011 = !{i64 1011}
!1012 = !{i64 1012}
!1013 = !{i64 1013}
!1015 = !{i64 1015}
'''

SELFTEST_EXPECT = [
    ('function_a000', 1001, 'NOBLK'),
    ('function_a001', 1004, 'BLK'),
    ('function_a001', 1005, 'BLK'),
    ('function_a001', 1006, 'BLK'),
    ('function_a002', 1002, 'BLK'),
    ('function_a002', 1007, 'NOBLK'),
    ('function_a002', 1008, 'UNK'),
    ('function_a002', 1009, 'BLK'),
    ('function_a002', 1010, 'BLK'),
    ('function_a002', 1011, 'NOBLK'),
    ('function_a002', 1012, 'UNK'),
    ('function_a002', 1015, 'NOBLK'),
    ('function_a003', 1013, 'NOBLK'),
]


def selftest():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, 'selftest.ll')
        with open(path, 'w') as f:
            f.write(SELFTEST_IR)
        index = {}
        keys, _ = scan(path, index)
    bad = 0
    for func, addr, want in SELFTEST_EXPECT:
        got, _ = classify(index, func, addr, keys)
        ok = got == want
        bad += 0 if ok else 1
        print('%s %s insn=%d want=%s got=%s' % ('ok  ' if ok else 'FAIL', func, addr, want, got))
    print('selftest %d cases, %d fail' % (len(SELFTEST_EXPECT), bad))
    return 1 if bad else 0


def main(argv):
    args = argv[1:]
    if args == ['--selftest']:
        return selftest()
    csv_out = None
    if '--csv' in args:
        i = args.index('--csv')
        csv_out = args[i + 1]
        del args[i:i + 2]
    if len(args) < 2:
        print(__doc__)
        return 2
    old, news = args[0], args[1:]
    _, rows = scan(old)
    new_by_key = defaultdict(list)
    index = {}
    for path in news:
        keys, _ = scan(path, index)
        for k, v in keys.items():
            new_by_key[k].extend(v)
    out = []
    for no, func, addr, line, inherited in rows:
        if addr is None:
            cat, ref = 'MISS', ''
        else:
            cat, ref = classify(index, func, addr, new_by_key)
        if inherited and cat != 'MISS':
            cat = cat + '*'
        out.append((no, func, hex(addr) if addr is not None else '', cat, ref, line.strip()))
    cnt = Counter(r[3].rstrip('*') for r in out)
    print('total %d (* = NOADDR 行の引継ぎ %d)' % (len(out), sum(1 for r in out if r[3].endswith('*'))))
    for k in ('BLK', 'NOBLK', 'UNK', 'MISS'):
        print('%-7s %d' % (k, cnt.get(k, 0)))
    print('functions %d' % len({r[1] for r in out}))
    fcnt = Counter((r[1], r[3]) for r in out)
    for (f, c), n in sorted(fcnt.items(), key=lambda kv: (-kv[1], kv[0])):
        print('  %s %s %d' % (f, c, n))
    if csv_out:
        with open(csv_out, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['old_line', 'function', 'insn_addr', 'class', 'new_line', 'old_text'])
            w.writerows(out)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
