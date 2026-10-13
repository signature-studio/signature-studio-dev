"""Gen_Render 差分 harness の共通部 (case 生成・結果 bin の読み書き・比較)。

results.bin (native / wasm 共通): 各 case {u32 status; u32 sig; u64 fault_rip; u64 fault_addr; u64 ret; u32 nd; u32 dst[nd]}
  status 0 = 正常 return / 1 = 中断 (sig = シグナル番号)。 dst の初期値は 0xA5A5A5A5 (書かれたかどうかを見分けるため)。
cases.bin: u32 ncases, 各 case {u32 length; u32 padD; u32 reset}
"""
import struct

FILL = 0xA5A5A5A5
HDR = struct.Struct('<IIQQQI')


def make_cases():
    """固定 case 列 (決定的)。 (length, padD, reset)。 reset=0 の case は前 case の this 状態を引き継ぐ"""
    return [(64, 0, 1), (64, 0, 0), (17, 3, 0), (1, 0, 0), (512, 1, 0), (64, 0, 1)]


def write_cases(path, cases):
    with open(path, 'wb') as f:
        f.write(struct.pack('<I', len(cases)))
        for c in cases:
            f.write(struct.pack('<III', *c))


def read_results(path):
    b = open(path, 'rb').read()
    out, o = [], 0
    while o < len(b):
        if o + HDR.size > len(b):
            raise ValueError('truncated header at %d' % o)
        st, sg, fr, fa, ret, nd = HDR.unpack_from(b, o)
        o += HDR.size
        if o + 4 * nd > len(b):
            raise ValueError('truncated dst at %d' % o)
        dst = struct.unpack_from('<%dI' % nd, b, o)
        o += 4 * nd
        out.append({'status': st, 'sig': sg, 'rip': fr, 'addr': fa, 'ret': ret, 'dst': dst})
    return out


def write_results(path, recs):
    with open(path, 'wb') as f:
        for r in recs:
            f.write(HDR.pack(r['status'], r['sig'], r['rip'], r['addr'], r['ret'], len(r['dst'])))
            f.write(struct.pack('<%dI' % len(r['dst']), *r['dst']))


def _ord(w):
    """float32 ビット列を符号をまたいで連続・単調な整数順序に (ulp 距離用)。 +0 と -0 は同値 (0x80000000)。 NaN は呼出側で除外"""
    m = w & 0x7fffffff
    return (0x80000000 - m) if w & 0x80000000 else (0x80000000 + m)


def _isnan(w):
    return (w & 0x7f800000) == 0x7f800000 and (w & 0x007fffff) != 0


def ulp_dist(a, b):
    if a == b:
        return 0
    if _isnan(a) or _isnan(b):
        return None  # NaN は bit 一致以外を不一致とする
    return abs(_ord(a) - _ord(b))


def native_valid(recs, nd_cases):
    """native が基準として使えるか。 (ok, 理由)。 中断・空出力・件数不一致は基準にしない"""
    if len(recs) != nd_cases:
        return False, 'native 結果 %d 件 / case %d 件' % (len(recs), nd_cases)
    for i, r in enumerate(recs):
        if r['status'] != 0:
            return False, 'case %d で native が中断 (sig %d, rip 0x%x, addr 0x%x)' % (i, r['sig'], r['rip'], r['addr'])
    wrote = sum(1 for r in recs for w in r['dst'] if w != FILL)
    if wrote == 0:
        return False, 'native が dst に 1 word も書いていない (空出力は基準にならない)'
    return True, 'native dst 書込 word %d' % wrote


def compare(nat, wsm, ulp=0):
    """native と wasm の bit 比較。 return (verdict, detail dict)"""
    if len(nat) != len(wsm):
        return 'SHAPE', {'reason': 'case 数 native %d / wasm %d' % (len(nat), len(wsm))}
    nbad = nwords = within = 0
    maxulp = 0
    first = None
    for i, (a, b) in enumerate(zip(nat, wsm)):
        if b['status'] != 0:
            return 'WASM-ABORT', {'case': i, 'sig': b['sig']}
        if len(a['dst']) != len(b['dst']):
            return 'SHAPE', {'reason': 'case %d の nd native %d / wasm %d' % (i, len(a['dst']), len(b['dst']))}
        if a['ret'] != b['ret']:
            nbad += 1
            first = first or ('ret', i, a['ret'], b['ret'])
        for k, (x, y) in enumerate(zip(a['dst'], b['dst'])):
            nwords += 1
            if x == y:
                continue
            d = ulp_dist(x, y)
            if ulp and d is not None and d <= ulp:  # ulp=0 は bit-exact (±0 の bit 差も DIFF)
                within += 1
                maxulp = max(maxulp, d)
                continue
            nbad += 1
            first = first or ('dst', i, k, x, y)
    det = {'words': nwords, 'bad': nbad, 'within_tol': within, 'max_ulp_within': maxulp, 'first': first}
    if nbad:
        return 'DIFF', det
    return ('PASS-TOL' if within else 'PASS'), det
