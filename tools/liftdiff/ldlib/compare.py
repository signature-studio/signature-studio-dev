"""native / wasm の case 結果を比較して差分 (diffs) を作る。ポインタは address ずれ (delta) を許容して正規化する。"""

M64 = (1 << 64) - 1
NATIVE_STACK_LO = 0x7000_0000_0000
SENTINEL = 0xCAFEBABE0BADF00D


class Ctx:
    """windows = [(lo, hi)] は wasm 側座標。native の同領域は +delta。"""

    def __init__(self, delta, windows, wasm_stack):
        self.delta = delta
        self.win = windows
        self.wstack = wasm_stack

    def n2w(self, v):
        """native 値 → wasm 座標 (領域内ポインタなら -delta)"""
        for lo, hi in self.win:
            if lo + self.delta <= v < hi + self.delta:
                return v - self.delta
        return v

    def eq(self, vn, vw, width=64):
        m = (1 << width) - 1
        vn &= M64
        vw &= M64
        if (vn & m) == (vw & m):
            return True
        if (self.n2w(vn) & m) == (vw & m):
            return True
        if vn >= NATIVE_STACK_LO and self.wstack[0] <= (vw & 0xffffffff) < self.wstack[1]:
            return True
        # 32bit 切り詰め後の rebase (wasm は ptr が 32bit)
        if width < 64 and (((vn - self.delta) & m) == (vw & m)):
            return True
        return False


def _blocks(mem):
    d = {}
    for b in mem:
        d[(b['r'], int(b['o'], 16))] = (int.from_bytes(bytes.fromhex(b['b']), 'little'), int.from_bytes(bytes.fromhex(b['a']), 'little'))
    return d


def cmp_mem(n, w, ctx, limit=8):
    bn, bw = _blocks(n.get('mem', [])), _blocks(w.get('mem', []))
    diffs = []
    for k in sorted(set(bn) | set(bw)):
        if k in bn and k in bw:
            vn, vw = bn[k][1], bw[k][1]
            if not ctx.eq(vn, vw):
                diffs.append({'r': k[0], 'o': hex(k[1]), 'native': hex(vn), 'wasm': hex(vw)})
        elif k in bn:
            pre, post = bn[k]
            if not ctx.eq(post, ctx.n2w(pre)):
                diffs.append({'r': k[0], 'o': hex(k[1]), 'native': hex(post), 'wasm': 'unchanged(%s)' % hex(pre)})
        else:
            pre, post = bw[k]
            vn = pre + ctx.delta if _in(ctx, pre) else pre
            if not ctx.eq(vn, post):
                diffs.append({'r': k[0], 'o': hex(k[1]), 'native': 'unchanged(%s)' % hex(pre), 'wasm': hex(post)})
    return diffs[:limit], len(diffs)


def _in(ctx, v):
    return any(lo <= v < hi for lo, hi in ctx.win)


def cmp_ret(n, w, ctx):
    rt = w.get('rtype', 'i64')
    if rt == 'void':
        return None
    if rt == 'double':
        a, b = int(n['x0'], 16), int(w['x0'], 16)
        return None if a == b else {'native_x0': hex(a), 'wasm_x0': hex(b)}
    if rt == 'float':
        a, b = int(n['x0'], 16) & 0xffffffff, int(w['x0'], 16)
        return None if a == b else {'native_x0': hex(a), 'wasm_x0': hex(b)}
    width = {'i64': 64, 'i32': 32, 'ptr': 32, 'i16': 16, 'i8': 8, 'i1': 1}.get(rt, 64)
    a, b = int(n['rax'], 16), int(w['rax'], 16)
    # native が実際に書いたバイトのみ比較 (sentinel と同じバイトは「書かれていない」とみなす: al/ax/eax 戻りの上位ゴミ対策)
    mask = 0
    for i in range(8):
        if ((a >> (8 * i)) & 0xff) != ((SENTINEL >> (8 * i)) & 0xff):
            mask |= 0xff << (8 * i)
    if mask == 0:
        return None
    mask &= (1 << width) - 1 if width < 64 else M64
    if mask == 0:
        return None
    if mask == M64 or mask == 0xffffffff:
        return None if ctx.eq(a, b, 64 if mask == M64 else 32) or ctx.eq(a, b, width) else {'native_rax': hex(a), 'wasm_rax': hex(b), 'width': width}
    return None if (a & mask) == (b & mask) else {'native_rax': hex(a), 'wasm_rax': hex(b), 'width': width, 'mask': hex(mask)}


def cmp_calls(n, w, ctx, stub_info):
    cn, cw = n.get('calls', []), w.get('calls', [])
    for i in range(max(len(cn), len(cw))):
        if i >= len(cn) or i >= len(cw):
            return {'index': i, 'native': cn[i]['n'] if i < len(cn) else None, 'wasm': cw[i]['n'] if i < len(cw) else None,
                    'kind': 'native_extra_call' if i < len(cn) else 'wasm_extra_call', 'native_len': len(cn), 'wasm_len': len(cw)}
        a, b = cn[i], cw[i]
        if a['n'] != b['n']:
            return {'index': i, 'native': a['n'], 'wasm': b['n'], 'kind': 'call_name'}
        info = stub_info.get(a['n'], {})
        widths = info.get('widths', [32] * 4)
        for k in range(min(4, len(widths))):
            if not ctx.eq(int(a['a'][k], 16), int(b['a'][k], 16), widths[k]):
                return {'index': i, 'name': a['n'], 'arg': k, 'native': a['a'][k], 'wasm': b['a'][k], 'kind': 'call_arg'}
    return None


def _width(ty):
    return {'i64': 64, 'ptr': 32, 'i32': 32, 'i16': 16, 'i8': 8, 'i1': 1, 'float': 32, 'double': 64}.get(ty, 64)


def cmp_trace(n, w, ctx, sigs, prefix='function_', skip=frozenset()):
    tn, tw = n.get('trace', []), w.get('trace', [])
    if skip:
        tn = [e for e in tn if int(e[0], 16) not in skip]
        tw = [e for e in tw if int(e[0], 16) not in skip]
    for i in range(max(len(tn), len(tw))):
        if i >= len(tn) or i >= len(tw):
            if n.get('trace_over', 0) or w.get('trace_over', 0):
                return None
            return {'index': i, 'kind': 'native_extra_entry' if i < len(tn) else 'wasm_extra_entry',
                    'va': (tn[i][0] if i < len(tn) else tw[i][0]), 'native_len': len(tn), 'wasm_len': len(tw)}
        a, b = tn[i], tw[i]
        if a[0] != b[0]:
            return {'index': i, 'kind': 'entry_va', 'native': a[0], 'wasm': b[0], 'native_len': len(tn), 'wasm_len': len(tw)}
        np_ = b[1]
        sig = sigs.get('%s%x' % (prefix, int(b[0], 16)), {}).get('params', [])
        for pos in range(min(np_, 8)):
            ty = sig[pos] if pos < len(sig) else 'i64'
            width = _width(ty)
            fp = ty in ('float', 'double')
            if fp and pos < 4:
                vn, vw = int(a[2 + 8 + pos], 16), int(b[2 + 8 + pos], 16)
            else:
                vn, vw = int(a[2 + pos], 16), int(b[2 + pos], 16)
            if not ctx.eq(vn, vw, width):
                return {'index': i, 'kind': 'entry_arg', 'va': a[0], 'pos': pos, 'type': ty, 'native': hex(vn), 'wasm': hex(vw)}
    return None


def compare_case(n, w, ctx, sigs, stub_info, skip=frozenset()):
    """戻り: dict(outcome, diffs{}) ; outcome ∈ equal / diff / wasm_trap / native_fault / both_fault / hang"""
    sn, sw = n.get('status'), w.get('status')
    if sn in ('hang', 'crash') or sw in ('hang', 'crash'):
        return {'outcome': 'hang', 'native': sn, 'wasm': sw}
    if sw == 'timeout' and sn == 'ok':
        return {'outcome': 'wasm_trap', 'native': sn, 'wasm': sw, 'wasm_detail': 'timeout: wasm did not finish within 1s (infinite loop?) while native completed'}
    if sn == 'timeout' or sw == 'timeout':
        return {'outcome': 'hang', 'native': sn, 'wasm': sw}
    n_ok, w_ok = sn == 'ok', sw == 'ok'
    if n_ok and not w_ok:
        return {'outcome': 'wasm_trap', 'native': sn, 'wasm': sw, 'wasm_detail': w.get('detail', '')}
    if not n_ok and w_ok:
        return {'outcome': 'native_fault', 'native': sn, 'wasm': sw, 'fault': n.get('fault'), 'native_detail': n.get('detail', '')}
    if not n_ok and not w_ok:
        return {'outcome': 'both_fault', 'native': sn, 'wasm': sw, 'wasm_detail': w.get('detail', ''), 'fault': n.get('fault')}
    d = {}
    r = cmp_ret(n, w, ctx)
    if r:
        d['ret'] = r
    m, cnt = cmp_mem(n, w, ctx)
    if m:
        d['mem'] = {'count': cnt, 'first': m}
    c = cmp_calls(n, w, ctx, stub_info)
    if c:
        d['calls'] = c
    t = cmp_trace(n, w, ctx, sigs, skip=skip)
    if t:
        d['trace'] = t
    ln = sum(1 for e in n.get('trace', []) if int(e[0], 16) not in skip)
    lw = sum(1 for e in w.get('trace', []) if int(e[0], 16) not in skip)
    return {'outcome': 'diff' if d else 'equal', 'diffs': d, 'leaf': bool(ln <= 1 and lw <= 1)}
