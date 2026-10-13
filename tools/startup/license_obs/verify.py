#!/usr/bin/env python3
"""results/ の主張を検査する (exit 0 = 全 PASS)。scan_consumers.py / run_cases.py とは別アルゴリズムの検算を含む。
  V1  capstone 非依存の生バイト走査 (rel32 から実効アドレスを逆算) が、スロット 0x15e0698 / 0x15e4790 を
      参照する命令の集合として capstone 走査の結果を包含する
  V2  scan 結果の不変条件 (直接参照 0 / write は 0x10c7cd0 内のみ / 静的初期バイト 0)
  V3  run_cases の期待値 (A 群 = flag 0x00・gradeChar 0x40、ネガティブコントロールが期待どおり変化)
"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from peidx import Image  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SLOT, GSLOT, FLAG = 0x15e0698, 0x15e4790, 0x14f84a8
fails = []


def check(name, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + name + (f' ({detail})' if detail else ''))
    if not cond:
        fails.append(name)


def raw_loads(im, target):
    """mov r64,[rip+rel32] (REX.W 8B /r, mod=00 rm=101) を生バイトから探す。命令長 7 固定。"""
    t = im.read(im.text_lo, im.text_hi - im.text_lo)
    pat = re.compile(rb'[\x48\x4c]\x8b[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]', re.S)
    out = set()
    for m in pat.finditer(t):
        i = m.start()
        rel = int.from_bytes(t[i + 3:i + 7], 'little', signed=True)
        va = im.text_lo + i
        if va + 7 + rel == target:
            out.add(va)
    return out


def main():
    im = Image()
    d = json.load(open(os.path.join(HERE, 'results', 'flag_sites.json')))
    cs_slot = {s['load'] for s in d['sites']}
    cs_grade = {g['load'] for g in d['grade_sites']}
    rs, rg = raw_loads(im, SLOT), raw_loads(im, GSLOT)
    check('V1a 生バイト走査 ⊇ capstone (スロット 0x15e0698)', cs_slot <= rs, f'capstone {len(cs_slot)} / raw {len(rs)} / raw-only {sorted(hex(x) for x in rs - cs_slot)}')
    check('V1b 生バイト走査 ⊇ capstone (gradeChar +0xd0 経路)', cs_grade <= rg, f'capstone {len(cs_grade)} / raw(0x15e4790 ロード全て) {len(rg)}')
    check('V1c 0x15e0698 ロードの差 = 0', rs == cs_slot)
    sm = d['summary']
    check('V2a 0x14f84a8 への直接 RIP 相対参照 = 0', len(sm['direct_refs_to_flag']) == 0)
    check('V2b flag write は全て 0x10c7cd0 内', sm['write_funcs'] == [0x10c7cd0], str([hex(x) for x in sm['write_funcs']]))
    check('V2c 静的初期バイト = 0x00 かつスロット値 = 0x14f84a8', sm['flag_initial_byte'] == '00' and sm['slot_value'] == hex(FLAG))
    grade_w = sorted({g['func'] for g in d['grade_sites'] if g.get('rw') == 'write'})
    check('V2d gradeChar write 関数 = {0x10c7cd0, 0x10d3a30, 0x11cb000}', grade_w == [0x10c7cd0, 0x10d3a30, 0x11cb000], str([hex(x) for x in grade_w]))
    c = {o['case'][:2]: o for o in json.load(open(os.path.join(HERE, 'results', 'cases.json')))}
    for k in ('A1', 'A2', 'A3', 'A4', 'D2'):
        check(f'V3 {k}: ok / flag 0x00 / gradeChar 0x40', c[k]['status'] == 'ok' and c[k]['flag_hex'] == '00' and c[k]['gradeChar_hex'] == '40')
    check('V3 N1 (gradeChar 初期値改変) → gradeChar 0x42', c['N1']['status'] == 'ok' and c['N1']['gradeChar_hex'] == '42')
    check('V3 N2 (jle を nop) → flag bit0 が立つ', c['N2']['status'] == 'ok' and int(c['N2']['flag_hex'], 16) & 1 == 1)
    check('V3 N3 (flag 初期値改変) → flag 0x04', c['N3']['status'] == 'ok' and c['N3']['flag_hex'] == '04')
    check('V3 B/D1 は VM 復号経路で停止 (未観測として記録)', all(c[k]['status'] != 'ok' for k in ('B1', 'B2', 'D1')))
    print('RESULT', 'FAIL' if fails else 'ALL PASS', fails)
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
