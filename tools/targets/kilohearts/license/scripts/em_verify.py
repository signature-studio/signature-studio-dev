#!/usr/bin/env python3
"""em_verify.py — CAB-247 (KH-10) 検証担当の独立再計算 (別アルゴリズム・規則 37)。

実装側 scripts/{f1088,xrefscan}.py は .pdata の関数範囲を 1 本ずつ舐めてから読/書を分類する。
本スクリプトは **逆方向** のアルゴリズムを採る:

  (1) disp32 == 0x1088 を「生バイト列 88 10 00 00 (LE)」の **高速部分文字列検索** で全部抜く
      (命令境界に依存しないため、走査アルゴリズムの差を吸収した上限)。各ヒットについて
      「そのヒットが ModRM の disp32 位置になる命令が、ヒット直前 15B 以内から decode できるか」
      を自前の最小 x86-64 長さデコーダで調べる (候補駆動 = traversal 駆動ではない)。
  (2) 直接 call は E8 rel32 の **生バイト全走査** (境界に依存しない)。.text 内の全 E8 を対象に
      するため、他命令の即値に紛れた E8 も拾う (偽陽性の可能性 = 上限)。targets に一致したものだけ数える。
  (3) thunk のマスク即値は関数先頭 32B の `mov eax, imm32` (B8) を自前パーサで読む。

pefile / capstone / RetDec 出力 / 実装側スクリプトは一切使わない = 独立再計算。

数え方の定義 (規則 36):
  - "(1) の sites" = 生バイト検索で 88 10 00 00 が見つかった箇所数 (上限)。
    "modrm 確認済み" = そのうち自前デコーダが「ヒット位置を disp32 とするメモリアクセス命令」と
    認定できたもの (偽陽性を除いた数)。read/write/other は opcode のみで判定する
    (write: 88/89/C6/C7, 0F 11/13/17/29/7F / read: 8A/8B, 0F 10/28/6F/7E/D6 / other: その他)。
  - "(2) の sites" = .text 内の全 E8 のうち target への rel32 が一致したもの。
    境界駆動でないため .pdata 境界の函数外・データ領域の E8 も拾う (上限)。
  - "(3) mask bits" = `mov eax, imm32` の即値の 1 ビット位置 (0-indexed)。

usage: python3 scripts/em_verify.py [--json OUT]
"""
import os as _os, sys as _sys
_sys.path.append(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', '..', '..', '..', 'shared'))
from paths import REPO_ROOT
import sys, json, struct, collections

CORE = _os.path.join(REPO_ROOT, 'tools/targets/kilohearts/work/winpkg/HeartCore.core_64')
IMG = 0x180000000
OFF = 0x1088
PAT = struct.pack('<i', OFF)          # 88 10 00 00

# ---------------------------------------------------------------- PE (最小)
def load_text(path):
    d = open(path, 'rb').read()
    pe = struct.unpack_from('<I', d, 0x3c)[0]
    nsec = struct.unpack_from('<H', d, pe + 6)[0]
    osz = struct.unpack_from('<H', d, pe + 20)[0]
    soff = pe + 24 + osz
    sections = []
    for i in range(nsec):
        e = d[soff + i * 40: soff + (i + 1) * 40]
        name = e[:8].rstrip(b'\0').decode()
        vs, va, rs, rp = struct.unpack_from('<IIII', e, 8)
        sections.append((name, va, max(vs, rs), rp))
    text = [s for s in sections if s[0] == '.text'][0]
    return d, sections, IMG + text[1], text[2], text[3]

# ------------------------------------------------------- x86-64 長さ + 分類
PFX = (0x66, 0x67, 0xF2, 0xF3, 0x2E, 0x36, 0x3E, 0x26, 0x64, 0x65)
IMM1 = {0x04, 0x0C, 0x14, 0x1C, 0x24, 0x2C, 0x34, 0x3C, 0x6A, 0x6B, 0x70, 0x71, 0x72, 0x73, 0x74,
        0x75, 0x76, 0x77, 0x78, 0x79, 0x7A, 0x7B, 0x7C, 0x7D, 0x7E, 0x7F, 0x80, 0x83, 0xA8, 0xB0,
        0xB1, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7, 0xC0, 0xC1, 0xC6, 0xCD, 0xD4, 0xD5, 0xE4, 0xE5,
        0xE6, 0xE7, 0xEB}
IMM2 = {0xC2, 0xCA}
IMM4 = {0x05, 0x0D, 0x15, 0x1D, 0x25, 0x2D, 0x35, 0x3D, 0x68, 0x69, 0x81, 0xA9, 0xC7, 0xE8, 0xE9,
        0xE0, 0xE1, 0xE2, 0xE3}
NO_MODRM1 = {0x27, 0x2F, 0x37, 0x3F, 0x40, 0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49,
             0x4A, 0x4B, 0x4C, 0x4D, 0x4E, 0x4F} | set(range(0x50, 0x60)) | {0x61, 0x90, 0x91, 0x92,
             0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9B, 0x9C, 0x9D, 0x9E, 0x9F, 0xA4, 0xA5,
             0xA6, 0xA7, 0xAA, 0xAB, 0xAC, 0xAD, 0xAE, 0xC9, 0xC3, 0xCB, 0xCC, 0xCE, 0xCF, 0xD7,
             0xF4, 0xF5, 0xF8, 0xF9, 0xFA, 0xFB, 0xFC, 0xFD}
NO_MODRM2 = {0x05, 0x06, 0x07, 0x08, 0x09, 0x0B, 0x30, 0x31, 0x32, 0x33, 0x77,
             0xA0, 0xA1, 0xA2, 0xA3, 0xA8, 0xA9, 0xAA, 0xC8, 0xC9, 0xCA, 0xCB, 0xCC, 0xCD, 0xCE, 0xCF}
IMM1_2 = {0x71, 0x72, 0x73, 0xBA}


def decode(b, off):
    """1 命令。disp32 位置・読書分類を返す。失敗/非メモリなら None。

    返り値の disp_off / len は off からの相対値。
    """
    n = len(b)
    i = 0
    while off + i < n and b[off + i] in PFX:
        i += 1
    if off + i >= n:
        return None
    if 0x40 <= b[off + i] <= 0x4F:                     # REX
        i += 1
    if off + i >= n:
        return None
    op = b[off + i]; i += 1
    two = False
    if op == 0x0F:
        if off + i >= n:
            return None
        op = 0x100 | b[off + i]; i += 1
        two = True
    op2 = (op & 0xFF) if two else None
    if not two:
        if op in NO_MODRM1:
            return None
        imm = 1 if op in IMM1 else (2 if op in IMM2 else (4 if op in IMM4 else 0))
    else:
        if op2 in NO_MODRM2:
            return None
        imm = 1 if op2 in IMM1_2 else (4 if 0x80 <= op2 <= 0x8F else 0)
    if off + i >= n:
        return None
    modrm = b[off + i]; i += 1
    mod, rm = modrm >> 6, modrm & 7
    if mod == 3:
        return None                              # レジスタオペランド
    disp_len = 0
    if rm == 4:
        if off + i >= n:
            return None
        sib = b[off + i]; i += 1
        if (sib >> 6) == 0 and (sib & 7) == 5:
            disp_len = 4
    if mod == 0 and rm == 5:
        disp_len = 4                            # rip 相対
    elif mod == 1:
        disp_len = 1
    elif mod == 2:
        disp_len = 4
    if disp_len != 4:
        return None                              # disp8 では 0x1088 は表せない
    if off + i + 4 + imm > n:
        return None
    disp = int.from_bytes(b[off + i:off + i + 4], 'little', signed=True)
    rip = (mod == 0 and rm == 5)
    return {'disp_off': i, 'len': i + 4 + imm, 'disp': disp, 'rip': rip, 'cls': cls_of(op, op2)}


def cls_of(op, op2):
    if op2 is None:
        if op in (0x88, 0x89, 0xC6, 0xC7):
            return 'write'
        if op in (0x8A, 0x8B):
            return 'read'
        return 'other'
    if op2 in (0x11, 0x13, 0x17, 0x29, 0x7F, 0x2B, 0x2F):
        return 'write'
    if op2 in (0x10, 0x28, 0x6F, 0x7E, 0xD6, 0x12, 0x14, 0x2A, 0x2C, 0x2D):
        return 'read'
    return 'other'


def main():
    d, sections, text_va, vsz, rp = load_text(CORE)
    buf = d[rp:rp + vsz]

    # ---------- (1) disp32 == 0x1088 の生バイト全検索
    raw = []
    p = buf.find(PAT)
    while p >= 0:
        raw.append(p)
        p = buf.find(PAT, p + 1)
    confirmed = []
    for p in raw:
        for back in range(1, 16):
            r = decode(buf, p - back)
            if r and r['disp_off'] == back and not r['rip'] and r['disp'] == OFF:
                confirmed.append((text_va + p - back, r['cls'], text_va + p, back))
                break
    cnt = collections.Counter(c[1] for c in confirmed)
    print('[+0x1088] raw byte hits (LE 88 10 00 00): %d' % len(raw))
    print('  confirmed as disp32 of a memory insn (own decoder, <=15B back): %d' % len(confirmed))
    print('  class: write %d, read %d, other %d' % (cnt['write'], cnt['read'], cnt['other']))

    # ---------- (2) E8 rel32 の生バイト全走査
    targets = {0x180051af0: 'EditorModel ctor', 0x18002dc30: 'editor document ctor',
               0x1800f6540: 'content setup writer', 0x180068f750: 'property setter',
               0x180052830: 'poll1', 0x180052a00: 'poll2', 0x18002e850: '+0x1088 writer',
               0x180022be0: 'EventSlot 起火', 0x180054b90: 'getStatus wrapper'}
    cc = collections.Counter()
    i, n = 0, len(buf)
    while i + 5 <= n:
        if buf[i] == 0xE8:
            rel = int.from_bytes(buf[i + 1:i + 5], 'little', signed=True)
            tgt = text_va + i + 5 + rel
            if tgt in targets:
                cc[tgt] += 1
        i += 1
    for t, nm in targets.items():
        print('  call %x (%s): %d' % (t, nm, cc[t]))

    # ---------- (3) thunk mask
    for t in (0x1800b4ac0, 0x1800b4ad0, 0x1800b4ae0, 0x1800b4af0, 0x1800b4b00):
        o = t - text_va
        seg = buf[o:o + 40]
        for k in range(len(seg) - 5):
            if seg[k] == 0xB8:
                imm = int.from_bytes(seg[k + 1:k + 5], 'little')
                print('  thunk %x: mov eax, 0x%x -> bits %s' % (t, imm, [b for b in range(32) if imm >> b & 1]))
                break
        else:
            print('  thunk %x: no B8 imm32 in first 40B' % t)

    # ---------- (4) 実装側と同じ単位 (関数) での比較のため .pdata で関数归属
    #           (PE テーブルを自前パーサで読む。f1088.py のアルゴリズムは使わない)
    pd = [s for s in sections if s[0] == '.pdata'][0]
    praw = d[pd[3]:pd[3] + pd[2]]
    starts, ends = [], {}
    for k in range(0, len(praw) // 12 * 12, 12):
        b, e, u = struct.unpack_from('<III', praw, k)
        if b:
            starts.append(IMG + b); ends[IMG + b] = IMG + e
    starts.sort()

    def fnof(x):
        lo, hi = 0, len(starts) - 1
        while lo < hi:                      # bisect_right
            mid = (lo + hi + 1) // 2
            if starts[mid] <= x:
                lo = mid
            else:
                hi = mid - 1
        return starts[lo] if starts[lo] <= x else None

    wfun, rfun = set(), set()
    for site, kls, _d, _b in confirmed:
        f = fnof(site)
        if f is None:
            continue
        (wfun if kls == 'write' else rfun).add(f)
    print('  fn attribution (.pdata, own parser): write fns %d, non-write fns %d'
          % (len(wfun), len(rfun)))

    if '--json' in sys.argv:
        json.dump({'raw_hits': ['%x' % (text_va + p) for p in raw],
                   'confirmed': ['%x' % c[0] for c in confirmed],
                   'class': dict(cnt),
                   'calls': {'%x' % t: cc[t] for t in targets}},
                  open(sys.argv[sys.argv.index('--json') + 1], 'w'), indent=1)


if __name__ == '__main__':
    main()
