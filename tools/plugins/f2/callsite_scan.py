#!/usr/bin/env python3
"""#1807 (PLG-F3-16): 0x411330 の呼出し元・pdata 範囲・格納先の初期値を生バイト走査で出す。

slot_base_store.py (capstone 逆アセンブル) とは別アルゴリズム。逆アセンブルはせず、
PE を VA 配置の平坦イメージに展開して次の 4 種を全バイト走査する:
  1. e8/e9 + rel32 の呼出し先が対象 VA に一致する位置 (直接 call/jmp)
  2. 8 byte の 0 埋め qword として対象 VA が現れる位置 (関数ポインタ等)
  3. ModRM が [rip+disp32] (mod=00 rm=101) の位置。有効アドレス = 次命令末尾 + disp32。
     命令末尾は即値長だけ後ろにずれるので、既知の即値 opcode ごとに補正する。
     opcode が 8D (lea) なら「アドレス計算のみ」、それ以外は「読み書き参照」として分ける。
  4. 対象 VA の 8 byte 値 (初期値)

使い方: python3 tools/plugins/f2/callsite_scan.py <block_PE.bin> [<target_hex>] [<rip_target_hex> ...]
既定: target 0x411330・rip target 0x86b188 0x86b128 (#1807 の測定と同じ)。
"""
import struct, sys

IMM = {0x80: 1, 0x83: 1, 0xC6: 1, 0x6B: 1, 0x81: 4, 0xC7: 4, 0x69: 4}


def load(path):
    raw = open(path, 'rb').read()
    pe = struct.unpack_from('<I', raw, 0x3C)[0]
    nsec = struct.unpack_from('<H', raw, pe + 6)[0]
    optsz = struct.unpack_from('<H', raw, pe + 20)[0]
    opt = pe + 24
    base = struct.unpack_from('<Q', raw, opt + 24)[0]
    sec_off = opt + optsz
    secs = []
    for k in range(nsec):
        o = sec_off + 40 * k
        name = raw[o:o + 8].rstrip(b'\0').decode()
        vsize, rva, rawsz, rawptr = struct.unpack_from('<IIII', raw, o + 8)
        secs.append((name, rva, vsize, rawsz, rawptr))
    top = max(rva + max(vsize, 1) for _, rva, vsize, _, _ in secs)
    img = bytearray(top)
    for name, rva, vsize, rawsz, rawptr in secs:
        n = min(rawsz, vsize) if vsize else rawsz
        img[rva:rva + n] = raw[rawptr:rawptr + n]
    pdata = [s for s in secs if s[0] == '.pdata'][0]
    pd = img[pdata[1]:pdata[1] + pdata[2]]
    funcs = []
    for i in range(len(pd) // 12):
        b, e, _ = struct.unpack_from('<III', pd, 12 * i)
        if b:
            funcs.append((base + b, base + e))
    return base, img, funcs


def main():
    path = sys.argv[1]
    target = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x411330
    rip_targets = [int(x, 16) for x in sys.argv[3:]] or [0x86b188, 0x86b128]
    base, img, funcs = load(path)
    n = len(img)

    calls = []
    for op in (0xE8, 0xE9):
        i = img.find(bytes([op]))
        while i != -1 and i + 5 <= n:
            rel = struct.unpack_from('<i', img, i + 1)[0]
            if base + i + 5 + rel == target:
                calls.append(base + i)
            i = img.find(bytes([op]), i + 1)
    print('[1] e8/e9 直接呼出し元: %d 件' % len(calls), ' '.join(hex(c) for c in calls))

    q = struct.pack('<Q', target)
    qhits = []
    i = img.find(q)
    while i != -1:
        qhits.append(base + i)
        i = img.find(q, i + 1)
    print('[2] qword 参照: %d 件' % len(qhits), ' '.join(hex(c) for c in qhits))

    rip = {t: {'lea': [], 'rw': []} for t in rip_targets}
    for i in range(1, n - 4):
        if img[i - 1] & 0xC7 != 0x05:
            continue
        disp = struct.unpack_from('<i', img, i)[0]
        op = img[i - 2]
        end = base + i + 4 + IMM.get(op, 0)
        ea = end + disp
        start = i - 2 - (1 if 0x40 <= img[i - 3] <= 0x4F else 0)
        if ea in rip:
            rip[ea]['lea' if op == 0x8D else 'rw'].append(base + start)
    for t in rip_targets:
        r = rip[t]
        print('[3] rip 有効アドレス %s: lea %d 件 %s / 読み書き %d 件 %s' % (
            hex(t), len(r['lea']), ' '.join(hex(x) for x in r['lea']),
            len(r['rw']), ' '.join(hex(x) for x in r['rw'])))

    for c in calls:
        for b, e in funcs:
            if b <= c < e:
                print('[4] 呼出し元 %s の pdata 範囲: [%s,%s)' % (hex(c), hex(b), hex(e)))
                break

    for t in rip_targets:
        off = t - base
        v = struct.unpack_from('<Q', img, off)[0]
        print('[5] %s の 8 byte 初期値 (PE 内): %s' % (hex(t), hex(v)))


if __name__ == '__main__':
    main()
