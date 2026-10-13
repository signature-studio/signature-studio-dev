#!/usr/bin/env python3
"""results/ の主張を検査する (exit 0 = 全 PASS)。scan_consumers.py / run_cases.py とは別アルゴリズムの検算を含む。
  V1  capstone 非依存の生バイト走査 (rel32 から実効アドレスを逆算) が、スロット 0x15e0698 / 0x15e4790 を
      参照する命令の集合として capstone 走査の結果を包含する
  V1d/e gradeChar レジスタ追跡 (266 ロード/102 関数) の別算法検算: .pdata の関数走査ではなく、生バイト走査で得た
      0x15e4790 ロード VA から capstone の detail モード (オペランド構造 base/disp・regs_access) で窓を直接デコードする
  V2  scan 結果の不変条件 (直接参照 0 / write は 0x10c7cd0 内のみ / 静的初期バイト 0)
  V3  run_cases の期待値 (A 群 = flag 0x00・gradeChar 0x40、ネガティブコントロールが期待どおり変化)
  V6  unit 初期化節 (VM ハンドラ表を作る 11 関数) の独立導出 (0x8c5cc0 の呼び出し元を生バイト走査 + .pdata) との一致
  V7  ILRegKey 非空ケース (B1/B2/B3/D1/D3) の終了・flag・gradeChar・到達点、ネガコン (NB0–NB3)、ilreg reader.mjs judge() との突合 (judge_xcheck.mjs と --neg)
  V5  gradeChar 追跡のネガティブコントロール (追跡を無効にすると連続形の 196 に戻る / r2 書換えの打切りを外すと件数が増える)
"""
import json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from peidx import Image  # noqa: E402
import scan_consumers  # noqa: E402
from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_MEM, CS_GRP_CALL, CS_OP_REG  # noqa: E402
from capstone.x86 import X86_INS_RET, X86_INS_JMP, X86_INS_LEA, X86_INS_MOV  # noqa: E402

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


GRADE_WINDOW, GOFF = 13, 0xd0
VOLATILE = {'rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'}


def full(name):
    """サブレジスタ名 → 64 ビット名 (al/ax/eax → rax, r8d → r8, sil → rsi)。"""
    m = re.fullmatch(r'r(\d+)[dwb]?', name)
    if m:
        return 'r' + m.group(1)
    m = re.fullmatch(r'(?:[re]?([abcd])x|([abcd])[lh])', name)
    if m:
        return 'r' + (m.group(1) or m.group(2)) + 'x'
    m = re.fullmatch(r'[re]?(si|di|bp|sp)l?', name)
    return 'r' + m.group(1) if m else name


def tracked_loads(im, loads, window=GRADE_WINDOW):
    """別算法の gradeChar 追跡。loads = 生バイト走査で得た 0x15e4790 ロードの VA。各 VA から 2 + window 命令を直接デコードし
    (関数境界を使わない)、[ld] r1 := [GSLOT]; r2 := [r1] (mem.base=r1, index なし, disp 0); 続く window 命令で mem.base=r2・disp=0xd0 を
    持つオペランドが最初に現れるまで追う。ret/jmp、または regs_access の書込レジスタ (部分書込を含む)・call による volatile 破壊で r2 が
    失われたら打切り。戻り値 {load VA: (使用 VA, 使用命令の id)}。"""
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    out = {}
    for va in sorted(loads):
        buf = im.read(va, 16 * (window + 2))
        ins = []
        for x in md.disasm(buf, va):
            ins.append(x)
            if len(ins) == window + 2:
                break
        if len(ins) < 2:
            continue
        a, b = ins[0], ins[1]
        if a.id != X86_INS_MOV or b.id != X86_INS_MOV:
            continue
        r1 = full(a.reg_name(a.operands[0].reg))
        o0, o1 = b.operands
        if o0.type != CS_OP_REG or o1.type != CS_OP_MEM or o1.mem.index or o1.mem.disp or full(b.reg_name(o1.mem.base)) != r1:
            continue
        r2 = full(b.reg_name(o0.reg))
        for y in ins[2:]:
            if any(o.type == CS_OP_MEM and o.mem.base and o.mem.index == 0 and o.mem.disp == GOFF and full(y.reg_name(o.mem.base)) == r2
                   for o in y.operands):
                out[va] = (y.address, y.id)
                break
            if y.id in (X86_INS_RET, X86_INS_JMP):
                break
            _, wr = y.regs_access()
            if r2 in {full(y.reg_name(r)) for r in wr} or (CS_GRP_CALL in y.groups and r2 in VOLATILE):
                break
    return out


def unit_inits_independent(im):
    """0x8c5cc0 (VM ハンドラ登録) への call rel32 を生バイトから探し、呼び出し元の .pdata 関数先頭の集合を返す。emu_reg.UNIT_INITS とは独立に導出。"""
    t = im.read(im.text_lo, im.text_hi - im.text_lo)
    out = set()
    for m in re.finditer(b'\xe8', t):
        i = m.start()
        if i + 5 > len(t):
            continue
        va = im.text_lo + i
        if va + 5 + int.from_bytes(t[i + 1:i + 5], 'little', signed=True) == 0x8c5cc0:
            f = im.func_of(va)
            if f:
                out.add(f)
    return out


def main():
    im = Image()
    d = json.load(open(os.path.join(HERE, 'results', 'flag_sites.json')))
    cs_slot = {s['load'] for s in d['sites']}
    cs_grade = {g['load'] for g in d['grade_sites']}
    rs, rg = raw_loads(im, SLOT), raw_loads(im, GSLOT)
    check('V1a 生バイト走査 ⊇ capstone (スロット 0x15e0698)', cs_slot <= rs, f'capstone {len(cs_slot)} / raw {len(rs)} / raw-only {sorted(hex(x) for x in rs - cs_slot)}')
    check('V1b 生バイト走査 ⊇ capstone (gradeChar 連続形; 部分集合検査で取りこぼしは検出しない → V1d)', cs_grade <= rg, f'capstone {len(cs_grade)} / raw(0x15e4790 ロード全て) {len(rg)}')
    check('V1c 0x15e0698 ロードの差 = 0', rs == cs_slot)
    sm = d['summary']
    check('V2a 0x14f84a8 への直接 RIP 相対参照 = 0', len(sm['direct_refs_to_flag']) == 0)
    check('V2b flag write は全て 0x10c7cd0 内', sm['write_funcs'] == [0x10c7cd0], str([hex(x) for x in sm['write_funcs']]))
    check('V2c 静的初期バイト = 0x00 かつスロット値 = 0x14f84a8', sm['flag_initial_byte'] == '00' and sm['slot_value'] == hex(FLAG))
    grade_w = sorted({g['func'] for g in d['grade_sites'] if g.get('rw') == 'write'})
    check('V2d gradeChar write 関数 (連続形で辿れた範囲 = 下限) = {0x10c7cd0, 0x10d3a30, 0x11cb000}', grade_w == [0x10c7cd0, 0x10d3a30, 0x11cb000], str([hex(x) for x in grade_w]))
    trk = {t['load']: t for t in d['grade_tracked']}
    ind = tracked_loads(im, rg)
    check('V1d 別算法 (生バイト起点 + detail モード) のレジスタ追跡 = scan の追跡形 266 ロード (集合一致)', set(ind) == set(trk) and len(ind) == 266,
          f'independent {len(ind)} / scan {len(trk)} / diff {sorted(hex(x) for x in set(ind) ^ set(trk))[:5]}')
    check('V1d2 追跡形 ⊇ 連続形 196', cs_grade <= set(trk) and len(cs_grade) == 196)
    check('V1d3 使用命令の VA が両算法で一致、lea = 69 (追加分は lea 69 + store 1)', all(ind[k][0] == trk[k]['use'] for k in ind if k in trk)
          and sum(1 for v in ind.values() if v[1] == X86_INS_LEA) == 69 and sm['grade_tracked_extra_by_kind'] == {'addr': 69, 'store': 1})
    f_ind = {im.func_of(k) for k in ind}
    f89 = {g['func'] for g in d['grade_sites']}
    check('V1e 追跡形の関数 102 (連続形 89 + 外 13)', len(f_ind) == 102 and len(f89) == 89 and len(f_ind - f89) == 13 and sorted(f_ind - f89) == sm['grade_tracked_funcs_outside_continuous'],
          f'{len(f_ind)} = 89 + {len(f_ind - f89)}')
    nt, nr = scan_consumers.grade_counts(im, track=False)[1], scan_consumers.grade_counts(im, redef_stop=False)[1]
    check('V5a ネガコン: 追跡を無効にすると連続形の 196 に戻る (≠266)', len(nt) == 196 and len(nt) != 266, f'{len(nt)}')
    check('V5b ネガコン: r2 書換えの打切りを外すと件数が増える (≠266)', len(nr) > 266, f'{len(nr)}')
    c = {o['case'].split()[0]: o for o in json.load(open(os.path.join(HERE, 'results', 'cases.json')))}
    for k in ('A1', 'A2', 'A3', 'A4', 'A5', 'D2'):
        check(f'V3 {k}: ok / flag 0x00 / gradeChar 0x40', c[k]['status'] == 'ok' and c[k]['flag_hex'] == '00' and c[k]['gradeChar_hex'] == '40')
    check('V3 N1 (gradeChar 初期値改変) → gradeChar 0x42', c['N1']['status'] == 'ok' and c['N1']['gradeChar_hex'] == '42')
    check('V3 N2 (jle を nop) → flag bit0 が立つ', c['N2']['status'] == 'ok' and int(c['N2']['flag_hex'], 16) & 1 == 1)
    check('V3 N3 (flag 初期値改変) → flag 0x04', c['N3']['status'] == 'ok' and c['N3']['flag_hex'] == '04')
    import emu_reg
    ind_units = unit_inits_independent(im)
    # unit 表 (.text 内の 16B 刻み {init, fini} ペア) に init 側として載っていること
    import struct
    tbl = {struct.unpack('<Q', im.read(a, 8))[0] for a in range(0x1376be0, 0x1377d00, 16)}
    check('V6a unit 初期化節 = 0x8c5cc0 呼び出し元の独立導出 (集合一致 11 関数)', ind_units == set(emu_reg.UNIT_INITS) and len(ind_units) == 11,
          f'独立 {len(ind_units)} / emu {len(emu_reg.UNIT_INITS)} / diff {sorted(hex(x) for x in ind_units ^ set(emu_reg.UNIT_INITS))}')
    check('V6b 11 関数は全て unit 表 (0x1376be0..) の init 側エントリ', set(emu_reg.UNIT_INITS) <= tbl)
    for k in ('B1', 'B2', 'B3', 'D1', 'D3'):
        o = c[k]
        ph = o['probe_hits']
        check(f'V7 {k}: ok / flag 0x00 / gradeChar 0x40 / 復号 VM 実行 / tier 全 skip (適用 0)',
              o['status'] == 'ok' and o['flag_hex'] == '00' and o['gradeChar_hex'] == '40' and ph['vm_decode'] == 1 and ph['tier_apply'] == 0 and ph['tier_skip'] == 3
              and ph['tier_record_search'] == 0, str(ph))
    check('V7 B1/B2/B3 の復号結果 head は同一 (マシン情報・cl 非依存)', len({c[k]['head_utf16_hex'] for k in ('B1', 'B2', 'B3')}) == 1)
    check('V7 D1/D3/B1 の復号結果 head は互いに異なる (入力に依存して VM が動いている)', len({c[k]['head_utf16_hex'] for k in ('B1', 'D1', 'D3')}) == 3)
    check('V7 A1 (ILRegKey 無し) と D2 (空) は VM を実行しない', c['A1']['probe_hits']['vm_decode'] == 0 and c['D2']['probe_hits']['vm_decode'] == 0)
    check('V7 NB0 (unit 初期化なし) は B1 と同入力で停止', c['NB0']['status'] != 'ok' and c['B1']['status'] == 'ok')
    check('V7 NB1 (VM 入口を ret) → head が B1 と変わる', c['NB1']['status'] == 'ok' and c['NB1']['head_utf16_hex'] != c['B1']['head_utf16_hex'])
    check('V7 NB2 (tier ゲート 4 個を nop) → record 検索・tier 適用に到達し gradeChar が 0x43 になる',
          c['NB2']['status'] == 'ok' and c['NB2']['probe_hits']['tier_apply'] > 0 and c['NB2']['gradeChar_hex'] == '43')
    check('V7 NB3 (ゲート 3 個のみ nop) → record 検索へ届くが tier 適用に届かず gradeChar 0x40',
          c['NB3']['status'] == 'ok' and c['NB3']['probe_hits']['tier_record_search'] > 0 and c['NB3']['probe_hits']['tier_apply'] == 0 and c['NB3']['gradeChar_hex'] == '40')
    jx = subprocess.run(['node', os.path.join(HERE, 'judge_xcheck.mjs')], capture_output=True, text=True)
    jr = json.loads(jx.stdout) if jx.stdout.strip() else []
    check('V7j reader.mjs judge() との突合 (A1/A3/A4/D2/B1/B3/D1/D3 の gradeChar・flag・button が一致)', jx.returncode == 0 and len(jr) == 8, f'{len(jr)} 件 rc={jx.returncode}')
    jn = subprocess.run(['node', os.path.join(HERE, 'judge_xcheck.mjs'), '--neg'], capture_output=True, text=True)
    check('V7k ネガコン: B1 の実測に正規書式の合成平文を judge() へ与えると不一致 (gradeChar 0x41) を検出する', jn.returncode == 0, jn.stdout.strip()[:160])
    print('RESULT', 'FAIL' if fails else 'ALL PASS', fails)
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
