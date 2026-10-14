#!/usr/bin/env python3
"""IR の HANDLE 幅を shimx 定義 (wasm32) に揃える (#1628 SHX-T25)。

RetDec は midiOutShortMsg の第 1 引数 (HMIDIOUT) を i64 で宣言し、呼出しも i64 で行う (lift の型推定)。
shimx の定義 (tools/shimx/src/midi_conv.c: UINT midiOutShortMsg(HANDLE h, DWORD msg)) は wasm32 の HANDLE = i32 なので、
wasm-ld は import と定義の型不一致を `signature mismatch` (warning) として出す。trace 版は gen_link.py が
IR の宣言をそのまま trace_wrap.c に写すため、同じ不一致がそこでも出る。

本 pass は宣言の第 1 引数を i32 に直し、各呼出しの第 1 引数を `trunc i64 <v> to i32` で切り詰める。
HMIDIOUT は wasm32 のハンドル値 (i32 に収まる) なので、下位 32 bit の切り詰めは値を変えない。
宣言が i64 でない関数は何もしない (冪等)。想定外の参照 (関数ポインタ等) が残るときは失敗する (fail-closed)。

  sx_handle_norm.py <in.ll> <out.ll> [--report report.json]
"""
import json, re, sys

FN = ('midiOutShortMsg',)   # 第 1 引数が HANDLE (wasm32 = i32) の shimx 定義。IR の宣言と呼出しを i32 に揃える


def norm(lines, name):
    decl_re = re.compile(r'^declare (\S+) @%s\((i64|i32)(, [^)]*)?\)' % re.escape(name))
    call_re = re.compile(r'(\bcall\b[^@\n]*@%s\()i64 ([^,()\s]+), ' % re.escape(name))
    decl_idx = [i for i, l in enumerate(lines) if decl_re.match(l)]
    ref_all = sum(l.count('@' + name + '(') for l in lines)
    if not decl_idx:
        return 0, 0
    if len(decl_idx) != 1:
        raise SystemExit('sx_handle_norm: %s の宣言が %d 件 (1 件を想定)' % (name, len(decl_idx)))
    if decl_re.match(lines[decl_idx[0]]).group(2) != 'i64':
        return 0, 0
    out, n_call = [], 0
    for i, l in enumerate(lines):
        if i == decl_idx[0]:
            l = decl_re.sub(lambda m: 'declare %s @%s(i32%s)' % (m.group(1), name, m.group(3) or ''), l, count=1)
            out.append(l)
            continue
        m = call_re.search(l)
        if m:
            n_call += 1
            tmp = '%%sxh_%d' % (i + 1)
            indent = l[:len(l) - len(l.lstrip())]
            out.append('%s%s = trunc i64 %s to i32' % (indent, tmp, m.group(2)))
            out.append(l[:m.start()] + m.group(1) + 'i32 ' + tmp + ', ' + l[m.end():])
            continue
        out.append(l)
    if n_call + 1 != ref_all:
        raise SystemExit('sx_handle_norm: %s の参照 %d 件のうち宣言・i64 呼出し %d 件以外が残る (想定外の参照)' % (name, ref_all, n_call + 1))
    lines[:] = out
    return 1, n_call


def main():
    args = sys.argv[1:]
    report = None
    if '--report' in args:
        k = args.index('--report')
        report = args[k + 1]
        del args[k:k + 2]
    if len(args) != 2:
        raise SystemExit(__doc__)
    src_path, dst_path = args
    lines = open(src_path, errors='replace').read().split('\n')
    res = {}
    for name in FN:
        d, c = norm(lines, name)
        res[name] = {'decl_changed': d, 'calls_truncated': c}
    open(dst_path, 'w').write('\n'.join(lines))
    if report:
        json.dump(res, open(report, 'w'), indent=1)
    print('[sx_handle_norm] ' + ' '.join('%s: decl=%d call=%d' % (k, v['decl_changed'], v['calls_truncated']) for k, v in res.items()))


if __name__ == '__main__':
    main()
