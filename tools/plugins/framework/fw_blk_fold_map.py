#!/usr/bin/env python3
"""fw_blk_fold_map.py — #3121 受入 2: 修正前 IR の `ptrtoint ([2 x i8]* @1 to i32)` の出どころを分類する.

  python3 fw_blk_fold_map.py OLD.ll NEW_CHUNK.ll... [--csv OUT.csv]

OLD = 修正前の stage-1 (fw6.restored.ll・BLK 配置の前)、NEW = 修正後の chunk 復元 IR (fw0〜fw7.restored.ll)。
chunk ごとに `!N` の metadata 定義が別なので、NEW は chunk 単位で読んで (関数, insn.addr) を合わせる
(merge 済み fw_all.restored.ll は metadata 定義を含まないので使えない)。
同じ `(関数名, !insn.addr)` の命令を NEW で見て分類する (両方とも元 VA 体系の IR):
  BLK     NEW の同じ命令の入力を SSA の def-use で遡ると (スタック変数は同じ基本ブロック内で直前の store だけを見る)、BLK 領域 [BLK, BLK+0x280) の読みに届く
          (旧 IR では BLK slot の読みが "$" 番地に畳まれた)
  NOBLK   遡った全経路が BLK 読みに届かず、関数引数・呼出し結果にも当たらない
  UNK     呼出し結果・関数引数・遡り上限で判定不能
  MISS    NEW に同じ (関数名, insn.addr) の命令が無い
  NOADDR  !insn.addr の無い行 (後段の LLVM 変換で増えた行)。直前の insn.addr を引き継いで同じ分類にする
"""
import csv
import re
import sys
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
DEPTH = 14
RE_INT = re.compile(r'(?<![\w.])(\d{7,})(?![\w.])')


def scan(path, index=None):
    """(func, addr) -> [(line_no, text)] と、TARGET を含む行を返す。index を渡すと def / store も集める."""
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
            continue
        ml = RE_LABEL.match(line)
        if ml and func is not None:
            block = ml.group(1)
            continue
        if not line.startswith(' ') or func is None:
            continue
        m = RE_INSN.search(line)
        addr = meta.get(m.group(1)) if m else None
        if index is not None:
            d = index.setdefault(func, {'def': {}, 'store': defaultdict(list)})
            md = RE_DEFN.match(line)
            if md:
                d['def'][md.group(1)] = line
                d.setdefault('at', {})[md.group(1)] = (no, block)
            if line.lstrip().startswith('store '):
                toks = RE_TOK.findall(line)
                if len(toks) >= 2:
                    d['store'][toks[-1]].append((no, block, toks[:-1]))
        if addr is not None:
            last = addr
            by_key[(func, addr)].append((no, line))
        if TARGET in line:
            target_rows.append((no, func, addr if addr is not None else last, line, addr is None))
    return by_key, target_rows


def trace(index, func, name, depth, seen):
    """name の値の流れを SSA で遡り 'BLK' / 'NOBLK' / 'UNK' を返す."""
    d = index.get(func)
    if d is None or depth <= 0:
        return 'UNK'
    if name in seen:
        return 'NOBLK'
    seen.add(name)
    text = d['def'].get(name)
    if text is None:
        return 'UNK'
    if blk_read(text):
        return 'BLK'
    if ' = call ' in text:
        return 'UNK'
    toks = [t for t in RE_TOK.findall(text.split(' = ', 1)[1]) if t != name]
    if ' = load ' in text and toks:
        ptr = toks[-1]
        ln, blk = d['at'][name]
        prior = [st for st in d['store'].get(ptr, []) if st[1] == blk and st[0] < ln]
        if not prior:
            return 'UNK'
        toks = prior[-1][2]
    res = 'NOBLK'
    for t in toks:
        r = trace(index, func, t, depth - 1, seen)
        if r == 'BLK':
            return 'BLK'
        if r == 'UNK':
            res = 'UNK'
    return res


def blk_read(text):
    body = RE_REF.sub('', text)
    for m in RE_INT.finditer(body):
        if BLK <= int(m.group(1)) < BLK_END:
            return True
    return False


def classify(index, func, addr, new_by_key):
    hits = new_by_key.get((func, addr))
    if not hits:
        return 'MISS', ''
    res = []
    for no, text in hits:
        if blk_read(text):
            return 'BLK', str(no)
        r = 'NOBLK'
        for t in RE_TOK.findall(text.split(' = ', 1)[1] if ' = ' in text else text):
            rr = trace(index, func, t, DEPTH, set())
            if rr == 'BLK':
                return 'BLK', str(no)
            if rr == 'UNK':
                r = 'UNK'
        res.append((r, no))
    cls = 'UNK' if any(r == 'UNK' for r, _ in res) else 'NOBLK'
    return cls, str(res[0][1])


def main(argv):
    args = argv[1:]
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
