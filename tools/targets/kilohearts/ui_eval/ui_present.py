#!/usr/bin/env python3
"""KH-7 (#59): HeartCore の「画面転送」呼び出し (UIWindowWin32 の WndProc, SetDIBitsToDevice の唯一の call site) を逆アセンブルから復元し、
引数の形を機械検査する。復元した形は shim_probe.c が M7 GUI shim へそのまま投入する。

usage: ui_present.py <HeartCore.core_64> <out.json>
終了コード: 0 = 復元検査 PASS かつ全ネガコンが期待どおり FAIL / 1 = 検査 FAIL またはネガコン失敗
"""
import sys, os, json, re
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from khlib import Core

# (id, 説明, 期待する命令列 (この順に window 内に現れる; 間に他命令があってよい))
PATTERNS = [
    ('P1', 'biSize = 40', ['mov dword ptr [rbp], 0x28']),
    ('P2', 'biWidth = [obj+0x78] (バックバッファ幅)', ['mov eax, dword ptr [rsi + 0x78]', 'mov dword ptr [rbp + 4], eax']),
    ('P3', 'biHeight = -[obj+0x7c] (top-down)', ['xor eax, eax', 'sub eax, dword ptr [rsi + 0x7c]', 'mov dword ptr [rbp + 8], eax']),
    ('P4', 'biPlanes=1, biBitCount=32', ['mov dword ptr [rbp + 0xc], 0x200001']),
    ('P5', 'biCompression=BI_RGB(0), biSizeImage=0', ['mov qword ptr [rbp + 0x10], 0']),
    ('P6', 'ps = BeginPaint(hwnd, &ps) (ps は rbp+0x40), rcPaint を [rbp+0x30] へコピー', ['lea rbx, [rbp + 0x40]', 'mov rdx, rbx', 'movups xmm0, xmmword ptr [rbp + 0x4c]', 'movaps xmmword ptr [rbp + 0x30], xmm0']),
    ('P7', 'lines = H, ySrc = H - rcPaint.bottom', ['mov r10d, dword ptr [rsi + 0x7c]', 'mov r11d, dword ptr [rbp + 0x3c]', 'mov esi, r10d', 'sub esi, r11d']),
    ('P8', 'xDest = left, yDest = top, w = right - left, h = bottom - top',
     ['mov edx, dword ptr [rbp + 0x30]', 'mov r8d, dword ptr [rbp + 0x34]', 'sub r11d, r8d', 'mov r9d, dword ptr [rbp + 0x38]', 'sub r9d, edx']),
    ('P9', 'stack 引数: cy / xSrc / ySrc / StartScan=0 / cLines / bits / bmi / ColorUse=0',
     ['mov qword ptr [rsp + 0x50], r14', 'mov dword ptr [rsp + 0x40], r10d', 'mov dword ptr [rsp + 0x30], esi', 'mov dword ptr [rsp + 0x28], edx',
      'mov dword ptr [rsp + 0x20], r11d', 'mov dword ptr [rsp + 0x58], 0', 'mov dword ptr [rsp + 0x38], 0']),
    ('P10', 'bits = [obj+0x58], bmi = &header(rbp)', ['mov rcx, qword ptr [rsi + 0x58]', 'mov r14, rbp', 'mov qword ptr [rsp + 0x48], rcx']),
]


def subseq(lines, seq):
    i = 0
    for l in lines:
        if i < len(seq) and l == seq[i]:
            i += 1
    return i == len(seq)


def window(core):
    xr = core.xrefs()
    sd = xr.get(('gdi32.dll', 'SetDIBitsToDevice'), [])
    if len(sd) != 1:
        raise SystemExit('SetDIBitsToDevice call site != 1 (%d)' % len(sd))
    site = sd[0][0]
    fb, fe = core.func_of(site)
    bp = [a for a, _ in xr.get(('user32.dll', 'BeginPaint'), []) if core.func_of(a) == (fb, fe)]
    if len(bp) != 1:
        raise SystemExit('BeginPaint call site in same function != 1')
    start = bp[0] - 0x60   # BeginPaint の少し前 (BITMAPINFOHEADER 構築) から
    ins = core.disasm(core.base + start, core.base + site + 6)
    # BeginPaint call の直前に戻って命令境界へ合わせ直す (disasm が命令途中から始まる場合に備え、関数先頭から再逆アセンブル)
    ins = core.disasm(core.base + fb, core.base + site + 6)
    ins = [i for i in ins if i[0] >= core.base + bp[0] - 0x80]
    return (fb, fe, site, bp[0], ins)


def check(core):
    fb, fe, site, bp, ins = window(core)
    lines = ['%s %s' % (m, o) for _, _, m, o in ins]
    res = {pid: subseq(lines, seq) for pid, _, seq in PATTERNS}
    # P11: BeginPaint の戻り値 rax が SetDIBitsToDevice の hdc(rcx) へ渡るまで rax が壊されない
    ok = False
    seen_bp = False
    for a, sz, m, o in ins:
        if a == core.base + bp:
            seen_bp = True
            continue
        if seen_bp:
            if m == 'mov' and o == 'rcx, rax':
                ok = True
                break
            if re.match(r'(rax|eax|ax|al),', o) and m not in ('cmp', 'test'):
                break
    res['P11'] = ok
    return res, ins, lines


def patch(core, ins, pat_mnem_ops, edit):
    """pat_mnem_ops と一致する最初の命令の bytes を edit(bytes)->bytes で書き換えた Core を返す"""
    for a, sz, m, o in ins:
        if '%s %s' % (m, o) == pat_mnem_ops:
            rva = a - core.base
            sec = core.pe.get_section_by_rva(rva)
            off = sec.PointerToRawData + rva - sec.VirtualAddress
            raw = bytes(core.data[off:off + sz])
            new = edit(raw)
            assert len(new) == len(raw) and new != raw
            d = bytearray(core.data)
            d[off:off + sz] = new
            return Core(core.path, data=d)
    raise SystemExit('patch target not found: ' + pat_mnem_ops)


def main():
    path, out = sys.argv[1], sys.argv[2]
    core = Core(path)
    res, ins, lines = check(core)
    fb, fe, site, bp, _ = window(core)
    xr = core.xrefs()
    in_fn = sorted({'%s!%s' % k for k, v in xr.items() for a, _ in v if fb <= a - 0 < fe})
    print('WndProc candidate (SetDIBitsToDevice を含む関数): VA %#x .pdata 範囲 %d B, call site %#x, BeginPaint %#x' % (
        core.base + fb, fe - fb, core.base + site, core.base + bp))
    print('同関数内の IAT 呼び出し (%d 種): %s' % (len(in_fn), ', '.join(in_fn)))
    for pid, desc, _ in PATTERNS:
        print('  [%s] %s: %s' % ('PASS' if res[pid] else 'FAIL', pid, desc))
    print('  [%s] P11: BeginPaint の戻り値 (rax) が rcx(hdc) へそのまま渡る' % ('PASS' if res['P11'] else 'FAIL'))
    fail = [k for k, v in res.items() if not v]

    # ネガティブコントロール: 実バイトを書き換えて再逆アセンブル → 対応する検査が FAIL になること
    ncs = []
    def nc(name, target, edit, expect):
        c2 = patch(core, ins, target, edit)
        r2, _, _ = check(c2)
        ok = (not r2[expect]) and all(v for k, v in r2.items() if k != expect)   # 期待した検査だけが FAIL
        ncs.append({'name': name, 'expect_fail': expect, 'observed_fail': sorted(k for k, v in r2.items() if not v), 'ok': ok})
        print('  [nc %s] %s -> FAIL したのは %s (期待 %s)' % ('ok' if ok else 'NG', name, sorted(k for k, v in r2.items() if not v), expect))
    nc('biBitCount 32 -> 24 (imm 0x200001 -> 0x180001)', 'mov dword ptr [rbp + 0xc], 0x200001',
       lambda b: b[:-4] + (0x180001).to_bytes(4, 'little'), 'P4')
    nc('ySrc = H - bottom の sub を add に改変', 'sub esi, r11d', lambda b: bytes([b[0], 0x01]) + b[2:] if b[0] != 0x44 else bytes([b[0], 0x01]) + b[2:], 'P7')
    nc('StartScan 0 -> 1', 'mov dword ptr [rsp + 0x38], 0', lambda b: b[:-4] + (1).to_bytes(4, 'little'), 'P9')
    nc('biSize 40 -> 56', 'mov dword ptr [rbp], 0x28', lambda b: b[:-4] + (56).to_bytes(4, 'little'), 'P1')
    json.dump({'wndproc_va': hex(core.base + fb), 'wndproc_pdata_bytes': fe - fb, 'call_site': hex(core.base + site),
               'iat_calls_in_wndproc': in_fn, 'patterns': {k: bool(v) for k, v in res.items()}, 'negative_controls': ncs,
               'call_shape': {'hdc': 'BeginPaint(hwnd,&ps)', 'xDest': 'ps.rcPaint.left', 'yDest': 'ps.rcPaint.top',
                              'w': 'right-left', 'h': 'bottom-top', 'xSrc': 'ps.rcPaint.left', 'ySrc': 'H - ps.rcPaint.bottom',
                              'StartScan': 0, 'cLines': 'H', 'bits': 'obj+0x58', 'bmi': 'BITMAPINFOHEADER{40,W,-H,1,32,BI_RGB,0}', 'ColorUse': 'DIB_RGB_COLORS'}},
              open(out, 'w'), indent=1, ensure_ascii=False)
    if fail or any(not n['ok'] for n in ncs):
        print('FAIL', fail, [n['name'] for n in ncs if not n['ok']])
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
