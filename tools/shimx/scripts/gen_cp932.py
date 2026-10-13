#!/usr/bin/env python3
"""CP932 (Windows-31J / Shift-JIS) 変換表 src/cp932_tab.c を生成する。

  gen_cp932.py [--src work/bestfit932.txt] [--out src/cp932_tab.c]

入力: Unicode Consortium 配布の Microsoft WindowsBestFit/bestfit932.txt
      (https://unicode.org/Public/MAPPINGS/VENDORS/MICSFT/WindowsBestFit/bestfit932.txt)。
      無ければ取得を試みる (work/ は gitignore。生成物 src/cp932_tab.c のみ commit)。
出力:
  shx_cp932_sb[256]       単一バイト → UTF-16 (リードバイトは 0xFFFF)
  shx_cp932_db[60*189]    DBCS (リード 0x81-0x9F,0xE0-0xFC × トレイル 0x40-0xFC) → UTF-16。0 = 未割当
  shx_cp932_wc[]          (wc<<16)|code を wc 昇順 (WCTABLE 全件 = 厳密 + best-fit)
"""
import argparse, os, re, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))
URL = 'https://unicode.org/Public/MAPPINGS/VENDORS/MICSFT/WindowsBestFit/bestfit932.txt'
LEAD_RANGES = [(0x81, 0x9F), (0xE0, 0xFC)]


def row_of(lead):
    if 0x81 <= lead <= 0x9F:
        return lead - 0x81
    if 0xE0 <= lead <= 0xFC:
        return lead - 0xE0 + 31
    raise ValueError(lead)


def parse(path):
    sb, db, wc = {}, {}, []
    sect, lead = None, None
    for raw in open(path, 'rb').read().split(b'\n'):
        ln = raw.decode('latin1').strip()
        if not ln:
            continue
        m = re.match(r'^(MBTABLE|WCTABLE|DBCSTABLE|DBCSRANGE|CPINFO|CODEPAGE|ENDCODEPAGE)\b', ln)
        if m:
            sect = m.group(1)
            if sect == 'DBCSTABLE':
                lead = int(re.search(r'LeadByte = (0x[0-9a-fA-F]+)', ln).group(1), 16)
            continue
        if 'Lead Byte Range' in ln:      # DBCSRANGE 内の範囲行 (0xe0 0xfc ...) はエントリではない
            continue
        m = re.match(r'^(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)', ln)
        if not m:
            continue
        a, b = int(m.group(1), 16), int(m.group(2), 16)
        if sect == 'MBTABLE':
            sb[a] = b
        elif sect == 'DBCSTABLE':
            db[(lead, a)] = b
        elif sect == 'WCTABLE':
            wc.append((a, b))
    return sb, db, wc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default=os.path.join(ROOT, 'work', 'bestfit932.txt'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'src', 'cp932_tab.c'))
    a = ap.parse_args()
    if not os.path.exists(a.src):
        os.makedirs(os.path.dirname(a.src), exist_ok=True)
        urllib.request.urlretrieve(URL, a.src)
    sb, db, wc = parse(a.src)

    # 未割当トレイルは bestfit では既定文字 U+30FB を指す。正規の 0x8145 (・) 以外は 0 (未割当) に落とす
    unassigned = [(k, v) for k, v in db.items() if v == 0x30FB and k != (0x81, 0x45)]
    for k, _ in unassigned:
        del db[k]
    for (ld, tr) in db:
        assert any(lo <= ld <= hi for lo, hi in LEAD_RANGES) and 0x40 <= tr <= 0xFC and tr != 0x7F, (ld, tr)
    leads = {ld for ld, _ in db}
    sbv = [0xFFFF] * 256
    for k, v in sb.items():
        sbv[k] = v
    for lo, hi in LEAD_RANGES:
        for b in range(lo, hi + 1):
            assert b not in sb, hex(b)
            sbv[b] = 0xFFFF
    assert all(sbv[b] != 0xFFFF for b in range(256) if not any(lo <= b <= hi for lo, hi in LEAD_RANGES))

    dbv = [0] * (60 * 189)
    for (ld, tr), v in db.items():
        dbv[row_of(ld) * 189 + (tr - 0x40)] = v
    wc.sort()
    assert len({w for w, _ in wc}) == len(wc), 'WCTABLE に wc 重複'
    for w, c in wc:
        assert 0 <= w <= 0xFFFF and 0 <= c <= 0xFFFF

    L = []
    L.append('/* 自動生成: scripts/gen_cp932.py (手編集禁止)。')
    L.append(' * 出典: Microsoft WindowsBestFit/bestfit932.txt (Unicode Consortium 配布, %s)。' % URL)
    L.append(' * sb=%d 件 / db=%d 件 (未割当トレイル %d 件を除外) / wc=%d 件 (WCTABLE 全件: 厳密 + best-fit) */' % (
        len(sb), len(db), len(unassigned), len(wc)))
    L.append('#include <stdint.h>')
    L.append('const uint16_t shx_cp932_sb[256] = {')
    for i in range(0, 256, 16):
        L.append('  ' + ','.join('0x%04X' % v for v in sbv[i:i + 16]) + ',')
    L.append('};')
    L.append('const uint16_t shx_cp932_db[60 * 189] = {')
    for i in range(0, len(dbv), 16):
        L.append('  ' + ','.join('0x%04X' % v for v in dbv[i:i + 16]) + ',')
    L.append('};')
    L.append('const uint32_t shx_cp932_wc[] = {')
    for i in range(0, len(wc), 8):
        L.append('  ' + ','.join('0x%08X' % ((w << 16) | c) for w, c in wc[i:i + 8]) + ',')
    L.append('};')
    L.append('const unsigned shx_cp932_wc_n = %d;' % len(wc))
    open(a.out, 'w').write('\n'.join(L) + '\n')
    print('gen_cp932: sb=%d db=%d (未割当除外 %d) wc=%d leads=%d -> %s (%d bytes)' % (
        len(sb), len(db), len(unassigned), len(wc), len(leads), a.out, os.path.getsize(a.out)))


if __name__ == '__main__':
    sys.exit(main())
