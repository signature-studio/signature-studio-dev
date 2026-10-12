#!/usr/bin/env python3
"""negcon_1bit.py — CAB-273 のネガティブコントロール (規則 41): 厳密比較が 1 bit 差を検出すること。

背景: tol gate 撤去前は region (resonator/stereo/delay) の f32/f64 値が `--tol` 経路で
|a-b| > 1.6*2^-12*max(|a|,|b|) + absFloor の gate 判定されていた (CAB-224 由来)。
撤去後は全バイト strict 比較なので、旧 tol 領域内の 1 bit 差も FAIL しなければならない。
本スクリプトは (A) 未改変 PASS・(B) 撤去後の 1 bit 改変 FAIL 検出・(C) 撤去前の同一改変が
gate に吸収されていたこと (= 撤去の効果) の 3 点を実測する。

数え方の定義 (規則 36):
  - 1 call = KHV2 の 1 関数呼出。1 trial = scenario 1 試行。region = trial 末尾テーブルの
    (off, len) 付き名前付きバイト列。post = call 後の arena [0, plen) の native 期待値
    (post の index = arena offset)。
  - 「1 bit 改変」= native 参照 (post) の 1 バイトの最下位 bit を XOR 0x01 で反転。
    改変バイト数 = 1 (返り値の bits で確認)。ファイルサイズは不変。
  - 改変対象 = 旧 snapins.json の tol エントリが載っていた **byte 範囲** (LEGACY_TOL)。
    region 全体ではなく entry 範囲を選ぶ (region は tol 範囲より広いことがある)。
  - 「gate に吸収」= (C) で compare.mjs の exit が 0 になること (1 bit 差を PASS と判定)。

合否基準: (A) exit 0 かつ (B) exit != 0。 (C) は撤去前後の対照として記録 (吸収 = 穴)。

usage: python3 scripts/negcon_1bit.py [name] [--no-legacy]
"""
import os
import struct
import subprocess
import sys
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = '/opt/emsdk/node/24.19.0_64bit/bin/node'
REL = 'tools/targets/kilohearts/snapins'

# 旧 snapins.json の tol エントリ (CAB-273 で撤去・git show HEAD:<path> で確認可能)。
# {region: [(off, len), ...]}  = region 先頭からの byte 範囲 (比較は byte 単位)。
LEGACY_TOL = {
    'resonator': {'self': [(96, 16), (160, 120)], 'bufL': [(0, 1040)], 'bufR': [(0, 1040)],
                  'histL': [(0, 8280)], 'histR': [(0, 8280)]},
    'stereo': {'self': [(96, 112)], 'P': [(12, 8)], 'bufL': [(0, 1040)], 'bufR': [(0, 1040)]},
    'delay': {'self': [(124, 196)], 'tap': [(32, 2784)], 'P': [(40, 8)],
              'bufL': [(0, 1040)], 'bufR': [(0, 1040)]},
}


def parse(path):
    """KHV2 vectors を読む (scripts/acc_khvec.py とは別に自前実装)。"""
    b = open(path, 'rb').read()
    assert b[0:4] == b'KHV2', 'bad magic'
    ntrials, _ = struct.unpack_from('<II', b, 4)
    p = 12
    trials = []
    for _ in range(ntrials):
        ncalls, _ = struct.unpack_from('<II', b, p); p += 8
        calls = []
        for _ in range(ncalls):
            np_ = struct.unpack_from('<I', b, p)[0]; p += 4
            for _ in range(np_):
                off, ln = struct.unpack_from('<II', b, p); p += 8 + ln
            p += 8 + 32 + 32 + 20          # va, a[4], x[4], rk/rax/xmm0
            plen = struct.unpack_from('<I', b, p)[0]; p += 4
            calls.append((p, plen))         # (post のファイル内 offset, plen)
            p += plen
        nreg = struct.unpack_from('<I', b, p)[0]; p += 4
        regs = []
        for _ in range(nreg):
            off, ln, nl = struct.unpack_from('<III', b, p); p += 12
            nm = b[p:p + nl].decode('latin1'); p += nl
            regs.append((off, ln, nm))
        trials.append((calls, regs))
    assert p == len(b), 'trailing bytes'
    return b, trials


def flip(path, spec, out):
    """旧 tol entry 範囲内の post 1 バイトの最下位 bit を反転させた vectors を out に書く。"""
    b, trials = parse(path)
    # 最も広い entry を優先 (改変が region 内で確実に tol 対象になるよう)
    cands = []
    for reg, ents in spec.items():
        for (eoff, elen) in ents:
            cands.append((elen, reg, eoff, elen))
    cands.sort(reverse=True)
    target = None
    for ti, (calls, regs) in enumerate(trials):
        for (_, reg, eoff, elen) in cands:
            r = [x for x in regs if x[2] == reg]
            if not r:
                continue
            roff, rlen, _ = r[0]
            if rlen < eoff:
                continue
            lo, hi = max(eoff, 0), min(eoff + elen, rlen)
            if hi <= lo:
                continue
            for (poff, plen) in calls:
                if plen > roff + eoff:
                    target = (ti, poff + roff + eoff, reg, eoff, plen)
                    break
            if target:
                break
        if target:
            break
    if not target:
        raise SystemExit('no call covers a legacy tol entry range')
    ti, idx, reg, eoff, plen = target
    ba = bytearray(b)
    before = ba[idx]
    ba[idx] = before ^ 0x01
    open(out, 'wb').write(bytes(ba))
    return dict(trial=ti, byte_index=idx, region=reg, entry_off=eoff, entry_len=elen, call_plen=plen,
                before=before, after=ba[idx])


def run(vec, name, tag='s0', tol_json=None, comparator=None):
    mod = os.path.join(ROOT, 'work', name, tag, 'mod.cjs')
    sig = os.path.join(ROOT, 'work', name, tag, 'sigs.json')
    cmp_path = comparator or os.path.join(ROOT, 'harness', 'compare.mjs')
    cmd = [NODE, cmp_path, vec, mod, sig]
    if tol_json:
        cmd += ['--tol', tol_json]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    last = r.stdout.strip().split('\n')[-1] if r.stdout.strip() else ''
    return r.returncode, last


def f32bits(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    name = args[0] if args else 'resonator'
    if name not in LEGACY_TOL:
        raise SystemExit('unknown snap-in %s (legacy tol spec: %s)' % (name, list(LEGACY_TOL)))
    vec = os.path.join(ROOT, 'work', name, 'vec_200_1.bin')
    assert os.path.exists(vec), 'no %s (run run_all.sh first)' % vec
    spec = LEGACY_TOL[name]
    out = os.path.join(ROOT, 'work', name, 'negcon_1bit.bin')
    info = flip(vec, spec, out)
    print('  flip: trial=%d region=%s+0x%x (tol entry [0x%x,0x%x)) plen=%d byte 0x%02x->0x%02x bits=1'
          % (info['trial'], info['region'], info['entry_off'], info['entry_off'],
             info['entry_off'] + info['entry_len'], info['call_plen'], info['before'], info['after']))
    rc_a, msg_a = run(vec, name)
    print('  A) unmodified        exit %d  %s' % (rc_a, msg_a[:260]))
    rc_b, msg_b = run(out, name)
    print('  B) 1-bit flip strict exit %d  %s' % (rc_b, msg_b[:260]))
    # (C) 撤去前の同一改変が gate に吸収されていたことの対照。
    #    撤去後の compare.mjs には tolerance 経路が無いので、HEAD (撤去前) の compare.mjs を
    #    work/ に展開してそれを使う (= 同一改変を旧実装で再判定)。tol 設定も HEAD の
    #    snapins.json から読み直す (build.py が書いていた tol.json と同形)。
    repo = '/home/ubuntu/work/webstudio'
    legacy_cmp = os.path.join(ROOT, 'work', 'negcon_compare_legacy.mjs')
    r = subprocess.run(['git', '-C', repo, 'show', 'HEAD:%s/harness/compare.mjs' % REL],
                       capture_output=True, text=True)
    if r.returncode == 0:
        open(legacy_cmp, 'w').write(r.stdout)
    legacy = None
    r = subprocess.run(['git', '-C', repo, 'show', 'HEAD:%s/snapins.json' % REL],
                       capture_output=True, text=True)
    if r.returncode == 0:
        old = json.loads(r.stdout).get(name, {})
        if old.get('tol'):
            legacy = os.path.join(ROOT, 'work', name, 'negcon_tol.json')
            json.dump(old['tol'], open(legacy, 'w'))
    rc_c = msg_c = None
    if os.path.exists(legacy_cmp) and legacy and '--no-legacy' not in sys.argv:
        rc_c, msg_c = run(out, name, comparator=legacy_cmp, tol_json=legacy)
        print('  C) 1-bit flip +legacy --tol exit %d  %s' % (rc_c, msg_c[:260]))
    ok = (rc_a == 0) and (rc_b != 0)
    print('  -> NEGCON %s (strict detects 1-bit diff; legacy gate %s)'
          % ('PASS' if ok else 'FAIL',
             'ABSORBED (exit 0 = the hole CAB-273 closes)' if rc_c == 0 else 'also detected' if rc_c else 'n/a'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
