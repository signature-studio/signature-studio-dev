#!/usr/bin/env python3
"""fa_call_trace.py STDERR_LOG : RetDec の --print-after-all の stderr から、
間接 call の VA (fa_residual.py の lost 行) が各 pass 段で生きているかを記録する (#1612 / ICALL-35).

判定:
- decode 直後 (pass 名 'Input binary to LLVM IR decoding') は命令 VA が `; 0xVA` コメント +
  `store volatile i64 <VA 10進>, i64* @_asm_program_counter` で残る。その VA の直後 (次の `; 0x` まで)
  に `call` 命令が無ければ GONE (decoder 段で call が消えた)。
- 後段は `!insn.addr !N` メタデータで追跡する。llvm.ctpop 等 intrinsic の call は数えない。
"""
import re, sys
from collections import OrderedDict

# VA -> ラベル (fa_residual.py の lost 行。値は 0x180c97aa0 系 と 0x180da6e60 系)
TARGETS = OrderedDict([
    (0x180c97e17, 'c97aa0 call[rax+10]'),
    (0x180c97e38, 'c97aa0 call[rax+20]'),
    (0x180c97e56, 'c97aa0 call[rax+8]'),
    (0x180c97e71, 'c97aa0 call[rax+20]#2'),
    (0x180da7261, 'da6e60 call[rax+30]'),
    (0x180da72fc, 'da6e60 call[rax+30]#2'),
])


def split_dumps(path):
    cur_name, cur, dumps = None, [], []
    with open(path, errors='replace') as f:
        for line in f:
            m = re.match(r'^\*\*\* IR Dump After (.*) \*\*\*$', line.rstrip('\n'))
            if m:
                if cur_name is not None:
                    dumps.append((cur_name, ''.join(cur)))
                cur_name, cur = m.group(1), []
            elif cur_name is not None:
                cur.append(line)
    if cur_name is not None:
        dumps.append((cur_name, ''.join(cur)))
    return dumps


def decode_alive(text, va):
    """decode 直後: `; 0xVA` の直後ブロックに call 行があるか (llvm.ctpop 等は除外)."""
    # 同じ VA の `; 0xVA` コメントが複数あっても、判定は最初の出現だけ (後続は見ない)。
    m = re.search(r'; 0x%x\n' % va, text)
    if not m:
        return None  # VA コメントが無い段 (decode 前) は判定しない
    nxt = re.search(r'\n; 0x[0-9a-f]+\n', text[m.end():])
    seg = text[m.end(): m.end() + (nxt.start() if nxt else 2000)]
    return any(re.search(r'\bcall\b', l) and '@llvm.' not in l for l in seg.splitlines())


def meta_alive(text, va):
    meta = {m.group(1): int(m.group(2)) for m in re.finditer(r'^!(\d+) = !\{i64 (\d+)\}', text, re.M)}
    if not meta:
        return None  # !insn.addr メタデータが無い段 (decode 前) は判定しない
    for line in text.splitlines():
        if 'call' not in line or '@llvm.' in line:
            continue
        for mm in re.finditer(r'!insn\.addr !(\d+)', line):
            if meta.get(mm.group(1)) == va:
                return True
    return False


def main():
    dumps = split_dumps(sys.argv[1])
    print('dumps', len(dumps))
    prev, first_gone = None, {}
    for i, (name, text) in enumerate(dumps):
        is_decode = name.startswith('Input binary to LLVM IR decoding')
        state = {}
        for va, label in TARGETS.items():
            state[label] = decode_alive(text, va) if is_decode else meta_alive(text, va)
        key = tuple(state.items())
        if key != prev:
            print('[%03d] %s' % (i, name[:90]))
            for label, ok in state.items():
                print('      %-24s %s' % (label, {True: 'alive', False: 'GONE', None: 'n/a'}[ok]))
            prev = key
    print('done')


if __name__ == '__main__':
    main()
