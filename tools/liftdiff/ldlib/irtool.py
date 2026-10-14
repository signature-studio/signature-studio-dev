"""IR (LLVM .ll) ユーティリティ: 関数署名の抽出・entry トレース計装・外部スタブ生成。

liftdiff は lift 結果 IR を「文字列として」扱う (llvm Python binding 不要)。署名は `define ... @function_<VA>(...)` 行から読む。
"""
import re

DEF_RE = re.compile(r'^define\s+(?P<pre>[^@]*?)@(?P<name>[A-Za-z0-9_.$]+)\((?P<args>.*)\)(?P<post>[^)]*)\{\s*$')
DECL_RE = re.compile(r'^declare\s+(?P<pre>[^@]*?)@(?P<name>[A-Za-z0-9_.$]+)\((?P<args>.*)\)(?P<post>[^)]*)$')
ATTR_WORDS = {'noundef', 'zeroext', 'signext', 'nonnull', 'readonly', 'writeonly', 'noalias', 'nocapture', 'inreg', 'returned',
              'weak', 'dso_local', 'internal', 'linkonce_odr', 'linkonce', 'external', 'local_unnamed_addr', 'unnamed_addr', 'fastcc', 'ccc',
              'hidden', 'protected', 'default', 'noreturn', 'nounwind'}


def split_top(s):
    out, cur, depth = [], '', 0
    for ch in s:
        if ch in '(<[{':
            depth += 1
        elif ch in ')>]}':
            depth -= 1
        if ch == ',' and depth == 0:
            out.append(cur.strip())
            cur = ''
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def param_type(p):
    """'i64 noundef %arg1' -> ('i64', '%arg1' or None)"""
    toks = p.split()
    # 型が <4 x float> や { .. } の場合
    if p.startswith('<') or p.startswith('{') or p.startswith('['):
        close = {'<': '>', '{': '}', '[': ']'}[p[0]]
        k = p.index(close)
        ty = p[:k + 1]
        rest = p[k + 1:].split()
    else:
        ty = toks[0]
        rest = toks[1:]
    nm = rest[-1] if rest and rest[-1].startswith('%') else None
    return ty, nm


def ret_type(pre):
    toks = [t for t in pre.split() if t not in ATTR_WORDS]
    if not toks:
        return 'void'
    # 戻り値型は残った最初のトークン (struct/vec は未対応 → 文字列結合)
    return ' '.join(toks)


def parse_sigs(ll_path, prefix='function_'):
    """{name: {'ret':..., 'params':[ty,...], 'defined':bool}}"""
    sigs = {}
    with open(ll_path, errors='replace') as f:
        for line in f:
            if line.startswith('define '):
                m = DEF_RE.match(line.rstrip('\n'))
                if m and m.group('name').startswith(prefix):
                    ps = [param_type(p) for p in split_top(m.group('args'))]
                    sigs[m.group('name')] = {'ret': ret_type(m.group('pre')), 'params': [t for t, _ in ps], 'defined': True}
            elif line.startswith('declare '):
                m = DECL_RE.match(line.rstrip('\n'))
                if m and m.group('name').startswith(prefix):
                    ps = [param_type(p) for p in split_top(m.group('args'))]
                    sigs.setdefault(m.group('name'), {'ret': ret_type(m.group('pre')), 'params': [t for t, _ in ps], 'defined': False})
    return sigs


INT_RE = re.compile(r'^i(\d+)$')


BLK_RE = re.compile(r'^dec_label_pc_([0-9a-fA-F]+):(\s*;.*)?$')


def instrument(ll_in, ll_out, prefix='function_', blocks=False):
    """各 `function_*` の entry に ld_trace(va, np, a0..a7, x0..x3) 呼出しを挿入する (意味不変)。
    blocks=True のとき、各 `dec_label_pc_<VA>:` の直後に ld_blk(VA) を挿入する (LD-64 / #1854)。
    戻り値: 計装した関数数"""
    n = 0
    with open(ll_in, errors='replace') as fi, open(ll_out, 'w') as fo:
        pending = None
        for line in fi:
            if line.lstrip().startswith('uselistorder'):
                continue
            if blocks:
                bm = BLK_RE.match(line.rstrip('\n'))
                if bm:
                    fo.write(line)
                    fo.write('  call void @ld_blk(i64 %d)\n' % int(bm.group(1), 16))
                    continue
            if pending is not None:
                # 直前が define 行。entry ラベル行ならその後ろ、そうでなければこの行の前に挿入
                if re.match(r'^[A-Za-z0-9_.$-]+:', line):
                    fo.write(line)
                    fo.write(pending)
                else:
                    fo.write(pending)
                    fo.write(line)
                pending = None
                continue
            fo.write(line)
            if line.startswith('define ') and line.rstrip().endswith('{'):
                m = DEF_RE.match(line.rstrip('\n'))
                if not m or not m.group('name').startswith(prefix):
                    continue
                name = m.group('name')
                try:
                    va = int(name[len(prefix):], 16)
                except ValueError:
                    continue
                ps = [param_type(p) for p in split_top(m.group('args'))]
                body = []
                A = ['0'] * 8
                X = ['0'] * 4
                for i, (ty, nm) in enumerate(ps[:8]):
                    ref = nm if nm else '%%%d' % i
                    t = '%%ld.%d' % i
                    mi = INT_RE.match(ty)
                    if ty == 'ptr':
                        body.append('  %s = ptrtoint ptr %s to i64' % (t, ref)); A[i] = t
                    elif mi and int(mi.group(1)) == 64:
                        A[i] = ref
                    elif mi and int(mi.group(1)) < 64:
                        body.append('  %s = zext %s %s to i64' % (t, ty, ref)); A[i] = t
                    elif ty == 'double':
                        body.append('  %s = bitcast double %s to i64' % (t, ref))
                        (X.__setitem__(i, t) if i < 4 else A.__setitem__(i, t))
                    elif ty == 'float':
                        body.append('  %s.b = bitcast float %s to i32' % (t, ref))
                        body.append('  %s = zext i32 %s.b to i64' % (t, t))
                        (X.__setitem__(i, t) if i < 4 else A.__setitem__(i, t))
                call = '  call void @ld_trace(i64 %d, i32 %d, %s, %s)\n' % (
                    va, len(ps), ', '.join('i64 ' + a for a in A), ', '.join('i64 ' + x for x in X))
                pending = '\n'.join(body) + ('\n' if body else '') + call
                n += 1
        if pending is not None:
            fo.write(pending)
        fo.write('\ndeclare void @ld_trace(i64, i32, i64, i64, i64, i64, i64, i64, i64, i64, i64, i64, i64, i64)\n')
        if blocks:
            fo.write('declare void @ld_blk(i64)\n')
    return n


C_TYPE = {'void': 'void', 'ptr': 'void*', 'float': 'float', 'double': 'double', 'i64': 'u64'}
SKIP_DECL = re.compile(r'^(llvm\.|__asm_|__divti3|__modti3|__multi3|__umodti3|__udivti3|__indirect_function_table|__stack_pointer|ld_trace$|ld_blk$|__readgsqword$|m11_counter_ptr$|m11_probe$|memcpy$|memset$|memmove$)')


def ctype(ty):
    if ty in C_TYPE:
        return C_TYPE[ty]
    m = INT_RE.match(ty)
    if m:
        return 'u64' if int(m.group(1)) == 64 else 'unsigned'
    return None


def gen_stubs(ll_path, defined_names, prefix='function_'):
    """IR の declare から、呼出しをログして ld_stub() の応答を返す C スタブを生成する。
    戻り値: (C ソース文字列, [名前...], 型未対応で飛ばした名前)
    CAB-233: 第5/6引数も ld_stub_x へ転送する (MultiByteToWideChar 等 6引数 API の dst 書込み用)。"""
    out = ['#include <stdint.h>', 'typedef unsigned long long u64;',
           'extern u64 ld_stub_x(const char* n, u64 a0, u64 a1, u64 a2, u64 a3, u64 a4, u64 a5);']
    names, skipped = [], []
    widths = {}
    seen = set()
    with open(ll_path, errors='replace') as f:
        for line in f:
            if not line.startswith('declare '):
                continue
            m = DECL_RE.match(line.rstrip('\n'))
            if not m:
                continue
            nm = m.group('name')
            if nm in seen or nm in defined_names or SKIP_DECL.match(nm):
                continue
            seen.add(nm)
            ps = [param_type(p)[0] for p in split_top(m.group('args'))]
            rt = ret_type(m.group('pre'))
            cps = [ctype(t) for t in ps]
            crt = ctype(rt)
            if crt is None or any(c is None or c == 'void' for c in cps):
                skipped.append(nm)
                continue
            names.append(nm)
            widths[nm] = [64 if c == 'u64' else 32 for c in cps[:4]]
            params = ', '.join('%s a%d' % (c, i) for i, c in enumerate(cps)) or 'void'
            av = []
            for i, c in enumerate(cps[:6]):
                if c in ('float', 'double'):
                    av.append('0')
                elif c == 'void*':
                    av.append('(u64)(uintptr_t)a%d' % i)
                else:
                    av.append('(u64)a%d' % i)
            while len(av) < 6:
                av.append('0')
            call = 'ld_stub_x("%s", %s)' % (nm, ', '.join(av))
            if crt == 'void':
                out.append('void %s(%s) { %s; }' % (nm, params, call))
            elif crt == 'void*':
                out.append('void* %s(%s) { return (void*)(uintptr_t)%s; }' % (nm, params, call))
            elif crt in ('float', 'double'):
                out.append('%s %s(%s) { %s; return 0; }' % (crt, nm, params, call))
            else:
                out.append('%s %s(%s) { return (%s)%s; }' % (crt, nm, params, crt, call))
    gen_stubs.widths = widths
    return '\n'.join(out) + '\n', names, skipped


GLOB_RE = re.compile(r'^@([\w.$-]+) = [^\[]*\[(\d+) x i8\]')
LOADG_RE = re.compile(r'load (i\d+|float|double), ptr @([\w.$-]+)')
BITS = {'i8': 8, 'i16': 16, 'i32': 32, 'i64': 64, 'i128': 128, 'float': 32, 'double': 64}
REGSLOT_RE = re.compile(r'bitcast ptr %(rax|rbx|rcx|rdx|rsi|rdi|rbp|rsp|r8|r9|r1[0-5])\b')
CALL_RE = re.compile(r'\bcall\b[^()@]*?\s(@[\w.$-]+|%[\w.$-]+)\(')


def ir_features(ll_path, prefix='function_'):
    """IR を 1 パスで走査し関数ごとに {icalls, fcmp, asm_calls, callees, allocas, unreachable} を返す。"""
    feats = {}
    cur = None
    gsize = {}
    with open(ll_path, errors='replace') as f:
        for line in f:
            if line.startswith('@'):
                mg = GLOB_RE.match(line)
                if mg:
                    gsize[mg.group(1)] = int(mg.group(2))
                continue
            if line.startswith('define '):
                m = DEF_RE.match(line.rstrip('\n'))
                cur = None
                if m and m.group('name').startswith(prefix):
                    cur = feats.setdefault(m.group('name'), dict(regslot_deref=0, icalls=0, fcmp=0, asm_calls=0, callees=[], allocas=0, unreachable=0, lines=0))
                continue
            if cur is None:
                continue
            if line.startswith('}'):
                cur = None
                continue
            cur['lines'] += 1
            if 'ptr @' in line and ' load ' in line:
                ml = LOADG_RE.search(line)
                if ml and ml.group(2) in gsize and BITS.get(ml.group(1), 0) > gsize[ml.group(2)] * 8:
                    cur['short_global_loads'] = cur.get('short_global_loads', 0) + 1
            if 'bitcast ptr %' in line and REGSLOT_RE.search(line):
                cur['regslot_deref'] += 1
            if ' call ' in line:
                m = CALL_RE.search(line)
                if m:
                    tgt = m.group(1)
                    if tgt[0] == '%':
                        cur['icalls'] += 1
                    elif tgt.startswith('@__asm_'):
                        cur['asm_calls'] += 1
                    elif tgt.startswith('@' + prefix):
                        cur['callees'].append(tgt[1:])
            elif ' fcmp ' in line:
                cur['fcmp'] += 1
            elif ' alloca ' in line:
                cur['allocas'] += 1
            elif 'unreachable' in line and line.strip() == 'unreachable':
                cur['unreachable'] += 1
    return feats


C_TY = {'double': 'double', 'float': 'float', 'long long': 'i64', 'unsigned long long': 'i64', 'uint64_t': 'i64', 'int64_t': 'i64',
        'int': 'i32', 'unsigned': 'i32', 'unsigned int': 'i32', 'uint32_t': 'i32', 'int32_t': 'i32', 'void': 'void',
        'uint8_t': 'i8', 'unsigned char': 'i8', 'char': 'i8', 'short': 'i16', 'uint16_t': 'i16', 'size_t': 'i32', 'u64': 'i64', 'u32': 'i32'}
CDEF_RE = re.compile(r'^\s*(?:static\s+|EMSCRIPTEN_KEEPALIVE\s+)*([A-Za-z_][\w\s\*]*?)\s+(function_[0-9a-f]+)\s*\(([^)]*)\)\s*\{', re.M)


def _cty(t):
    t = t.replace('const', '').replace('volatile', '').strip()
    if '*' in t:
        return 'ptr'
    return C_TY.get(' '.join(t.split()))


def parse_c_sigs(path, prefix='function_'):
    """C で手書きされた function_<VA> 定義の署名 (IR 署名相当) を抽出。型を解釈できないものは除外。"""
    out = {}
    try:
        txt = open(path, errors='replace').read()
    except OSError:
        return out
    for m in CDEF_RE.finditer(txt):
        ret, name, args = m.group(1), m.group(2), m.group(3).strip()
        r = _cty(ret.replace('*', ' * ')) if '*' not in ret else 'ptr'
        if r is None:
            continue
        ps = []
        ok = True
        if args and args != 'void':
            for a in split_top(args):
                a = re.sub(r'\b(const|volatile)\b', '', a).strip()
                # 末尾の識別子 (引数名) を除去
                mm = re.match(r'^(.*?)([A-Za-z_]\w*)?$', a)
                tyname = a
                if '*' in a:
                    ps.append('ptr'); continue
                toks = a.split()
                tyname = ' '.join(toks[:-1]) if len(toks) > 1 else a
                c = C_TY.get(tyname) or C_TY.get(a)
                if c is None:
                    ok = False; break
                ps.append(c)
        if ok:
            out[name] = {'ret': r, 'params': ps, 'defined': True, 'c': True}
    return out
