"""native / wasm の case 結果を比較して差分 (diffs) を作る。ポインタは address ずれ (delta) を許容して正規化する。"""
import math

M64 = (1 << 64) - 1
NATIVE_STACK_LO = 0x7000_0000_0000
SENTINEL = 0xCAFEBABE0BADF00D
DEFAULT_WASM_TIMEOUT_MS = 1000     # ld_runner.mjs の vm timeout 既定 (target JSON wasm_timeout_ms で上書き)
DEFAULT_WASM_SLOWDOWN = 20.0       # wasm (-O0 + 計装) が native の何倍まで遅くなり得るかの仮定 (target JSON wasm_slowdown_bound)


def wasm_timing_params(t):
    """target JSON の wasm_timeout_ms (正の整数) / wasm_slowdown_bound (正の数) を検証して (ms, slowdown) を返す。
    不正値は raise する: ランナ側の既定値 (Number(x) || 1000) と判定閾値が食い違うのを防ぐ。"""
    ms = t.get('wasm_timeout_ms', DEFAULT_WASM_TIMEOUT_MS)
    sl = t.get('wasm_slowdown_bound', DEFAULT_WASM_SLOWDOWN)
    if isinstance(ms, bool) or not isinstance(ms, (int, float)) or not math.isfinite(ms) or ms <= 0 or int(ms) != ms:
        raise ValueError('wasm_timeout_ms must be a positive integer (got %r)' % (ms,))
    if isinstance(sl, bool) or not isinstance(sl, (int, float)) or not math.isfinite(sl) or sl <= 0:
        raise ValueError('wasm_slowdown_bound must be a positive number (got %r)' % (sl,))
    return int(ms), float(sl)


class Ctx:
    """windows = [(lo, hi)] は wasm 側座標。native の同領域は +delta。"""

    def __init__(self, delta, windows, wasm_stack, wasm_timeout_ms=DEFAULT_WASM_TIMEOUT_MS, wasm_slowdown=DEFAULT_WASM_SLOWDOWN):
        self.wasm_timeout_ms = wasm_timeout_ms
        self.wasm_slowdown = wasm_slowdown
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


def _bytemask(pre, post):
    """pre と post で値が変わった byte の mask (8B ワード内)"""
    m = 0
    for i in range(8):
        if ((pre >> (8 * i)) & 0xff) != ((post >> (8 * i)) & 0xff):
            m |= 0xff << (8 * i)
    return m


def _overlay(base, post, mask):
    return (base & ~mask & M64) | (post & mask)


def eq_block_bytewise(pre_n, post_n, pre_w, post_w, ctx):
    """部分上書きされた ptr 入りワードの比較 (LD-11 / #548)。各側で pre/post が変化した byte だけを post から取り、
    変化していない byte は pre (native 側は wasm 座標へ ptr 正規化) を使って合成した語を比較する。
    ptr 正規化の対象は変化していない byte に限る (変化した byte は生値を比較するので、書込み値の rebase 漏れは隠れない)。"""
    mn, mw = _bytemask(pre_n, post_n), _bytemask(pre_w, post_w)
    if not (mn or mw):
        return ctx.eq(pre_n, pre_w)
    wn = _overlay(ctx.n2w(pre_n), post_n, mn)
    ww = _overlay(pre_w, post_w, mw)
    return wn == ww


def cmp_mem(n, w, ctx, limit=8):
    bn, bw = _blocks(n.get('mem', [])), _blocks(w.get('mem', []))
    diffs = []
    for k in sorted(set(bn) | set(bw)):
        if k in bn and k in bw:
            vn, vw = bn[k][1], bw[k][1]
            if not ctx.eq(vn, vw) and not eq_block_bytewise(bn[k][0], vn, bw[k][0], vw, ctx):
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
        ent = sigs.get('%s%x' % (prefix, int(b[0], 16)), {})
        sig = ent.get('params', [])
        ir = ent.get('ir_params', [])
        for pos in range(min(np_, 8)):
            ty = sig[pos] if pos < len(sig) else 'i64'
            width = _width(ty)
            fp = ty in ('float', 'double')
            if fp and pos < 4:
                vn, vw = int(a[2 + 8 + pos], 16), int(b[2 + 8 + pos], 16)
            else:
                vn, vw = int(a[2 + pos], 16), int(b[2 + pos], 16)
            if pos < len(ir) and ir[pos] == 'i128':
                # LD-248 (#4975): i128 位置は値を bit 単位で比べる。ctx.eq の stack 範囲規則は native の大きい値と
                # wasm の 0 を一致と見なすため (1.5 と 0 が一致扱いになる)、i128 位置には当てない。
                if (vn & M64) != (vw & M64):
                    return {'index': i, 'kind': 'entry_arg', 'va': a[0], 'pos': pos, 'type': ty, 'native': hex(vn), 'wasm': hex(vw)}
                continue
            if not ctx.eq(vn, vw, width):
                return {'index': i, 'kind': 'entry_arg', 'va': a[0], 'pos': pos, 'type': ty, 'native': hex(vn), 'wasm': hex(vw)}
    return None


def compare_case(n, w, ctx, sigs, stub_info, skip=frozenset()):
    """戻り: dict(outcome, diffs{}) ; outcome ∈ equal / diff / wasm_trap / wasm_timeout_native_long / native_fault / both_fault / hang"""
    sn, sw = n.get('status'), w.get('status')
    if sn in ('hang', 'crash') or sw in ('hang', 'crash'):
        return {'outcome': 'hang', 'native': sn, 'wasm': sw}
    if sw == 'timeout' and sn == 'ok':
        nms = n.get('ms')
        # native 自身が wasm_timeout_ms / wasm_slowdown 以上かかった case は、wasm が正常でも打切られ得る (LD-11 / #548)。
        # 欠陥 (wasm_trap) とは区別し、比較不能 (unexec) として別 outcome にする。native ms 不明 (旧ランナ) は従来どおり wasm_trap。
        if nms is not None and nms * ctx.wasm_slowdown >= ctx.wasm_timeout_ms:
            return {'outcome': 'wasm_timeout_native_long', 'native': sn, 'wasm': sw, 'native_ms': nms,
                    'wasm_timeout_ms': ctx.wasm_timeout_ms, 'wasm_slowdown_bound': ctx.wasm_slowdown}
        return {'outcome': 'wasm_trap', 'native': sn, 'wasm': sw, 'native_ms': nms,
                'wasm_detail': 'timeout: wasm did not finish within %dms (infinite loop?) while native completed%s' % (
                    ctx.wasm_timeout_ms, '' if nms is None else ' in %.3fms' % nms)}
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
