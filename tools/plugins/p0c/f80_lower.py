#!/usr/bin/env python3
"""f80_lower.py — x86_fp80 (x87) → f64 lowering pass (CAB-196 P0c-2 / REPORT §3.4 の 4 点).

  python3 f80_lower.py IN.ll OUT.ll [--report r.json] [--chop-funcs f1,f2,...]

実装する 4 点 (tools/plugins/p0c/REPORT.md §3.4 判定に基づく):

  [1] x87 命令の f64 lowering
      - 型置換: x86_fp80 → double (define/declare/alloca/load/store/算術/fcmp/select/
        phi/call 引数・返値/frontend_reg_load.fpr・store.fpr の全シグネチャ含む)
      - 0xK 定数 (f80 bits) → 0xH (f64 bits, Fraction による正確な最近接丸め)
      - @llvm.*.f80 → @llvm.*.f64 (sin/cos/exp2/round/fabs/...)
      - same-type 化した fpext/fptrunc (double→double) は RAUW で消去 (値保存:
        fpext f64→f80 と fptrunc f80→f64 の往復は -0.0/NaN payload 含め恒等)
      - i3 (x87 stack index) → i32 (wasm legalization 安定化; fw_f80.py と同方針)

  [2] fldcw RC=chop 区間 → trunc
      - RetDec は fist/fistp を無条件に fptosi (=trunc) で模型化する。chop 区間では
        これが正しいのでそのまま保持する (--chop-funcs で指定した関数内)。
      - chop 区間の外 (ambient RC=nearest; Delphi 既定 CW $1332 / fldcw 復帰値 0x033F)
        の fist/fistp は llvm.rint を挿入して最近接丸めに修正する
        (実機 0x5de3e0 で native==rint 100% / native==trunc 74.1% を実測)。
      - --chop-funcs は機械語分類 (f80_assess.py の rc_chop label) から与える。

  [3] i64 保持
      - fild qword→i64 (sitofp は正確) / fistp(RC=nearest)←i64 は i64 ドメインを維持。
        f64 を中継する fild→fistp 恒等チェーン (%a = sitofp i64 %x to double 直後に
        %b = fptosi double %a to i64, 中間 def なし) は %b = %x へ畳む (2^53 超で
        f64 丸めが発生する経路の構造的排除)。k80 では RetDec が既に i64 化済み
        (0x5e0330) のため適用例は無いが, framework lift (CAB-194) 向けに実装。

  [4] f80 spill slot の排除
      - alloca x86_fp80 は型置換で alloca double になる (k80 実測 3 件)。
        load/store も f64 幅に縮むため 16B slot が不要になる。

pass は冪等 (2 回適用で byte 一致) かつ llvm-as 通過。f80 を含まない関数は
1 行も変更しない (f80-free 関数の非干渉性 — i3 が無い関数では全変換が no-op)。

制約 (REPORT 追記節に記録):
  - fstp dword の RC (chop 区間内の f32 丸め) は nearest のまま (LLVM constrained FP
    を要するため非対応; tie case は確率的に ~2^-25/case で差分試験の実測値に含む)。
  - fistp の overflow→0x8000... indefinite と NaN→indefinite 正規化は非対応
    (RetDec fptosi モデルのまま; 対象範囲の入力では非発生)。
"""
import argparse
import json
import re
import struct
from fractions import Fraction


def f80const_to_f64(khex):
    """0xK + 20桁 hex (16bit sign/exp / 64bit mantissa) → f64 bits int (正確な最近接丸め)。"""
    h = khex.strip()
    if len(h) != 20:
        return None
    try:
        se = int(h[0:4], 16)
        mant = int(h[4:20], 16)
    except ValueError:
        return None
    sign = se >> 15
    exp = se & 0x7FFF
    if exp == 0x7FFF:                                     # inf / nan
        if mant == 0:
            v = float('-inf') if sign else float('inf')
            return struct.unpack('<Q', struct.pack('<d', v))[0]
        return 0x7FF8000000000000                          # canonical qNaN
    if exp == 0 and mant == 0:
        v = -0.0 if sign else 0.0
        return struct.unpack('<Q', struct.pack('<d', v))[0]
    val = Fraction(mant, 1) * (Fraction(2) ** (exp - 16383 - 63))
    if sign:
        val = -val
    return struct.unpack('<Q', struct.pack('<d', float(val)))[0]


def rauw_in_func(body, dst, src):
    """関数本体テキスト内の %dst の全使用を %src へ置換 (定義行は残置, word 境界厳守)。"""
    pat = re.compile(r'(?<![\w.%-])' + re.escape(dst) + r'(?![\w.-])')
    out_lines = []
    for ln in body.split('\n'):
        if re.match(r'\s*' + re.escape(dst) + r'\s*=', ln):
            out_lines.append(ln)
            continue
        out_lines.append(pat.sub(src, ln))
    return '\n'.join(out_lines)


def lower_constants(text, rep):
    """x86_fp80 0xK... → double 0xH... (正確な最近接丸め)。
    2 段: (a) 型プレフィクス付き (call/store/select/ret/global 等) は double 0xH へ、
    (b) bare (fadd/fcmp 等の型宣言済みオペランド) は 0xH のみへ。"""
    def ksub_full(m):
        v = f80const_to_f64(m.group(1))
        if v is None:
            return m.group(0)
        rep['f80_consts'] += 1
        return 'double 0x%016X' % v

    def ksub_bare(m):
        v = f80const_to_f64(m.group(1))
        if v is None:
            return m.group(0)
        rep['f80_consts'] += 1
        return '0x%016X' % v
    text = re.sub(r'x86_fp80 0xK([0-9A-Fa-f]{20})\b', ksub_full, text)
    text = re.sub(r'(?<![\w.])0xK([0-9A-Fa-f]{20})\b', ksub_bare, text)
    return text


def erase_same_type_convs(funcs, rep):
    """fpext/fptrunc double→double (f80 型置換の結果 same-type 化) を RAUW で消去。

    funcs: list of [header, body] (body を in-place 更新)。連鎖が収束するまで反復。
    """
    conv_re = re.compile(r'^(\s*)(%[\w.$-]+) = (?:fpext|fptrunc) double (%[\w.$-]+) to double\s*$')
    total = 0
    for _round in range(16):
        n = 0
        for f in funcs:
            lines = f[1].split('\n')
            subs = []
            keep = []
            for ln in lines:
                m = conv_re.match(ln)
                if m:
                    subs.append((m.group(2), m.group(3)))
                    n += 1
                else:
                    keep.append(ln)
            if subs:
                body = '\n'.join(keep)
                for dst, src in subs:
                    body = rauw_in_func(body, dst, src)
                f[1] = body
        total += n
        if n == 0:
            break
    rep['same_type_conv_erased'] = total
    return funcs


def count_uses(body, name, defline):
    """body 中の %name の使用数 (定義行を除く)。"""
    pat = re.compile(r'(?<![\w.%-])' + re.escape(name) + r'(?![\w.-])')
    n = 0
    for ln in body.split('\n'):
        if ln == defline or re.match(r'\s*' + re.escape(name) + r'\s*=', ln):
            continue
        n += len(pat.findall(ln))
    return n


def collapse_fild_fistp_chains(funcs, rep):
    """[3] i64 保持: sitofp i64→double の直後に fptosi double→i64 (中間 def なし) なら恒等畳み込み。"""
    n = 0
    for f in funcs:
        for _round in range(8):
            lines = f[1].split('\n')
            subs = []                                      # (fptosi_dst, sitofp_src)
            sitofp_defs = []
            for i, ln in enumerate(lines):
                m = re.match(r'^(\s*)(%[\w.$-]+) = sitofp i64 (%[\w.$-]+) to double\s*$', ln)
                if m:
                    sitofp_defs.append((i, m.group(1), m.group(2), m.group(3), ln))
            if not sitofp_defs:
                break
            for i, ind, dst, src, ln in sitofp_defs:
                nxt = [l for l in lines[i + 1:] if l.strip() and not l.strip().startswith(';')]
                if not nxt:
                    continue
                m = re.match(r'^\s*(%[\w.$-]+) = fptosi double ' + re.escape(dst) + r' to i64\s*$', nxt[0])
                if m:
                    subs.append((m.group(1), src, m.group(0)))
            if not subs:
                break
            body = '\n'.join(lines)
            for fptosi_dst, src, fptosi_ln in subs:
                body = rauw_in_func(body, fptosi_dst, src)
            # 使用が消えた sitofp/fptosi 行を削除
            keep = []
            for ln in body.split('\n'):
                m1 = re.match(r'^\s*(%[\w.$-]+) = sitofp i64 [%\w.$-]+ to double\s*$', ln)
                m2 = re.match(r'^\s*(%[\w.$-]+) = fptosi double [%\w.$-]+ to i64\s*$', ln)
                if (m1 or m2) and count_uses(body, (m1 or m2).group(1), ln) == 0:
                    n += 1
                    continue
                keep.append(ln)
            f[1] = '\n'.join(keep)
    rep['fild_fistp_i64_folded'] = n


def fix_fistp_rounding(funcs, chop_set, rep):
    """[2] chop 区間外の fptosi (fist/fistp 模型) に llvm.rint を挿入 (RC=nearest 化)。"""
    conv_re = re.compile(r'^(\s*)(%[\w.$-]+) = fptosi double (%[\w.$-]+) to (i16|i32|i64)\s*$')
    ins = 0
    rint_decl = 'declare double @llvm.rint.f64(double)'
    for f in funcs:
        fname_m = re.search(r'@([\w.$-]+)\(', f[0])
        if not fname_m:
            continue
        fname = fname_m.group(1)
        if fname in chop_set:
            continue                                       # chop 区間: trunc (=fptosi) が正しい
        lines = f[1].split('\n')
        rint_vals = set()
        for ln in lines:
            m = re.match(r'^\s*(%[\w.$-]+) = call double @llvm\.rint\.f64\(double (%[\w.$-]+)\)', ln)
            if m:
                rint_vals.add(m.group(1))
        out = []
        changed = False
        for ln in lines:
            m = conv_re.match(ln)
            if m and m.group(3) not in rint_vals:
                ind, dst, v, ity = m.group(1), m.group(2), m.group(3), m.group(4)
                rn = '%%rint.%s' % dst[1:]
                out.append('%s%s = call double @llvm.rint.f64(double %s)' % (ind, rn, v))
                out.append('%s%s = fptosi double %s to %s' % (ind, dst, rn, ity))
                ins += 1
                changed = True
            else:
                out.append(ln)
        if changed:
            f[1] = '\n'.join(out)
    rep['fistp_rint_inserted'] = ins
    return rint_decl


def dedupe_declares(text):
    """同一シグネチャ declare の重複除去 (初出採用)。"""
    seen = set()
    out = []
    for ln in text.split('\n'):
        m = re.match(r'^declare (.+)$', ln)
        if m:
            key = ' '.join(m.group(1).split())
            if key in seen:
                continue
            seen.add(key)
        out.append(ln)
    return '\n'.join(out)


def token_lower(text, rep):
    """S1+S2+S4 のトークン置換 (f80 定数 / 型 / intrinsic 名 / i3)。冪等。"""
    text = lower_constants(text, rep)
    text = text.replace('x86_fp80', 'double')
    text = re.sub(r'@(llvm\.[a-z0-9.]+)\.f80\b', r'@\1.f64', text)
    n3 = len(re.findall(r'(?<![\w.%-])i3(?![\w.-])', text))
    text = re.sub(r'(?<![\w.%-])i3(?![\w.-])', 'i32', text)
    rep['i3_replaced'] += n3
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--report')
    ap.add_argument('--chop-funcs', default='',
                    help='fldcw RC=chop 区間を持つ関数名カンマ区切り (fist/fistp を trunc のまま保持)')
    a = ap.parse_args()
    chop_set = set(x for x in a.chop_funcs.replace(',', ' ').split() if x)
    rep = {'f80_tokens_in': 0, 'f80_tokens_out': 0, 'f80_consts': 0, 'intrinsics_renamed': 0,
           'same_type_conv_erased': 0, 'fild_fistp_i64_folded': 0, 'fistp_rint_inserted': 0,
           'i3_replaced': 0, 'chop_funcs': sorted(chop_set)}

    text = open(a.src, errors='replace').read()
    rep['f80_tokens_in'] = text.count('x86_fp80')
    rep['intrinsics_renamed'] = len(re.findall(r'@llvm\.[a-z0-9.]+\.f80\b', text))

    # --- 関数 split: preamble + (header, body, inter) 連鎖 ---
    starts = [m.start() for m in re.finditer(r'(?m)^define [^\n]*\{', text)]
    head = text[:starts[0]] if starts else text
    chunks = []
    for k, s in enumerate(starts):
        e_next = starts[k + 1] if k + 1 < len(starts) else len(text)
        seg = text[s:e_next]
        nl = seg.index('\n') + 1
        header = seg[:nl]
        rest = seg[nl:]
        mclose = rest.rindex('\n}\n')
        if mclose < 0:
            chunks.append([header, rest, ''])
        else:
            body = rest[:mclose]
            inter = rest[mclose + 3:]
            chunks.append([header, body, '\n}\n' + inter])

    # --- S1/S2 (関数本体を先に same-type 化しておく) ---
    head = token_lower(head, rep)
    for c in chunks:
        c[1] = token_lower(c[1], rep)

    # --- S3: same-type fpext/fptrunc 消去 (RAUW, 連鎖収束) ---
    funcs = [[c[0], c[1]] for c in chunks]
    erase_same_type_convs(funcs, rep)
    for c, f in zip(chunks, funcs):
        c[1] = f[1]

    # --- S5: fild→fistp i64 恒等畳み込み ---
    funcs = [[c[0], c[1]] for c in chunks]
    collapse_fild_fistp_chains(funcs, rep)
    for c, f in zip(chunks, funcs):
        c[1] = f[1]

    # --- S6: fistp RC=nearest 化 (rint 挿入) ---
    funcs = [[c[0], c[1]] for c in chunks]
    rint_decl = fix_fistp_rounding(funcs, chop_set, rep)
    for c, f in zip(chunks, funcs):
        c[1] = f[1]

    # --- 再構築 ---
    result = head
    for header, body, inter in chunks:
        result += header + body + inter

    # --- グローバル・トークン処理 (declare/global 等の非関数部を含む最終正規化) ---
    result = token_lower(result, rep)
    if rep['fistp_rint_inserted'] and rint_decl not in result:
        result = result.rstrip('\n') + '\n\n' + rint_decl + '\n'

    result = dedupe_declares(result)
    rep['f80_tokens_out'] = result.count('x86_fp80')

    open(a.dst, 'w').write(result)
    if a.report:
        json.dump(rep, open(a.report, 'w'), indent=1)
    print('[f80_lower]', json.dumps(rep))


if __name__ == '__main__':
    main()
