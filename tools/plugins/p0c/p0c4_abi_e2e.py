#!/usr/bin/env python3
"""p0c4_abi_e2e.py — CAB-253 (ARG pass ABI 推定強化) の 1 コマンド e2e + 独立検算。

  python3 tools/plugins/p0c/p0c4_abi_e2e.py [cases]     # 既定 200

数え方の定義 (規則 36):
  kernel        = block18983_PE.bin の kernel 表 (0x5e19f0 が代入する 80 実装。
                 inventory/kernel_table.py が 80/80 hash 一致を確認済み)
  status        = build_argmodel の leftover 判定。
                   ok       = 機械語が読む slot のうち IR 引数に割り当てられないものがない
                   abi-mismatch = 未割当の使用 slot がある (数値差分の対象外)
                   groupb   = Group B helper (外部呼出) 参照で数値差分対象外
  buf_diff      = native 機械語と IR の出力バッファの bit 不一致 cell 数
                 (f32 4 B 単位・1 kernel 1 case で最大 16,452 cell = NBUF_B 65,808/4)。
                 NaN 同士は nandiff に分離し buf_diff には数えない (k80_diff.py の実装どおり)
  ret_diff      = 戻り値 (i64) の不一致 case 数 ( native が rax を放置する kernel では
                 200/200 など意味のない値になる。合否は buf_diff のみで判定)
  crash 4       = 0x5de710 / 0x5df610 / 0x5e05b0 / 0x5e0d80 (CAB-253 起点の sig11 4 kernel)

このスクリプトは独立再計算 (規則 37): e2e (p0c3_e2e.sh) を呼ばずに
  (1) k80abi.py で機械語 ABI を再スキャン
  (2) f80_lower → k80_argfix → x87fix の鎖を再構築 (冪等性も確認)
  (3) k80_diff.py を別プロセスで実行して CSV を読み直す
  (4) kernel_table.py で 80/80/45/10,886 B/x87 28 を突き合わせる
"""
import csv
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
NINE = ['0x5de820', '0x5dedf0', '0x5dfb60', '0x5df210', '0x5df240', '0x5e0760',
        '0x5e0b70', '0x5e0bb0', '0x5e1590', '0x5e1780', '0x5e0330']
CRASH4 = ['0x5de710', '0x5df610', '0x5e05b0', '0x5e0d80']
B6 = ['0x5dee90', '0x5df040', '0x5e09f0', '0x5e0a70', '0x5e0b10', '0x5e1210']
UCOMI_FIX = ['0x5e12b0']  # #3439: ucomiss の被演算子・flags を接続 (k80_argfix [C]・[D])
# #2182 (P0c-17): census の buf_diff≠0 だった 18 kernel。修復後は 2000 case で全て buf_diff=0
# (10000 case では 0x5dffc0 のみ buf_diff=3: REPORT_APPENDIX_H §19.1・#3280)
FIX18 = ['0x5de620', '0x5dea40', '0x5dec40', '0x5dedb0', '0x5dee20', '0x5dee50', '0x5df340',
         '0x5dfae0', '0x5dfbe0', '0x5dfc90', '0x5dfdb0', '0x5dffc0', '0x5dfff0', '0x5e0300',
         '0x5e0350', '0x5e03f0', '0x5e12c0', '0x5e1490']
HB_N = 15  # k80_hand_bodies.py の BODIES 14 + GLOBAL_INITS 1 (#2182)
EXT_FUNCS = 'function_5dfc90,function_5dfbe0,function_5dfd30,function_5dfdb0'
EXT_CHOPF = 'function_5dfbe0,function_5dfc90,function_5dfdb0'
EXT_CHOPR = '5dfbe0:5dfc0a-5dfc7c,5dfc90:5dfcb5-5dfd1e,5dfdb0:5dfded-5dfe40'


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        sys.stderr.write(r.stdout[-3000:] + r.stderr[-3000:])
        raise SystemExit('[FAIL] %s' % ' '.join(cmd))
    return r.stdout


def main():
    cases = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    os.environ['TMPDIR'] = os.path.join(HERE, 'work', 'tmp')
    os.makedirs(os.environ['TMPDIR'], exist_ok=True)
    d3 = os.path.join(HERE, 'work', 'diff3')
    os.makedirs(d3, exist_ok=True)

    print('== [1] k80abi (機械語 win64 ABI 抽出: ゼロ化 idiom 除外・xmm_insns・clip/ptr_struct) ==')
    run(['python3', os.path.join(HERE, 'k80abi.py')])
    abi = json.load(open(os.path.join(HERE, 'work', 'k80abi.json')))
    print('   kernels=%d  clip_index=%s' % (
        len(abi), [k for k in sorted(abi) if abi[k]['clip_index']]))
    print('   ptr_struct=%s' % {k: v['ptr_struct'] for k, v in abi.items() if v['ptr_struct']})

    print('== [2] f80_lower → k80_argfix → x87fix ==')
    # lift_ranges.sh は ir5_patch の後に fix_asm_stores (movlps/movsd 等の 64bit 部分 store 復元) を
    # 適用するが、k80.lift.ll はその前段出力。本 e2e でも同 pass を先に通す (P0c-5 / #269)。
    st_in = os.path.join(HERE, 'work', 'k80.lift.ll')
    if os.environ.get('K80_NO_ASMSTORES') != '1':
        st_in = os.path.join(d3, 'k80.lift.st.ll')
        run(['python3', os.path.join(HERE, '..', 'lift', 'passes', 'fix_asm_stores.py'),
             os.path.join(HERE, 'work', 'k80.lift.ll'), st_in])
    run(['python3', os.path.join(HERE, 'f80_lower.py'),
         st_in, os.path.join(d3, 'k80.lower.ll'),
         '--report', os.path.join(d3, 'k80.lower.json'),
         '--chop-funcs', 'function_5dfbe0,function_5dfc90,function_5dfdb0'])
    run(['python3', os.path.join(HERE, 'k80_argfix.py'),
         os.path.join(d3, 'k80.lower.ll'), os.path.join(d3, 'k80.argfix.ll'),
         '--abi', os.path.join(HERE, 'work', 'k80abi.json'),
         '--report', os.path.join(d3, 'k80.argfix.json')])
    # P0c-7 (#310): ucomiss 結果を捨てて符号が定数化された lift (0x5e0d80) の修復
    if os.environ.get('K80_NO_UCOMISIGN') != '1':
        ucs = os.path.join(d3, 'k80.argfix.ucs.ll')
        run(['python3', os.path.join(HERE, 'k80_ucomi_sign.py'),
             os.path.join(d3, 'k80.argfix.ll'), ucs, '--func', 'function_5e0d80',
             '--report', os.path.join(d3, 'k80.ucomi_sign.json')])
        os.replace(ucs, os.path.join(d3, 'k80.argfix.ll'))
    # #982: fistp qword の上位 dword store 欠落 (0x5de3e0) を関数指定で復元 (K80_NO_FISTP_HI=1 で外す)
    if os.environ.get('K80_NO_FISTP_HI') != '1':
        fhi = os.path.join(d3, 'k80.argfix.fhi.ll')
        run(['python3', os.path.join(HERE, '..', 'lift', 'passes', 'fix_fistp_hi_store.py'),
             os.path.join(d3, 'k80.argfix.ll'), fhi, '--func', 'function_5de3e0',
             '--report', os.path.join(d3, 'k80.fistp_hi.json')])
        os.replace(fhi, os.path.join(d3, 'k80.argfix.ll'))
    rep = json.load(open(os.path.join(d3, 'k80.argfix.json')))
    print('   argfix: movd=%d helper_xmm=%d struct_copy=%d orphan(gpr/float)=%d/%d' % (
        rep['movd_fixed'], rep['helper_xmm_fixed'], rep['struct_copy_fixed'],
        rep['orphan_gpr_fixed'], rep['orphan_float_fixed']))
    funcs = ('function_5de820,function_5dedf0,function_5dfb60,function_5dfbe0,'
             'function_5dfc90,function_5dfd30,function_5dfdb0')
    run(['python3', os.path.join(HERE, 'x87fix.py'),
         os.path.join(d3, 'k80.argfix.ll'), os.path.join(d3, 'k80.x87fix.ll'),
         '--report', os.path.join(d3, 'x87fix.json'), '--funcs', funcs,
         '--chop-f32-fns', 'function_5dfbe0,function_5dfc90,function_5dfdb0'])
    # #983: レジスタ経由 deref の落ち (0x5dee90 / 0x5df040 の arg4 読み元, 0x5e02b0 の [arg2] base) を機械語どおりに戻す
    dfx = os.path.join(d3, 'k80.deref.ll')
    run(['python3', os.path.join(HERE, 'k80_deref_fix.py'),
         os.path.join(d3, 'k80.x87fix.ll'), dfx])

    print('== [3] llvm-as + x87fix 冪等性 ==')
    run(['llvm-as', os.path.join(d3, 'k80.x87fix.ll'), '-o', os.path.join(d3, 'k80.x87fix.bc')])
    run(['python3', os.path.join(HERE, 'x87fix.py'),
         os.path.join(d3, 'k80.x87fix.ll'), os.path.join(d3, 'k80.x87fix2.ll'),
         '--report', os.path.join(d3, 'x87fix2.json'), '--funcs', funcs,
         '--chop-f32-fns', 'function_5dfbe0,function_5dfc90,function_5dfdb0'])
    if open(os.path.join(d3, 'k80.x87fix.ll'), 'rb').read() != \
       open(os.path.join(d3, 'k80.x87fix2.ll'), 'rb').read():
        raise SystemExit('[FAIL] x87fix not idempotent')
    print('   idempotent OK / llvm-as OK')

    print('== [4] argfix も冪等 (2 回適用 byte 一致) ==')
    run(['python3', os.path.join(HERE, 'k80_argfix.py'),
         os.path.join(d3, 'k80.argfix.ll'), os.path.join(d3, 'k80.argfix2.ll'),
         '--abi', os.path.join(HERE, 'work', 'k80abi.json')])
    if open(os.path.join(d3, 'k80.argfix.ll'), 'rb').read() != \
       open(os.path.join(d3, 'k80.argfix2.ll'), 'rb').read():
        raise SystemExit('[FAIL] k80_argfix not idempotent')
    print('   idempotent OK')

    # #2182 (P0c-17): census の buf_diff≠0 18 kernel の修復。
    #  (a) 4 kernel は x87 拡張精度 (80-bit) の dd エミュレーション (p0c4_e2e.py と同じ ext pass)
    #  (b) 残りは k80_hand_bodies.py で機械語どおりの本体に差し替え (関数シグネチャ不変)
    ext = os.path.join(d3, 'k80.ext.ll')
    run(['python3', os.path.join(HERE, 'f80_lower.py'), dfx, ext,
         '--ext', '--ext-funcs', EXT_FUNCS, '--chop-funcs', EXT_CHOPF, '--chop-ranges', EXT_CHOPR])
    hb = os.path.join(d3, 'k80.hb.ll')
    hbj = os.path.join(d3, 'k80.hb.json')
    run(['python3', os.path.join(HERE, 'k80_hand_bodies.py'), ext, hb, '--report', hbj])
    hb2 = os.path.join(d3, 'k80.hb2.ll')
    hb2j = os.path.join(d3, 'k80.hb2.json')
    run(['python3', os.path.join(HERE, 'k80_hand_bodies.py'), hb, hb2, '--report', hb2j])
    if open(hb, 'rb').read() != open(hb2, 'rb').read():
        raise SystemExit('[FAIL] k80_hand_bodies not idempotent')
    for j in (hbj, hb2j):
        n = len(json.load(open(j))['replaced'])
        if n != HB_N:
            raise SystemExit('[FAIL] k80_hand_bodies 置換件数 %d (期待 %d = BODIES 14 + GLOBAL_INITS 1)' % (n, HB_N))
    run(['llvm-as', hb, '-o', os.path.join(d3, 'k80.hb.bc')])

    print('== [5] 差分試験 (native vs 修復後 IR, %d case/kernel, fork 隔離) ==' % cases)
    out = run(['python3', os.path.join(HERE, 'k80_diff.py'),
               '--ir', hb, '--cases', str(cases)])
    rows = {}
    for ln in out.split('\n'):
        f = ln.split(',')
        if len(f) >= 8 and f[0].startswith('0x'):
            rows[f[0]] = f
    print('   %-10s %-9s %8s %8s %9s %s' % ('kernel', 'class', 'ret_diff', 'buf_diff', 'maxulp', 'status'))
    for k in sorted(rows):
        f = rows[k]
        print('   %-10s %-9s %8s %8s %9s %s' % (f[0], f[1], f[3], f[4], f[6][:9], f[7]))

    # #3439 (P0c-21): 0x5e12b0 は書き込みを持たず buf_diff が自明に 0 になるため、戻り値 (xmm0) を native と比べる
    print('== [5b] 戻り値試験 (0x5e12b0: native vs 修復後 IR, #3439) ==')
    print('   ' + run(['python3', os.path.join(HERE, 'ucomi_ret_check.py'), hb]).strip())

    print('== [6] 検算: status センサス ==')
    ok = [k for k in rows if rows[k][7] == 'ok']
    sig = sorted(k for k in rows if rows[k][7].startswith('sig'))
    print('   run=%d  ok=%d  sig11=%d (%s)' % (len(rows), len(ok), len(sig), ' '.join(sig)))

    print('== [7] 受入基準 ==')
    fails = []
    for k in NINE:
        r = rows.get(k)
        if r is None or r[4] != '0':
            fails.append('%s buf_diff=%s (期待 0)' % (k, r[4] if r else 'not-run'))
    for k in FIX18:
        r = rows.get(k)
        if r is None or r[4] != '0':
            fails.append('%s buf_diff=%s (期待 0: #2182)' % (k, r[4] if r else 'not-run'))
    # #2182 の回帰 (受入 2): CSV に出た全 kernel (67) が buf_diff=0 のまま
    for k in sorted(rows):
        if rows[k][4] != '0':
            fails.append('%s buf_diff=%s (期待 0: 回帰)' % (k, rows[k][4]))
    for k in CRASH4:
        r = rows.get(k)
        if r is None or r[7].startswith('sig'):
            fails.append('%s %s (期待: sig なし)' % (k, r[7] if r else 'not-run'))
    # #277: native crash (sig) の kernel が 0 / 対象 B の 6 kernel が ok モデルで CSV に出る
    # (0x5e12b0 は #3439 で ucomiss の被演算子・flags を接続して ok になった: REPORT_APPENDIX_H §20)
    for k in sorted(rows):
        if rows[k][7].startswith('sig'):
            fails.append('%s %s (期待: sig なし)' % (k, rows[k][7]))
    for k in B6:
        r = rows.get(k)
        if r is None or r[7] != 'ok':
            fails.append('%s %s (期待: ok モデル)' % (k, r[7] if r else 'not-run'))
    # #3439 (P0c-21): 0x5e12b0 は xmm0/xmm1 の引数と ucomiss flags を持ち、ok で CSV に出る (buf_diff=0)
    for k in UCOMI_FIX:
        r = rows.get(k)
        if r is None or r[7] != 'ok' or r[4] != '0':
            fails.append('%s %s buf_diff=%s (期待: ok かつ buf_diff=0: #3439)' % (
                k, r[7] if r else 'not-run', r[4] if r else '-'))
    if fails:
        for f in fails:
            print('   [FAIL]', f)
        raise SystemExit('[FAIL] 受入基準未達')
    print('   ① 回帰 %d kernel buf_diff=0: %s' % (len(NINE), ' '.join(NINE)))
    print('   ① #2182 修復 %d kernel buf_diff=0 / CSV 全 %d kernel buf_diff=0' % (len(FIX18), len(rows)))
    print('   ② crash 4 (0x5de710/0x5df610/0x5e05b0/0x5e0d80) すべて sig なしで CSV に出る')
    print('   ③ 冪等性 (x87fix / k80_argfix 2 回適用 byte 一致) 維持')
    print('   ④ llvm-as 通過')

    print('== [8] kernel 表 (80/80) の再確認 ==')
    d = eval(run(['python3', os.path.join(REPO, 'tools', 'plugins', 'inventory', 'kernel_table.py')]))
    assert d['implementations'] == 80 and d['variables'] == 45, d
    assert d['bytes'] == 10886 and d['kernels_with_x87_asm'] == 28, d
    print('   45 variables / 80 implementations / 10,886 B / x87 28 — 一致')
    print('== p0c4 ABI e2e OK ==')
    return 0


if __name__ == '__main__':
    sys.exit(main())
