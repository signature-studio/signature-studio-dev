#!/usr/bin/env python3
"""PLG-F2-3 (#515) 補助実行: 9 パターン (ptr-rich random) では native が全滅 / ループ長が引数依存で実行不能・時間切れになる関数を、
引数の意味に合わせた手作り case (小さい count、ポインタ鎖) で再採点する。 出力形式は leaf_diff.sh と同じ (liftdiff FORMAT §3)。

  python3 tools/plugins/f2/leaf_custom.py          (前提: leaf_diff.sh 実行済み = targets/*.json と build 済み wasm)
出力: work/f2/leaf_custom/<block>.jsonl  (target 名・VA・verdict は主採点と同じキー)

対象と case の根拠 (機械語):
  0x73e640 / 0x6e9440  rcx=this: [[[this+0x43c]+8]] を辿った先の byte の下位 5 bit で `1<<n` (0 なら 1) を返す。
                       ptr 3 段のため ptr-rich random の 9 パターンでは native が全て segv。 鎖を arena に手で張り、byte を振る
  0x73fa20 / 0x6ec2a0  (this, src, count): src の byte を bit に詰める 32 回までのループ。 pall は count=arena アドレスで巨大ループ
                       → wasm が 1s 上限で打切り (= 実行時間の問題で lift 差分ではない可能性)。 小さい count で再採点
  0x6f1c60             [this+0x360]==1 && [this+0x361]!=0: 9 パターンでは真が出にくい。 2 byte を直接振る (ネガコン load_drop/offset_shift の未検出から追加)
  0x6bfec0             xmm1 を入力に使う clamp + 除算/乗算 (ネガコン load_drop の未検出から追加)。 native にだけ f:<bits> で xmm1 を渡す
  0x6cd8a0             (this): byte 1 を [this+0x35af] に書くだけ。 9 パターンの差分は ptr 入り 8B ブロックの 1 byte 上書きで、native/wasm の arena base 差
                       (delta) を比較器が正規化できない偽陽性。 ptr を含まない (zero) arena で再採点
  0x5de300 / 0x6c9b60  前者: 9 パターンで native 完走 1 case のみ。 float 配列を張って idx を振る。 後者: xmm2 (float) を入力に使う (IR 署名に無い) ので native にだけ f:<bits> を渡す
  0x6f23b0             (this, idx): float 配列 [[this+0x1c] + idx*4 + 0x2d0] を返す。 this+0x1c の ptr 1 段のため random では native が全て segv
  0x73fa70 / 0x6ec2f0  (this, mask, dst, count): mask の bit i を dst[i] (byte) に展開。 count=-1 / 0 / 1 / 7 / 31 / 32 / 40
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGINS = os.path.abspath(os.path.join(HERE, '..'))
LD = os.path.abspath(os.path.join(PLUGINS, '..', 'liftdiff'))
W = os.path.join(PLUGINS, 'work', 'f2')
sys.path.insert(0, LD)
import liftdiff as L          # noqa: E402
from ldlib import cases, irtool   # noqa: E402
from ldlib.session import Session   # noqa: E402

# 主採点 (9 パターン) の不一致が比較系の偽陽性と確定したもの: va -> 根拠。 leaf_report.py が「補助 case で全 equal」のときだけ最終判定を match に上書きする
ARTIFACT = {
    0x6cd8a0: 'ptr 入り 8B ブロックの 1 byte 上書き: native と wasm の差が arena base 差 delta=0x400000 のみ (compare.cmp_mem が部分上書き後の ptr を正規化できない)',
    0x73fa20: 'wasm 1s 上限: ループ回数 = count 下位 32bit (pall では arena アドレス ≒ 5.7e8 回) で native は完走し wasm -O0 が打切り',
    0x6ec2a0: 'wasm 1s 上限: 0x73fa20 と同一コード (同一ハッシュ)',
}
BYTES12 = '0102040810204080ff00aa55'
SPEC = {}


def chain_cases():
    out = []
    for v in ('00', '01', '03', '1f', '20', '25', 'ff'):
        out.append(('c%s' % v, ['i:a:0x1000'], '-', 'a:0x143c:q=a:0x2000;a:0x2008:q=a:0x3000;a:0x3000:q=a:0x4000;a:0x4008:' + v))
    return out


def count_cases():
    return [('n%d' % n, ['i:a:0x1000', 'i:a:0x2000', 'i:0x%x' % n], '-', 'a:0x2000:' + BYTES12 + '00' * 28) for n in (0, 1, 5, 8, 31, 32, 40)]


def mask_cases():
    return [('m%d' % (n & 0xff), ['i:a:0x1000', 'i:0xa5f00f33', 'i:a:0x2000', 'i:0x%x' % (n & 0xffffffffffffffff)], '-', None) for n in (-1, 0, 1, 7, 31, 32, 40)]


def idx_cases():
    patch = 'a:0x101c:q=a:0x2000;a:0x22cc:db0f4940' + '0000c03f' + '000000c0' + '0000803f'
    return [('i%s' % ('m1' if i < 0 else i), ['i:a:0x1000', 'i:0x%x' % (i & 0xffffffffffffffff)], '-', patch) for i in (-1, 0, 1, 2)]


def pairs_cases():
    fl = '0000c03f' + '000010c0' + '00004040' + 'f9021550' + '00000080' + '0000c07f' + '01000000' + '0000807f'   # 1.5 -2.25 3 1e10 -0 NaN denormal inf
    return [('k%d' % k, ['i:a:0x1000', 'i:a:0x2000', 'i:0x%x' % k], '-', 'a:0x2000:' + fl) for k in (1, 2, 3, 4)]


def xmm2_cases():
    # (this, idx, xmm2=float): 機械語は xmm2 を入力に使う。 IR 署名に xmm2 は無いため native にだけ f:<bits> を渡す
    out = []
    for idx in (0, 1):
        for nm, bits in (('lo', 0x3f800000), ('hi', 0x40400000)):
            out.append(('x%d%s' % (idx, nm), ['i:a:0x1000', 'i:0x%x' % idx, 'f:0x%x' % bits], '-', 'a:0x17e0:0000004000000040'))
    return out


def flag2_cases():
    # return [this+0x360]==1 && [this+0x361]!=0 : 9 パターンでは真になる組合せがほぼ出ない (ネガコンで検出力不足を確認) ため 2 byte を直接振る
    return [('b%s' % v, ['i:a:0x1000'], '-', 'a:0x1360:' + v) for v in ('0101', '0100', '0001', '0205', '0102')]


def divmul_cases():
    # 0x6bfec0: xmm1 (float 入力) を rip 相対の 2 定数と比べて [this+0x60] に clamp 値を置き、/ [this+0x18] (int) * [this+8] (float) を [this+0x1c] へ。
    # IR 署名に xmm1 は無いので native にだけ f:<bits> を渡す。 値は clamp の両側と中間を狙う
    out = []
    for nm, bits in (('tiny', 0x3a83126f), ('half', 0x3f000000), ('x100', 0x42c80000), ('neg', 0xc0000000), ('big', 0x49742400)):
        out.append(('v%s' % nm, ['i:a:0x1000', 'f:0x%x' % bits], '-', 'a:0x1018:04000000;a:0x1008:00000040'))
    return out


def zero_cases():
    return [('zero%d' % k, ['i:a:0x%x' % (0x1000 * k)], '-', None) for k in (1, 3)]


for va, f in ((0x6f1c60, flag2_cases), (0x6bfec0, divmul_cases), (0x6cd8a0, zero_cases), (0x5de300, pairs_cases), (0x6c9b60, xmm2_cases), (0x6f23b0, idx_cases), (0x73e640, chain_cases), (0x6e9440, chain_cases), (0x73fa20, count_cases), (0x6ec2a0, count_cases), (0x73fa70, mask_cases), (0x6ec2f0, mask_cases)):
    SPEC[va] = f()


def run_block(tp, vas, out_path):
    """target JSON `tp` 上で SPEC のある `vas` を補助採点し、liftdiff 形式の JSONL を out_path に書く。 戻り: {va: verdict}"""
    sess = Session(tp, shards=1, build=False)
    irfeats = irtool.ir_features(sess.t['ir'], sess.prefix)
    out, ver = open(out_path, 'w'), {}
    for va in sorted(vas):
        names = []
        for nm, args, blob, patch in SPEC[va]:
            key = 'x%x_%s' % (va, nm)
            cases.CUSTOM[key] = (args, blob, patch)
            names.append(key)
        res = sess.run_functions([va], names, with_refine=False)
        rec = L.make_record(sess, res[va], irfeats)
        for c in rec['cases']:
            c['pattern'] = c['pattern'].split('_', 1)[1]
        out.write(json.dumps(rec) + '\n')
        ver[va] = rec['verdict']
        print('%s %s verdict=%s %s' % (hex(va), sess.t['name'], rec['verdict'],
              ' '.join('%s:%s' % (c['pattern'], c['outcome']) for c in rec['cases'])), flush=True)
    out.close()
    return ver


def main():
    meta = {int(r['va'], 16): r for r in json.load(open(os.path.join(W, 'leaf.json')))}
    os.makedirs(os.path.join(W, 'leaf_custom'), exist_ok=True)
    for b in sorted({meta[va]['block'] for va in SPEC}):
        run_block(os.path.join(W, 'targets', 'eqf%d.json' % b), [v for v in SPEC if meta[v]['block'] == b],
                  os.path.join(W, 'leaf_custom', '%d.jsonl' % b))


if __name__ == '__main__':
    main()
