#!/usr/bin/env python3
"""M11 IR 後処理: boot_final.ll → boot_final3.ll

 1. function_* の define を weak 化 (tools/m11/m11_ov.c の強シンボルで差替可能にする。
    RetDec が落とす間接 call / stack 引数の取りこぼしを関数単位で手修正するための仕組み)
 2. 間接 call 用トランポリン m11_tr_<fn> (全 i64×8 引数, i64 返り) と VA→トランポリン表を IR 末尾に付加
    (RetDec は IR から間接 call を全て落とす: 実測 boot closure 7416 fn 中 0 件。
     Delphi の unit init ループ / VMT / TLS hook は C override 側で m11_icall(va,...) 経由で呼ぶ)
 使い方: python3 m11_post.py IN.ll OUT.ll [--report REPORT.json]
"""
import os, re, sys, json

src, dst = sys.argv[1], sys.argv[2]
rep = {}
if '--report' in sys.argv:
    rep_path = sys.argv[sys.argv.index('--report') + 1]
else:
    rep_path = None
text = open(src).read()
# #5666: 計測専用 (M11_INSTR_412BR=1)。function_4128b0 の 412770 呼出し直前 (分岐 2・3 を通過した点) で 3 値を観測する
if os.environ.get('M11_INSTR_412BR') == '1':
    _m = re.findall(r'^  %13 = call i64 @function_412770\(ptr nonnull inttoptr \(i64 (\d+) to ptr\)\)\n', text, re.M)
    assert len(_m) == 1, '412770 呼出し (4128b0 の分岐 2-3 の後) が一意に見つからない: %d' % len(_m)
    _call412770 = '  %%13 = call i64 @function_412770(ptr nonnull inttoptr (i64 %s to ptr))\n' % _m[0]
    text = text.replace(_call412770, '  call void @m11_412770_br_obs(i64 %7, i32 %9, i32 %10)\n' + _call412770)
# #5761: 計測専用 (M11_INSTR_80E040=1)。function_80e040 の loop 内 864fe0 呼出し直前で (ebx, 残り反復 rsi, this) を観測する。
#   count (list+16) は観測 call の中で [[G]]+188 を読み直す (80e084 の 1 回読みとの差を見る)。
if os.environ.get('M11_INSTR_80E040') == '1':
    _f0 = text.index('\ndefine i64 @function_80e040() ')
    _f1 = text.index('\ndefine ', _f0 + 1)
    _c = '  %24 = call i64 @function_864fe0(i64 %23, ptr nonnull %21)\n'
    assert text[_f0:_f1].count(_c) == 1, '80e040 の 864fe0 呼出しが一意に見つからない'
    text = text[:_f0] + text[_f0:_f1].replace(_c, '  call void @m11_80e040_loop_obs(i64 %rbx.0.reload, i64 %rsi.0, i64 %23)\n' + _c) + text[_f1:]
_gate = '  %8 = icmp eq i64 %7, 0\n'
if os.environ.get('M11_INSTR_412BR') == '3':   # 3 = 呼出し直前ではなく分岐 2 の判定 (%7) の直前で 3 値を観測する (呼出しに届かない unit の原因を見る)
    _f0 = text.index('\ndefine i64 @function_4128b0() ')
    _f1 = text.index('\ndefine ', _f0 + 1)
    assert text[_f0:_f1].count(_gate) == 1, 'gate が function_4128b0 内で一意に見つからない'
    text = text[:_f0] + text[_f0:_f1].replace(_gate, '  call void @m11_412770_gate_obs(i64 %7)\n' + _gate) + text[_f1:]
if os.environ.get('M11_INSTR_412BR') == '2':   # 2 = 2 本目の呼出し (分岐 2・3 を通らない経路) も観測する
    _m2 = re.findall(r'^  %52 = call i64 @function_412770\(ptr inttoptr \(i64 (\d+) to ptr\)\)\n', text, re.M)
    assert len(_m2) == 1, '412770 の 2 本目の呼出し (4128b0 の [18787456] 経路) が一意に見つからない: %d' % len(_m2)
    _call2 = '  %%52 = call i64 @function_412770(ptr inttoptr (i64 %s to ptr))\n' % _m2[0]
    text = text.replace(_call2, '  call void @m11_412770_br2_obs()\n' + _call2)

def ptypes(args):
    out = []
    depth = 0
    cur = ''
    for ch in args:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if ch == ',' and depth == 0:
            out.append(cur.strip()); cur = ''
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    tys = []
    for p in out:
        toks = p.split()
        tys.append(toks[0])
    return tys


def_re = re.compile(r'^define (?P<ret>[^@]*?)@(?P<nm>function_[0-9a-f]+)\((?P<args>[^)]*)\)(?P<rest>.*)$', re.M)
fns = []


# ---------------------------------------------------------------
# [sigfix] call site / callee 署名不一致の解消.
#  RetDec は関数ごとに引数数・戻り型を独立に推定するため, closure 内 call 27,714 件中 約 6,600 件で
#  署名が食い違う (実測). LLVM-wasm の FixFunctionBitcasts は食い違いを thunk 化し, 表現できない型差
#  (ptr/i128/void 戻り等) の thunk は body=unreachable になる (実測: 132 thunk / 2,431 call site が実行時 trap).
#  call site を callee の定義署名に合わせて書換える: 余剰引数は捨て, 不足は 0 詰め, 型は trunc/zext/inttoptr/ptrtoint で変換,
#  戻り値は call site が期待する型へ変換 (void 戻りは 0).
#  注意: 不足引数の 0 詰めは「RetDec が落とした stack 引数」の意味補完ではない (値は未知). 意味保証なし.
# ---------------------------------------------------------------
_ATTR = re.compile(r'^(?:(?:nonnull|noundef|signext|zeroext|noalias|readonly|align \d+|dereferenceable\(\d+\))\s+)+')


def _split_top(s):
    out, depth, cur = [], 0, ''
    for ch in s:
        if ch in '([{<':
            depth += 1
        elif ch in ')]}>':
            depth -= 1
        if ch == ',' and depth == 0:
            out.append(cur.strip()); cur = ''
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def _conv(val, frm, to, tmp):
    """returns (lines, newval)"""
    if frm == to:
        return [], val
    n = tmp()
    ints = {'i1': 1, 'i8': 8, 'i16': 16, 'i32': 32, 'i64': 64, 'i128': 128}
    if frm in ints and to in ints:
        op = 'trunc' if ints[frm] > ints[to] else 'zext'
        return ['  %s = %s %s %s to %s' % (n, op, frm, val, to)], n
    if frm == 'ptr' and to in ints:
        if ints[to] == 32:
            return ['  %s = ptrtoint ptr %s to i32' % (n, val)], n
        n2 = tmp()
        op = 'trunc' if ints[to] < 32 else 'zext'   # #2715: i8/i1/i16 への変換は trunc (zext は狭い型へ書けない)
        return ['  %s = ptrtoint ptr %s to i32' % (n, val), '  %s = %s i32 %s to %s' % (n2, op, n, to)], n2
    if frm in ints and to == 'ptr':
        if ints[frm] == 32:
            return ['  %s = inttoptr i32 %s to ptr' % (n, val)], n
        if ints[frm] > 32:
            n1 = tmp()
            return ['  %s = trunc %s %s to i32' % (n1, frm, val), '  %s = inttoptr i32 %s to ptr' % (n, n1)], n
        n1 = tmp()
        return ['  %s = zext %s %s to i32' % (n1, frm, val), '  %s = inttoptr i32 %s to ptr' % (n, n1)], n
    return None, None


def _zero(ty):
    if ty == 'ptr':
        return 'null'
    if ty in ('float', 'double'):
        return '0.0'
    if ty.startswith('%') or ty.startswith('<') or ty.startswith('['):
        return 'zeroinitializer'
    return '0'


def _const(ty, cv):
    v = cv['val']
    if cv['kind'] == 'ptr':
        return 'inttoptr (i64 %d to ptr)' % v if ty == 'ptr' else str(v & ((1 << int(ty[1:])) - 1))
    if ty == 'ptr':
        return 'inttoptr (i64 %d to ptr)' % v
    return str(v & ((1 << int(ty[1:])) - 1)) if ty.startswith('i') else _zero(ty)


def sigfix(text, report, pads=None, fixes=None, slots=None):
    sigs = {}
    for m in re.finditer(r'^(?:define|declare)(?: weak)? (\S+) @(function_[0-9a-f]+)\(([^)]*)\)', text, re.M):
        ret, nm, args = m.groups()
        sigs[nm] = (ret, [a.strip().split()[0] for a in args.split(',') if a.strip()])
    callre = re.compile(r'^(\s*)(%[\w.$-]+ = )?(tail )?call (\S+) @(function_[0-9a-f]+)\((.*)\)\s*$')
    out = []
    ctr = [0]

    def tmp():
        ctr[0] += 1
        return '%%m11sf%d' % ctr[0]
    fixed = skipped = 0
    applied = [0]
    slot_ctr = [0]
    cur = None
    ordn = {}
    ncall = {}
    _c = None
    for line in text.split('\n'):
        if line.startswith('define '):
            dm = re.search(r'@([\w.$]+)\(', line)
            _c = dm.group(1) if dm else None
        elif ' call ' in line and _c:
            cm = re.search(r'call \S+ @(function_[0-9a-f]+)\(', line)
            if cm:
                ncall[(_c, cm.group(1))] = ncall.get((_c, cm.group(1)), 0) + 1
    ent_alloca = set()
    ent_open = False
    for line in text.split('\n'):
        if line.startswith('define '):
            dm = re.search(r'@([\w.$]+)\(', line)
            cur = dm.group(1) if dm else None
            ordn = {}
            ent_alloca = set()
            ent_open = True
        elif ent_open and re.match(r'^\s*(%[\w.$-]+ = )?(br|ret|switch|indirectbr|invoke|resume|unreachable|callbr)\b', line):
            ent_open = False
        elif ent_open:
            am = re.match(r'^\s*(%stack_var_-?\d+) = alloca\b', line)
            if am:
                ent_alloca.add(am.group(1))
        m = callre.match(line) if ' call ' in line else None
        if not m:
            out.append(line)
            continue
        ind, lhs, tail, sret, nm, argstr = m.groups()
        sig = sigs.get(nm)
        if not sig:
            out.append(line); continue
        tret, tparams = sig
        k = ordn[nm] = ordn.get(nm, -1) + 1
        args = []
        for a in _split_top(argstr):
            ty = a.split()[0]
            rest = _ATTR.sub('', a[len(ty):].strip())
            args.append((ty, rest))
        if tret == sret and [t for t, _ in args] == tparams:
            out.append(line); continue
        if any(t.startswith('%') for t in tparams) or tret.startswith('%') or sret.startswith('%') or any(t.startswith('%') for t, _ in args):
            skipped += 1
            out.append(line); continue
        pre, newargs, bad = [], [], False
        if pads is not None and len(args) < len(tparams):
            pads.append({'caller': cur, 'callee': nm, 'k': k, 'n': ncall.get((cur, nm), 0), 'have': len(args), 'want': len(tparams)})
        for i, pt in enumerate(tparams):
            if i < len(args):
                ty, val = args[i]
                ls, nv = _conv(val, ty, pt, tmp)
                if ls is None:
                    bad = True; break
                pre += ls
                newargs.append('%s %s' % (pt, nv))
            else:
                sv = slots.get((cur, nm, k, i)) if slots else None
                if sv is not None and sv not in ent_alloca:
                    # entry block 内で呼出しより前に定義された alloca だけ使う (それ以外は呼出し箇所を支配せず IR 不正になる)
                    report['sigfix_slot_nonentry'] = report.get('sigfix_slot_nonentry', 0) + 1
                    sv = None
                if sv is not None and (pt == 'ptr' or pt.startswith('i')):
                    if pt == 'ptr':
                        newargs.append('ptr nonnull %s' % sv)
                    else:
                        slot_ctr[0] += 1
                        pv = '%%m11sl%d' % slot_ctr[0]
                        pre.append('  %s = ptrtoint ptr %s to i64' % (pv, sv))
                        ls, nv = _conv(pv, 'i64', pt, lambda: '%%m11sl%dx' % slot_ctr[0])
                        pre += ls
                        newargs.append('%s %s' % (pt, nv))
                    report['sigfix_slot_injected'] = report.get('sigfix_slot_injected', 0) + 1
                    continue
                cv = fixes.get((cur, nm, k, i)) if fixes else None
                if cv is not None and cv.get('bits') is not None and pt != 'i%d' % cv['bits']:
                    cv = None
                if cv is None:
                    newargs.append('%s %s' % (pt, _zero(pt)))
                else:
                    newargs.append('%s %s' % (pt, _const(pt, cv)))
                    applied[0] += 1
        if bad:
            skipped += 1
            out.append(line); continue
        call = '%s %s call %s @%s(%s)' % (ind, '', tret, nm, ', '.join(newargs))
        call = '  ' + (tail or '') + 'call %s @%s(%s)' % (tret, nm, ', '.join(newargs))
        if not lhs:
            out.extend(pre); out.append(call); fixed += 1; continue
        dst = lhs.split('=')[0].strip()
        if tret == sret:
            out.extend(pre); out.append('  %s = %s' % (dst, call.strip())); fixed += 1; continue
        if tret == 'void':
            out.extend(pre); out.append(call)
            if sret == 'ptr':
                out.append('  %s = inttoptr i32 0 to ptr' % dst)
            else:
                out.append('  %s = add %s 0, 0' % (dst, sret))
            fixed += 1; continue
        r = tmp()
        ls, nv = _conv(r, tret, sret, tmp)
        if ls is None:
            skipped += 1; out.append(line); continue
        out.extend(pre); out.append('  %s = %s' % (r, call.strip())); out.extend(ls)
        out.append('  %s = %s' % (dst, ('add %s %s, 0' % (sret, nv)) if sret != 'ptr' else ('getelementptr i8, ptr %s, i32 0' % nv)))
        fixed += 1
    report['sigfix_const_recovered'] = applied[0]
    report['sigfix_rewritten'] = fixed
    report['sigfix_skipped'] = skipped
    print('[m11_post][sigfix] call site 署名書換え: %d (型未対応で skip: %d)' % (fixed, skipped))
    return '\n'.join(out)


# 呼出し計数 probe (FastMM4 の入口): 計数 wrapper を weak で被せ, 本体は __lifted に改名
PROBES = {0x409410: 'GetMem', 0x409440: 'FreeMem', 0x407a50: 'FastMM_GetMem(407a50)', 0x407e20: 'FastMM_FreeMem(407e20)',
          0x4120c0: 'InitUnits', 0x4128b0: 'Halt0',
          0x4fa210: 'ListFind(4fa210)', 0x47a250: 'ListRaise(47a250)'}   # M11-N40: 末尾追加 (既存 index 0-5 不変; OFF の survey 結果の不変は作業者報告・未検証, REPORT_739 §2)
if os.environ.get('M11_INSTR_413060') == '1':   # #944: 計測専用。既定 0 では入れず、既定 build の post 出力を main と同一に保つ
    PROBES[0x413060] = 'function_413060'   # index 8 (末尾追加; 既存 index 不変)
if os.environ.get('M11_INSTR_40FF70') == '1':   # #882: 計測専用。wrapper で m11_p144_obs を呼ぶ (PROBES には入れず、index を変えない)
    PROBES[0x40ff70] = 'function_40ff70'
if os.environ.get('M11_INSTR_40FFE0') == '1':   # #882: 計測専用。40ff70 の caller (arg1 の出所) を観測する
    PROBES[0x40ffe0] = 'function_40ffe0'
if os.environ.get('M11_INSTR_60A270') == '1':   # #882: 計測専用。40ffe0 の caller (this = arg1 の出所) を観測する
    PROBES[0x60a270] = 'function_60a270'
if os.environ.get('M11_INSTR_412770') == '1':   # #3325: 計測専用。function_412770 の入口で arg1 と [arg1+0] を観測する (既定 0 では入れない)
    PROBES[0x412770] = 'function_412770'
if os.environ.get('M11_INSTR_E3EF60') == '1':   # #2407: 計測専用。function_e3ef60 の入口で arg1 (this = rcx) を観測する (既定 0 では入れない)
    PROBES[0xe3ef60] = 'function_e3ef60'
if os.environ.get('M11_INSTR_414C70') == '1':   # #5358: 計測専用。function_414c70 の入口で arg1..arg3 を観測する (既定 0 では入れない。IR 本体は変えない)
    PROBES[0x414c70] = 'function_414c70'
probe_wrappers = []
# #882 計測専用: function_40ff70 の入口で p-144 (arg1-0x90) と先頭ノードを観測する (既定 0 では入れない)
M11_INSTR_40FF70 = os.environ.get('M11_INSTR_40FF70') == '1'
M11_INSTR_40FFE0 = os.environ.get('M11_INSTR_40FFE0') == '1'
M11_INSTR_60A270 = os.environ.get('M11_INSTR_60A270') == '1'
M11_INSTR_412770 = os.environ.get('M11_INSTR_412770') == '1'
M11_INSTR_4128B0 = os.environ.get('M11_INSTR_4128B0') == '1'   # #4457: 計測専用。function_4128b0 の入口で 412770 分岐の 3 値を観測する (既定 0 では入れない)
M11_INSTR_E3EF60 = os.environ.get('M11_INSTR_E3EF60') == '1'
M11_INSTR_414C70 = os.environ.get('M11_INSTR_414C70') == '1'


# #1542 計測専用: 413060 の計測 hook を 3 点に分けて単発で切り分ける (既定 '' は従来どおり)
#   noprobe: wrapper から m11_probe(8) の呼出しを外す (改名・dest 観測は残す)
#   noren  : 413060 を wrapper 化せず本体を元の名前・元の形のまま残す (probe も dest 観測も入らない)
#   nodecl : m11_dest_obs の宣言と呼出しを外す (probe は残す)
M11_PROBE_VARIANT = os.environ.get('M11_PROBE_VARIANT', '')
if M11_PROBE_VARIANT and os.environ.get('M11_INSTR_413060') != '1':
    sys.exit('[m11_post] M11_PROBE_VARIANT は M11_INSTR_413060=1 のときだけ有効')
def weaken(m):
    ret = m.group('ret').strip()
    nm = m.group('nm')
    args = m.group('args')
    fns.append((nm, ret, args))
    va = int(nm.split('_')[1], 16)
    if va == 0x413060 and M11_PROBE_VARIANT == 'noren':
        return 'define weak %s @%s(%s)%s' % (ret, nm, args, m.group('rest'))
    if va in PROBES:
        idx = list(PROBES).index(va)
        pnames = ['%%p%d' % i for i in range(len(ptypes(args)))]
        ptys = ptypes(args)
        plist = ', '.join('%s %s' % (t, pn) for t, pn in zip(ptys, pnames))
        clist = ', '.join('%s %s' % (t, pn) for t, pn in zip(ptys, pnames))
        rt = ret.split()[0]
        w = ['define weak %s @%s(%s) {' % (ret, nm, plist)]
        if not (va == 0x413060 and M11_PROBE_VARIANT == 'noprobe'):
            w += ['  call void @m11_probe(i32 %d)' % idx]
        if va == 0x40ff70 and M11_INSTR_40FF70:
            w += ['  call void @m11_p144_obs(i64 %p0)']
        if va == 0x40ffe0 and M11_INSTR_40FFE0:
            w += ['  call void @m11_ffe0_obs(i64 %p0)']
        if va == 0x60a270 and M11_INSTR_60A270:
            w += ['  call void @m11_a270_obs(i64 %p0)']
        if va == 0x412770 and M11_INSTR_412770:
            w += ['  %pi = ptrtoint ptr %p0 to i64', '  call void @m11_412770_obs(i64 %pi)']
        if va == 0x4128b0 and M11_INSTR_4128B0:
            w += ['  call void @m11_4128b0_obs()']
        if va == 0xe3ef60 and M11_INSTR_E3EF60:
            w += ['  call void @m11_e3ef60_obs(i64 %p0)']
        if va == 0x414c70 and M11_INSTR_414C70:
            w += ['  call void @m11_414c70_obs(i64 %p0, i64 %p1, i64 %p2)']
        if rt == 'void':
            w += ['  call void @%s__lifted(%s)' % (nm, clist), '  ret void']
        else:
            w += ['  %%r = call %s @%s__lifted(%s)' % (rt, nm, clist)]
            if va == 0x413060 and M11_PROBE_VARIANT != 'nodecl':  # #944: 呼出し後の dest を観測 (OFF/ON 共通のフック。ネガコン変更もここで行う)
                w += ['  call void @m11_dest_obs(i64 %p0)']
            w += ['  ret %s %%r' % rt]
        w.append('}')
        probe_wrappers.append('\n'.join(w))
        return 'define %s @%s__lifted(%s)%s' % (ret, nm, args, m.group('rest'))
    return 'define weak %s @%s(%s)%s' % (ret, nm, args, m.group('rest'))

pads = []
fixes = None
if '--fixes' in sys.argv:
    fixes = {(f['caller'], f['callee'], f['k'], f['pos']): dict(f['const'], bits=f.get('bits')) for f in json.load(open(sys.argv[sys.argv.index('--fixes') + 1]))['fixes']}
slots = None
if '--slots' in sys.argv:
    # M11-N201 (#3932): m11_setother_slot_class.py の出力のうち実値化 (lea_alloca) の行だけを 0 詰め引数へ入れる
    slots = {(r['caller'], r['callee'], r['k'], r['pos']): r['value'][1:] for r in json.load(open(sys.argv[sys.argv.index('--slots') + 1]))
             if r['class'] == '実値化' and r['reason'] == 'lea_alloca' and r['value'] and r['value'].startswith('&%stack_var_')}
    rep['sigfix_slot_entries'] = len(slots)
text = sigfix(text, rep, pads, fixes, slots)
rep['sigfix_zeropad_sites'] = len(pads)
rep['sigfix_zeropad_args'] = sum(p['want'] - p['have'] for p in pads)
print('[m11_post][sigfix] 0 詰め call site: %d (0 詰め引数 %d)' % (rep['sigfix_zeropad_sites'], rep['sigfix_zeropad_args']))
if '--pads' in sys.argv:
    json.dump(pads, open(sys.argv[sys.argv.index('--pads') + 1], 'w'))
text = def_re.sub(weaken, text)

NMAX = 8
tr = []
tab = []
maxargs = 0
for (nm, ret, args) in fns:
    tys = ptypes(args)
    maxargs = max(maxargs, len(tys))
    if len(tys) > NMAX:
        continue
    ret = ret.split()[0] if ret else 'void'
    va = int(nm.split('_')[1], 16)
    L = ['define i64 @m11_tr_%s(i64 %%a0, i64 %%a1, i64 %%a2, i64 %%a3, i64 %%a4, i64 %%a5, i64 %%a6, i64 %%a7) {' % nm]
    cargs = []
    for i, t in enumerate(tys):
        v = '%%a%d' % i
        if t == 'i64':
            cargs.append('i64 %s' % v)
        elif t in ('i32', 'i16', 'i8', 'i1'):
            L.append('  %%c%d = trunc i64 %s to %s' % (i, v, t))
            cargs.append('%s %%c%d' % (t, i))
        elif t == 'ptr':
            L.append('  %%c%d = inttoptr i64 %s to ptr' % (i, v))
            cargs.append('ptr %%c%d' % i)
        elif t == 'i128':
            L.append('  %%c%d = zext i64 %s to i128' % (i, v))
            cargs.append('i128 %%c%d' % i)
        elif t == 'double':
            L.append('  %%c%d = bitcast i64 %s to double' % (i, v))
            cargs.append('double %%c%d' % i)
        elif t == 'float':
            L.append('  %%t%d = trunc i64 %s to i32' % (i, v))
            L.append('  %%c%d = bitcast i32 %%t%d to float' % (i, i))
            cargs.append('float %%c%d' % i)
        elif t == '%tagPOINT':
            # #4184 (LD-200): POINT は 8 バイト値渡し (x64 rcx = x | y<<32)。下位 32bit が x、上位が y
            L.append('  %%px%d = trunc i64 %s to i32' % (i, v))
            L.append('  %%ps%d = lshr i64 %s, 32' % (i, v))
            L.append('  %%py%d = trunc i64 %%ps%d to i32' % (i, i))
            L.append('  %%u%d = insertvalue %%tagPOINT undef, i32 %%px%d, 0' % (i, i))
            L.append('  %%c%d = insertvalue %%tagPOINT %%u%d, i32 %%py%d, 1' % (i, i, i))
            cargs.append('%%tagPOINT %%c%d' % i)
        else:
            L.append('  ; unsupported param %s' % t)
            cargs.append('%s zeroinitializer' % t)
    callexpr = 'call %s @%s(%s)' % (ret, nm, ', '.join(cargs))
    if ret == 'void':
        L.append('  ' + callexpr)
        L.append('  ret i64 0')
    elif ret == 'i64':
        L.append('  %r = ' + callexpr)
        L.append('  ret i64 %r')
    elif ret in ('i32', 'i16', 'i8', 'i1'):
        L.append('  %r = ' + callexpr)
        L.append('  %%z = zext %s %%r to i64' % ret)
        L.append('  ret i64 %z')
    elif ret == 'ptr':
        L.append('  %r = ' + callexpr)
        L.append('  %p = ptrtoint ptr %r to i32')
        L.append('  %z = zext i32 %p to i64')
        L.append('  ret i64 %z')
    elif ret == 'i128':
        L.append('  %r = ' + callexpr)
        L.append('  %z = trunc i128 %r to i64')
        L.append('  ret i64 %z')
    else:
        L.append('  %r = ' + callexpr)
        L.append('  ret i64 0')
    L.append('}')
    tr.append('\n'.join(L))
    tab.append((va, nm))

tab.sort()
# C prototype header: IR の署名そのまま (C override が呼ぶ extern を署名ずれさせない: ずれると wasm-ld が trap thunk を生成する)
CT = {'i64': 'unsigned long long', 'i32': 'unsigned int', 'i16': 'unsigned int', 'i8': 'unsigned int', 'i1': 'unsigned int',
      'ptr': 'void*', 'void': 'void', 'i128': 'unsigned __int128', 'double': 'double', 'float': 'float'}
hdr = ['/* auto-gen by m11_post.py: IR function_* の C 署名 */']
for (nm, ret, args) in fns:
    rt = CT.get(ret.split()[0], 'unsigned long long')
    ats = ', '.join(CT.get(t, 'unsigned long long') for t in ptypes(args)) or 'void'
    hdr.append('extern %s %s(%s);' % (rt, nm, ats))
open(dst.replace('.ll', '_sigs.h'), 'w').write('\n'.join(hdr) + '\n')
ent = ', '.join('{ i32, ptr } { i32 %d, ptr @m11_tr_%s }' % (va, nm) for va, nm in tab)
# 計測時 (M11_INSTR_413060=1) のみ PROBES に 0x413060 が入り、dest 観測の宣言が出る
tail = ['', 'declare void @m11_probe(i32)'] + (['declare void @m11_dest_obs(i64)'] if 0x413060 in PROBES and M11_PROBE_VARIANT not in ('nodecl', 'noren') else []) + (['declare void @m11_p144_obs(i64)'] if M11_INSTR_40FF70 else []) + (['declare void @m11_ffe0_obs(i64)'] if M11_INSTR_40FFE0 else []) + (['declare void @m11_a270_obs(i64)'] if M11_INSTR_60A270 else []) + (['declare void @m11_412770_obs(i64)'] if M11_INSTR_412770 else []) + (['declare void @m11_4128b0_obs()'] if M11_INSTR_4128B0 else []) + (['declare void @m11_412770_br_obs(i64, i32, i32)'] if os.environ.get('M11_INSTR_412BR') in ('1', '2') else []) + (['declare void @m11_412770_gate_obs(i64)'] if os.environ.get('M11_INSTR_412BR') == '3' else []) + (['declare void @m11_80e040_loop_obs(i64, i64, i64)'] if os.environ.get('M11_INSTR_80E040') == '1' else []) + (['declare void @m11_412770_br2_obs()'] if os.environ.get('M11_INSTR_412BR') == '2' else []) + (['declare void @m11_e3ef60_obs(i64)'] if M11_INSTR_E3EF60 else []) + (['declare void @m11_414c70_obs(i64, i64, i64)'] if M11_INSTR_414C70 else []) + probe_wrappers + ['', '; ---- m11_post.py: 間接 call トランポリン + VA 表 ----']
tail.extend(tr)
tail.append('@m11_disp_n = constant i32 %d' % len(tab))
tail.append('@m11_disp_tab = constant [%d x { i32, ptr }] [%s]' % (len(tab), ent))
text = text.rstrip('\n') + '\n' + '\n'.join(tail) + '\n'
open(dst, 'w').write(text)
import json as _j
open(dst.replace('.ll', '_probes.json'), 'w').write(_j.dumps(list(PROBES.values())))
rep.update({'weak_defines': len(fns), 'trampolines': len(tab), 'max_args': maxargs})
print('[m11_post] weak defines: %d, trampolines: %d, max params: %d -> %s' % (len(fns), len(tab), maxargs, dst))
if rep_path:
    json.dump(rep, open(rep_path, 'w'))
