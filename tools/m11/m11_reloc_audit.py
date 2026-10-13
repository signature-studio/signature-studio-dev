#!/usr/bin/env python3
# M11-N21 (#572): FLEngine PE の .reloc DIR64 全件が m11_data_gen の補正条件で拾われるかを全数照合する。
# 3 通りで各 DIR64 (RVA r, 8B slot) を判定し、互いに矛盾すれば FAIL (非 0):
#   (a) 式 OLD : lo <= r <  lo + len - 8   (m11_data_gen.py 修正前の条件)
#   (b) 式 NEW : lo <= r <= lo + len - 8   (8B slot が区間に完全に収まる条件)
#   (c) 実出力 : m11_data_gen.py が書いた m11_data.c の実バイトを PE 原本と比較し、slot が実際に補正されたか
# 期待値は引数で固定する (既定は「実出力が式 NEW と一致し、補正漏れ 0」)。
#   python3 m11_reloc_audit.py PE DATA_C [--lb 0x0] [--json out.json] [--expect-missed N]
#     --expect-missed N : 実出力で「補正されるべきなのに原本のまま」の slot 数が N でなければ FAIL
#                        (修正前コードの確認は N=1, 修正後は N=0)
import sys, os, re, struct, json, argparse

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from lb_base import IMG_BASE
sys.path.insert(0, os.environ.get('M11_OTTLIB_DIR', os.path.join(BASE, '..', 'm6')))
from ottlib import Bin

IMG_SPAN = 0x1ac0000     # m11_data_gen.py の値条件 (LVA_SH < v < LVA_SH + 0x1ac0000)


def collect_relocs(W):
    out = []
    for (n, lo, data) in W.sections:
        if n != '.reloc':
            continue
        i = 0
        while i + 8 <= len(data):
            page, blksz = struct.unpack_from('<II', data, i)
            if blksz == 0 or blksz < 8 or page == 0:
                break
            for k in range((blksz - 8) // 2):
                e = struct.unpack_from('<H', data, i + 8 + k * 2)[0]
                if (e >> 12) == 10:
                    out.append(page + (e & 0xfff))
            i += blksz
    return out


def parse_data_c(path):
    txt = open(path).read()
    out = {}
    for m in re.finditer(r'static const unsigned char dlld_(\w+)\[\] = \{\n(.*?)\n\};', txt, re.S):
        out['.' + m.group(1).lstrip('_')] = bytes(int(x, 16) for x in re.findall(r'0x([0-9a-f]{2})', m.group(2)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pe')
    ap.add_argument('data_c')
    ap.add_argument('--lb', default='0')
    ap.add_argument('--json')
    ap.add_argument('--expect-missed', type=int, default=None)
    a = ap.parse_args()
    LB = int(a.lb, 0)
    W = Bin(a.pe)
    secs = {n: (lo, bytes(d)) for (n, lo, d) in W.sections if n in ('.rdata', '.data')}
    allsecs = [(n, lo, len(d)) for (n, lo, d) in W.sections]
    out = parse_data_c(a.data_c)
    for n, (lo, d) in secs.items():
        assert len(out[n]) == len(d), (n, len(out[n]), len(d))
    relocs = collect_relocs(W)

    def where(r):
        for n, lo, ln in allsecs:
            if lo <= r < lo + ln:
                return n
        return '(none)'

    by_sec, rows, other = {}, [], {}
    for r in relocs:
        sec = where(r)
        if sec not in secs:
            other[sec] = other.get(sec, 0) + 1
            continue
        lo, orig = secs[sec]
        off = r - lo
        fits = off + 8 <= len(orig)                       # slot 全体が区間内
        v = struct.unpack_from('<Q', orig, off)[0] if fits else None
        val_ok = v is not None and IMG_BASE < v < IMG_BASE + IMG_SPAN
        should = fits and val_ok                           # 補正されるべき slot
        old = lo <= r < lo + len(orig) - 8
        new = lo <= r <= lo + len(orig) - 8
        got = None
        if fits:
            got = struct.unpack_from('<Q', out[sec], off)[0]
        patched = fits and got != v
        right = fits and val_ok and got == v - IMG_BASE + LB
        d = by_sec.setdefault(sec, dict(dir64=0, fits=0, value_ok=0, old_picks=0, new_picks=0,
                                        actually_patched=0, missed=0))
        d['dir64'] += 1; d['fits'] += fits; d['value_ok'] += val_ok
        d['old_picks'] += old; d['new_picks'] += new
        d['actually_patched'] += patched
        miss = should and not right
        d['missed'] += miss
        rows.append(dict(sec=sec, rva=r, v=v, old=old, new=new, patched=patched, right=right, miss=miss))
    # 区間境界ごとの内訳 (各区間の先頭 / 末尾 16B 内)
    bnd = {}
    for n, (lo, orig) in secs.items():
        end = lo + len(orig)
        bnd[n] = dict(lo=lo, end=end, len=len(orig), last_slot_rva=end - 8,
                      head16=[x for x in rows if x['sec'] == n and x['rva'] < lo + 16],
                      tail16=[x for x in rows if x['sec'] == n and x['rva'] >= end - 16])
    miss = [x for x in rows if x['miss']]
    old_new_diff = [x for x in rows if x['old'] != x['new']]
    bad = []
    # 整合: 実出力で補正された slot 集合が式 OLD (補正前の実装) と一致すること (値条件は別)
    for x in rows:
        if x['v'] is None:
            continue
        val_ok = IMG_BASE < x['v'] < IMG_BASE + IMG_SPAN
        if (x['patched']) != (x['old'] and val_ok) and (x['patched']) != (x['new'] and val_ok):
            bad.append(x)
    print('[audit] PE=%s LB=0x%x DIR64 total=%d' % (a.pe, LB, len(relocs)))
    for n in ('.rdata', '.data'):
        d = by_sec.setdefault(n, dict(dir64=0, fits=0, value_ok=0, old_picks=0, new_picks=0,
                                      actually_patched=0, missed=0))
        print('[audit] %-7s lo=0x%x len=%d: DIR64=%d slot収まる=%d 値条件OK=%d | 式OLD選択=%d 式NEW選択=%d | 実出力で補正=%d 補正漏れ=%d' % (
            n, secs[n][0], len(secs[n][1]), d['dir64'], d['fits'], d['value_ok'], d['old_picks'], d['new_picks'],
            d['actually_patched'], d['missed']))
    print('[audit] 補正対象外セクションの DIR64: %s' % json.dumps(other))
    print('[audit] 式 OLD と NEW で選択が分かれる DIR64: %d 件' % len(old_new_diff))
    for x in old_new_diff:
        print('[audit]   境界 slot sec=%s rva=0x%x orig=0x%x old=%s new=%s 実出力で補正=%s' % (
            x['sec'], x['rva'], x['v'], x['old'], x['new'], x['patched']))
    print('[audit] 補正漏れ (値条件OKなのに実出力が正しい LVA でない): %d 件' % len(miss))
    for x in miss:
        print('[audit]   MISS sec=%s rva=0x%x orig=0x%x' % (x['sec'], x['rva'], x['v']))
    print('[audit] 実出力が OLD/NEW どちらの式とも合わない slot: %d 件' % len(bad))
    res = dict(pe=a.pe, lb=LB, dir64_total=len(relocs), by_section=by_sec, other_sections=other,
               old_new_diff=old_new_diff, missed=miss, inconsistent=bad, boundary=bnd)
    if a.json:
        json.dump(res, open(a.json, 'w'), indent=1)
    rc = 0
    if bad:
        print('[audit] FAIL: 実出力が式と矛盾'); rc = 1
    if a.expect_missed is not None:
        if len(miss) == a.expect_missed:
            print('[audit] PASS: 補正漏れ == 期待 %d' % a.expect_missed)
        else:
            print('[audit] FAIL: 補正漏れ %d != 期待 %d' % (len(miss), a.expect_missed)); rc = 1
    return rc


if __name__ == '__main__':
    sys.exit(main())
