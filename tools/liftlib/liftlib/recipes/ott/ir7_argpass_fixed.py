#!/usr/bin/env python3
"""ir7_argpass.py (M7 PoC): RetDec closure lift の f32 (xmm) 引数失落に対する
最小修正 IR pass (PoC)。tools/m5 / tools/m6 の pass は読取のみで本 pass 自体は
tools/m7/ 配下に独立実装 (import も改変 copy もしない)。

対象 pattern ([P2] f32 引数接続の 3 pattern のうち「pattern B: 呼出 site の xmm drop」):

  (1) target 関数 (既定: OTTProcessor::setParameter = function_180120af0) の
      closure lift 系 IR 内 define は RetDec が signature を 2-arg (obj, index)
      で推定し f32 (xmm2=value) を落とす (pattern A 検出)。さらに
      closure lift (--select-ranges) の define 本体は jump table 分岐を lift
      できず `xor i64 0,0; ret` に退化する (本体退化証跡)。
  (2) 呼出 site (ctor function_18011d400 内の vtable call [rax+0x50] を
      RetDec が direct 化した call) の直前に `call i128 @__asm_movss(i32 %X)`
      (xmm2 読込疑似 call; %X = f32 生 bits) が出るが、その結果は呼出後
      未使用 — つまり xmm2 の値 bits は IR 上に**回収可能**で呼出直後に捨て
      られている (pattern B 検出)。これを 3rd arg として target に渡すよう
      自動書替する (本 pass の最小修正)。
  (3) target 本体は dsm (full lift の disassembly) から jump table の全 case
      を自動抽出し、機械語の store 組 (movss [rcx+D],xmm2 / [r9+D],xmm2 /
      clamp 演算 / flag バイト) を faithful に IR 化して再生成する (pattern A
      の本体退化の代替補償)。新 signature:
      define i64 @TARGET(i64 obj, i64 index, i64 xmm2bits)

制約 (PoC スコープ):
  - dsm の case slice が想定テンプレート (TAIL_AB / TAIL_IDX / CLAMP / FLAG /
    RET0) に分類できない場合は assert で落とす (無黙って変えない)。
  - rip 相対定数は linear memory 実データ (m6_data_install 後の 0x30000000+RVA)
    からの生 bits load で参照 (@global_var_ 定義の有無に非依存:
    mul 定数 0x301fee90 は ir6_gdata 400 件の対象外のため)。

使い方:
  python3 ir7_argpass.py IN_LL OUT_LL [--dsm DSM] [--report JSON]
    [--target function_180120af0] [--tail function_18011de50]
"""
import argparse
import json
import os
import re
import sys

TARGET_DEFAULT = 'function_180120af0'
TAIL_DEFAULT = 'function_18011de50'
SHIFT_BASE = 0x30000000     # ir6_shift.py 後の DLL VA base
IMAGE_BASE = 0x180000000

INSTR_RE = re.compile(r'^(0x[0-9a-f]+):\s+([0-9a-f][0-9a-f](?: [0-9a-f][0-9a-f])*)\s+(.*)$')
FUNC_HDR_RE = re.compile(r'^; function: (\S+) at (0x[0-9a-f]+) -- (0x[0-9a-f]+)')
DATA_HDR_RE = re.compile(r'^; data inside code section at (0x[0-9a-f]+) -- (0x[0-9a-f]+)')


# ----------------------------------------------------------------- dsm parse

def parse_dsm_for_function(path, fname):
  """dsm から fname の実体命令列と全 data block bytes を返す.

  return (insns, data_bytes, (f_start, f_end))
    insns: list[(addr:int, nbytes:int, text:str)] アドレス順
    data_bytes: dict addr -> byte (data-in-code block 全体)
  """
  insns = []
  data_bytes = {}
  hdr = None
  cur_key = None
  with open(path, errors='replace') as f:
    for line in f:
      m = FUNC_HDR_RE.match(line)
      if m:
        cur_key = ('func', m.group(1))
        if m.group(1) == fname:
          hdr = (int(m.group(2), 16), int(m.group(3), 16))
        continue
      m = DATA_HDR_RE.match(line)
      if m:
        cur_key = ('data', int(m.group(1), 16), int(m.group(2), 16))
        continue
      if cur_key and cur_key[0] == 'data':
        mm = re.match(r'^0x([0-9a-f]+):\s+([0-9a-f ]+)\|.*\|?\s*$', line.rstrip('\n'))
        if mm:
          a0 = int(mm.group(1), 16)
          for i, b in enumerate(re.findall(r'[0-9a-f]{2}', mm.group(2))):
            data_bytes[a0 + i] = int(b, 16)
        else:
          cur_key = None
        continue
      p = INSTR_RE.match(line)
      if p:
        cur_key = ('ins',)
        a0 = int(p.group(1), 16)
        for k, b in enumerate(re.findall(r'[0-9a-f]{2}', p.group(2))):
          # 機械語 raw bytes も byte map へ (data block 切出れずの dsm 破綻区間からの回収)
          data_bytes.setdefault(a0 + k, int(b, 16))
        insns.append((a0, 1, p.group(3)))
  if hdr is None:
    raise AssertionError(f'dsm: function {fname} not found')
  f_start, f_end = hdr
  fi = sorted([x for x in insns if f_start <= x[0] < f_end], key=lambda x: x[0])
  return fi, data_bytes, (f_start, f_end)


def extract_cases(insns, data_bytes):
  """jump table dispatch の case slice を抽出.

  x64 前提 shape (setParameter 0x180120af0 実測):
    cmp edx, 0x13
    ja  default
    lea r10, [rip - X]                    ; r10 = rip + disp = IMAGE_BASE
    movsxd rax, edx
    mov r8d, dword ptr [r10 + rax*4 + TBL]
    add r8, r10
    jmp r8
  """
  addr_map = {a: t for a, n, t in insns}
  ordered = sorted(addr_map)
  ncases = None
  default_va = None
  for i, (a, n, t) in enumerate(insns):
    m = re.match(r'cmp edx, (0x[0-9a-f]+)\s*$', t)
    if m and i + 1 < len(insns):
      nxt = ordered[ordered.index(a) + 1]
      mj = re.match(r'ja (0x[0-9a-f]+)', addr_map[nxt])
      if mj:
        ncases = int(m.group(1), 16) + 1
        default_va = int(mj.group(1), 16)
        break
  if ncases is None:
    raise AssertionError('dsm: cmp edx / ja dispatch head が見付からない')
  tbl_disp = None
  r10 = None
  for i, (a, n, t) in enumerate(insns):
    m = re.match(r'mov r8d, dword ptr \[r10 \+ rax\*4 \+ (0x[0-9a-f]+)\]\s*$', t)
    if m:
      tbl_disp = int(m.group(1), 16)
    m2 = re.match(r'lea r10, \[rip ([+-]) (0x[0-9a-f]+)\]\s*$', t)
    if m2:
      nxt = ordered[ordered.index(a) + 1]
      disp = int(m2.group(2), 16)
      if m2.group(1) == '-':
        disp = -disp
      r10_calc = nxt + disp
      if r10_calc == IMAGE_BASE or r10 is None:
        r10 = r10_calc
  if tbl_disp is None or r10 is None:
    raise AssertionError('dsm: jump table 読込命令が見付からない')
  tbl_addr = r10 + tbl_disp
  entries = []
  for i in range(ncases):
    b = [data_bytes.get(tbl_addr + i * 4 + k) for k in range(4)]
    if any(v is None for v in b):
      raise AssertionError(f'dsm: table entry {i} の bytes 取得不能 (tbl=0x{tbl_addr:x})')
    off = b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24)
    entries.append(r10 + off)
  uniq = sorted(set(entries))
  slices = {}
  for i, tg in enumerate(entries):
    nxt2 = [e for e in uniq if e > tg]
    end = nxt2[0] if nxt2 else (max(a for a, _, _ in insns) + 1)
    slices[i] = [(a, n, t) for a, n, t in insns if tg <= a < end]
  return slices, {'ncases': ncases, 'tbl_addr': tbl_addr, 'r10': r10,
                  'default_va': default_va, 'entries': entries}


# ------------------------------------------------------- case slice → IR

class CaseSynth:
  """case 1 つを IR block に変換 (想定テンプレート外は assert)。

  入力仮定 (合成 define 内):
    %arg1 = obj (rcx)  %ap_idx = i32 index  %ap_f = f32 value
    %ap_v = i32 bits   %ap_r9 = i64 chunk base (r9)
  """

  def __init__(self, tail_name, shift_base, no_tail=False):
    self.no_tail = no_tail
    self.tail = tail_name
    self.tail_va = int(tail_name.rsplit('_', 1)[-1], 16)
    self.shift = shift_base
    self.ctr = 0

  def fresh(self, tag='x'):
    self.ctr += 1
    return f'%ap{self.ctr:02d}{tag}'

  # ---- helpers

  def abs_store32(self, base, disp, val):
    t1 = self.fresh('a')
    lines = []
    if disp:
      lines.append(f'  {t1} = add i64 {base}, {disp}')
      dst = t1
    else:
      dst = base
    p = self.fresh('p')
    lines.append(f'  {p} = inttoptr i64 {dst} to ptr')
    lines.append(f'  store i32 {val}, ptr {p}, align 4')
    return lines

  def idx_store32(self, base, disp, val, idx64):
    # M8 修正 (tools/m7/REPORT.md §3-(d) 5 / §3-(b)): x64 の
    #   movss [rcx + rax*4 + D], xmm2  = base + (idx << 2) + D
    # であり, scale 前に disp を加算する旧実装 ((idx + D) << 2) は
    # idx != 0 で member mirror store 先がずれる。shl を先に実施して
    # base + shl(idx,2) + D の順に再構成した正本形。
    lines = []
    t1 = self.fresh('s')
    lines.append(f'  {t1} = shl i64 {idx64}, 2')
    t2 = self.fresh('a')
    lines.append(f'  {t2} = add i64 {base}, {t1}')
    if disp:
      t3 = self.fresh('d')
      lines.append(f'  {t3} = add i64 {t2}, {disp}')
      dst = t3
    else:
      dst = t2
    p = self.fresh('p')
    lines.append(f'  {p} = inttoptr i64 {dst} to ptr')
    lines.append(f'  store i32 {val}, ptr {p}, align 4')
    return lines

  def abs_store8(self, base, disp, val):
    t1 = self.fresh('b')
    lines = []
    if disp:
      lines.append(f'  {t1} = add i64 {base}, {disp}')
      dst = t1
    else:
      dst = base
    p = self.fresh('p')
    lines.append(f'  {p} = inttoptr i64 {dst} to ptr')
    lines.append(f'  store i8 {val}, ptr {p}, align 1')
    return lines

  def idx_store8(self, disp, val, idx64):
    lines = []
    if disp:
      t = self.fresh('d')
      lines.append(f'  {t} = add i64 {idx64}, {disp}')
      add_in = t
    else:
      add_in = idx64
    t1 = self.fresh('b')
    lines.append(f'  {t1} = add i64 %arg1, {add_in}')
    p = self.fresh('p')
    lines.append(f'  {p} = inttoptr i64 {t1} to ptr')
    lines.append(f'  store i8 {val}, ptr {p}, align 1')
    return lines

  def load_const(self, rip_addr):
    addr = self.shift + (rip_addr - IMAGE_BASE)
    p = self.fresh('c')
    v = self.fresh('cI')
    f = self.fresh('cF')
    return [
      f'  {p} = inttoptr i64 {addr} to ptr',
      f'  {v} = load i32, ptr {p}, align 1',
      f'  {f} = bitcast i32 {v} to float',
    ]

  def tailcall(self):
    res = self.fresh('tr')
    if self.no_tail:
      return ['  ret i64 0']
    return [f'  {res} = tail call i64 @{self.tail}(i64 %arg1)',
            f'  ret i64 {res}']

  # ---- main case classifier

  def synth(self, case_no, seq):
    texts = [(a, n, t) for a, n, t in seq]
    txts = [t for _, _, t in texts]
    kinds = [t.split()[0] for t in txts if t]
    # (a) TAIL_AB / TAIL_IDX / RET0
    if kinds == ['movss', 'movss', 'jmp']:
      jmp = txts[2]
      m = re.match(r'jmp (0x[0-9a-f]+)', jmp)
      assert int(m.group(1), 16) == self.tail_va, f'tail jmp 先が {self.tail} でない: {jmp}'
      rc_ok = re.match(r'movss dword ptr \[rcx(?: \+ (0x[0-9a-f]+|[0-9a-f]+))?\], xmm2', txts[0])
      r9_ok = re.match(r'movss dword ptr \[r9(?: \+ (0x[0-9a-f]+|[0-9a-f]+))?\], xmm2', txts[1])
      assert rc_ok and r9_ok, f'TAIL_AB store 形式: {txts[:2]}'
      d1 = int(rc_ok.group(1), 16) if rc_ok.group(1) else 0
      d2 = int(r9_ok.group(1), 16) if r9_ok.group(1) else 0
      lines = self.abs_store32('%arg1', d1, '%ap_v') + self.abs_store32('%ap_r9', d2, '%ap_v')
      lines += self.tailcall()
      return (f'TAIL_AB(rcx+{hex(d1)},r9+{hex(d2)})', lines)
    # (d) FLAG (xorps で 0.0 との ucomiss → flag byte store) — case slice は分岐
    #     をブレイクしないため jp/jne 双方の store を 1 つに統合
    #     (movsxd r8, edx で始まる flag 系 case もあるので xorps 先判定)
    if 'xorps' in kinds:
      lines, notes = self._synth_flag(seq)
      return (notes, lines)
    # (b) TAIL_IDX (movsxd の case; jump table からの共通 slice)
    if kinds and kinds[0] == 'movsxd':
      rc_idx = [re.match(r'movss dword ptr \[rcx \+ rax\*4 \+ (0x[0-9a-f]+|[0-9a-f]+)\], xmm2', t) for t in txts
                if re.match(r'movss dword ptr \[rcx \+ rax\*4 \+ (0x[0-9a-f]+|[0-9a-f]+)\], xmm2', t)]
      r9_idx = [re.match(r'movss dword ptr \[r9 \+ rax\*4\], xmm2', t) for t in txts
                if re.match(r'movss dword ptr \[r9 \+ rax\*4\], xmm2', t)]
      if rc_idx and r9_idx:
        ix = self.fresh('ix')
        lines = [f'  {ix} = sext i32 %ap_idx to i64']
        d = int(rc_idx[0].group(1), 16)
        lines += self.idx_store32('%arg1', d, '%ap_v', ix)
        lines += self.idx_store32('%ap_r9', 0, '%ap_v', ix)
        if any(t.startswith('addss') for t in txts):
          # addss xmm2, xmm2 → 別 slot の2乗系 store (idx+0xc)
          rc_last = rc_idx[-1]
          d2 = int(rc_last.group(1), 16)
          dm = self.fresh('dv')
          lines.append(f'  {dm} = fadd float %ap_f, %ap_f')
          db = self.fresh('dvb')
          lines.append(f'  {db} = bitcast float {dm} to i32')
          lines += self.idx_store32('%arg1', d2, db, ix)
          lines.append('  ret i64 0')
          return (f'TAIL_IDX_x2(rcx+idx*4+{hex(d)},r9+idx*4,x2@{hex(d2)})', lines)
        lines += self.tailcall()
        return (f'TAIL_IDX(rcx+idx*4+{hex(d)},r9+idx*4)', lines)
      raise AssertionError(f'case {case_no}: movsxd slice で store 組解析不可: {txts}')
    # (c) CLAMP (comiss で定数分岐; jb → (v-A)*B+C, fall → v*2)
    if 'comiss' in kinds:
      lines, notes = self._synth_clamp(seq)
      return (notes, lines)
    # (e) bare ret (default)
    if kinds == ['ret']:
      return ('RET0', ['  ret i64 0'])
    raise AssertionError(f'case {case_no} が想定テンプレートに合致しない: kinds={kinds} texts={txts}')

  def _synth_clamp(self, seq):
    texts = [t for _, _, t in seq]
    addrs = [a for a, _, _ in seq]
    ins_end = {}
    for i, a in enumerate(addrs):
      ins_end[a] = addrs[i + 1] if i + 1 < len(addrs) else a
    i = 0
    A_addr = None
    vstores = []
    while i < len(seq):
      a, n, t = seq[i]
      m = re.match(r'movss xmm1, dword ptr \[rip \+ (0x[0-9a-f]+)\]\s*$', t)
      if m:
        A_addr = ins_end[a] + int(m.group(1), 16)
        i += 1
        continue
      mm = re.match(r'movss dword ptr \[(rcx|r9)(?: \+ (0x[0-9a-f]+|[0-9a-f]+))?\], xmm2\s*$', t)
      if mm:
        vstores.append((mm.group(1), int(mm.group(2), 16) if mm.group(2) else 0))
        i += 1
        continue
      if re.match(r'movss xmm0, dword ptr \[rcx', t):
        i += 1
        continue
      if t.startswith('comiss'):
        i += 1
        break
      raise AssertionError(f'CLAMP 先頭走査で予想外: {t!r}')
    m = re.match(r'(j[a-z]+) (0x[0-9a-f]+)', seq[i][2])
    assert m and m.group(1) == 'jb', f'CLAMP jb 以外 unsupported: {seq[i][2]}'
    jtgt = int(m.group(2), 16)
    fall = seq[i + 1][0]
    st2 = None
    B_addr = None
    C_addr = None
    for a, n, t in seq:
      if a < fall:
        continue
      if re.match(r'addss xmm0, xmm0', t):
        continue
      if re.match(r'subss xmm0, xmm1', t):
        continue
      m2 = re.match(r'mulss xmm0, dword ptr \[rip \+ (0x[0-9a-f]+)\]\s*$', t)
      if m2:
        B_addr = ins_end[a] + int(m2.group(1), 16)
        continue
      m3 = re.match(r'addss xmm0, dword ptr \[rip \+ (0x[0-9a-f]+)\]\s*$', t)
      if m3:
        C_addr = ins_end[a] + int(m3.group(1), 16)
        continue
      mm4 = re.match(r'movss dword ptr \[(?:rcx|r9)(?: \+ (0x[0-9a-f]+|[0-9a-f]+))?\], xmm0\s*$', t)
      if mm4:
        st2 = int(mm4.group(1), 16) if mm4.group(1) else 0
        continue
      if t.strip() == 'ret':
        continue
      raise AssertionError(f'CLAMP path 予想外: {t!r}')
    assert A_addr and B_addr and C_addr and st2 is not None, 'CLAMP 構成要素不足'
    lines = []
    for reg, d in vstores:
      base = '%arg1' if reg == 'rcx' else '%ap_r9'
      lines += self.abs_store32(base, d, '%ap_v')
    lines += self.load_const(A_addr)
    A = lines[-1].split()[0]
    cmp_v = self.fresh('gt')
    b1 = self.fresh('b1')
    b2 = self.fresh('b2')
    lines.append(f'  {cmp_v} = fcmp ugt float %ap_f, {A}')
    lines.append(f'  br i1 {cmp_v}, label {b1}, label {b2}')
    lines.append(b1.lstrip('%') + ':')
    lines += self.load_const(B_addr)
    B = lines[-1].split()[0]
    lines += self.load_const(C_addr)
    C = lines[-1].split()[0]
    t1 = self.fresh('t')
    lines.append(f'  {t1} = fsub float %ap_f, {A}')
    t2 = self.fresh('t')
    lines.append(f'  {t2} = fmul float {t1}, {B}')
    t3 = self.fresh('t')
    lines.append(f'  {t3} = fadd float {t2}, {C}')
    t4 = self.fresh('t')
    lines.append(f'  {t4} = bitcast float {t3} to i32')
    lines += self.abs_store32('%arg1', st2, t4)
    lines.append('  ret i64 0')
    lines.append(b2.lstrip('%') + ':')
    t5 = self.fresh('t')
    lines.append(f'  {t5} = fadd float %ap_f, %ap_f')
    t6 = self.fresh('t')
    lines.append(f'  {t6} = bitcast float {t5} to i32')
    lines += self.abs_store32('%arg1', st2, t6)
    lines.append('  ret i64 0')
    notes = f'CLAMP(A@{hex(A_addr)},B@{hex(B_addr)},C@{hex(C_addr)},st@{hex(st2)})'
    return lines, notes

  def _synth_flag(self, seq):
    """flag テンプレート: jp / jne が同一点に分岐 (NaN と non-zero で flag=1)
    で, fall に flag=0。slice の branch 構造を 1 直線に圧縮 (flag byte の値は
    (unordered || v != 0) ? 1 : 0)。
    """
    vstores = []
    fstores = []
    uses_jmp = False
    for a, n, t in seq:
      m = re.match(r'movss dword ptr \[r9 \+ r\w+\*4\], xmm2\s*$', t)
      if m:
        vstores.append(('idx9', 0))
        continue
      m = re.match(r'movss dword ptr \[r9(?: \+ (0x[0-9a-f]+|[0-9a-f]+))?\], xmm2\s*$', t)
      if m:
        vstores.append(('r9', int(m.group(1), 16) if m.group(1) else 0))
        continue
      m = re.match(r'movss dword ptr \[rcx(?: \+ (0x[0-9a-f]+|[0-9a-f]+))?\], xmm2\s*$', t)
      if m:
        vstores.append(('obj', int(m.group(1), 16) if m.group(1) else 0))
        continue
      m = re.match(r'mov byte ptr \[(rcx|r9) \+ (0x[0-9a-f]+|[0-9a-f]+)\], a\w\s*$', t)
      if m:
        fstores.append(('abs', m.group(1), int(m.group(2), 16)))
        continue
      m = re.match(r'mov byte ptr \[r\w+ \+ rcx \+ (0x[0-9a-f]+|[0-9a-f]+)\], a\w\s*$', t)
      if m:
        fstores.append(('idx', None, int(m.group(1), 16)))
        continue
      if t.startswith('movsxd'):
        continue
      if t.startswith('xorps') or t.startswith('ucomiss'):
        continue
      if re.match(r'j(p|ne) 0x', t):
        continue
      if re.match(r'mov al, [01]', t):
        continue
      if re.match(r'xor eax, eax', t):
        continue
      m = re.match(r'jmp (0x[0-9a-f]+)', t)
      if m:
        assert int(m.group(1), 16) == self.tail_va, f'FLAG tail jmp 非 {self.tail}: {t}'
        uses_jmp = True
        continue
      if t.strip() == 'ret':
        continue
      raise AssertionError(f'FLAG 想定外 ins: {t!r}')
    assert fstores, 'FLAG: flag byte store が見付からない'
    # jp/jne 両経路の flag store は同一 slot の重複 → 順序保持で dedupe
    fstores = list(dict.fromkeys(fstores))
    vstores = list(dict.fromkeys(vstores))
    have_idx = (any(k == 'idx9' for k, _ in vstores)
                or any(k == 'idx' for k, _, _ in fstores))
    lines = []
    if have_idx:
      ixn = self.fresh('ix')
      lines.append(f'  {ixn} = sext i32 %ap_idx to i64')
    for kind, d in vstores:
      if kind == 'idx9':
        lines += self.idx_store32('%ap_r9', 0, '%ap_v', ixn)
      elif kind == 'r9':
        lines += self.abs_store32('%ap_r9', d, '%ap_v')
      else:
        lines += self.abs_store32('%arg1', d, '%ap_v')
    uno = self.fresh('u')
    ne = self.fresh('n')
    fl = self.fresh('f')
    fb = self.fresh('fb')
    lines.append(f'  {uno} = fcmp uno float %ap_f, 0.000000e+00')
    lines.append(f'  {ne} = fcmp une float %ap_f, 0.000000e+00')
    lines.append(f'  {fl} = or i1 {uno}, {ne}')
    lines.append(f'  {fb} = zext i1 {fl} to i8')
    for kind, reg, d in fstores:
      if kind == 'abs':
        base = '%arg1' if reg == 'rcx' else '%ap_r9'
        lines += self.abs_store8(base, d, fb)
      else:
        lines += self.idx_store8(d, fb, ixn)
    if uses_jmp:
      lines += self.tailcall()
    else:
      lines.append('  ret i64 0')
    notes = ('FLAG(v=' + ','.join(f'{k}{hex(d)}' for k, d in vstores)
             + ',f=' + ','.join(f'idx{hex(d)}' if kind == 'idx' else f'{kind}@{hex(d)}'
                                for kind, _, d in fstores)
             + (',tail' if uses_jmp else '') + ')')
    return lines, notes


# --------------------------------------------------------------- main IR ops

def find_define_block(lines, name):
  """define … @name( で始まり次 top-level で終わる block 区間を返す"""
  start = None
  for i, l in enumerate(lines):
    if start is None:
      if l.startswith('define ') and f'@{name}(' in l:
        start = i
      continue
    if (l.startswith('define ') or l.startswith('declare ') or
        l.startswith('uselistorder') or (l and l[0] == '@')):
      return start, i
  return (start, len(lines)) if start is not None else None


def main():
  ap = argparse.ArgumentParser()
  ap.add_argument('src')
  ap.add_argument('dst')
  ap.add_argument('--dsm', default=None)
  ap.add_argument('--report', default=None)
  ap.add_argument('--target', default=TARGET_DEFAULT)
  ap.add_argument('--tail', default=TAIL_DEFAULT)
  ap.add_argument('--shift', type=lambda s: int(s, 0), default=SHIFT_BASE)
  ap.add_argument('--no-tail', action='store_true', help='診断用: tail call 削除 ret (SEO diagnostics)')
  args = ap.parse_args()

  if args.dsm is None:
    args.dsm = os.path.join('work', 'full_t1.drc.dsm')

  rep = {'target': args.target, 'tail': args.tail, 'patterns': {}, 'synth': {}}
  zctr = [0]

  lines = open(args.src).read().splitlines()

  # ---- (1) pattern A: target define の退化・2arg 化を検出
  blk = find_define_block(lines, args.target)
  assert blk, f'target define ({args.target}) が IR に無い'
  s, e = blk
  header = lines[s]
  body = lines[s + 1:e]
  insns = [l for l in body if l.startswith('  ') and l.strip()]
  degenerate = (len(insns) <= 4 and any('xor i64 0, 0' in l for l in insns)
                and any(re.match(r'^  ret ', l) for l in insns))
  assert '%arg2' in header, f'target は想定 (…, %arg2) でない: {header}'
  rep['patterns']['A'] = {
    'target_define': header,
    'body_insn_count': len(insns),
    'body_degenerate_ret0': bool(degenerate),
    'conclusion': 'pattern A 成立: RetDec closure lift は signature を 2-arg 推定 + '
                  '本体を jump table dispatch の lift 失敗で ret0 退化。xmm 引数は '
                  'closure IR 上に存在しない。',
  }

  # ---- (2) pattern B: 呼出 site 書替 (xmm2 bits を 3rd arg 化)
  movss_re = re.compile(r'^\s*(%[\w.\-]+) = call i128 @__asm_movss\(i32 (%[\w.\-]+)\)\s*$')
  call_re = re.compile(r'^\s*(%[\w.\-]+) = call i64 @' + re.escape(args.target) + r'\((.*?)\)\s*$')
  out = []
  sites = 0
  patched = 0
  last_movss_src = None
  for l in lines:
    mc = call_re.match(l)
    if mc:
      sites += 1
      cur = [x.strip() for x in mc.group(2).split(',')]
      if len(cur) == 2 and last_movss_src is not None:
        z = f'%apz{zctr[0]}'
        zctr[0] += 1
        out.append(f'  {z} = zext i32 {last_movss_src} to i64')
        new_args = ', '.join(cur + ['i64 ' + z])
        out.append(re.sub(r'@' + re.escape(args.target) + r'\(.*\)$',
                          f'@{args.target}({new_args})', l))
        patched += 1
        last_movss_src = None
        continue
      last_movss_src = None
    mv = movss_re.match(l)
    if mv:
      last_movss_src = mv.group(2)
      out.append(l)
      continue
    if (l.startswith('dec_label_pc_') or l.startswith('define ')
        or l.startswith('declare ')):
      last_movss_src = None
    out.append(l)
  lines = out
  assert sites > 0 and patched > 0, 'pattern B 候補 call site が見付からない'
  rep['patterns']['B'] = {
    'callsites_of_target': sites,
    'callsites_patched_3arg': patched,
    'mechanism': '呼出直前の call i128 @__asm_movss(i32 %X) の %X (f32 bits) が呼出後未使用 → '
                 'zext i32→i64 で 3rd arg 化。xmm2 値 bits は IR 上に回収可能 (pattern B 成立)。',
  }

  # ---- (3) dsm から target 本体 (全 case) を抽出して再生成
  blk = find_define_block(lines, args.target)
  s, e = blk
  insns, data_bytes, rng = parse_dsm_for_function(args.dsm, args.target)
  slices, jinfo = extract_cases(insns, data_bytes)
  synth = CaseSynth(args.tail, args.shift, no_tail=args.no_tail)
  rep['synth']['jump_table'] = {
    'addr': hex(jinfo['tbl_addr']),
    'ncases': jinfo['ncases'],
    'entries': [hex(x) for x in jinfo['entries']],
  }
  case_labels = [f'%apcase{i:02d}' for i in range(jinfo['ncases'])]
  kinds = []
  blocks = []
  for i in range(jinfo['ncases']):
    kind, body_lines = synth.synth(i, slices[i])
    kinds.append(kind)
    blocks.append((case_labels[i], body_lines))
  rep['synth']['case_kinds'] = kinds

  # ---- (4) define 合成 + splice
  new_def = [f'define i64 @{args.target}(i64 %arg1, i64 %arg2, i64 %arg3) local_unnamed_addr {{']
  new_def += [
    'dec_label_pc_180120af0:',
    '  %ap_v = trunc i64 %arg3 to i32',
    '  %ap_f = bitcast i32 %ap_v to float',
    '  %ap_idx = trunc i64 %arg2 to i32',
    '  %apr0 = add i64 %arg1, 40',
    '  %apr1 = inttoptr i64 %apr0 to ptr',
    '  %apr2 = load i32, ptr %apr1, align 4',
    '  %apr3 = sext i32 %apr2 to i64',
    '  %apr4 = mul i64 %apr3, 108',
    '  %apr5 = add i64 %arg1, 312',
    '  %apr6 = inttoptr i64 %apr5 to ptr',
    '  %apr7 = load i64, ptr %apr6, align 8',
    '  %ap_r9 = add i64 %apr7, %apr4',
  ]
  tbl = '\n    '.join(f'i32 {i}, label {c}' for i, c in enumerate(case_labels))
  new_def.append(f'  switch i32 %ap_idx, label %apdefault [ {tbl} ]')
  for tag, body_lines in blocks:
    new_def.append(tag.lstrip('%') + ':')
    new_def += body_lines
  new_def.append('apdefault:')
  new_def.append('  ret i64 0')
  new_def.append('}')
  out = lines[:s] + new_def + lines[e:]

  with open(args.dst, 'w') as f:
    f.write('\n'.join(out) + '\n')
  rep['synth']['out_lines'] = len(out)
  if args.report:
    os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
    with open(args.report, 'w') as f:
      json.dump(rep, f, ensure_ascii=False, indent=2)
  print(f"[ir7_argpass] target={args.target} patternA(degenerate={degenerate}) "
        f"callsites={sites} patched={patched} cases={jinfo['ncases']} -> {args.dst}")
  return 0


if __name__ == '__main__':
  sys.exit(main())
