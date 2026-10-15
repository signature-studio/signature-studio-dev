#!/usr/bin/env python3
"""VEX の comis/ucomis (vcomisd/vucomisd/vcomiss/vucomiss) の flag (CF/ZF/PF) を同一ブロック内の読み出しに反映する ([PLG-F3-14] #1774).

RetDec は vcomis を flag 副作用の無い void 呼び出し (__asm_v*comis*) として出すため、直後の分岐が読む flag は
ブロック先頭で load した古い値 (%zf.N.reload 等) のまま。 本 pass は各呼び出しの直後に fcmp 由来の flag を作り、
同じブロック内で呼び出し後に読まれる古い reload を差し替える (ir6_pass.py [P1] と同じ式: CF=lt|uno, ZF=eq|uno, PF=uno)。
呼び出し自体は残す (helper は未実装 stub のまま = unimpl に見える。 silent な flag 欠落を隠さないため)。

差し替えないもの (件数を stderr に出す): ブロック外で読まれる flag (xblk)・ブロック先頭 load 以外の flag 参照 (other)。
非 VEX の comis/ucomis は対象外 (#1774 の範囲外。 comiss/comisd の残件は REPORT に残す)。

usage: vex_comis_flags.py <in.ll> <out.ll>
"""
import re, sys

CALL = re.compile(r'^(\s*)call void @__asm_v(u?)comis([sd])(?:__\d+)?\(i128 (%[\w.\-]+), (i64|i128) ([^)]+)\)\s*$')
RELOAD = re.compile(r'^\s*%((?:cf|zf|pf)\.\d+)\.reload = load i1,')
FLAGREF = re.compile(r'%((?:cf|zf|pf)\.\d+)\.reload(?![\w.\-])')
LABEL = re.compile(r'^(?:[\w.$\-]+|\d+):(\s*;.*)?$')
TERM = re.compile(r'^\s*(br |ret |switch |unreachable|indirectbr)')


def block_start(L, k):
    s = k
    while s > 0 and not LABEL.match(L[s]) and not L[s].startswith('define '):
        s -= 1
    return s


def block_end(L, k):
    e = k
    while e + 1 < len(L) and not TERM.match(L[e]):
        e += 1
    return e


def fn_end(L, k):
    e = k
    while e + 1 < len(L) and not L[e].startswith('}'):
        e += 1
    return e


def operand(L, tag, idx, width, src, is_const, val, ty, out):
    """src (i128 %x or i64 ...) を width bit の値に揃え、ty 型の SSA 名を返す。 失敗時 None。"""
    name = '%%vc%s%s' % (tag, idx)
    if is_const:
        v = int(val) & ((1 << width) - 1)
        out.append('  %s = bitcast i%d %d to %s' % (name, width, v, ty))
        return name
    sw = 128 if src == 'i128' else 64
    if sw < width:
        return None
    cur = val
    if sw > width:
        out.append('  %s_t = trunc %s %s to i%d' % (name, src, val, width))
        cur = '%s_t' % name
    out.append('  %s = bitcast i%d %s to %s' % (name, width, cur, ty))
    return name


def main():
    src, dst = sys.argv[1], sys.argv[2]
    L = open(src).read().split('\n')
    calls = [k for k, l in enumerate(L) if CALL.match(l)]
    stats = {'calls': len(calls), 'sites': 0, 'uses': 0, 'xblk': 0, 'other': 0, 'skip': 0}
    for k in reversed(calls):
        m = CALL.match(L[k])
        kind = m.group(3)
        ty, width = ('double', 64) if kind == 'd' else ('float', 32)
        tag = str(k)
        pre = {}
        s = block_start(L, k)
        for j in range(s, k):
            r = RELOAD.match(L[j])
            if r:
                pre[r.group(1)] = '%%%s.reload' % r.group(1)
        e = block_end(L, k)
        if not pre:
            stats['other'] += sum(1 for j in range(k + 1, e + 1) if FLAGREF.search(L[j]))
            continue
        ops = []
        f1 = operand(L, tag, 'a', width, 'i128', False, m.group(4), ty, ops)
        f2 = operand(L, tag, 'b', width, m.group(5), m.group(5) == 'i64' and m.group(6).lstrip('-').isdigit(), m.group(6), ty, ops)
        if f1 is None or f2 is None:
            stats['skip'] += 1
            continue
        ops += [
            '  %%vc%slt = fcmp ult %s %s, %s' % (tag, ty, f1, f2),
            '  %%vc%seq = fcmp ueq %s %s, %s' % (tag, ty, f1, f2),
            '  %%vc%suo = fcmp uno %s %s, %s' % (tag, ty, f1, f2),
            '  %%vc%scf = or i1 %%vc%slt, %%vc%suo' % (tag, tag, tag),
            '  %%vc%szf = or i1 %%vc%seq, %%vc%suo' % (tag, tag, tag),
            '  %%vc%spf = or i1 %%vc%suo, false' % (tag, tag),
        ]
        newv = {'cf': '%%vc%scf' % tag, 'zf': '%%vc%szf' % tag, 'pf': '%%vc%spf' % tag}
        repl = {'%%%s.reload' % n: newv[n.split('.')[0]] for n in pre}
        stats['sites'] += 1
        for j in range(k + 1, e + 1):
            def sub(mm):
                key = '%%%s.reload' % mm.group(1)
                if key in repl:
                    stats['uses'] += 1
                    return repl[key]
                stats['other'] += 1
                return mm.group(0)
            L[j] = FLAGREF.sub(sub, L[j])
        # 同一ブロックの後ろで 1 度も読まれない flag 名は xblk の数に入れる (後続ブロックの参照は差し替えない)
        fe = fn_end(L, k)
        for j in range(e + 1, fe + 1):
            stats['xblk'] += len(FLAGREF.findall(L[j]))
        L[k + 1:k + 1] = ops
    open(dst, 'w').write('\n'.join(L))
    print('[vex_comis_flags] calls %(calls)d sites %(sites)d replaced_uses %(uses)d xblk_uses %(xblk)d other_flag_refs %(other)d skip %(skip)d' % stats, file=sys.stderr)


if __name__ == '__main__':
    main()
