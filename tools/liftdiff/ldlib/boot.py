"""boot 状態の生成: native で unit 初期化 (Delphi InitTable) を順次実行し、その時点のメモリ状態を native/wasm 双方の pristine にする。

wasm 側は lift が壊れていて unit 初期化を通せない (M11) ため、「正しい状態」を native 実機械語で作って移送する。
状態中のポインタ (image 内 / heap 内) は native 座標 → wasm 座標へ (-delta) 書き換える。
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


def build_state(sess, upto=None, log=print):
    """native で unit 0..k-1 を実行 (k = upto か、最初に失敗する手前まで)。戻り: dict(state, units_run, units_total, first_fail)"""
    t = sess.t
    ptr_rva = int(t['init_table_rva'], 16)
    units = read_inittable_units(sess.pe, ptr_rva)
    log('[boot] InitTable: %d units' % len(units))

    def fresh():
        return Runner('native', ['setarch', '-R', __import__('os').path.join(__import__('os').path.dirname(__file__), '..', 'work/ld_native'), t['pe']],
                      sess.init_lines('native'), timeout=20.0)

    def run_units(n):
        r = fresh()
        fails = []
        for i in range(n):
            if units[i] == 0:
                continue
            res = r.run_cases(['id=u%d fn=%x blob=- args= keep=1 trace=0' % (i, units[i])], ['u%d' % i])[0]
            if res.get('status') != 'ok':
                fails.append((i, res))
                break
        return r, fails

    k = upto
    if k is None:
        # 失敗する最初の unit を探す
        r = fresh()
        k = len(units)
        for i in range(len(units)):
            if units[i] == 0:
                continue
            res = r.run_cases(['id=u%d fn=%x blob=- args= keep=1 trace=0' % (i, units[i])], ['u%d' % i])[0]
            if res.get('status') != 'ok':
                k = i
                log('[boot] unit #%d (init %#x) failed natively: %s %s' % (i, units[i], res.get('status'), res.get('detail')))
                break
        r.close()
    log('[boot] executing units 0..%d natively' % (k - 1))
    r, fails = run_units(k)
    r._send('STATE')
    r.p.stdin.flush()
    line = r._recv(60.0)
    st = json.loads(line)
    r._send('SSNAP')
    r.p.stdin.flush()
    return r, {'state': st, 'units_run': k, 'units_total': len(units), 'first_fail': k if k < len(units) else None}


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
