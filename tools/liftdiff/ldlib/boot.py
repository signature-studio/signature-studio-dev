"""boot 状態の生成: native で unit 初期化 (Delphi InitTable) を順次実行し、その時点のメモリ状態を native/wasm 双方の pristine にする。

wasm 側は lift が壊れていて unit 初期化を通せない (M11) ため、「正しい状態」を native 実機械語で作って移送する。
状態中のポインタ (image 内 / heap 内) は native 座標 → wasm 座標へ (-delta) 書き換える。

CAB-233: mode を追加した。
  units  (従来動作): unit 0 から 1 本ずつ CASE keep=1 で実行し、最初の失敗で止める。
  entry:            entry_point(hinst,1,0) を 1 case で直接実行 (実 InitUnits ループが unit を進める)。
                    stub 応答の不足等で途中止まりになった場合も、そこまでの状態を採用する。
  hybrid (既定の推奨): entry 実行 → その到達 unit (InitCount) の次から残りを unit 単位で継続。
                    unit 単位の実行は実 InitUnits と同じ「proc && *proc」判定を行い、
                    失敗した unit は記録して続行する (tolerant)。boot カバー unit 数を最大化する。
"""
import json, struct

from .runners import Runner


def read_inittable_units(pe, table_rva):
    """Delphi の InitTable (count:u32, units:u64 → [(init, fini) 16B]) → unit 初期化関数 VA 列"""
    count = struct.unpack('<I', pe.read(table_rva, 4))[0]
    units = struct.unpack('<Q', pe.read(table_rva + 8, 8))[0] - pe.base
    return [struct.unpack('<Q', pe.read(units + i * 16, 8))[0] for i in range(count)]


def rebase_hex(hexs, ctx, pe_size, base):
    """hex 文字列中の 8B 整列 qword を native→wasm 座標へ. (rebased 数, 変換後 hex)"""
    b = bytearray(bytes.fromhex(hexs))
    n = 0
    for i in range(0, len(b) - 7, 8):
        v = struct.unpack_from('<Q', b, i)[0]
        w = ctx.n2w(v)
        if w != v:
            struct.pack_into('<Q', b, i, w)
            n += 1
    return n, b.hex()


def _peek_u64(r, tok):
    r._send('PEEK %s 8' % tok)
    r.p.stdin.flush()
    v = r._recv(30)
    if not v:
        return 0
    return struct.unpack('<Q', bytes.fromhex(v[:16]))[0]


def build_state(sess, upto=None, log=print, mode='units', post=None):
    """native で unit 初期化を実行して状態を作る。
    post(r, sess) を指定すると、unit 初期化の後・状態採取の前に native ランナ r で呼ばれる (戻り値は detail['post'])。
    戻り: dict(state, units_run, units_total, first_fail, mode, detail)"""
    t = sess.t
    ptr_rva = int(t['init_table_rva'], 16)
    units = read_inittable_units(sess.pe, ptr_rva)
    log('[boot] InitTable: %d units (mode=%s)' % (len(units), mode))

    def fresh():
        return Runner('native', ['setarch', '-R', __import__('os').path.join(__import__('os').path.dirname(__file__), '..', 'work/ld_native'), t['pe']],
                      sess.init_lines('native'), timeout=20.0)

    detail = {'mode': mode}
    k = 0
    fails = []
    entry_ran = False

    r = fresh()
    if mode in ('entry', 'hybrid'):
        ep = sess.pe.base + sess.pe.pe.OPTIONAL_HEADER.AddressOfEntryPoint
        res = r.run_cases(['id=ep fn=%x blob=- args=i:0x%x,i:0x1,i:0x0 keep=1' % (ep, sess.pe.base)], ['ep'])[0]
        entry_ran = True
        k = _peek_u64(r, 'i:0x11eac98')   # System.InitCount (実 InitUnits が進めた分)
        detail['entry_status'] = res.get('status')
        detail['entry_detail'] = (res.get('detail') or '')[:120]
        if res.get('status') != 'ok':
            log('[boot] entry_point 止まり: %s %s (InitCount=%d)' % (res.get('status'), (res.get('detail') or '')[:60], k))
        else:
            log('[boot] entry_point 完走 (InitCount=%d)' % k)
        if mode == 'entry':
            st = _dump_state(r)
            r.close()
            detail['units_ok'] = k
            detail['units_fail'] = 0
            return None, {'state': st, 'units_run': k, 'units_total': len(units),
                          'first_fail': k if k < len(units) else None, 'mode': mode, 'detail': detail}

    # ---- unit 単位フェーズ (hybrid: entry の続きから / units: 最初から) ----
    if mode == 'hybrid':
        # InitCount の次の unit から (entry フェーズで実行済みの分を飛ばす)
        start = k + 1 if entry_ran else 0
    else:
        start = 0
        if upto is None:
            # 失敗する最初の unit を探す (従来動作)
            for i in range(len(units)):
                if units[i] == 0:
                    continue
                res = r.run_cases(['id=u%d fn=%x blob=- args= keep=1 trace=0' % (i, units[i])], ['u%d' % i])[0]
                if res.get('status') != 'ok':
                    k = i
                    log('[boot] unit #%d (init %#x) failed natively: %s %s' % (i, units[i], res.get('status'), res.get('detail')))
                    break
                k = i + 1
            upto = k
    if upto is not None:
        end = min(upto, len(units))
    else:
        end = len(units)

    ok = 0
    if entry_ran:
        ok = k   # entry フェーズで実行済み
    for i in range(start, end):
        if units[i] == 0:
            continue
        # 実 InitUnits と同じ判定: proc && *proc (先頭 8B が 0 の unit は呼ばない)
        if _peek_u64(r, 'i:0x%x' % (units[i] - sess.pe.base)) == 0:
            continue
        res = r.run_cases(['id=u%d fn=%x blob=- args= keep=1 trace=0' % (i, units[i])], ['u%d' % i])[0]
        if res.get('status') == 'ok':
            ok += 1
        else:
            fails.append((i, '%x' % units[i], res.get('status'), (res.get('detail') or '')[:60]))
            if mode == 'units':
                break   # 従来動作: 最初の失敗で止める
    if entry_ran and fails:
        log('[boot] unit 単位フェーズ: ok+%d / fail %d (最初: %s)' % (ok - (k if entry_ran else 0), len(fails), fails[0][:3]))
    if post is not None:
        detail['post'] = post(r, sess)
    st = _dump_state(r)
    r.close()
    detail['units_ok'] = ok
    detail['units_fail'] = len(fails)
    detail['fails_head'] = fails[:10]
    covered = k + (ok - k if entry_ran else 0)
    return None, {'state': st, 'units_run': covered, 'units_total': len(units),
                  'first_fail': fails[0][0] if fails else None, 'mode': mode, 'detail': detail}


INIT_TABLE_PTR_RVA = 0x11eac90   # System.@InitUnits が読む InitTable 参照 (global slot)
INIT_COUNT_RVA = 0x11eac98       # System.InitCount (InitUnits が進める)
TLS_ARRAY_OFF = 0x1000           # heap 内 TLS 配列 (rt/ld_core.h LD_TLS_OFF)


def _img_u64(st, addr, n=8):
    """STATE の image run から addr の n byte を読む (無ければ None)"""
    for rva, hx in st['img']:
        a = int(rva, 16)
        if a <= addr and addr + n <= a + len(hx) // 2:
            return bytes.fromhex(hx)[addr - a:addr - a + n]
    return None


def precondition(st):
    """boot 状態が InitUnits の前提 (InitTable 参照・InitCount・TLS index) を満たすか。
    InitUnits は InitTable 参照が 0 だと何もせず戻るため、これが無い状態での比較は空振り一致になる。
    戻り: dict(table_ptr, init_count, tls_set, ok)"""
    tp = _img_u64(st, INIT_TABLE_PTR_RVA)
    ic = _img_u64(st, INIT_COUNT_RVA, 4)
    h = bytes.fromhex(st['heap'])
    tls_set = sum(1 for i in range(1, 1024) if int.from_bytes(h[TLS_ARRAY_OFF + i * 8:TLS_ARRAY_OFF + i * 8 + 8], 'little'))
    d = {'table_ptr': int.from_bytes(tp, 'little') if tp else 0,
         'init_count': int.from_bytes(ic, 'little') if ic else 0,
         'tls_set': tls_set}
    d['ok'] = d['table_ptr'] != 0 and d['init_count'] != 0 and d['tls_set'] > 0
    return d


def _dump_state(r):
    r._send('STATE')
    r.p.stdin.flush()
    line = r._recv(60.0)
    st = json.loads(line)
    r._send('SSNAP')
    r.p.stdin.flush()
    return st


def state_lines_for(kind, st, sess):
    """STATE JSON → ランナへ送る行 (kind: native/wasm)"""
    L = []
    nreb = 0
    for rva, hx in st['img']:
        if kind == 'wasm':
            n, hx = rebase_hex(hx, sess.ctx, sess.pe.size, sess.pe.base)
            nreb += n
        L.append('SIMG %x %s' % (int(rva, 16), hx))
    hp = st['heap']
    if kind == 'wasm':
        n, hp = rebase_hex(hp, sess.ctx, sess.pe.size, sess.pe.base)
        nreb += n
    L.append('SHEAP %s' % hp)
    L.append('SMODEL %d %d' % (st['heap_used'], st['hw']))
    L.append('SSNAP')
    return L, nreb
