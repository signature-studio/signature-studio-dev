#!/usr/bin/env python3
"""ir9_bootstraps.py (M9): 起動経路 + CRT 数学系の破れ修復 pass.

入力: tools/m8/work/ott_argpass8.ll (m7/m8 鎖の直後)、dsm (突合・const 確認用)。
出力: tools/m9/work/ott_m9.ll (emcc 入力)。

修復群:
  [F3] resume (function_180120800) — 仮想 call [rax+0xf8] (=getSR = obj+0x18) と
       comiss/fallback (44000 → 44100) branch が lift 脱落 → SR=0 / ramp gain 全部 1.0
       (probe 実測)。→ 本体を @m9_resume_reinit (C port) へ置換
  [F4] function_180126040 — (rcx, xmm1=f0, xmm2=Q) 2 xmm arg 脱落 →
       3-arg define (m9_svf_reset C port) へ差替
  [F5] ctor 内 gate box vcall 群 ([rax+0x38]=126370 / [rax+0x88]=1263e0 /
       [rax+0x80]=126340) → 1 個の @m9_gbox_ctor_setup direct call へ統合
       (anchor = ctor defaults setParameter loop 直前; dsm 順序 C port 内で保持),
       126130 内 1263f0/1264e0 直接 call に f64/xmm const arg thread (IR 即値 bits)。
  [F6] 1801b4220 (exp) / 1801b4900 (log) / 1801ba860 (tan) define を C stub 呼出へ
       差替し全 0-arg 呼出 site を「直前 __asm_{movsd,mulsd,addsd,subsd,divsd}」dest で
       1-arg 化 (xmm0 thread)。
"""
import argparse
import json
import os
import re
import sys

SD_OPS = ('movsd', 'mulsd', 'addsd', 'subsd', 'divsd')

CRT_SWTCH = {
    'function_1801b4220': 'm9_dexp',     # exp(double) — dB→linear (final loop)
    'function_1801b4900': 'm9_dlog',     # log(double) — identity probe で dsm と突合する
    'function_1801ba860': 'm9_dtan',     # tan(double) → f32 vcvtsd2ss 戻値 [F4]
}

# f64 bits 即値 (実行モジュール rdata 実測, m9_dumpconsts.mjs)
D64_44100 = 0x40E5888000000000   # 44100.0
D64_100 = 0x4059000000000000     # 100.0
D64_10 = 0x4024000000000000      # 10.0
D64_1E6 = 0x412E848000000000     # 1000000.0
D64_5 = 0x4014000000000000      # 5.0 (1264e0 xmm1 const @0x1801f3d20 実測)


def fn_range(lines, fname):
  hdr = re.compile(r'^define [^@]*@' + re.escape(fname) + r'\(')
  for i, l in enumerate(lines):
    if hdr.match(l):
      j = i
      while j < len(lines) and not lines[j].startswith('}'):
        j += 1
      return i, j
  return None, None


def fix_declares(lines, name, argty, retty='i64'):
  pat = re.compile(r'^declare \S+ @' + re.escape(name) + r'\(')
  out = []
  for l in lines:
    if pat.match(l):
      l = f'declare {retty} @{name}(' + ', '.join(argty) + ') local_unnamed_addr'
    out.append(l)
  return out


# ================================================================ [F6] CRT

def crt_patch(lines, rep):
  gidx = [0]
  for name, cstub in CRT_SWTCH.items():
    di, dj = fn_range(lines, name)
    if di is None:
      raise AssertionError(f'{name}: define 未検出')
    m = re.match(r'^define [^(]*@' + re.escape(name) + r'\(([^)]*)\)', lines[di])
    assert m, name
    old_sig = m.group(1).strip()
    if old_sig != '' and old_sig != 'i64 %arg1':
      rep['crt'][name] = f'already-arg ({old_sig}), skip'
      continue
    call_re = re.compile(r'^\s*(?:%[\w.\-]+ = )?call (i64|void|i128) @' + re.escape(name) + r'\(\)\s*$')
    out, i, n_sites = [], 0, 0
    gbase = gidx[0]
    while i < len(lines):
      l = lines[i]
      m2 = call_re.match(l)
      if not m2:
        out.append(l)
        i += 1
        continue
      arg_op, hit = None, len(out)
      for j in range(len(out) - 1, max(len(out) - 90, -1), -1):
        mm = re.match(r'^\s*(%[\w.\-]+) = call i128 @__asm_(' + '|'.join(SD_OPS) + r')\((.*)\)\s*$', out[j])
        if mm:
          arg_op, hit = mm.group(1), j
          break
      if arg_op is None:
        # フォールバック (CAB-239): P1 region が生成する正規名 (接尾付き) も探す。
        # 無接尾で見つかる場合 (legacy) は上の経路と同じ結果ゆえ出力は不変。
        for j in range(len(out) - 1, max(len(out) - 90, -1), -1):
          mm = re.match(r'^\s*(%[\w.\-]+) = call i128 @__asm_(' + '|'.join(SD_OPS) + r')(?:__[a-z0-9]+|\.\d+|__\d+)?\((.*)\)\s*$', out[j])
          if mm:
            arg_op, hit = mm.group(1), j
            break
      if arg_op is None:
        ctx = ' // '.join(x.strip() for x in out[-5:])
        raise AssertionError(f'{name}: idx {i} 呼出直前 __asm_{"|".join(SD_OPS)} なし (thread 先未特定) ctx=[{ctx}]')
      tz = f'%crz{gbase + n_sites:05d}'
      out.append(f'  {tz} = trunc i128 {arg_op} to i64      ; [F6] xmm0 arg thread (ir9)')
      m3 = re.match(r'^\s*(%[\w.\-]+ = )?call (i64|void|i128) @' + re.escape(name) + r'\(\)\s*$', l)
      if m3.group(1):
        out.append(f'  {m3.group(1)}call {m3.group(2)} @{cstub}(i64 {tz})')
      else:
        out.append(f'  call {m3.group(2)} @{cstub}(i64 {tz})')
      n_sites += 1
      i += 1
    lines = out
    di, dj = fn_range(lines, name)
    body_new = [
      f'define i64 @{name}(i64 %argx) local_unnamed_addr {{',
      'dec_label_pc_crtsw:',
      f'  %b = call i64 @{cstub}(i64 %argx)',
      '  ret i64 %b',
      '}',
    ]
    lines = lines[:di] + body_new + lines[dj + 1:]
    lines = fix_declares(lines, name, ['i64'])
    rep['crt'][name] = f'threaded={n_sites}, stub={cstub}'
    gidx[0] += n_sites
  return lines


# ================================================================ [F4] SVF cut set

def svf_coeff_reset(lines, rep):
  body = [
    'define i64 @function_180126040(i64 %arg1, i64 %argf0b, i64 %argqb) local_unnamed_addr {',
    'dec_label_pc_180126040:',
    '  ; ir9 [F4] 忠実 C port (dsm 0x180126040..bf; tan は m9_dtan 戻値 f32)',
    '  call void @m9_svf_reset(i64 %arg1, i64 %argf0b, i64 %argqb)',
    '  ret i64 0',
    '}',
  ]
  di, dj = fn_range(lines, 'function_180126040')
  if di is None:
    raise AssertionError('function_180126040 define 未検出')
  lines = lines[:di] + body + lines[dj + 1:]
  lines = fix_declares(lines, 'function_180126040', ['i64', 'i64', 'i64'])
  rep['svf126040'] = '3-arg + C port (m9_svf_reset)'
  return lines


# ================================================================ [F5] gate box

def fix_126130(lines, rep):
  p = 'function_180126130'
  di, dj = fn_range(lines, p)
  if di is None:
    raise AssertionError('126130 define 未検出')
  seg = lines[di:dj + 1]
  dsv = []
  for l in seg:
    mm = re.match(r'^\s*(%[\w.\-]+) = call i128 @__asm_movsd\(i64 (\d+)\)\s*$', l)
    if mm:
      dsv.append((mm.group(1), int(mm.group(2))))
  def take(bits):
    for v, b in dsv:
      if b == bits:
        return v
    raise AssertionError(f'126130 内 bits {hex(bits)} 即値 movsd なし')
  v44100 = take(D64_44100)
  v100 = take(D64_100)
  v10 = take(D64_10)
  v5 = take(D64_5)
  rep['126130_fix'] = []
  out = []
  seen = 0
  for l in seg:
    lm = l.strip()
    if '@function_1801263f0(i64 %arg1)' in lm:
      rep['126130_fix'].append('1263f0 4-arg 化 (xmm1=10.0, xmm2=100.0, xmm3=44100.0)')
      mcall = re.match(r'^(\s*)(%[\w.\-]+ = )?call (i64|i128|void) @function_1801263f0\(i64 %arg1\)\s*$', l)
      assert mcall, f'1263f0 呼出形想定外: {l}'
      d = mcall.group(2) or ''
      out.append(f'{mcall.group(1)}{d}call i64 @function_1801263f0(i64 %arg1, i64 {D64_10}, i64 {D64_100}, i64 {D64_44100})')
      seen += 1
      continue
    if '@function_1801264e0(' in lm:
      rep['126130_fix'].append('1264e0 3-arg 化 (xmm1=5.0, xmm2=1e6)')
      mcall = re.match(r'^(\s*)(%[\w.\-]+ = )?call (i64|i128|void) @function_1801264e0\((i64 %[\w.\-]+)\)\s*$', l)
      assert mcall, f'1264e0 呼出形想定外: {l}'
      d = mcall.group(2) or ''
      obj = mcall.group(4)
      out.append(f'{mcall.group(1)}{d}call i64 @function_1801264e0({obj}, i64 {D64_5}, i64 {D64_1E6})')
      seen += 1
      continue
    out.append(l)
  lines = lines[:di] + out + lines[dj + 1:]
  if seen != 2:
    raise AssertionError(f'126130 内 1263f0/1264e0 呼出数 {seen} != 2')
  # define 差替 (3/2-arg adapters → C port)
  di, dj = fn_range(lines, 'function_1801263f0')
  if di is None:
    raise AssertionError('1263f0 define 未検出')
  body_new = [
    'define i64 @function_1801263f0(i64 %arg1, i64 %a1, i64 %a2, i64 %a3) local_unnamed_addr {',
    'dec_label_pc_1801263f0:',
    '  ; ir9 [F5] C 忠実 port (dsm 0x1801263f0..4d7)',
    '  call void @m9_box1263f0bits(i64 %arg1, i64 %a1, i64 %a2, i64 %a3)',
    '  ret i64 %arg1',
    '}',
  ]
  lines = lines[:di] + body_new + lines[dj + 1:]
  lines = fix_declares(lines, 'function_1801263f0', ['i64'] * 4)
  di, dj = fn_range(lines, 'function_1801264e0')
  if di is None:
    raise AssertionError('1264e0 define 未検出')
  body_new = [
    'define i64 @function_1801264e0(i64 %arg1, i64 %a1, i64 %a2) local_unnamed_addr {',
    'dec_label_pc_1801264e0:',
    '  call void @m9_box1264e0bits(i64 %arg1, i64 %a1, i64 %a2)',
    '  ret i64 %arg1',
    '}',
  ]
  lines = lines[:di] + body_new + lines[dj + 1:]
  lines = fix_declares(lines, 'function_1801264e0', ['i64'] * 3)
  return lines


def ctor_insert_gbox_call(lines, rep):
  p = 'function_18011d400'
  di, dj = fn_range(lines, p)
  if di is None:
    raise AssertionError('ctor define 未検出')
  seg = lines[di:dj + 1]
  # anchor: 最後の function_1801a30d0 (memset) 呼出 (box/[0x250]/[0x258] alloc+memset 完了後)
  pat = re.compile(r'^\s*(?:%[\w.\-]+ = )?call (i64|i128|void) @function_1801a30d0\(')
  cands = [j for j, l in enumerate(seg) if pat.match(l)]
  if not cands:
    raise AssertionError('ctor 内 memset direct 呼出未検出')
  j = cands[-1]
  seg2 = seg[:j + 1] + [
    '  ; ir9 [F5] gate box cluster の統合直呼 (dsm 0x18011d546..da66; C 側に順序を担保)',
    '  %gscz = call i64 @m9_gbox_ctor_setup(i64 %arg1)',
  ] + seg[j + 1:]
  lines = lines[:di] + seg2 + lines[dj + 1:]
  rep['ctor_gbox'] = f'inserted after local memset idx {j}'
  return lines


# ================================================================ [F3] resume

def replace_resume(lines, rep):
  body = [
    'define i64 @function_180120800(i64 %arg1) local_unnamed_addr {',
    'dec_label_pc_180120800:',
    '  ; ir9 [F3] 忠実 C port (m9_resume_reinit; dsm 0x180120800..ab6)',
    '  call void @m9_resume_reinit(i64 %arg1)',
    '  ret i64 0',
    '}',
  ]
  di, dj = fn_range(lines, 'function_180120800')
  if di is None:
    raise AssertionError('resume define 未検出')
  lines = lines[:di] + body + lines[dj + 1:]
  rep['resume'] = 'C port (m9_resume_reinit)'
  return lines


# ================================================================ [F8] band filter

def fix_126670(lines, rep):
  p = 'function_180126670'
  di, dj = fn_range(lines, p)
  if di is None:
    raise AssertionError('126670 define 未検出')
  # 呼出 site は全体 (ctor 内) に散在 → 全体走査. define を先に差替。
  body_new = [
    f'define i64 @{p}(i64 %arg1, i64 %a1b) local_unnamed_addr {{',
    'dec_label_pc_180126670:',
    '  ; ir9 [F8] band filter setup C port (dsm 0x180126670..918)',
    '  call void @m9_band_filter_setup(i64 %arg1, i64 %a1b)',
    '  ret i64 0',
    '}',
  ]
  lines = lines[:di] + body_new + lines[dj + 1:]
  call_re = re.compile(r'^  (%[\w.\-]+ = )?call (i64|i128|void) @' + p + r'\((i64 %[\w.\-]+)\)$')
  movss_re = re.compile(r'^  (%[\w.\-]+ = )?call i128 @__asm_movss\(i32 (\d+)\)$')
  out = []
  lastbits = None
  nbit = 0
  bits_list = []
  for l in lines:
    mm = movss_re.match(l)
    if mm:
      lastbits = int(mm.group(2))
    mcall = call_re.match(l)
    if mcall:
      out.append(f'  {mcall.group(1)}call i64 @{p}(i64 {mcall.group(3)}, i64 {lastbits})'.replace('i64 i64', 'i64', 1))
      bits_list.append(lastbits)
      nbit += 1
      continue
    out.append(l)
  if nbit != 8:
    raise AssertionError(f'126670 direct call {nbit} != 8')
  lines = out
  lines = fix_declares(lines, p, ['i64', 'i64'])
  rep['126670'] = f'8 sites bits={bits_list[0:4]}+{bits_list[4:8]}'
  return lines


# ================================================================ [F9] table base remap

def fix_tablebase(lines, rep, newbase=0x30000000):
  """broken-lift 算術合成 table base の即値 remap PoC (m6 REPORT §7-6).
     実測: c38c8 family の base 定数は 0x18026c9f0 / 0x18026c950 (.data) /
     0x18021e500 (.rdata) の**10 進即値** (6444992848 等) — ir6_shift は hex 形式
     (0x18xxxxxx) の VA/global_name のみ remap し得るため 10 進形が未 shift
     ⇒ wasm linear addr そのまま (0x18026c9f0 ≫ memsize) で OOB。
     本 pass は c38c8 family 3 define 内の 0x180200000..0x180300000 即値を
     m6_data install の linear 対応 (v - 0x180000000 + newbase) へ shift する
     (newbase は pipeline から --newbase=<LB_BASE> で渡す, CAB-220)。
     (これにより table の hydrate は既存 m6_data memcpy で完結 = PoC 最小構成)"""
  #
  nrem = 0
  lo, hi = 0x180200000, 0x180300000
  pat = re.compile(r'\b(\d{9,11}|0x[0-9a-fA-F]{9,12})\b')

  def sub(mo):
    nonlocal nrem
    tok = mo.group(1)
    try:
      v = int(tok, 0)
    except ValueError:
      return tok
    if lo <= v < hi:
      nrem += 1
      return str(v - 0x180000000 + newbase)   # linear 対応 (m6_data install 表)
    return tok

  tgt = ['function_1801c38c8', 'function_1801c69cc', 'function_1801c91cc']
  for p in tgt:
    di, dj = fn_range(lines, p)
    if di is None:
      raise AssertionError(f'{p} define 未検出')
    seg = lines[di:dj + 1]
    out = []
    for l in seg:
      out.append(pat.sub(sub, l))
    lines[di:dj + 1] = out
  rep['tablebase'] = f'remapped={nrem} (0x{lo:x}..0x{hi:x} dec-immediate -> linear newbase=0x{newbase:x})'
  return lines

# ================================================================ driver

def main():
  ap = argparse.ArgumentParser()
  ap.add_argument('src')
  ap.add_argument('dst')
  ap.add_argument('--dsm', default=None)
  ap.add_argument('--report', default=None)
  ap.add_argument('--newbase', type=lambda s: int(s, 0), default=0x30000000,
                  help='m6_data install の linear base (pipeline から LB_BASE を渡す, CAB-220)')
  args = ap.parse_args()
  rep = {'modes': ['f3', 'f4', 'f5', 'f6', 'f8'], 'crt': {}, '126130_fix': []}
  lines = open(args.src, errors='replace').read().splitlines()
  # m9 C 側 extern の declare 追加 (emcc の C 定義と結合)
  decls = [
    'declare void @m9_resume_reinit(i64) local_unnamed_addr',
    'declare void @m9_svf_reset(i64, i64, i64) local_unnamed_addr',
    'declare void @m9_box1263f0bits(i64, i64, i64, i64) local_unnamed_addr',
    'declare void @m9_box1264e0bits(i64, i64, i64) local_unnamed_addr',
    'declare i64 @m9_gbox_ctor_setup(i64) local_unnamed_addr',
    'declare i64 @m9_dexp(i64) local_unnamed_addr',
    'declare i64 @m9_dlog(i64) local_unnamed_addr',
    'declare i64 @m9_dtan(i64) local_unnamed_addr',
    'declare void @m9_band_filter_setup(i64, i64) local_unnamed_addr',
  ]
  for d in decls:
    lines.append(d)
  lines = crt_patch(lines, rep)
  lines = fix_126670(lines, rep)
  lines = svf_coeff_reset(lines, rep)
  lines = fix_tablebase(lines, rep, args.newbase)
  lines = fix_126130(lines, rep)
  lines = ctor_insert_gbox_call(lines, rep)
  lines = replace_resume(lines, rep)
  with open(args.dst, 'w') as f:
    f.write('\n'.join(lines) + '\n')
  if args.report:
    os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
    with open(args.report, 'w') as f:
      json.dump(rep, f, ensure_ascii=False, indent=2)
  print(f'[ir9_bootstraps] crt={sum(1 for v in rep["crt"].values() if "threaded" in v)} '
        f'| resume=Cport | svf=3arg | gbox=1 | 130fix={len(rep["126130_fix"])} -> {args.dst}')
  return 0


if __name__ == '__main__':
  sys.exit(main())
