#!/usr/bin/env python3
"""acc_pname.py — CAB-137 独立再計算: effGetParamName の実測値 (別アルゴリズム)。

定義 (規則 36):
  - 文字列は entry runner が STR (0x30320000) から 0x201 B 読み出した hex の先頭から
    NUL までを ASCII デコードしたもの (harness 側の前填充 0xcc は無視)。
  - 'Bypass' 判定 = param idx 0 の getParamName 文字列が 'Bypass' であること。
  - pdisplay は CRT 初期化前 (旧 build) では native 参照が取れない param があるため
    snapshot の entry build では 7 param (DISP_OK) のみ比較対象。

使い方: python3 tools/ott/accept/acc_pname.py [--scen .../scen.json] [--matrix .../matrix]
"""
import json
import os
import sys

STR_HEX_LEN = 0x201 * 2
DISP_OK = [4, 11, 12, 13, 14, 15, 19]


def dec(buf):
    if buf is None:
        return None
    b = bytes.fromhex(buf)
    i = b.find(b'\x00')
    if i >= 0:
        b = b[:i]
    return b.decode('ascii', 'replace')


def load_matrix(mdir):
    n = json.load(open(os.path.join(mdir, 'nat_result.json')))
    w = json.load(open(os.path.join(mdir, 'wasm_result.json')))
    return n.get('scenarios', n), (w.get('scenarios', w) if 'scenarios' in w else w)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    mdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, '..', 'work', 'entrylift', 'matrix')
    nat, was = load_matrix(mdir)

    print('== getParamName (virt_pname: idx 0..20) ==')
    rows = []
    for i, call in enumerate(nat['virt_pname']['calls']):
        if call.get('kind') != 'virt':
            continue
        idx = i  # virt 呼出は scenario の steps 順 = idx 0..20
        ns, ws_ = dec(call.get('buf')), dec(was['virt_pname']['calls'][i].get('buf'))
        rows.append((idx, ns, ws_, ns == ws_))
    for idx, ns, ws_, ok in rows:
        print('  idx %2d native=%-22r wasm=%-22r %s' % (idx, ns, ws_, 'MATCH' if ok else 'DIFF'))

    print('== getParamLabel (virt_plabel: idx 0..19) ==')
    for i, call in enumerate(nat['virt_plabel']['calls']):
        if call.get('kind') != 'virt':
            continue
        ns, ws_ = dec(call.get('buf')), dec(was['virt_plabel']['calls'][i].get('buf'))
        print('  idx %2d native=%-20r wasm=%-20r %s' % (i-1, ns, ws_, 'MATCH' if ns == ws_ else 'DIFF'))

    print('== getParamDisplay (DISP_OK: integer formatter only) ==')
    for i, call in enumerate(nat['virt_pdisplay']['calls']):
        if call.get('kind') != 'virt':
            continue
        ns, ws_ = dec(call.get('buf')), dec(was['virt_pdisplay']['calls'][i].get('buf'))
        print('  idx %2d native=%-20r wasm=%-20r %s' % (DISP_OK[i-1], ns, ws_, 'MATCH' if ns == ws_ else 'DIFF'))

    print('== getParameter xmm0 (getp_range: idx 0..19) ==')
    ng = nw = 0
    for i, call in enumerate(nat['getp_range']['calls']):
        if call.get('kind') != 'getp':
            continue
        a = call.get('xmm0')
        b = was['getp_range']['calls'][i].get('xmm0')
        if isinstance(a, int) and isinstance(b, int):
            ng += 1
            nw += (a == b)
    print('  xmm0 comparable calls %d / equal %d' % (ng, nw))
    # xmm0 bit pattern -> float
    import struct
    vals = []
    for i, call in enumerate(nat['getp_range']['calls']):
        if call.get('kind') != 'getp':
            continue
        a = call.get('xmm0')
        if isinstance(a, int):
            vals.append(struct.unpack('<f', struct.pack('<I', a & 0xffffffff))[0])
    print('  native xmm0 (as f32) idx0..19:', [round(v, 4) for v in vals])

    # 'Bypass' 判定
    idx0 = [r for r in rows if r[0] == 0]
    print()
    print('== 判定 ==')
    if idx0:
        _, ns, ws_, ok = idx0[0]
        print('  effGetParamName(0) native=%r wasm=%r 一致=%s' % (ns, ws_, ok))
        print('  "Bypass" か: native=%s wasm=%s' % (ns == 'Bypass', ws_ == 'Bypass'))
    # getParamName は r8 バッファに書く (戻り rax はバッファポインタ)
    print('  getp_range の out_f (float* 側) 全 0 か (xmm0 返値の裏付け):',
          all(c.get('out_f') == 0 for c in nat['getp_range']['calls'] if c.get('kind') == 'getp'))


if __name__ == '__main__':
    main()
