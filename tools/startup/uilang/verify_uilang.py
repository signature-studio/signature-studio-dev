#!/usr/bin/env python3
"""verify_uilang.py — ST-T19 (#591) の静的根拠を FLEngine_x64.dll から機械照合する。stdlib のみ。
tools/startup/loadpaths/verify_refs.py の PE クラス (.pdata 関数境界・RIP 相対文字列参照・E8 呼出辺) を再利用する。

照合 (全て DLL のバイト列。1 件でも不一致なら exit 1):
  A. GetUserPreferredUILanguages: 遅延 import 表 (.didata) の 1 スロットが kernel32!GetUserPreferredUILanguages で、
     そのスロットを経由する `jmp [rip+disp]` thunk を 1 つ特定 → thunk 呼出元 = 0x9df190 だけ。
  B. 0x9df190 の呼出し方: thunk を 2 回 call (1 回目 buf=NULL / 2 回目 buf 指定)、第 1 引数 `mov ecx, 8` (MUI_LANGUAGE_NAME) が 2 回、
     最初の '-' を探す関数 (0x4150d0) を使う。呼出元 = 0x9deaa0 / 0x1265c30 の 2 関数のみ。
  C. 0x9deaa0 の分岐: 0x9dece0(…,0) の結果が空のときだけ 0x9df190 を呼び、結果を 0x414e70 で 'zh' (0x9decbc) と比較、一致時だけ 0x9df010 で保存。
     0x9df010 は Software\\Image-Line\\Shared\\Language の 'Program language' を書く。
     0x9dece0 が読む 'Program Language' 既定値の符号化 (0x9deca8 = 'zh' を WideChar 毎 -50 した文字列) を復号して 'zh' に一致。
  D. lang-svg: '.svg' リテラルを参照する関数は 0xdceea0 だけ。0xdceea0 は直接 call されず、0xdcf270 が lea でアドレスを取る。
     0xdcf270 は Delphi published method 表 (TToolbarForm) の項目 'FlagBtnPaint' のコードポインタ。
  E. 標準フォント: Windows フォント名リテラルの参照関数一覧 (--fonts-json に出力)。
     フォント選択 0x668d30 の分岐 (SHGetFolderPathW(CSIDL_FONTS=0x14) 相当 0x81bca0 → "<名前>.ttf" の存在確認 0x819110 → 無ければ OpenSans-Regular 等)。

usage: verify_uilang.py <FLEngine_x64.dll> [--spec uilang.json] [--fonts-json out.json]
"""
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'loadpaths'))
import verify_refs as V  # noqa: E402


def literals_in(pe, d, fva):
    """関数 fva 内の RIP 相対 lea が指すリテラル (出現順 [(va, text)])"""
    b, e = [(b, e) for b, e in pe.funcs if b + pe.base == fva][0]
    out = []
    for _n, va, _sz, raw, rsz, ch in pe.secs:
        if not ch & 0x20000000:
            continue
        blob = d[raw:raw + rsz]
        for i in range(max(b - va, 0), min(e - va, len(blob)) - 7):
            if blob[i] & 0xf8 == 0x48 and blob[i + 1] == 0x8d and (blob[i + 2] & 0xc7) == 0x05:
                t = va + i + 7 + struct.unpack_from('<i', blob, i + 3)[0]
                cands = [s for s in pe.literal(t) if re.fullmatch(r'[\x20-\x7e]{1,60}', s)]
                if cands:
                    out.append((va + i + pe.base, max(cands, key=len)))
    return sorted(out)


def call_sites(pe, d, callee_va, within=None):
    """callee_va を直接 call する E8 の VA 一覧 (within=(lo,hi) VA で絞り込み)"""
    T = callee_va - pe.base
    out = []
    for _n, va, _sz, raw, rsz, ch in pe.secs:
        if not ch & 0x20000000:
            continue
        blob = d[raw:raw + rsz]
        i = blob.find(b'\xe8')
        while i >= 0 and i + 5 <= len(blob):
            if va + i + 5 + struct.unpack_from('<i', blob, i + 1)[0] == T:
                a = va + i + pe.base
                if within is None or within[0] <= a < within[1]:
                    out.append(a)
            i = blob.find(b'\xe8', i + 1)
    return out


def delay_import_slot(pe, d, dll, fn):
    po = struct.unpack_from('<I', d, 0x3C)[0]
    dr, _ds = struct.unpack_from('<II', d, po + 24 + 112 + 8 * 13)
    x = pe.rva2off(dr)
    while True:
        _a, nm, _m, iat, int_, _b, _u, _t = struct.unpack_from('<IIIIIIII', d, x)
        if nm == 0:
            return None
        name = d[pe.rva2off(nm):][:40].split(b'\0')[0].decode()
        i = 0
        while True:
            t = struct.unpack_from('<Q', d, pe.rva2off(int_) + 8 * i)[0]
            if t == 0:
                break
            h = pe.rva2off(t & 0x7fffffff)
            if name.lower() == dll and d[h + 2:h + 80].split(b'\0')[0].decode() == fn:
                return iat + 8 * i + pe.base
            i += 1
        x += 32


def jmp_thunks_to(pe, d, slot_va):
    out = []
    for _n, va, _sz, raw, rsz, ch in pe.secs:
        if not ch & 0x20000000:
            continue
        blob = d[raw:raw + rsz]
        i = blob.find(b'\xff\x25')
        while i >= 0 and i + 6 <= len(blob):
            if va + i + 6 + struct.unpack_from('<i', blob, i + 2)[0] + pe.base == slot_va:
                out.append(va + i + pe.base)
            i = blob.find(b'\xff\x25', i + 1)
    return out


def main(argv):
    dll = argv[1]
    fonts_out = None
    if '--fonts-json' in argv:
        fonts_out = argv[argv.index('--fonts-json') + 1]
    spec_path = argv[argv.index('--spec') + 1] if '--spec' in argv else os.path.join(HERE, 'uilang.json')
    spec = json.load(open(spec_path))
    d = open(dll, 'rb').read()
    pe = V.PE(d)
    B = pe.base
    strrefs, calls = pe.scan()
    starts = {b + B for b in pe.starts}
    ends = {b + B: e + B for b, e in pe.funcs}
    fails, ok = [], []

    def check(cond, msg):
        (ok if cond else fails).append(msg)

    def func_of(va):
        f = pe.func_of(va - B)
        return f[0] + B if f else None

    # ---- A
    slot = delay_import_slot(pe, d, 'kernel32.dll', 'GetUserPreferredUILanguages')
    check(slot is not None, 'A1 遅延 import に kernel32!GetUserPreferredUILanguages がある')
    thunks = jmp_thunks_to(pe, d, slot) if slot else []
    check(len(thunks) == 1, f'A2 そのスロットを経由する jmp thunk が 1 つ (実測 {len(thunks)} 個)')
    thunk = thunks[0] if thunks else None
    sites = call_sites(pe, d, thunk) if thunk else []
    callers = sorted({func_of(a) for a in sites})
    check(callers == [int(x, 16) for x in spec['gupl_callers']],
          f'A3 thunk の呼出元関数 = {spec["gupl_callers"]} (実測 {[hex(c) for c in callers]})')
    # ---- B
    f190 = 0x9df190
    inside = [a for a in sites if f190 <= a < ends[f190]]
    check(len(inside) == 2, f'B1 0x9df190 内の thunk call は 2 回 (実測 {len(inside)})')
    blob190 = d[pe.rva2off(f190 - B):pe.rva2off(ends[f190] - B)]
    check(blob190.count(b'\xb9\x08\x00\x00\x00') == 2, 'B2 0x9df190 に `mov ecx, 8` (MUI_LANGUAGE_NAME) が 2 回')
    check(0x4150d0 in {c + B for c in calls.get(f190 - B, set())}, 'B3 0x9df190 は文字列内検索 0x4150d0 (最初の "-") を呼ぶ')
    c190 = sorted({func_of(a) for a in call_sites(pe, d, f190)})
    check(c190 == [0x9deaa0, 0x1265c30], f'B5 0x9df190 の呼出元関数は 0x9deaa0 / 0x1265c30 の 2 つだけ (実測 {[hex(c) for c in c190]})')
    lits190 = [s for _a, s in literals_in(pe, d, f190)]
    check(lits190 == ['-'], f'B4 0x9df190 が参照するリテラルは "-" のみ (実測 {lits190})')
    # ---- C
    f = 0x9deaa0
    cs = sorted(c + B for c in calls.get(f - B, set()))
    for need in (0x9dece0, 0x9df190, 0x414e70, 0x9dee40, 0x9df010, 0x9de620, 0x9de810):
        check(need in cs, f'C1 0x9deaa0 は {hex(need)} を呼ぶ')
    order = sorted(call_sites(pe, d, 0x9dece0, (f, ends[f])) + call_sites(pe, d, 0x9df190, (f, ends[f])) +
                   call_sites(pe, d, 0x9df010, (f, ends[f])))
    names = {0x9dece0: 'read', 0x9df190: 'os', 0x9df010: 'save'}
    seq = []
    for a in order:
        for t, nm in names.items():
            if a in call_sites(pe, d, t, (f, ends[f])):
                seq.append(nm)
    check(seq == ['read', 'os', 'save', 'read'], f'C2 0x9deaa0 の呼出順 read→os→save→read (実測 {seq})')
    lit = {s for _a, s in literals_in(pe, d, f)}
    check('zh' in lit, 'C3 0x9deaa0 が "zh" リテラルを参照')
    p = pe.rva2off(0x9deca8 - B)
    ln = struct.unpack_from('<i', d, p - 4)[0]
    dec = ''.join(chr((c - 50) & 0xffff) for c in struct.unpack('<%dH' % ln, d[p:p + 2 * ln]))
    check(ln == 2 and dec == 'zh', f'C4 0x9deaa0 が 0x9dea10 に渡す符号化文字列 (WideChar -50) = "zh" (実測 len={ln} {dec!r})')
    # 0x9deb8c の `jne` が 'zh' 不一致時に保存を飛ばす (0x9deb8c: 0f85 / 75 xx で 0x9debab へ)
    o = pe.rva2off(0x9deb8c - B)
    br = d[o:o + 6]
    tgt = None
    if br[0] == 0x75:
        tgt = 0x9deb8c + 2 + struct.unpack_from('<b', br, 1)[0]
    elif br[:2] == b'\x0f\x85':
        tgt = 0x9deb8c + 6 + struct.unpack_from('<i', br, 2)[0]
    check(tgt == 0x9debab, f'C5 0x9deb8c の jne は 0x9debab (保存を飛ばす) へ (実測 {hex(tgt) if tgt else None})')
    l10 = {s for _a, s in literals_in(pe, d, 0x9df010)}
    check({'Software\\Image-Line\\Shared\\Language', 'Program language', 'Regional note names', 'Accidental Mode'} <= l10,
          f'C7 0x9df010 が書くキー/値 = Language 配下の Program language / Regional note names / Accidental Mode (実測 {sorted(l10)})')
    # ---- D
    svg_fs = sorted(f_ + B for f_, ss in strrefs.items() if '.svg' in ss)
    check(svg_fs == [0xdceea0], f'D1 ".svg" を参照する関数は 0xdceea0 のみ (実測 {[hex(x) for x in svg_fs]})')
    check(call_sites(pe, d, 0xdceea0) == [], 'D2 0xdceea0 への直接 call は 0 件')
    f270 = 0xdcf270
    lea = []
    T = 0xdceea0 - B
    for _n, va, _sz, raw, rsz, ch in pe.secs:
        if not ch & 0x20000000:
            continue
        blob = d[raw:raw + rsz]
        for i in range(len(blob) - 7):
            if blob[i] & 0xf8 == 0x48 and blob[i + 1] == 0x8d and (blob[i + 2] & 0xc7) == 0x05 and \
                    va + i + 7 + struct.unpack_from('<i', blob, i + 3)[0] == T:
                lea.append(va + i + B)
    check([func_of(a) for a in lea] == [f270], f'D3 0xdceea0 のアドレスを取る lea は 0xdcf270 内に 1 件 (実測 {[hex(a) for a in lea]})')
    check(0x5262d0 in {c + B for c in calls.get(f270 - B, set())}, 'D4 0xdcf270 は 0x5262d0 (遅延実行登録) を呼ぶ')
    # published method 表: 0xdcf270 を指す再配置済みポインタが 1 つあり、その直後の ShortString が FlagBtnPaint
    po = struct.unpack_from('<I', d, 0x3C)[0]
    rv, rs = struct.unpack_from('<II', d, po + 24 + 112 + 8 * 5)
    x = pe.rva2off(rv)
    end = x + rs
    refs = []
    while x < end:
        pg, bs = struct.unpack_from('<II', d, x)
        if bs == 0:
            break
        for k in range((bs - 8) // 2):
            e = struct.unpack_from('<H', d, x + 8 + 2 * k)[0]
            if e >> 12 == 10:
                r = pg + (e & 0xfff)
                o = pe.rva2off(r)
                if o and struct.unpack_from('<Q', d, o)[0] == f270:
                    refs.append(r + B)
        x += bs
    check(len(refs) == 1, f'D5 0xdcf270 を指す絶対ポインタ (.reloc DIR64) は 1 件 (実測 {[hex(a) for a in refs]})')
    nm = None
    if refs:
        o = pe.rva2off(refs[0] + 8 - B)
        nm = d[o + 1:o + 1 + d[o]].decode('latin-1')
    check(nm == 'FlagBtnPaint', f'D6 そのポインタの直後の ShortString = FlagBtnPaint (実測 {nm!r})')
    # 同じ published 表内にクラス名 TToolbarForm (ToolbarLanguagesMenu / FlagBtn / FlagBtnPanel も)
    base = pe.rva2off(0xdc7000 - B)
    win = d[base:base + 0x1000]
    for nmx in (b'\x14ToolbarLanguagesMenu', b'\x0cFlagBtnPanel', b'\x07FlagBtn', b'\x0cTToolbarForm'):
        check(nmx in win, f'D7 Delphi ShortString {nmx[1:].decode()} (長さバイト付き) が 0xdc7000 台のクラス表にある')
    # ---- E
    fonts = {}
    for name in spec['font_names']:
        refs_ = sorted(f_ + B for f_, ss in strrefs.items() if name in ss)
        fonts[name] = [hex(a) for a in refs_]
    sel = literals_in(pe, d, 0x668d30)
    seq = [s for _a, s in sel]
    for need in ('segoeui.ttf', 'segoeui', 'segoeuisl.ttf', 'segoeuisl', 'tahoma', 'consola', 'lucon', 'OpenSans-Regular', 'OpenSans-CondLight',
                 'ILGlyphsEx.ilfont', 'WebSymbols-Regular.otf', 'PT_Sans-Web-Regular.ttf'):
        check(need in seq, f'E1 0x668d30 が "{need}" を参照')
    check(0x81bca0 in {c + B for c in calls.get(0x668d30 - B, set())}, 'E2 0x668d30 は 0x81bca0 (フォルダ取得) を呼ぶ')
    check(0x819110 in {c + B for c in calls.get(0x668d30 - B, set())}, 'E3 0x668d30 は 0x819110 (ファイル存在確認) を呼ぶ')
    check(len(call_sites(pe, d, 0x81bca0, (0x668d30, ends[0x668d30]))) == 1 and
          d[pe.rva2off(0x669096 - B):pe.rva2off(0x669096 - B) + 5] == b'\xba\x14\x00\x00\x00',
          'E4 0x668d30 の 0x81bca0 呼出は 1 回で edx = 0x14 (CSIDL_FONTS)')
    # segoeui.ttf (0x6690df) の存在確認結果 [rbp+0x57f] が 0 のとき `je 0x6693b8` で OpenSans-Regular (0x6693e4) 側へ落ちる
    o = pe.rva2off(0x6691ff - B)
    check(d[o:o + 2] == b'\x0f\x84' and 0x6691ff + 6 + struct.unpack_from('<i', d, o + 2)[0] == 0x6693b8,
          'E6 0x6691ff: segoeui 不在 (je) → 0x6693b8')
    seq_i = {s: [a for a, x in sel if x == s] for s in ('segoeui.ttf', 'OpenSans-Regular')}
    check(0x6690df in seq_i['segoeui.ttf'] and 0x6693e4 in seq_i['OpenSans-Regular'] and 0x6693b8 < 0x6693e4,
          'E7 segoeui.ttf (0x6690df) と OpenSans-Regular (0x6693e4) が 0x668d30 内にあり 0x6693b8 < 0x6693e4 (アドレス順のみ。到達性は未検査)')
    o81 = {c + B for c in calls.get(0x81bca0 - B, set())}
    check({0x593450, 0x81bb20} <= o81, 'E5 0x81bca0 は 0x593450 (SHGetFolderPathW の delay thunk) と 0x81bb20 (GetWindowsDirectory 系フォールバック) を呼ぶ')
    json_out = {'font_literal_refs': fonts, 'select_sequence_0x668d30': [(hex(a), s) for a, s in sel]}
    if fonts_out:
        json.dump(json_out, open(fonts_out, 'w'), ensure_ascii=False, indent=1)
    print(json.dumps({'ok': len(ok), 'fail': len(fails), 'gupl_thunk': hex(thunk) if thunk else None, 'gupl_slot': hex(slot) if slot else None,
                      'gupl_call_sites': [hex(a) for a in sites]}, ensure_ascii=False))
    for m in fails:
        print('FAIL', m)
    return 1 if fails else 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv))
