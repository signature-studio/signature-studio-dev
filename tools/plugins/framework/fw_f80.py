#!/usr/bin/env python3
"""fw_f80.py — x86_fp80 (x87) を wasm32 でコンパイル可能な f64 に coerce する (P0a smoke 用の近似; 本命は CAB-196 の f80→f64 lowering pass).

  python3 fw_f80.py IN.ll OUT.ll [--report r.json]

* x86_fp80 → double (全置換), @llvm.X.f80 → @llvm.X.f64
* 0xK<16進> (f80 ビットパターン) → 0xH<16進> (f64 bits, 最近接丸め)
* fpext/fptrunc が same-type 化する分 (double→double) は fadd 0.0 で通す (値保存; -0 は +0 に正規化される近似を明記)
* i3 (x87 スタック index) → i32 (wasm が i3 を legalization しないケースの回避; 演算は trunc/zext で整合)
* f80 関数を init 経路で呼ぶと精度が f64 に落ちる (80bit mantissa → 53bit) — 実測は REPORT に記録
"""
import argparse, json, re, struct


def f80_to_f64(khex):
    """0xK + 20桁 hex (16bit sign+exp / 64bit mantissa) → f64 bits hex (0xH + 16桁)"""
    h = khex.strip()
    if len(h) != 20:
        return None
    se = int(h[0:4], 16)
    mant = int(h[4:20], 16)
    sign = se >> 15
    exp = se & 0x7FFF
    if exp == 0 and mant == 0:
        return struct.unpack('<Q', struct.pack('<d', -0.0 if sign else 0.0))[0]
    if exp == 0x7FFF:                      # inf / nan
        if mant == 0:
            v = float('inf') if not sign else float('-inf')
        else:
            v = float('nan')
        return struct.unpack('<Q', struct.pack('<d', v))[0]
    # 正規化 mantissa (integer bit が立っていない subnormal 分も丸めで処理)
    val = mant * 2.0 ** (exp - 16383 - 63)
    if sign:
        val = -val
    return struct.unpack('<Q', struct.pack('<d', val))[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--report')
    a = ap.parse_args()
    text = open(a.src, errors='replace').read()
    rep = {'f80_tokens': text.count('x86_fp80'), 'i3_tokens': 0, 'consts': 0, 'same_type_fix': 0}
    # f80 定数 → f64 bits
    def ksub(m):
        v = f80_to_f64(m.group(1))
        if v is None:
            return m.group(0)
        rep['consts'] += 1
        return 'double 0x%016X' % v
    text = re.sub(r'x86_fp80 0xK([0-9A-Fa-f]+)', ksub, text)
    # 型が左 operand 側のみで定数に型が付かない形 (fadd double %x, 0xK.. 等) の残りを全変換
    def ksub2(m):
        v = f80_to_f64(m.group(1))
        if v is None:
            return m.group(0)
        rep['consts'] += 1
        return '0x%016X' % v
    text = re.sub(r'\b0xK([0-9A-Fa-f]{16,20})\b', ksub2, text)
    # intrinsic 名
    text = re.sub(r'@(llvm\.[a-z0-9.]+)\.f80\b', r'@\1.f64', text)
    # 型置換
    text = text.replace('x86_fp80', 'double')
    # same-type fpext/fptrunc → fadd 0.0 (値保存近似)
    def stfix(m):
        rep['same_type_fix'] += 1
        return '%s%s = fadd double %s, 0.0' % (m.group(1), m.group(2), m.group(3))
    text = re.sub(r'^(\s*)(%[\w.-]+) = (?:fpext|fptrunc) double (%[\w.-]+) to double(,.*)?$', stfix, text, flags=re.M)
    # i3 → i32 (wasm legalization 安定性; x87 index のみに使用)
    n3 = len(re.findall(r'\bi3\b', text))
    rep['i3_tokens'] = n3
    text = re.sub(r'\bi3\b', 'i32', text)
    open(a.dst, 'w').write(text)
    if a.report:
        json.dump(rep, open(a.report, 'w'), indent=1)
    print('[f80]', json.dumps(rep))


if __name__ == '__main__':
    main()
