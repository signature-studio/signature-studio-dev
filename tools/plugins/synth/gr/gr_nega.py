#!/usr/bin/env python3
"""gr_judge.py のネガティブコントロール。 合成 (非実機) の results.bin で判定の識別力を測る。
 これは判定器の検査であり、実プラグインの出力ではない (合成 native は実プラグインの出力と無関係)。
 control (wasm = native のコピー) は rc 0、各改変は rc 1 かつ期待した判定種別が出ること。 1 件でも外れたら exit 1。
 usage: gr_nega.py
"""
import os, random, subprocess, sys, tempfile, copy
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gr_lib as L

J = os.path.join(HERE, 'gr_judge.py')
BLK = ['21151', '21204', '22433', '23738', '23913', '23915', '24146', '24158', '24162', '24165', '24297', '24315']


def synth_native(seed):
    rnd = random.Random(seed)
    recs = []
    for n, _p, _r in L.make_cases():
        nd = 2 * n + 16
        dst = [L.FILL] * nd
        for k in range(2 * n):  # 有限な float (指数部 0x3e..0x40) の合成値
            dst[k] = (rnd.randrange(2) << 31) | (rnd.randrange(0x3e, 0x41) << 23) | rnd.randrange(1 << 23)
        recs.append({'status': 0, 'sig': 0, 'rip': 0, 'addr': 0, 'ret': 0, 'dst': dst})
    return recs


def setup(d, mutate=None, ulp_args=()):
    nd, wd = os.path.join(d, 'n'), os.path.join(d, 'w')
    os.makedirs(nd, exist_ok=True); os.makedirs(wd, exist_ok=True)
    with open(os.path.join(d, 't.tsv'), 'w') as f:
        for b in BLK:
            f.write('%s\tname\t0x400000\t100\n' % b)
    for i, b in enumerate(BLK):
        nat = synth_native(i)
        L.write_results(os.path.join(nd, b + '.bin'), nat)
        w = copy.deepcopy(nat)
        if mutate:
            w = mutate(i, b, nd, wd, w)
        if w is not None:
            L.write_results(os.path.join(wd, b + '.bin'), w)
    return nd, wd, os.path.join(d, 't.tsv')


def run(d, mutate=None, extra=()):
    nd, wd, t = setup(d, mutate)
    p = subprocess.run([sys.executable, J, nd, wd, t, *extra], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def flip(w, case=1, k=5, bit=1):
    w[case]['dst'][k] ^= bit
    return w


def m_one_bit(i, b, nd, wd, w):
    return flip(w) if i == 0 else w


def m_abort(i, b, nd, wd, w):
    if i == 2:
        w[0]['status'] = 1; w[0]['sig'] = 11
    return w


def m_missing(i, b, nd, wd, w):
    return None if i == 4 else w


def m_shape(i, b, nd, wd, w):
    if i == 5:
        w[0]['dst'] = w[0]['dst'][:-1]
    return w


def m_ret(i, b, nd, wd, w):
    if i == 6:
        w[1]['ret'] = 7
    return w


def m_nan(i, b, nd, wd, w):
    if i == 7:
        w[2]['dst'][3] = 0x7fc00000
    return w


def m_native_abort(i, b, nd, wd, w):
    if i == 8:
        nat = synth_native(i); nat[2]['status'] = 1; nat[2]['sig'] = 11
        L.write_results(os.path.join(nd, b + '.bin'), nat)
    return w


def m_native_empty(i, b, nd, wd, w):
    if i == 9:
        nat = synth_native(i)
        for r in nat:
            r['dst'] = [L.FILL] * len(r['dst'])
        L.write_results(os.path.join(nd, b + '.bin'), nat)
    return w


def m_native_missing(i, b, nd, wd, w):
    if i == 10:
        os.remove(os.path.join(nd, b + '.bin'))
    return w


def m_ulp1(i, b, nd, wd, w):
    return flip(w, bit=1) if i == 3 else w


def m_ulp8(i, b, nd, wd, w):
    return flip(w, bit=8) if i == 3 else w


def set_pair(nat_w, wsm_w, b, nd, shell, i=3):
    """shell i の case 1 / word 5 を native = nat_w、wasm = wsm_w にする (符号をまたぐ組の合成用)"""
    if shell != i:
        return None
    nat = synth_native(shell)
    nat[1]['dst'][5] = nat_w
    L.write_results(os.path.join(nd, b + '.bin'), nat)
    w = copy.deepcopy(nat)
    w[1]['dst'][5] = wsm_w
    return w


def m_sign_denorm(i, b, nd, wd, w):  # +最小非正規数 vs -最小非正規数 (距離 2)
    return set_pair(0x00000001, 0x80000001, b, nd, i) or w


def m_sign_zero(i, b, nd, wd, w):  # +0 vs -0 (距離 0)
    return set_pair(0x00000000, 0x80000000, b, nd, i) or w


def m_sign_tiny(i, b, nd, wd, w):  # +1e-9 vs -1e-9 (距離 2*0x2f...)
    import struct
    p = struct.unpack('<I', struct.pack('<f', 1e-9))[0]
    return set_pair(p, p | 0x80000000, b, nd, i) or w


CASES = [
    # (名前, mutate, 追加引数, 期待 rc, 出力に含むべき文字列, 含んではいけない文字列)
    ('control (wasm = native)', None, (), 0, 'OK 12/12', 'FAIL'),
    ('1 サンプルの bit 反転 (shell 1 本、許容なし)', m_one_bit, (), 1, 'DIFF=1', 'OK 12/12'),
    ('差 1 ulp、許容なし (strict)', m_ulp1, (), 1, 'DIFF=1', 'OK 12/12'),
    ('差 1 ulp、--ulp 2 (許容内 = 合格、PASS-TOL に分類)', m_ulp1, ('--ulp', '2'), 0, 'PASS-TOL=1', 'FAIL'),
    ('差 8 ulp、--ulp 2 (許容外)', m_ulp8, ('--ulp', '2'), 1, 'DIFF=1', 'OK 12/12'),
    ('符号違い +denorm/-denorm (距離 2)、--ulp 2 (許容内 = PASS-TOL)', m_sign_denorm, ('--ulp', '2'), 0, 'PASS-TOL=1', 'FAIL'),
    ('符号違い +denorm/-denorm (距離 2)、--ulp 1 (許容外)', m_sign_denorm, ('--ulp', '1'), 1, 'DIFF=1', 'OK 12/12'),
    ('符号違い +0/-0、許容なし (bit 違いは DIFF)', m_sign_zero, (), 1, 'DIFF=1', 'OK 12/12'),
    ('符号違い +0/-0、--ulp 1 (同値扱い = PASS-TOL)', m_sign_zero, ('--ulp', '1'), 0, 'PASS-TOL=1', 'FAIL'),
    ('符号違い +1e-9/-1e-9 (距離 1628627134)、--ulp 100 (許容外)', m_sign_tiny, ('--ulp', '100'), 1, 'DIFF=1', 'OK 12/12'),
    ('wasm が中断', m_abort, (), 1, 'WASM-ABORT=1', 'OK 12/12'),
    ('wasm 結果ファイルなし', m_missing, (), 1, 'MISSING-WASM=1', 'OK 12/12'),
    ('wasm の出力長が 1 word 短い', m_shape, (), 1, 'SHAPE=1', 'OK 12/12'),
    ('wasm の戻り値だけ違う', m_ret, (), 1, 'DIFF=1', 'OK 12/12'),
    ('wasm が NaN (巨大な --ulp でも bit 一致でなければ不一致)', m_nan, ('--ulp', '100000000'), 1, 'DIFF=1', 'OK 12/12'),
    ('native が中断 (基準にならない)', m_native_abort, (), 1, 'INVALID-REF=1', 'OK 12/12'),
    ('native が dst に何も書かない', m_native_empty, (), 1, 'INVALID-REF=1', 'OK 12/12'),
    ('native 結果ファイルなし', m_native_missing, (), 1, 'INVALID-REF=1', 'OK 12/12'),
]


def main():
    bad = 0
    for name, mut, extra, want_rc, want_txt, ban_txt in CASES:
        with tempfile.TemporaryDirectory() as d:
            rc, out = run(d, mut, extra)
        ok = rc == want_rc and want_txt in out and ban_txt not in out
        print('%-4s %-62s rc=%d (期待 %d)%s' % ('OK' if ok else 'NG', name, rc, want_rc, '' if ok else '  出力: ' + out.strip().splitlines()[-1]))
        bad += not ok
    print('[gr_nega] %s (%d ケース中 NG %d)' % ('FAIL' if bad else 'OK', len(CASES), bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
