#!/usr/bin/env python3
"""f80_lower.py — x86_fp80 (x87) → f64 lowering pass (CAB-196 P0c-2 / REPORT §3.4 の 4 点)
   + ext-emulation mode (CAB-196 継続 / REPORT §9.4 の設計位置).

  python3 f80_lower.py IN.ll OUT.ll [--report r.json] [--chop-funcs f1,f2,...] [--no-rint]
  python3 f80_lower.py IN.ll OUT.ll --ext --ext-funcs f1,f2,... [--report r.json]

## 通常モード (f80→f64 lowering) — 実装する 4 点 (REPORT §3.4 判定に基づく):

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
        (実機 0x5de3e0 で native==rint 100% を実測; trunc 一致率は入力分布依存 —
        検収再現: 音響 k/1000 で 50.4% / f64 全エントロピーで 98.7% — rint 挿入が必須)。
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
  - --no-rint: [2] の rint 挿入を無効化 (framework 適用用 — cvttsd2si 由来の fptosi と
    fist 由来を IR 上は区別できないため, framework 側は RetDec trunc 模型を維持)。

## ext-emulation mode (--ext --ext-funcs) — x87 64-bit mantissa (ext) の dd エミュレーション

P0c-3 (REPORT §9.4) の残差 (±1-8 f32 ulp) の原因は「x87 64-bit mantissa (ext) と
double 53-bit の演算精度差」。本モードは指定関数内の x87 ドメイン値を double-double
(hi, lo) で表現し, 各演算後に 64-bit significand への最近接偶数丸め (x87 レジスタ
セマンティクス) を再現する。

  表現: 各 ext 値 %v → %v.x87h / %v.x87l の SSA ペア。fpr 経由の値は IR 内部の
    グローバル @__fpr2_store[16 x double] (hi=2i, lo=2i+1) を介して受け渡す
    (ハーネス C 側の変更を不要にするため IR 自己完結)。devirtualized 関数では
    reg2mem spill slot に shadow alloca (%slot.x87lo) を追加して lo を保持。
  演算: TwoSum (add/sub), Dekker TwoProd (mul, C=2^27+1 分割) → round64
    (k = rint(lo·2^(63-e)), 値 = hi + k·2^(e-63) を dd で保持)。
    op-level 3M case + kernel 形 chain 3M case で native x87 long double と
    全数 bit-exact を検証済み (検証スクリプトは REPORT §10 参照)。
  fist (整数化): 53-bit 中継を経ない単一丸め (n0 = rint/trunc(hi),
    d = (hi−n0)+lo は exact, tie は偶数 / trunc は符号翻訳規則) — R10 clamp と合成。
  適用条件: 関数内の double 算術 (fadd/fsub/fmul) が全て x87 由来
    (4 kernel 0x5dfbe0/0x5dfc90/0x5dfd30/0x5dfdb0 で確認済み)。
    fdiv/frem を含む関数は安全側スキップ。f32 store は 53-bit 中継の
    2 段丸め差分 ~2^-29/case が理論上残る (3M case 実測 0)。
  冪等: 変換済み関数は %..x87h 定義の存在で検出しスキップ。
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




# ============================================================
# ext-emulation mode (--ext): x87 64-bit mantissa via double-double
# ============================================================
LIT_RE = re.compile(r'^(0x[0-9A-Fa-f]+|[-\d.]+(?:[eE][-\d]+)?)$')
RE_EXT_DEF = re.compile(r'^(\s*)(%[\w.$-]+) = (fadd|fsub|fmul) double ([\w.%$-]+), ([\w.%$-]+)(?:,\s*![\w.]+\s*!\d+)*\s*$')
RE_EXT_FPRLOAD = re.compile(r'^(\s*)(%[\w.$-]+) = call double @__frontend_reg_load\.fpr\(i32 ([\w.%$-]+)\)(?:,\s*![\w.]+\s*!\d+)*\s*$')
RE_EXT_FPRSTORE = re.compile(r'^(\s*)call void @__frontend_reg_store\.fpr\(i32 ([\w.%$-]+), double ([\w.%$-]+)\)(?:,\s*![\w.]+\s*!\d+)*\s*$')
RE_EXT_SLOTSTORE = re.compile(r'^(\s*)store double ([\w.%$-]+), (?:ptr|double\*) ([\w.%$-]+)(?:,\s*![\w.]+\s*!\d+)*\s*$')
RE_EXT_SLOTLOAD = re.compile(r'^(\s*)(%[\w.$-]+) = load double, (?:ptr|double\*) ([\w.%$-]+)(?:,\s*![\w.]+\s*!\d+)*\s*$')
RE_EXT_ALLOCA = re.compile(r'^(\s*)(%[\w.$-]+) = alloca double(?:,\s*![\w.]+\s*!\d+)*\s*$')
RE_EXT_FPTRUNC = re.compile(r'^(\s*)(%[\w.$-]+) = fptrunc double ([\w.%$-]+) to float(?:,\s*![\w.]+\s*!\d+)*\s*$')
RE_EXT_RINT = re.compile(r'^(\s*)(%[\w.$-]+) = call double @llvm\.rint\.f64\(double ([\w.%$-]+)\)(?:,\s*![\w.]+\s*!\d+)*\s*$')
RE_EXT_FPTOSI = re.compile(r'^(\s*)(%[\w.$-]+) = fptosi double ([\w.%$-]+) to i\d+(?:,\s*![\w.]+\s*!\d+)*\s*$')
RE_EXT_CMP = re.compile(r'^(\s*)(%[\w.$-]+) = fcmp \w+ double ([\w.%$-]+), ([\w.%$-]+)(?:,\s*![\w.]+\s*!\d+)*\s*$')
RE_EXT_SELECT = re.compile(r'^(\s*)(%[\w.$-]+) = select i1 ([\w.%$-]+), double ([\w.%$-]+), double ([\w.%$-]+)(?:,\s*![\w.]+\s*!\d+)*\s*$')
RE_EXT_RET = re.compile(r'^(\s*)ret double ([\w.%$-]+)(?:,\s*![\w.]+\s*!\d+)*\s*$')

# fpr2 モデルの IR 自己完続実装 (ハーネス C 側変更を不要にする)。
# C 実装は g_fpr[i & 7] (8 slot)。dd 化しても slot 対応を変えないため
# **先に & 7 してから 2 倍**する (shl してから & 31 すると負 index で
# 16 要素配列の外側 (index 16..31) に落ちて slot 対応が壊れる)。
EXT_RUNTIME_LL = r"""
@__fpr2_store = global [16 x double] zeroinitializer, align 8

define double @__frontend_reg_load.fpr2h(i32 %i) local_unnamed_addr {
  %w = and i32 %i, 7
  %i2 = shl i32 %w, 1
  %p = getelementptr [16 x double], ptr @__fpr2_store, i32 0, i32 %i2
  %v = load double, ptr %p, align 8
  ret double %v
}

define double @__frontend_reg_load.fpr2l(i32 %i) local_unnamed_addr {
  %w = and i32 %i, 7
  %i2 = shl i32 %w, 1
  %i2p = add i32 %i2, 1
  %p = getelementptr [16 x double], ptr @__fpr2_store, i32 0, i32 %i2p
  %v = load double, ptr %p, align 8
  ret double %v
}

define void @__frontend_reg_store.fpr2h(i32 %i, double %v) local_unnamed_addr {
  %w = and i32 %i, 7
  %i2 = shl i32 %w, 1
  %p = getelementptr [16 x double], ptr @__fpr2_store, i32 0, i32 %i2
  store double %v, ptr %p, align 8
  ret void
}

define void @__frontend_reg_store.fpr2l(i32 %i, double %v) local_unnamed_addr {
  %w = and i32 %i, 7
  %i2 = shl i32 %w, 1
  %i2p = add i32 %i2, 1
  %p = getelementptr [16 x double], ptr @__fpr2_store, i32 0, i32 %i2p
  store double %v, ptr %p, align 8
  ret void
}
"""
EXT_RINT_DECL = 'declare double @llvm.rint.f64(double)'


class ExtMinter:
    """関数内で一意な %base.x87<suffix><n> を採名。
    数値名 base (%17) は LLVM の数値 ID に接尾辞を付けられないため
    quoted identifier (%"17.x87h1") を用いる (_xn と同じ規約)。"""
    def __init__(self):
        self.n = 0

    def get(self, base, suffix):
        self.n += 1
        core = base[1:]
        if re.match(r'^\d+$', core):
            return '%%"%s.x87%s%d"' % (core, suffix, self.n)
        return '%s.x87%s%d' % (base, suffix, self.n)


def _xn(base, suffix):
    """ext ペアの名前。数値名 (%17) は quoted identifier (%"17.x87h") で参照する
    (LLVM の数値 ID に接尾辞は付けられないため)。"""
    core = base[1:]
    if re.match(r'^\d+$', core):
        return '%%"%s.x87%s"' % (core, suffix)
    return '%s.x87%s' % (base, suffix)


def _ext_parse_defs(lines):
    defs = {}
    defre = re.compile(r'^\s*(%[\w.$-]+) = (.+?)(?:\s*;.*)?$')
    for li, ln in enumerate(lines):
        m = defre.match(ln)
        if not m:
            continue
        name, rhs = m.group(1), m.group(2)
        d = {'line': li, 'rhs': rhs, 'kind': 'other'}
        if '@__frontend_reg_load.fpr(' in rhs:
            d['kind'] = 'fprload'
        elif '@llvm.rint.f64' in rhs:
            d['kind'] = 'rint'
        else:
            mo = RE_EXT_DEF.match(ln)
            if mo:
                d['kind'] = mo.group(3)
            elif rhs.startswith('load double,'):
                d['kind'] = 'slotload'
        defs[name] = d
    return defs


def _ext_analyze(lines, defs):
    """ext 値集合 + ext spill slot 特定。

    適用条件 (--ext-funcs で指定する関数の前提): 関数内の double 算術
    (fadd/fsub/fmul) は全て x87 由来 → 全て 64-bit sig 丸め対象。
    根: @__frontend_reg_load.fpr / ext slot からの load。
    """
    ext = set()
    for name, d in defs.items():
        if d['kind'] in ('fprload', 'fadd', 'fsub', 'fmul'):
            ext.add(name)
    allocas = {}
    for li, ln in enumerate(lines):
        ma = RE_EXT_ALLOCA.match(ln)
        if ma:
            allocas[ma.group(2)] = li
    slot_ptrs = {}
    for li, ln in enumerate(lines):
        ms = RE_EXT_SLOTSTORE.match(ln)
        if ms and ms.group(2) in ext and ms.group(3) in allocas:
            slot_ptrs.setdefault(ms.group(3), ms.group(3) + '.x87lo')
    for name, d in defs.items():
        if d['kind'] == 'slotload':
            m = RE_EXT_SLOTLOAD.match(lines[d['line']])
            if m and m.group(3) in slot_ptrs:
                ext.add(name)
    return ext, slot_ptrs, allocas


def _ext_round64(h2, l2, base, mi, out, chop=False, mul=False):
    """round64: (h2,l2) → base.x87h / base.x87l。
    (ext_core_test.c round64 と同一 — 3M case/mode で native x87 と bit 一致検証済)

    k = rint(lo·2^(63-e))      (nearest: round-half-even)
        (chop: floor/ceil — total (h2+lo) の 0 へ向かう切捨て。trunc は整数部と
         加法的でないため符号で floor/ceil を使い分ける)
    H = fl(hi + k·2^(e-63)), L = (hi-H)+k·2^(e-63)   (exact)
    hi の指数が安全域外 (oa<65 or oa>2044) は dd merge (hi+lo) のまま。
    零符号: 結果が零のとき h2 (= fl(正確 op) の IEEE 零符号) を継承。"""
    v_bt = mi.get(base, 'bt')
    v_e10 = mi.get(base, 'e10')
    v_oa = mi.get(base, 'oa')
    v_ob = mi.get(base, 'ob')
    v_ok = mi.get(base, 'ok')
    v_and = mi.get(base, 'and')
    v_pow2 = mi.get(base, 'p2')
    v_p2z = mi.get(base, 'p2z')
    v_lneg = mi.get(base, 'lneg')
    v_sh = mi.get(base, 'sh')
    v_lk = mi.get(base, 'lk')
    v_k = mi.get(base, 'k')
    v_H = mi.get(base, 'H')
    v_dh = mi.get(base, 'dh')
    v_L = mi.get(base, 'L')
    v_Hg = mi.get(base, 'Hg')
    v_hg = mi.get(base, 'hg')
    v_lg = mi.get(base, 'lg')
    v_iz = mi.get(base, 'iz')
    v_H0 = mi.get(base, 'H0')
    v_L0 = mi.get(base, 'L0')
    v_eb = mi.get(base, 'eb')
    v_eb2 = mi.get(base, 'eb2')
    v_eb3 = mi.get(base, 'eb3')
    v_eb4 = mi.get(base, 'eb4')
    v_sc = mi.get(base, 'sc')
    v_ei = mi.get(base, 'ei')
    v_ei2 = mi.get(base, 'ei2')
    v_ei3 = mi.get(base, 'ei3')
    v_ei4 = mi.get(base, 'ei4')
    v_ic = mi.get(base, 'ic')
    v_t = mi.get(base, 't')
    v_shb = mi.get(base, 'shb')
    v_kf = mi.get(base, 'kf')
    v_kc = mi.get(base, 'kc')
    v_kp = mi.get(base, 'kp')
    v_lpos = mi.get(base, 'lpos')
    v_hpos = mi.get(base, 'hpos')
    v_dec = mi.get(base, 'dec')
    out.append('  %s = bitcast double %s to i64' % (v_bt, h2))
    out.append('  %s = lshr i64 %s, 52' % (v_e10, v_bt))
    out.append('  %s = and i64 %s, 2047' % (v_oa, v_e10))
    out.append('  %s = icmp uge i64 %s, 65' % (v_ob, v_oa))
    out.append('  %s = icmp ule i64 %s, 2044' % (v_ok, v_oa))
    out.append('  %s = and i1 %s, %s' % (v_and, v_ob, v_ok))
    # grid shift: h2 が厳密に 2 のべき乗で「大きさが減る向き」(h2>0 かつ lo<0 / h2<0 かつ lo>0)
    # のとき正確値は下の binade に落ちるので ulp64 は半分 (shift 64)。それ以外は 63。
    # (P0c-8: 旧実装は lo<0 のみ判定で h2=-2^k, lo<0 を誤って shift 64 にしていた)
    out.append('  %s = and i64 %s, 4503599627370495' % (v_pow2, v_bt))
    out.append('  %s = icmp eq i64 %s, 0' % (v_p2z, v_pow2))
    out.append('  %s = fcmp olt double %s, 0.0' % (v_lneg, l2))
    out.append('  %s = fcmp ogt double %s, 0.0' % (v_lpos, l2))
    out.append('  %s = fcmp ogt double %s, 0.0' % (v_hpos, h2))
    out.append('  %s = select i1 %s, i1 %s, i1 %s' % (v_dec, v_hpos, v_lneg, v_lpos))
    out.append('  %s = and i1 %s, %s' % (v_shb, v_p2z, v_dec))
    out.append('  %s = select i1 %s, i64 64, i64 63' % (v_sh, v_shb))
    out.append('  %s = add i64 2046, %s' % (v_eb2, v_sh))
    out.append('  %s = sub i64 %s, %s' % (v_eb3, v_eb2, v_oa))
    out.append('  %s = shl i64 %s, 52' % (v_eb4, v_eb3))
    out.append('  %s = bitcast i64 %s to double' % (v_sc, v_eb4))
    out.append('  %s = fmul double %s, %s' % (v_lk, l2, v_sc))
    if chop:
        # x87 RC=chop: total の 0 へ向かう切捨て。p/ulp64 は整数なので
        # trunc_tz(I+x)-I = (I>=0) ? floor(x) : ceil(x)。
        out.append('  %s = call double @llvm.floor.f64(double %s)' % (v_kf, v_lk))
        out.append('  %s = call double @llvm.ceil.f64(double %s)' % (v_kc, v_lk))
        out.append('  %s = fcmp oge double %s, 0.0' % (v_kp, h2))
        out.append('  %s = select i1 %s, double %s, double %s'
                   % (v_k, v_kp, v_kf, v_kc))
    else:
        out.append('  %s = call double @llvm.rint.f64(double %s)' % (v_k, v_lk))
    out.append('  %s = sub i64 %s, %s' % (v_ei2, v_oa, v_sh))
    out.append('  %s = shl i64 %s, 52' % (v_ei4, v_ei2))
    out.append('  %s = bitcast i64 %s to double' % (v_ic, v_ei4))
    out.append('  %s = fmul double %s, %s' % (v_t, v_k, v_ic))
    out.append('  %s = fadd double %s, %s' % (v_H, h2, v_t))
    out.append('  %s = fsub double %s, %s' % (v_dh, h2, v_H))
    out.append('  %s = fadd double %s, %s' % (v_L, v_dh, v_t))
    out.append('  %s = fadd double %s, %s' % (v_Hg, h2, l2))
    out.append('  %s = select i1 %s, double %s, double %s' % (v_hg, v_and, v_H, v_Hg))
    out.append('  %s = select i1 %s, double %s, double 0.000000e+00' % (v_lg, v_and, v_L))
    # 零符号保存: hg == 0 のとき h2 (= fl(正確 op) の零符号) を継承し lo も同符号零。
    # これにより (hi,lo) の merge (hi+lo) も native と同符号の零になる。
    out.append('  %s = fcmp oeq double %s, 0.0' % (v_iz, v_hg))
    out.append('  %s = select i1 %s, double %s, double %s' % (v_H0, v_iz, h2, v_hg))
    out.append('  %s = select i1 %s, double %s, double %s' % (v_L0, v_iz, v_H0, v_lg))
    out.append('  %s = fmul double %s, 1.0' % (_xn(base, 'h'), v_H0))
    out.append('  %s = fmul double %s, 1.0' % (_xn(base, 'l'), v_L0))


def _lit_zero(x):
    """リテラル x が ±0 か (hex bits / 十進)。"""
    if x.startswith(('0x', '0X')):
        try:
            return (int(x, 16) & 0x7FFFFFFFFFFFFFFF) == 0
        except ValueError:
            return False
    try:
        return float(x) == 0.0
    except ValueError:
        return False


def _ext_pair(x, ext, seq, mi, base, neg):
    """operand x (ext 値名 or leaf/literal) → (hi, lo) 名。
    neg=True (fsub の被加数) は fneg。leaf/literal の low は (0.0 / -0.0) リテラル。
    ただしリテラルが ±0 のときは lo も同一符号零 (零符号保存; %m マージ対策)。"""
    if x in ext:
        h, l = _xn(x, 'h'), _xn(x, 'l')
        if neg:
            nh = mi.get(base, 'nh')
            seq.append('  %s = fneg double %s' % (nh, h))
            nl = mi.get(base, 'nl')
            seq.append('  %s = fneg double %s' % (nl, l))
            h, l = nh, nl
        return h, l
    if LIT_RE.match(x):
        if neg:
            nh = '-' + x if not x.startswith('-') else x[1:]
            return (nh, nh if _lit_zero(x) else '-0.0')
        return (x, x if _lit_zero(x) else '0.0')
    if neg:
        nh = mi.get(base, 'nh')
        seq.append('  %s = fneg double %s' % (nh, x))
        return (nh, '-0.0')
    return (x, '0.0')


def _ext_arith(op, a, b, base, ext, mi, chop=False, mul=False):
    """fadd/fsub/fmul → dd 演算系列 (ext_core_test.c と同一の演算順)。
    fsub は b ペアを fneg して TwoSum に帰着する。"""
    seq = []
    if op == 'fmul':
        ah, al = _ext_pair(a, ext, seq, mi, base, False)
        bh, bl = _ext_pair(b, ext, seq, mi, base, False)
        v_p = mi.get(base, 'p')
        v_ta = mi.get(base, 'ta')
        v_da = mi.get(base, 'da')
        v_aha = mi.get(base, 'aha')
        v_ala = mi.get(base, 'ala')
        v_tb = mi.get(base, 'tb')
        v_db = mi.get(base, 'db')
        v_bhb = mi.get(base, 'bhb')
        v_blb = mi.get(base, 'blb')
        v_ahbh = mi.get(base, 'ahbh')
        v_albh = mi.get(base, 'albh')
        v_ahbl = mi.get(base, 'ahbl')
        v_albl = mi.get(base, 'albl')
        v_s1 = mi.get(base, 's1')
        v_s2 = mi.get(base, 's2')
        v_s3 = mi.get(base, 's3')
        v_err = mi.get(base, 'err')
        v_c1 = mi.get(base, 'c1')
        v_c2 = mi.get(base, 'c2')
        v_l0 = mi.get(base, 'l0')
        v_l1 = mi.get(base, 'l1')
        seq.append('  %s = fmul double %s, %s' % (v_p, ah, bh))
        seq.append('  %s = fmul double 0x41A0000002000000, %s' % (v_ta, ah))
        seq.append('  %s = fsub double %s, %s' % (v_da, v_ta, ah))
        seq.append('  %s = fsub double %s, %s' % (v_aha, v_ta, v_da))
        seq.append('  %s = fsub double %s, %s' % (v_ala, ah, v_aha))
        seq.append('  %s = fmul double 0x41A0000002000000, %s' % (v_tb, bh))
        seq.append('  %s = fsub double %s, %s' % (v_db, v_tb, bh))
        seq.append('  %s = fsub double %s, %s' % (v_bhb, v_tb, v_db))
        seq.append('  %s = fsub double %s, %s' % (v_blb, bh, v_bhb))
        seq.append('  %s = fmul double %s, %s' % (v_ahbh, v_aha, v_bhb))
        seq.append('  %s = fmul double %s, %s' % (v_albh, v_ala, v_bhb))
        seq.append('  %s = fmul double %s, %s' % (v_ahbl, v_aha, v_blb))
        seq.append('  %s = fmul double %s, %s' % (v_albl, v_ala, v_blb))
        seq.append('  %s = fsub double %s, %s' % (v_s1, v_p, v_ahbh))
        seq.append('  %s = fsub double %s, %s' % (v_s2, v_s1, v_albh))
        seq.append('  %s = fsub double %s, %s' % (v_s3, v_s2, v_ahbl))
        seq.append('  %s = fsub double %s, %s' % (v_err, v_albl, v_s3))
        seq.append('  %s = fmul double %s, %s' % (v_c1, al, bh))
        seq.append('  %s = fmul double %s, %s' % (v_c2, ah, bl))
        seq.append('  %s = fadd double %s, %s' % (v_l0, v_err, v_c1))
        seq.append('  %s = fadd double %s, %s' % (v_l1, v_l0, v_c2))
        _ext_round64(v_p, v_l1, base, mi, seq, chop, mul=True)
        return seq
    ah, al = _ext_pair(a, ext, seq, mi, base, False)
    bh, bl = _ext_pair(b, ext, seq, mi, base, op == 'fsub')
    v_s = mi.get(base, 's')
    v_q = mi.get(base, 'q')
    v_r = mi.get(base, 'r')
    v_q2 = mi.get(base, 'q2')
    v_r2 = mi.get(base, 'r2')
    v_e0 = mi.get(base, 'e0')
    v_l0 = mi.get(base, 'l0')
    v_l1 = mi.get(base, 'l1')
    seq.append('  %s = fadd double %s, %s' % (v_s, ah, bh))
    seq.append('  %s = fsub double %s, %s' % (v_q, v_s, bh))
    seq.append('  %s = fsub double %s, %s' % (v_r, ah, v_q))
    seq.append('  %s = fsub double %s, %s' % (v_q2, v_s, v_q))
    seq.append('  %s = fsub double %s, %s' % (v_r2, bh, v_q2))
    seq.append('  %s = fadd double %s, %s' % (v_e0, v_r, v_r2))
    seq.append('  %s = fadd double %s, %s' % (v_l0, v_e0, al))
    seq.append('  %s = fadd double %s, %s' % (v_l1, v_l0, bl))
    _ext_round64(v_s, v_l1, base, mi, seq, chop, mul)
    return seq


def _ext_fist_round(X, mi, chop, out):
    """fist の d-based 単一丸め (53-bit 中継を経ない) + R10 clamp。
    ext_core_test.c dd_fist_near / dd_fist_chop と同一 (bit 一致検証済)。

    near: n0 = rint(hi); d0 = hi-n0 (exact, |d0|<=0.5)。tie 判定は d0==±0.5 と lo の符号で行う
          (P0c-8: 旧実装は d=(d0+lo) を f64 で丸めて 0.5 と比較し、lo の符号を失っていた)。
    chop: n0 = trunc(hi); (hi-n0)=0 で lo が hi と反符号 -> 0 側 1 歩
          (V = hi+lo は整数から外れる; trunc_tz は整数側に丸まる)。
    clamp: |丸め値| >= 2^31 -> -2^31 (x87 fist overflow -> integer indefinite)。"""
    vh, vl = _xn(X, 'h'), _xn(X, 'l')
    v = lambda t: mi.get(X, t)
    if chop:
        t0, t1 = v('t0'), v('t1')
        tis, hpos = v('tis'), v('hpos')
        lneg, lpos = v('lneg'), v('lpos')
        opp, adj = v('opp'), v('adj')
        step, t0s, n = v('step'), v('t0s'), v('n')
        out.extend([
            '  %s = call double @llvm.trunc.f64(double %s)' % (t0, vh),
            '  %s = fsub double %s, %s' % (t1, vh, t0),
            '  %s = fcmp oeq double %s, 0.0' % (tis, t1),
            '  %s = fcmp ogt double %s, 0.0' % (hpos, vh),
            '  %s = fcmp olt double %s, 0.0' % (lneg, vl),
            '  %s = fcmp ogt double %s, 0.0' % (lpos, vl),
            '  %s = select i1 %s, i1 %s, i1 %s' % (opp, hpos, lneg, lpos),
            '  %s = and i1 %s, %s' % (adj, tis, opp),
            '  %s = select i1 %s, double -1.0, double 1.0' % (step, hpos),
            '  %s = fadd double %s, %s' % (t0s, t0, step),
            '  %s = select i1 %s, double %s, double %s' % (n, adj, t0s, t0),
        ])
    else:
        n0, d0, d1 = v('n0'), v('d0'), v('d1')
        p1, m1 = v('p1'), v('m1')
        g1, l1 = v('g1'), v('l1')
        g1a, g1b, l1a, l1b = v('g1a'), v('g1b'), v('l1a'), v('l1b')
        h5, hm5, lp0, ln0, lz0 = v('h5'), v('hm5'), v('lp0'), v('ln0'), v('lz0')
        q1, q2 = v('q1'), v('q2')
        bt, od, oi = v('bt'), v('od'), v('oi')
        ep, em = v('ep'), v('em')
        s1, s2, f1, n = v('s1'), v('s2'), v('f1'), v('n')
        out.extend([
            '  %s = call double @llvm.rint.f64(double %s)' % (n0, vh),
            '  %s = fsub double %s, %s' % (d0, vh, n0),
            '  %s = fadd double %s, %s' % (d1, d0, vl),
            '  %s = fadd double %s, 1.0' % (p1, n0),
            '  %s = fadd double %s, -1.0' % (m1, n0),
            '  %s = fcmp ogt double %s, 0.5' % (g1a, d1),
            '  %s = fcmp oeq double %s, 0.5' % (h5, d0),
            '  %s = fcmp oeq double %s, -0.5' % (hm5, d0),
            '  %s = fcmp ogt double %s, 0.0' % (lp0, vl),
            '  %s = fcmp olt double %s, 0.0' % (ln0, vl),
            '  %s = fcmp oeq double %s, 0.0' % (lz0, vl),
            '  %s = and i1 %s, %s' % (g1b, h5, lp0),
            '  %s = or i1 %s, %s' % (g1, g1a, g1b),
            '  %s = fcmp olt double %s, -0.5' % (l1a, d1),
            '  %s = and i1 %s, %s' % (l1b, hm5, ln0),
            '  %s = or i1 %s, %s' % (l1, l1a, l1b),
            '  %s = and i1 %s, %s' % (q1, h5, lz0),
            '  %s = and i1 %s, %s' % (q2, hm5, lz0),
            '  %s = bitcast double %s to i64' % (bt, n0),
            '  %s = and i64 %s, 1' % (od, bt),
            '  %s = icmp ne i64 %s, 0' % (oi, od),
            '  %s = select i1 %s, double %s, double %s' % (ep, oi, p1, n0),
            '  %s = select i1 %s, double %s, double %s' % (em, oi, m1, n0),
            '  %s = select i1 %s, double %s, double %s' % (s1, g1, p1, n0),
            '  %s = select i1 %s, double %s, double %s' % (s2, l1, m1, s1),
            '  %s = select i1 %s, double %s, double %s' % (f1, q1, ep, s2),
            '  %s = select i1 %s, double %s, double %s' % (n, q2, em, f1),
        ])
    cg, cl, co, cv = v('cg'), v('cl'), v('co'), v('cv')
    out.extend([
        '  %s = fcmp oge double %s, 0x41E0000000000000' % (cg, n),
        '  %s = fcmp ole double %s, 0xC1E0000000000000' % (cl, n),
        '  %s = or i1 %s, %s' % (co, cg, cl),
        '  %s = select i1 %s, double 0xC1E0000000000000, double %s' % (cv, co, n),
    ])
    return cv


def _ext_store_f32(X, mi, chop, out):
    """f32 store の 64-bit -> 32-bit 正確丸め (ext_core_test.c dd_f32 と同一)。

      f = RN32(H); exact = (fpext(f) == H)
      chop:    exact で lo と hi が反符号 (0 方向へずれる) -> 0 へ 1 歩 /
               非 exact で 0 から遠いへ丸められた -> 0 へ 1 歩 (trunc 化)
      nearest: H が厳密に f32 中点 (bits&0x1FFFFFFF == 0x10000000) のときだけ
               lo で確定 (lo=0 は even のまま; lo と even 側が違う方へ 1 ulp)
    戻り値: 最終 float の SSA 名。"""
    vh, vl = _xn(X, 'h'), _xn(X, 'l')
    v = lambda t: mi.get(X, t)
    chopc_ = mi.get(X, 'chopc')
    (f_, fe_, ong_, pos_, up_, dn_, away_, lp_, ln_, lne_, opp_, naw_,
     cad_, ca2_, nong_, nad_, chopadj_, bt_, lo_, midv_, mid_, nd_,
     nearadj_, n4_, n5_, tow_, awayf_, stepn_, resn_, resc_, nearadj2_) = \
        [v(t) for t in ('f', 'fe', 'ong', 'pos', 'up', 'dn', 'away', 'lp', 'ln',
                        'lne', 'opp', 'naw', 'cad', 'ca2', 'nong', 'nad',
                        'chopadj', 'bt', 'lo', 'midv', 'mid', 'nd', 'nearadj',
                        'n4', 'n5', 'tow', 'awayf', 'stepn', 'resn', 'resc',
                        'nearadj2')]
    s_ = _xn(X, 's')
    o = out.append
    o('  %s = fptrunc double %s to float' % (f_, vh))
    o('  %s = fpext float %s to double' % (fe_, f_))
    o('  %s = fcmp oeq double %s, %s' % (ong_, fe_, vh))
    o('  %s = fcmp oge double %s, 0.0' % (pos_, vh))
    o('  %s = fcmp ogt double %s, %s' % (up_, fe_, vh))
    o('  %s = fcmp olt double %s, %s' % (dn_, fe_, vh))
    o('  %s = select i1 %s, i1 %s, i1 %s' % (away_, pos_, up_, dn_))
    o('  %s = fcmp ogt double %s, 0.0' % (lp_, vl))
    o('  %s = fcmp olt double %s, 0.0' % (ln_, vl))
    o('  %s = fcmp one double %s, 0.0' % (lne_, vl))
    o('  %s = select i1 %s, i1 %s, i1 %s' % (opp_, pos_, ln_, lp_))
    o('  %s = select i1 %s, i1 %s, i1 %s' % (naw_, pos_, lp_, ln_))
    o('  %s = and i1 %s, %s' % (cad_, ong_, lne_))
    o('  %s = and i1 %s, %s' % (ca2_, cad_, opp_))
    o('  %s = xor i1 %s, true' % (nong_, ong_))
    o('  %s = and i1 %s, %s' % (nad_, nong_, away_))
    o('  %s = or i1 %s, %s' % (chopadj_, ca2_, nad_))
    o('  %s = bitcast double %s to i64' % (bt_, vh))
    o('  %s = and i64 %s, 536870911' % (lo_, bt_))          # 下位 29 bit (ext_core_test.c と同一: 0x1FFFFFFF)
    o('  %s = icmp eq i64 %s, 268435456' % (midv_, lo_))
    o('  %s = and i1 %s, %s' % (mid_, midv_, nong_))
    o('  %s = xor i1 %s, %s' % (nd_, naw_, away_))
    o('  %s = and i1 %s, %s' % (nearadj_, mid_, lne_))
    o('  %s = and i1 %s, %s' % (nearadj2_, nearadj_, nd_))
    o('  %s = call float @nextafterf(float %s, float 0xFFF0000000000000)' % (n4_, f_))
    o('  %s = call float @nextafterf(float %s, float 0x7FF0000000000000)' % (n5_, f_))
    o('  %s = select i1 %s, float %s, float %s' % (tow_, pos_, n4_, n5_))
    o('  %s = select i1 %s, float %s, float %s' % (awayf_, pos_, n5_, n4_))
    if chop:
        o('  %s = select i1 %s, float %s, float %s' % (resc_, chopadj_, tow_, f_))
        o('  %s = fmul float %s, 1.0' % (s_, resc_))
    else:
        o('  %s = select i1 %s, float %s, float %s' % (stepn_, naw_, awayf_, tow_))
        o('  %s = select i1 %s, float %s, float %s' % (resn_, nearadj2_, stepn_, f_))
        o('  %s = fmul float %s, 1.0' % (s_, resn_))
    return s_


def _parse_chop_ranges(spec):
    """'5dfbe0:5dfc0a-5dfc7c,5dfdb0:5dfded-5dfe40' -> {'5dfbe0': [(lo,hi),...]}"""
    rng = {}
    for part in (spec or '').replace(';', ',').split(','):
        part = part.strip()
        if not part or ':' not in part:
            continue
        va, segs = part.split(':', 1)
        va = va.strip().lstrip('0x').lower()
        for seg in segs.split('|'):
            seg = seg.strip()
            if '-' not in seg:
                continue
            lo, hi = seg.split('-', 1)
            rng.setdefault(va, []).append((int(lo, 16), int(hi, 16)))
    return rng


def _resolve_src(vname, defs, ext, depth=3):
    """sink のオペランド名から ext 値名を解決 (select クランプ / rint 呼出を透視)。"""
    if vname in ext:
        return vname
    if depth <= 0:
        return None
    d = defs.get(vname)
    if d is None:
        return None
    m = re.match(r'^select i1 [\w.$%-]+, double [^,]+, double ([\w.$%-]+)$', d['rhs'])
    if m:
        return _resolve_src(m.group(1), defs, ext, depth - 1)
    m = re.match(r'^call double @llvm\.rint\.f64\(double ([\w.$%-]+)\)$', d['rhs'])
    if m:
        return _resolve_src(m.group(1), defs, ext, depth - 1)
    return None


def ext_emulate(text, ext_funcs, rep, chop_funcs='', chop_ranges=None):
    """--ext モード本体。戻り値: (result_text, used_rint, used_fpr2, used_nextafter)。
    chop_funcs: fldcw RC=chop 区間全体を持つ関数名集合 (レベル指定)。
    chop_ranges: "va:lo-hi,..." — fldcw のアドレスレンジ。レンジ内の label の
    ブロックだけ chop (区間外は nearest)。"""
    want = set(x for x in ext_funcs.replace(',', ' ').split() if x)
    chop = set(x for x in chop_funcs.replace(',', ' ').split() if x)
    rng = _parse_chop_ranges(chop_ranges or '')
    starts = [m.start() for m in re.finditer(r'(?m)^define [^\n]*\{', text)]
    head = text[:starts[0]] if starts else text
    chunks = []
    for k, s in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else len(text)
        seg = text[s:e]
        nl = seg.index('\n') + 1
        header = seg[:nl]
        rest = seg[nl:]
        mclose = rest.rindex('\n}\n')
        if mclose < 0:
            chunks.append([header, rest, ''])
        else:
            chunks.append([header, rest[:mclose], '\n}\n' + rest[mclose + 3:]])
    rep['ext_functions'] = []
    used_rint = False
    used_fpr2 = False
    used_nextafter = False
    for ci, (header, body, inter) in enumerate(chunks):
        fm = re.search(r'@([\w.$-]+)\(', header)
        fname = fm.group(1) if fm else '?'
        if fname not in want:
            continue
        lines = body.split('\n')
        if any('.x87' in ln for ln in lines):
            rep['ext_functions'].append({'name': fname, 'status': 'skip:already-ext'})
            continue
        defs = _ext_parse_defs(lines)
        unsupported = sorted({d['rhs'].split()[0] for d in defs.values()
                              if d['kind'] == 'other' and re.match(r'^(fdiv|frem) double', d['rhs'])})
        if unsupported:
            rep['ext_functions'].append({'name': fname, 'status': 'skip:unsupported-op',
                                         'ops': unsupported})
            continue
        ext, slot_ptrs, allocas = _ext_analyze(lines, defs)
        if not ext:
            rep['ext_functions'].append({'name': fname, 'status': 'skip:no-ext-values'})
            continue
        mi = ExtMinter()
        plans = {}                              # line idx -> [replacement lines]
        sink_use = {}
        store_rewrites = {}                     # store line idx -> ext 値名
        drop_lines = set()                       # line idx -> 削除 (旧 x87c 鎖)
        fva = None
        if fname.startswith('function_'):
            try:
                fva = int(fname.split('_', 1)[1], 16)
            except ValueError:
                fva = None
        cur_va = fva or 0
        va_of = {}
        for _i, _ln in enumerate(lines):
            va_of[_i] = cur_va
            _m = re.match(r'^(dec_label_pc_[0-9a-fA-F]+)', _ln)
            if _m:
                cur_va = int(_m.group(1).rsplit('_', 1)[1], 16)

        def chop_here(li):
            if rng and fva is not None:
                for lo, hi in rng.get('%x' % fva, ()):
                    if lo <= va_of.get(li, fva) < hi:
                        return True
                return False
            return fname in chop

        for li, ln in enumerate(lines):
            md = RE_EXT_DEF.match(ln)
            ml = RE_EXT_FPRLOAD.match(ln)
            mfs = RE_EXT_FPRSTORE.match(ln)
            mst = RE_EXT_SLOTSTORE.match(ln)
            mld = RE_EXT_SLOTLOAD.match(ln)
            mr = RE_EXT_RINT.match(ln)
            if md:
                plans[li] = _ext_arith(md.group(3), md.group(4), md.group(5),
                                       md.group(2), ext, mi, fname in chop,
                                       md.group(3) == 'fmul')
                used_rint = True
            elif ml:
                base, idx = ml.group(2), ml.group(3)
                used_fpr2 = True
                plans[li] = [
                    '  %s = call double @__frontend_reg_load.fpr2h(i32 %s)' % (_xn(base, 'h'), idx),
                    '  %s = call double @__frontend_reg_load.fpr2l(i32 %s)' % (_xn(base, 'l'), idx),
                ]
            elif mfs:
                ind, idx, val = mfs.group(1), mfs.group(2), mfs.group(3)
                used_fpr2 = True
                if val in ext:
                    plans[li] = [
                        '%scall void @__frontend_reg_store.fpr2h(i32 %s, double %s)' % (ind, idx, _xn(val, 'h')),
                        '%scall void @__frontend_reg_store.fpr2l(i32 %s, double %s)' % (ind, idx, _xn(val, 'l')),
                    ]
                else:
                    plans[li] = [
                        '%scall void @__frontend_reg_store.fpr2h(i32 %s, double %s)' % (ind, idx, val),
                        '%scall void @__frontend_reg_store.fpr2l(i32 %s, double 0.000000e+00)' % (ind, idx),
                    ]
            elif mst:
                ind, val, ptr = mst.group(1), mst.group(2), mst.group(3)
                if ptr in slot_ptrs:
                    used_fpr2 = True
                    if val in ext:
                        plans[li] = [
                            '%sstore double %s, ptr %s' % (ind, _xn(val, 'h'), ptr),
                            '%sstore double %s, ptr %s' % (ind, _xn(val, 'l'), slot_ptrs[ptr]),
                        ]
                    else:
                        plans[li] = [
                            '%sstore double %s, ptr %s' % (ind, val, ptr),
                            '%sstore double 0.000000e+00, ptr %s' % (ind, slot_ptrs[ptr]),
                        ]
            elif mld:
                base, ptr = mld.group(2), mld.group(3)
                if ptr in slot_ptrs:
                    used_fpr2 = True
                    ext.add(base)
                    plans[li] = [
                        '  %s = load double, ptr %s' % (_xn(base, 'h'), ptr),
                        '  %s = load double, ptr %s' % (_xn(base, 'l'), slot_ptrs[ptr]),
                    ]
            elif mr and mr.group(3) in ext:
                # rint 直後に fptosi (or select クランプ → fptosi) が続く場合は
                # RE_EXT_FPTOSI 側が _resolve_src で同一 ext 値を処理する。
                # ここでも変換すると同じ ext 値の fist 系列が 2 回出力され,
                # 後段の fptosi だけが生きて IR が肥大化する (5dfd30 で実測)。
                # → 後続 30 行以内に fptosi でこの rint 結果を使う行があれば skip。
                near_fptosi = False
                for lj in range(li + 1, min(len(lines), li + 30)):
                    if lines[lj].lstrip().startswith('dec_label_'):
                        break
                    if re.search(r'fptosi double %s to i\d+(?:,\s*![\w.]+\s*!\d+)*\s*$'
                                 % re.escape(mr.group(2)), lines[lj]):
                        near_fptosi = True
                        break
                if not near_fptosi:
                    used_rint = True
                    seq = []
                    n = _ext_fist_round(mr.group(3), mi, chop_here(li), seq)
                    seq.append('  %s = fptosi double %s to i32' % (mr.group(2), n))
                    plans[li] = seq
            m2 = RE_EXT_FPTRUNC.match(ln)
            if m2 and m2.group(3) in ext:
                X = m2.group(3)
                sink_use[X] = True
                for lj in range(li + 1, min(len(lines), li + 30)):
                    if re.match(r'^\s*store float [\w.$%-]+, float\* ', lines[lj]):
                        store_rewrites[lj] = X
                        break
                    if lines[lj].lstrip().startswith('store '):
                        break
                    if lines[lj].lstrip().startswith('dec_label_'):
                        break
                seq = []
                _ext_store_f32(X, mi, chop_here(li), seq)
                used_nextafter = True
                plans[li] = seq
                # 旧 x87fix の f32 nearest/chop 補正鎖 (%x87c*) は ext の
                # 正確丸めに置き換わるので, fptrunc 行から store 行までを落とす
                # store 行自身は store_rewrites で %X.x87s に書換えるので
                # drop_lines には入れない (入れると store ごと消えて buffer 未書込 = 全 cell 差分)
                for lj in range(li + 1, min(len(lines), li + 30)):
                    if lines[lj].lstrip().startswith('store float '):
                        break                       # store 行は store_rewrites が書換える
                    if lines[lj].lstrip().startswith('dec_label_'):
                        break
                    if '%x87c' in lines[lj] or 'nextafterf' in lines[lj]:
                        drop_lines.add(lj)
                    elif lines[lj].lstrip().startswith('store '):
                        break
            m2 = RE_EXT_FPTOSI.match(ln)
            if m2:
                X = _resolve_src(m2.group(3), defs, ext)
                if X is not None:
                    sink_use[X] = True
                    seq = []
                    n = _ext_fist_round(X, mi, chop_here(li), seq)
                    it = re.search(r'to (i\d+)(?:,\s*![\w.]+\s*!\d+)*\s*$', ln).group(1)
                    seq.append('  %s = fptosi double %s to %s' % (m2.group(2), n, it))
                    used_rint = True
                    plans[li] = seq
                    # x87fix R10 の旧 clamp 鎖 (%x87v*) も ext の clamp に
                    # 置き換わるので前方の定義を落とす
                    for lj in range(li - 1, max(-1, li - 8), -1):
                        if '%x87v' in lines[lj] or 'nextafterf' in lines[lj]:
                            drop_lines.add(lj)
                        elif lines[lj].lstrip().startswith('dec_label_'):
                            break
                    for lj in range(li + 1, min(len(lines), li + 8)):
                        if lines[lj].lstrip().startswith('dec_label_'):
                            break
                        if '%x87v' in lines[lj] or 'nextafterf' in lines[lj]:
                            drop_lines.add(lj)
            m2 = RE_EXT_CMP.match(ln)
            if m2:
                for gname in (m2.group(3), m2.group(4)):
                    if gname in ext:
                        sink_use[gname] = True
            m2 = RE_EXT_SELECT.match(ln)
            if m2:
                for gname in (m2.group(4), m2.group(5)):
                    if gname in ext:
                        sink_use[gname] = True
            m2 = RE_EXT_RET.match(ln)
            if m2 and m2.group(2) in ext:
                sink_use[m2.group(2)] = True
        need_m = {name for name in ext if sink_use.get(name)}
        out = []
        for li, ln in enumerate(lines):
            if li in drop_lines:
                continue
            if li in store_rewrites:
                ms2 = re.match(r'^(\s*)store float ([\w.$%-]+), (.*)$', ln)
                if ms2:
                    out.append('%sstore float %s, %s' % (ms2.group(1), _xn(store_rewrites[li], 's'),
                                                        ms2.group(3)))
                    continue
            if li in plans:
                repl = plans[li]
                for part in repl:
                    out.append(part)
                cand = None
                for nm2 in need_m:
                    hd = _xn(nm2, 'h')
                    if any(p.startswith('  ' + hd + ' = ') or p.lstrip().startswith(hd + ' = ') for p in repl):
                        cand = nm2
                        break
                if cand is not None:
                    out.append('  %s = fadd double %s, %s' % (_xn(cand, 'm'), _xn(cand, 'h'), _xn(cand, 'l')))
                continue
            ln2 = ln
            for mm in (RE_EXT_FPTRUNC, RE_EXT_FPTOSI):
                m2 = mm.match(ln2)
                if m2 and m2.group(3) in need_m:
                    ln2 = ln2.replace('double %s' % m2.group(3), 'double %s' % _xn(m2.group(3), 'm'), 1)
            m2 = RE_EXT_CMP.match(ln2)
            if m2:
                a, b = m2.group(3), m2.group(4)
                if a in need_m:
                    ln2 = ln2.replace('double %s,' % a, 'double %s,' % _xn(a, 'm'), 1)
                if b in need_m:
                    ln2 = re.sub(r'(, )%s((?:,\s*![\w.]+\s*!\d+)*\s*)$' % re.escape(b), r'\g<1>%s\g<2>' % _xn(b, 'm'), ln2, count=1)
            m2 = RE_EXT_SELECT.match(ln2)
            if m2:
                a, b = m2.group(4), m2.group(5)
                if a in need_m:
                    ln2 = ln2.replace('double %s,' % a, 'double %s,' % _xn(a, 'm'), 1)
                if b in need_m:
                    ln2 = re.sub(r'(, double )%s((?:,\s*![\w.]+\s*!\d+)*\s*)$' % re.escape(b), r'\g<1>%s\g<2>' % _xn(b, 'm'), ln2, count=1)
            m2 = RE_EXT_RET.match(ln2)
            if m2 and m2.group(2) in need_m:
                ln2 = ln2.replace('ret double %s' % m2.group(2), 'ret double %s' % _xn(m2.group(2), 'm'), 1)
            out.append(ln2)
            ma = RE_EXT_ALLOCA.match(ln)
            if ma and ma.group(2) in slot_ptrs:
                out.append('  %s = alloca double' % slot_ptrs[ma.group(2)])
        rewritten = len(plans) + len(store_rewrites) + len(drop_lines)
        if rewritten == 0:
            rep['ext_functions'].append({'name': fname, 'status': 'skip:no-rewrite',
                                         'ext_values': len(ext),
                                         'slots': sorted(slot_ptrs.keys())})
            continue
        chunks[ci][1] = '\n'.join(out)
        rep['ext_functions'].append({'name': fname, 'status': 'ext',
                                     'ext_values': len(ext),
                                     'rewritten': rewritten,
                                     'slots': sorted(slot_ptrs.keys())})
    result = head
    for header, body, inter in chunks:
        result += header + body + inter
    return result, used_rint, used_fpr2, used_nextafter


F80B_DECL = 'declare i64 @llvm.ctlz.i64(i64, i1)'
RE_F80B_TO = re.compile(r'^(\s*)(%[\w.$-]+) = bitcast x86_fp80 (%[\w.$-]+) to i80(.*)$')
RE_F80B_FROM = re.compile(r'^(\s*)(%[\w.$-]+) = bitcast i80 (%[\w.$-]+) to x86_fp80(.*)$')


def _f80b_to_image(ind, dst, src, p):
    """double src → x87 80-bit 像 i80 (dst)。 符号 / 指数 15 bit / 仮数 64 bit (整数ビット付き)。
    subnormal double は ctlz で正規化する。 NaN / inf は指数 0x7FFF。"""
    L = []

    def o(name, rhs):
        L.append('%s%s = %s' % (ind, name, rhs))
    o(p + 'b', 'bitcast double %s to i64' % src)
    o(p + 'sg', 'lshr i64 %sb, 63' % p)
    o(p + 'sx', 'zext i64 %ssg to i80' % p)
    o(p + 'sh', 'shl i80 %ssx, 79' % p)
    o(p + 'eh', 'lshr i64 %sb, 52' % p)
    o(p + 'e11', 'and i64 %seh, 2047' % p)
    o(p + 'raw', 'and i64 %sb, 4503599627370495' % p)
    o(p + 'rz', 'icmp eq i64 %sraw, 0' % p)
    o(p + 'ez', 'icmp eq i64 %se11, 0' % p)
    o(p + 'nz', 'xor i1 %srz, true' % p)
    o(p + 'sub', 'and i1 %sez, %snz' % (p, p))
    o(p + 'zd', 'and i1 %sez, %srz' % (p, p))
    o(p + 'spec', 'icmp eq i64 %se11, 2047' % p)
    o(p + 'rg', 'select i1 %srz, i64 1, i64 %sraw' % (p, p))
    o(p + 's', 'call i64 @llvm.ctlz.i64(i64 %srg, i1 false)' % p)
    o(p + 'msub', 'shl i64 %srg, %ss' % (p, p))
    o(p + 'm11', 'shl i64 %sraw, 11' % p)
    o(p + 'mn', 'or i64 %sm11, 9223372036854775808' % p)
    o(p + 'ms', 'select i1 %ssub, i64 %smsub, i64 %smn' % (p, p, p))
    o(p + 'mant', 'select i1 %szd, i64 0, i64 %sms' % (p, p))
    o(p + 'ex1', 'add i64 %se11, 15360' % p)
    o(p + 'ex2', 'sub i64 15372, %ss' % p)
    o(p + 'ex3', 'select i1 %sspec, i64 32767, i64 %sex1' % (p, p))
    o(p + 'ex4', 'select i1 %ssub, i64 %sex2, i64 %sex3' % (p, p, p))
    o(p + 'ex', 'select i1 %szd, i64 0, i64 %sex4' % (p, p))
    o(p + 'ex80', 'zext i64 %sex to i80' % p)
    o(p + 'exs', 'shl i80 %sex80, 64' % p)
    o(p + 'mz', 'zext i64 %smant to i80' % p)
    o(p + 't1', 'or i80 %ssh, %sexs' % (p, p))
    o(dst, 'or i80 %st1, %smz' % (p, p))
    return L


def _f80b_from_image(ind, dst, src, p):
    """x87 80-bit 像 i80 src → double (dst)。 仮数 64 bit を 53 bit に最近接偶数丸め。
    double の指数範囲外は inf / 0 に丸める (subnormal の結果は 0 に落とす: 精度の制限)。"""
    L = []

    def o(name, rhs):
        L.append('%s%s = %s' % (ind, name, rhs))
    o(p + 'xs', 'lshr i80 %s, 79' % src)
    o(p + 'xs64', 'trunc i80 %sxs to i64' % p)
    o(p + 'sgn', 'shl i64 %sxs64, 63' % p)
    o(p + 'xe', 'lshr i80 %s, 64' % src)
    o(p + 'xe64', 'trunc i80 %sxe to i64' % p)
    o(p + 'ex', 'and i64 %sxe64, 32767' % p)
    o(p + 'mt', 'trunc i80 %s to i64' % src)
    o(p + 'exz', 'icmp eq i64 %sex, 0' % p)
    o(p + 'exs', 'icmp eq i64 %sex, 32767' % p)
    o(p + 'keep', 'lshr i64 %smt, 11' % p)
    o(p + 'rem', 'and i64 %smt, 2047' % p)
    o(p + 'hgt', 'icmp ugt i64 %srem, 1024' % p)
    o(p + 'heq', 'icmp eq i64 %srem, 1024' % p)
    o(p + 'kl', 'and i64 %skeep, 1' % p)
    o(p + 'kb', 'icmp ne i64 %skl, 0' % p)
    o(p + 'tie', 'and i1 %sheq, %skb' % (p, p))
    o(p + 'up', 'or i1 %shgt, %stie' % (p, p))
    o(p + 'upz', 'zext i1 %sup to i64' % p)
    o(p + 'keep2', 'add i64 %skeep, %supz' % (p, p))
    o(p + 'carry', 'icmp eq i64 %skeep2, 9007199254740992' % p)
    o(p + 'keep3', 'select i1 %scarry, i64 4503599627370496, i64 %skeep2' % (p, p))
    o(p + 'carz', 'zext i1 %scarry to i64' % p)
    o(p + 'E0', 'sub i64 %sex, 15360' % p)
    o(p + 'E', 'add i64 %sE0, %scarz' % (p, p))
    o(p + 'inf', 'icmp sge i64 %sE, 2047' % p)
    o(p + 'low', 'icmp sle i64 %sE, 0' % p)
    o(p + 'fb', 'shl i64 %sE, 52' % p)
    o(p + 'frac', 'and i64 %skeep3, 4503599627370495' % p)
    o(p + 'bn', 'or i64 %sfb, %sfrac' % (p, p))
    o(p + 'bi', 'select i1 %sinf, i64 9218868437227405312, i64 %sbn' % (p, p))
    o(p + 'sn', 'sub i64 1, %sE' % p)
    o(p + 'snok', 'icmp sle i64 %ssn, 52' % p)
    o(p + 'snc', 'select i1 %ssnok, i64 %ssn, i64 1' % (p, p))
    o(p + 'sh2', 'add i64 %ssnc, 11' % p)
    o(p + 'sq', 'lshr i64 %smt, %ssh2' % (p, p))
    o(p + 'smask0', 'shl i64 1, %ssh2' % p)
    o(p + 'smask', 'sub i64 %ssmask0, 1' % p)
    o(p + 'srem', 'and i64 %smt, %ssmask' % (p, p))
    o(p + 'shm1', 'sub i64 %ssh2, 1' % p)
    o(p + 'shalf', 'shl i64 1, %sshm1' % p)
    o(p + 'sgt', 'icmp ugt i64 %ssrem, %sshalf' % (p, p))
    o(p + 'seq', 'icmp eq i64 %ssrem, %sshalf' % (p, p))
    o(p + 'sqo0', 'and i64 %ssq, 1' % p)
    o(p + 'sqo', 'icmp ne i64 %ssqo0, 0' % p)
    o(p + 'stie', 'and i1 %sseq, %ssqo' % (p, p))
    o(p + 'sup', 'or i1 %ssgt, %sstie' % (p, p))
    o(p + 'supz', 'zext i1 %ssup to i64' % p)
    o(p + 'sfr', 'add i64 %ssq, %ssupz' % (p, p))
    o(p + 'sbits0', 'or i64 %ssfr, %ssgn' % (p, p))
    o(p + 'sn53', 'icmp eq i64 %ssn, 53' % p)
    o(p + 'sm53', 'icmp ugt i64 %smt, 9223372036854775808' % p)
    o(p + 'sm53z', 'zext i1 %ssm53 to i64' % p)
    o(p + 'sb53', 'or i64 %ssm53z, %ssgn' % (p, p))
    o(p + 'sbits1', 'select i1 %ssn53, i64 %ssb53, i64 %ssgn' % (p, p, p))
    o(p + 'sbits', 'select i1 %ssnok, i64 %ssbits0, i64 %ssbits1' % (p, p, p))
    o(p + 'b2', 'select i1 %slow, i64 %ssbits, i64 %sbi' % (p, p, p))
    o(p + 'nf', 'lshr i64 %smt, 11' % p)
    o(p + 'nfr', 'and i64 %snf, 4503599627370495' % p)
    o(p + 'nb', 'or i64 %snfr, 9218868437227405312' % p)
    o(p + 'b3', 'select i1 %sexs, i64 %snb, i64 %sb2' % (p, p, p))
    o(p + 'b4', 'select i1 %sexz, i64 0, i64 %sb3' % (p, p))
    o(p + 'bf', 'or i64 %sb4, %ssgn' % (p, p))
    o(dst, 'bitcast i64 %sbf to double' % p)
    return L


def expand_f80_bitcasts(text, rep):
    """E7: bitcast x86_fp80 ↔ i80 (x87 の 80 bit 像を読む・組む命令) を double の bit 再構成に展開する。
    型名の置換 (token_lower) では bitcast double to i80 が残り emcc が落ちるため、先に展開する。
    精度: 結果は 53 bit の double に丸まる (f80 → f64 の既存方式と同じ)。 native x87 とはビット一致しない。
    末尾メタデータ (例: !insn.addr) は展開の最後の命令に付け直す。 llvm.ctlz.i64 の declare は呼び元で足す。"""
    out = []
    n_to = n_from = 0
    for k, ln in enumerate(text.split('\n')):
        mt = RE_F80B_TO.match(ln)
        mf = RE_F80B_FROM.match(ln) if not mt else None
        if mt:
            ind, dst, src, tail = mt.group(1), mt.group(2), mt.group(3), mt.group(4)
            p = '%%f80b%d.' % k
            seq = _f80b_to_image(ind, dst, src, p)
            n_to += 1
        elif mf:
            ind, dst, src, tail = mf.group(1), mf.group(2), mf.group(3), mf.group(4)
            p = '%%f80b%d.' % k
            seq = _f80b_from_image(ind, dst, src, p)
            n_from += 1
        else:
            out.append(ln)
            continue
        seq[-1] = seq[-1] + tail
        out.extend(seq)
    rep['f80_bitcast_to_image'] = n_to
    rep['f80_bitcast_from_image'] = n_from
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
    ap.add_argument('--no-rint', action='store_true',
                    help='[2] の rint 挿入を無効化 (framework 適用用: RetDec trunc 模型を維持)')
    ap.add_argument('--ext', action='store_true',
                    help='ext-emulation mode (x87 64-bit mantissa を double-double で再現)')
    ap.add_argument('--ext-funcs', default='',
                    help='ext モード対象関数名カンマ区切り')
    ap.add_argument('--chop-ranges', dest='chop_ranges', default='',
                    help='fldcw RC=chop のアドレスレンジ "va:lo-hi,..." (ブロック単位)')
    a = ap.parse_args()
    chop_set = set(x for x in a.chop_funcs.replace(',', ' ').split() if x)

    if a.ext:
        # --- ext-emulation mode: lowering 済み IR に対して dd 変換のみ行う ---
        text = open(a.src, errors='replace').read()
        rep = {'mode': 'ext', 'f80_tokens_in': text.count('x86_fp80')}
        result, used_rint, used_fpr2, used_na = ext_emulate(
            text, a.ext_funcs, rep, a.chop_funcs, a.chop_ranges)
        if used_fpr2 and '@__fpr2_store' not in result:
            result = result.rstrip('\n') + '\n' + EXT_RUNTIME_LL
        if used_rint and EXT_RINT_DECL not in result:
            result = result.rstrip('\n') + '\n\n' + EXT_RINT_DECL + '\n'
        if used_na and '@nextafterf' in result and 'declare float @nextafterf' not in result:
            result = result.rstrip('\n') + '\n\ndeclare float @nextafterf(float, float)\n'
        result = dedupe_declares(result)
        open(a.dst, 'w').write(result)
        if a.report:
            json.dump(rep, open(a.report, 'w'), indent=1, ensure_ascii=False)
        next_ = [f for f in rep.get('ext_functions', []) if f['status'] == 'ext']
        skip = [f['name'] for f in rep.get('ext_functions', []) if f['status'].startswith('skip')]
        print('[f80_lower-ext] ext=%d skip=%d %s' % (len(next_), len(skip), skip))
        return

    rep = {'f80_tokens_in': 0, 'f80_tokens_out': 0, 'f80_consts': 0, 'intrinsics_renamed': 0,
           'same_type_conv_erased': 0, 'fild_fistp_i64_folded': 0, 'fistp_rint_inserted': 0,
           'i3_replaced': 0, 'chop_funcs': sorted(chop_set), 'no_rint': bool(a.no_rint),
           'f80_bitcast_to_image': 0, 'f80_bitcast_from_image': 0}

    text = open(a.src, errors='replace').read()
    rep['f80_tokens_in'] = text.count('x86_fp80')
    rep['intrinsics_renamed'] = len(re.findall(r'@llvm\.[a-z0-9.]+\.f80\b', text))
    text = expand_f80_bitcasts(text, rep)
    f80b_decl = bool(rep['f80_bitcast_to_image'] or rep['f80_bitcast_from_image'])

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
    if a.no_rint:
        rep['fistp_rint_inserted'] = 0
        rint_decl = 'declare double @llvm.rint.f64(double)'
    else:
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
    if f80b_decl and F80B_DECL not in result:
        result = result.rstrip('\n') + '\n\n' + F80B_DECL + '\n'

    result = dedupe_declares(result)
    rep['f80_tokens_out'] = result.count('x86_fp80')

    open(a.dst, 'w').write(result)
    if a.report:
        json.dump(rep, open(a.report, 'w'), indent=1)
    print('[f80_lower]', json.dumps(rep))


if __name__ == '__main__':
    main()
