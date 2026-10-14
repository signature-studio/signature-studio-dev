#!/usr/bin/env python3
"""[PLG-F3-17 / #1834] RetDec が i32 と推定した仮引数が、本体ではポインタ (`inttoptr i64 %argN`) として使われる関数を i64 に直す。
観測: function_18004f7f8(i64 %arg1, i32 %arg2) の本体は `icmp eq i32 %arg2, 0` と `inttoptr i64 %arg2 to ptr` を持つ。
実機 (block19048 @0x18004f7f8) では第 2 引数は rdx (64 bit) で `test rdx, rdx` / `movups [rdx]` と読む。 i32 は RetDec の型推定の誤り。
呼び出し側は `trunc i64 W to i32` か `i32 0` で渡していたため、同じ誤りを引きずっている。
対象は、本体での使用が `icmp ... i32 %argN` と `inttoptr i64 %argN` だけの i32 仮引数に限る (他の使用があれば何もしない)。
(1) 定義の `i32 %argN` を `i64 %argN` にし、本体の icmp を i64 に揃える。
(2) module 内の call site の `i32 X` を i64 で渡す (`trunc i64 W to i32` は W を直接渡す / `0` は `i64 0` / それ以外は zext)。
(3) 宣言・定義の引数型が ptr の関数へ i64 値を渡す call と、本体の `ptr %X` で X が i64 の値のものを `inttoptr` で揃える (`FreeEnvironmentStringsW` の `%penv` 類型。19048 の `function_180051a20(i64 %penv)` で発火する)。
usage: fix_arg_width.py IN.ll OUT.ll   (stderr: 修正数)
"""
import re, sys

src = open(sys.argv[1]).read().split('\n')


def func_span(lines, si):
    end = si + 1
    while end < len(lines) and not lines[end].startswith('}'):
        end += 1
    return end


def parse_args(s):
    return [a.strip() for a in re.split(r',\s*(?![^()]*\))', s) if a.strip()]


# 1) 対象 (関数名 -> 引数番号の集合) を集める
targets = {}   # name -> {k: '%argN'}
for si, l in enumerate(src):
    m = re.match(r'^define (\S+) @([\w.$]+)\((.*?)\)', l)
    if not m:
        continue
    end = func_span(src, si)
    body = src[si + 1:end]
    for k, a in enumerate(parse_args(m.group(3))):
        t = a.split()
        if len(t) != 2 or t[0] != 'i32' or not t[1].startswith('%'):
            continue
        v = re.escape(t[1])
        if not any(re.search(r'inttoptr i64 %s to ptr' % v, b) for b in body):
            continue
        other = [b for b in body
                 if re.search(r'%s(?![\w.$])' % v, b)
                 and not re.search(r'icmp \w+ i32 %s, ' % v, b)
                 and not re.search(r'inttoptr i64 %s to ptr' % v, b)]
        if other:
            print('fix_arg_width: skip %s %s (other uses: %d)' % (m.group(2), t[1], len(other)), file=sys.stderr)
            continue
        targets.setdefault(m.group(2), {})[k] = t[1]

nd = nc = 0
out = []
i = 0
while i < len(src):
    l = src[i]
    m = re.match(r'^define (\S+) @([\w.$]+)\((.*?)\)(.*)$', l)
    if m and m.group(2) in targets:
        end = func_span(src, i)
        fix = targets[m.group(2)]
        newargs = []
        for k, a in enumerate(parse_args(m.group(3))):
            if k in fix:
                newargs.append('i64 ' + fix[k])
                nd += 1
            else:
                newargs.append(a)
        out.append('define %s @%s(%s)%s' % (m.group(1), m.group(2), ', '.join(newargs), m.group(4)))
        vnames = set(fix.values())
        for b in src[i + 1:end]:
            for v in vnames:
                b = re.sub(r'(icmp \w+) i32 (%s)(?![\w.$])' % re.escape(v), r'\1 i64 \2', b)
            out.append(b)
        i = end
        continue
    out.append(l)
    i += 1

# 2) call site
final = []
trunc_src = {}
uid = 0
for l in out:
    if l.startswith('define '):
        trunc_src = {}
    mt = re.match(r'^\s*(%[\w.$]+) = trunc i64 (\S+) to i32$', l)
    if mt:
        trunc_src[mt.group(1)] = mt.group(2)
    mc = re.match(r'^(\s*)((?:%[\w.\-]+ = )?)(call|tail call) (\S+) @([\w.$]+)\((.*)\)(.*)$', l)
    if mc and mc.group(5) in targets:
        ind = mc.group(1)
        new, pre = [], []
        for k, a in enumerate(parse_args(mc.group(6))):
            t = a.split()
            if k in targets[mc.group(5)] and len(t) == 2 and t[0] == 'i32':
                v = t[1]
                if v == '0':
                    new.append('i64 0')
                elif v in trunc_src:
                    new.append('i64 ' + trunc_src[v])
                else:
                    uid += 1
                    nm = '%%argw_%d' % uid
                    pre.append('%s%s = zext i32 %s to i64' % (ind, nm, v))
                    new.append('i64 ' + nm)
                nc += 1
            else:
                new.append(a)
        final.extend(pre)
        l = '%s%s%s %s @%s(%s)%s' % (ind, mc.group(2), mc.group(3), mc.group(4), mc.group(5), ', '.join(new), mc.group(7))
    final.append(l)


# 3) 宣言・定義の引数型が ptr の関数へ i64 値を渡す call を inttoptr で揃える (本体の使用を変えない)
sigs = {}
for l in final:
    m = re.match(r'^(?:define|declare) \S+ @([\w.$]+)\((.*?)\)', l)
    if m:
        sigs[m.group(1)] = [a.split()[0] if a.split() else '' for a in parse_args(m.group(2))]
ptr_calls = 0
ptr_uses = 0
res2 = []
i64s = set()
for l in final:
    if l.startswith('define '):
        m = re.match(r'^define \S+ @[\w.$]+\((.*?)\)', l)
        i64s = set(re.findall(r'i64 (%[\w.$]+)', m.group(1)))
    else:
        d = re.match(r'^\s*(%[\w.$]+) = (?:ptrtoint .* to i64|(?:add|sub|mul|and|or|xor|shl|lshr|ashr|select|load|zext|sext|trunc|call) (?:i1 [^,]+, )?i64\b)', l)
        if d:
            i64s.add(d.group(1))
    if not l.startswith('define ') and not l.startswith('declare ') and re.search(r'\bptr %[\w.$]+', l) and i64s:
        def _ptr_op(m):
            global uid, ptr_uses
            v = m.group(1)
            if v not in i64s:
                return m.group(0)
            uid += 1
            ptr_uses += 1
            nm = '%%argp_%d' % uid
            res2.append('  %s = inttoptr i64 %s to ptr' % (nm, v))
            return 'ptr ' + nm
        if not re.match(r'^\s*%[\w.$]+ = inttoptr i64', l):
            l = re.sub(r'ptr (%[\w.$]+)(?![\w.$-])', _ptr_op, l)
    mc = re.match(r'^(\s*)((?:%[\w.\-]+ = )?)(call|tail call) (\S+) @([\w.$]+)\((.*)\)(.*)$', l)
    if mc and mc.group(5) in sigs and 'ptr' in sigs[mc.group(5)]:
        ptypes = sigs[mc.group(5)]
        args = parse_args(mc.group(6))
        new, pre, here = [], [], 0
        for k, a in enumerate(args):
            t = a.split()
            if k < len(ptypes) and ptypes[k] == 'ptr' and len(t) == 2 and t[0] == 'i64':
                if t[1] == '0':
                    new.append('ptr null')
                    here += 1
                elif t[1] in i64s:
                    uid += 1
                    nm = '%%argp_%d' % uid
                    pre.append('%s%s = inttoptr i64 %s to ptr' % (mc.group(1), nm, t[1]))
                    new.append('ptr ' + nm)
                    here += 1
                else:
                    new.append(a)
            else:
                new.append(a)
        ptr_calls += here
        if here:
            res2.extend(pre)
            l = '%s%s%s %s @%s(%s)%s' % (mc.group(1), mc.group(2), mc.group(3), mc.group(4), mc.group(5), ', '.join(new), mc.group(7))
    res2.append(l)

open(sys.argv[2], 'w').write('\n'.join(res2))
print('fix_arg_width: defs =', nd, 'callsites =', nc, 'ptr_args =', ptr_calls, 'ptr_uses =', ptr_uses, file=sys.stderr)
