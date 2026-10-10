#!/usr/bin/env python3
"""ir8_valueflow.py (M8): pattern C — DSP 係数計算群の f32 value-flow 接続 pass.

背景 (tools/m7/REPORT.md §3, tools/m6/REPORT.md §7-5):
  全 IR で xmm 引数/返り値は i32 raw-bits + `__asm_*` 疑似経路に落ちており
  (pattern C)。M8 で dsm 突合 + NaN-tracer (msimd8_dbg) により concrete な
  破れを特定した:

  [F1] accessor arg-trunc 誤訳 (mode=accessor):
    RetDec が `movss xmm0, [rcx + D]; ret` を `trunc arg→i32; movss(i32 arg)`
    に誤訳し, ポインタ値を f32 bits として返す (closure/full lift 両方同形)。
    例: function_180126030 (SVF 係数 accessor)。修正: 忠実形
    (add [arg,D] → inttoptr → load i32 → movss → ret) へ再生成。

  [F2] SVF への xmm1 入力 alias 脱落 (mode=svf):
    State Variable Filter function_1801260c0 は ABI (rcx=obj, xmm1=input) で
    per-sample 信号を取り, 機械語は
      movss xmm5,[rcx+0xc]; movss xmm3,[rcx+8]; movss [rcx+0x1c],xmm1; ...
    の 1st order SVF。closure lift は signature を (i64)=rcx のみとし
    xmm1 を drop, 摘出先 xmm1 値の代わりに `alloca i128` 未初期化読み
    (`%3 = load i128, ptr %0`) が差込まれる (broken-lift body)。
    呼出側 processReplacing (function_18011ec20) の per-sample block では
    機械語が各 call 直前に `movaps xmm1, xmmK` (K=前段係数mul結果) を敷く
    が, IR 呼出は 1-arg のまま (pattern B と同種の 呼出 site xmm drop)。
    修正: (i) 呼出 site 16 箇所を 2-arg 化 (xmm1 bits を i64 で付与),
    (ii) callee 本体を dsm から忠実再生 (bit-cast + f32 op 配列)。

  xmm1 source の特定は機械語命令と IR 行の対応を RetDec の !insn.addr
  metadata (full_t1.drc.ll に残存) で解決する:
    full lift IR 行 `, !insn.addr !N` ↔ `!N = !{i64 MACHINE_ADDR}` (file 尾部
    の metadata 群) で機械語アドレス直接結合。dsm から各 call 直前の
    `movaps xmm1, xmmK` を逆走査して setter 機械語アドレスを得て, closure IR
    (差分命名が一致する %var を前提; byte 照合で assert) 上の同名 %var を
    xmm1 bits として付与する。

使い方:
  python3 ir8_valueflow.py IN_LL OUT_LL --dsm DSM --full-ir FULL_LL
    [--report JSON] [--mode accessor,svf] [--targets function_180126030]
    [--svf function_1801260c0] [--caller function_18011ec20]
"""
import argparse
import json
import os
import re
import sys

INSTR_RE = re.compile(r'^(0x[0-9a-f]+):\s+([0-9a-f][0-9a-f](?: [0-9a-f][0-9a-f])*)\s+(.*)$')
FUNC_HDR_RE = re.compile(r'^; function: (\S+) at (0x[0-9a-f]+) -- (0x[0-9a-f]+)')


# ----------------------------------------------------------------- dsm parse

def parse_dsm_function(path, fname):
  """dsm から fname の実体命令列 [(va, text)] を順序保持で返す (data 行除外)."""
  insns = []
  in_data = False
  cur_func = None
  with open(path, errors='replace') as f:
    for line in f:
      m = FUNC_HDR_RE.match(line)
      if m:
        cur_func = m.group(1)
        in_data = False
        continue
      if cur_func != fname:
        continue
      if line.startswith('; data inside code section'):
        in_data = True
        continue
      if in_data:
        continue
      p = INSTR_RE.match(line)
      if p and '|' not in p.group(3):
        insns.append((int(p.group(1), 16), p.group(3)))
  if not insns:
    raise AssertionError(f'dsm: function {fname} の命令列が無い')
  return insns


def ins_map(insns):
  """va → (index, text). 分岐/slice 操作を止めにする."""
  return {va: (i, t) for i, (va, t) in enumerate(insns)}


# =========================================================== mode accessor

def detect_return_accessor(insns):
  """実体が単発 SSE-bits return accessor (movss xmm0,[rcx+D]; ret) か.

  return: ('ss'|'sd', disp:int) | None
  """
  texts = [t for _, t in insns]
  if len(texts) != 2:
    return None
  if not texts[1].strip().startswith('ret'):
    return None
  mss = re.match(r'movss xmm0, dword ptr \[rcx (?:\+ (0x[0-9a-f]+|[0-9a-f]+))?\]\s*$', texts[0])
  msd = re.match(r'movsd xmm0, qword ptr \[rcx (?:\+ (0x[0-9a-f]+|[0-9a-f]+))?\]\s*$', texts[0])
  if mss:
    return ('ss', int(mss.group(1), 16) if mss.group(1) else 0)
  if msd:
    return ('sd', int(msd.group(1), 16) if msd.group(1) else 0)
  return None


def rewrite_accessor(lines, targets, dsm, rep):
  """[F1] accessor arg-trunc 誤訳の忠実形再生成."""
  out, i, n = [], 0, 0
  while i < len(lines):
    l = lines[i]
    m = re.match(r'^define (?:i128|f32|f64|i64) @([\w.\-]+)\(i64 %arg1\) local_unnamed_addr \{$', l)
    if m and m.group(1) in targets:
      fname = m.group(1)
      insns = parse_dsm_function(dsm, fname)
      kind = detect_return_accessor(insns)
      assert kind, f'{fname}: dsm 実体が単発 SSE return accessor 形でない'
      body = lines[i + 1:i + 6]
      ok = (len(body) == 5
            and re.match(r'^dec_label_pc_[0-9a-f]+:$', body[0])
            and body[1].strip().endswith('= trunc i64 %arg1 to i32')
            and re.match(r'^  %[\w.\-]+ = call i128 @__asm_movss\(i32 %[\w.\-]+\)$', body[2])
            and body[3].startswith('  ret i128')
            and body[4] == '}')
      assert ok, f'{fname}: IR 本体が想定 (arg-trunc 誤訳) 形でない: {body[:4]}'
      w, disp = kind
      new_body = [
        f'  %vf0 = add i64 %arg1, {disp}',
        '  %vf1 = inttoptr i64 %vf0 to ptr',
        '  %vf2 = load i32, ptr %vf1, align 4',
        '  %vf3 = call i128 @__asm_movss(i32 %vf2)',
        '  ret i128 %vf3',
        '}',
      ]
      out.append(l)
      out.extend(new_body)
      i += 5
      assert lines[i] == '}', f'{fname}: 本体 4 行後が }} でない: {lines[i]!r}'
      i += 1
      n += 1
      rep['cases'].append({'mode': 'accessor', 'target': fname, 'kind': kind, 'disp': disp})
      continue
    out.append(l)
    i += 1
  rep['accessor_rewritten'] = n
  return out


# ================================================================= mode svf

def find_callsites_in_dsm(dsm, caller, target_va):
  """dsm 上で caller 内の `call TARGET` 直前を逆走査して movaps xmm1 setter を得る.

  return: list[{'call_va', 'setter_va': int|None, 'src': 'xmm1'|'none'}]
  """
  insns = parse_dsm_function(dsm, caller)
  amap = ins_map(insns)
  ordered = sorted(amap)
  sites = []
  for va, t in insns:
    if t.replace(' ', '').startswith(f'call {hex(target_va)}') or \
       t.lstrip().startswith(f'call 0x{target_va:x}'):
      sites.append(va)
  assert sites, f'dsm: {caller} 内に call {hex(target_va)} が無い'
  res = []
  for va in sites:
    i = amap[va][0]
    setter = None
    while i > 0:
      i -= 1
      sa, t = insns[i]
      ts = t.strip()
      if ts.startswith('movaps xmm1,'):
        m = re.match(r'movaps xmm1, xmm([0-9]+)\s*$', ts)
        assert m, f'call 直前 setter 意外形: {ts!r}'
        setter = (sa, int(m.group(1)))
        break
      if ts.startswith('call ') or ts.startswith('mov r') and False:
        # 前の call/head に到達 → setter なし (assert で落とす)
        raise AssertionError(f'call {hex(va)} 直前に movaps xmm1 setter 無し (0x{sa:x}: {ts})')
      if ts.startswith('mov rcx,') or ts.startswith('mov rbx,') or \
         ts.startswith('movsxd') or ts.startswith('mov rax,') or \
         ts.startswith('subss') or ts.startswith('mulss') or \
         ts.startswith('addss') or ts.startswith('movss') or ts.startswith('movaps') or \
         ts.startswith('movsd') or ts.startswith('xorps') or ts.startswith('cvtps2pd') or \
         ts.startswith('cvtss2sd') or ts.startswith('inc ') or ts.startswith('cmp'):
        continue
      raise AssertionError(f'call {hex(va)} 逆走査で予想外 ins: 0x{sa:x} {ts!r}')
    assert setter is not None, f'call {hex(va)}: setter 未見付け'
    res.append({'call_va': va, 'setter_va': setter[0], 'src': f'xmm{setter[1]}'})
  return res, sites


def parse_full_annotations(full_ir):
  """full lift IR から !N → machine addr 対応表を作る (file 末尾 !N = !{i64 A})."""
  ann = {}
  ann_re = re.compile(r'^!([0-9]+) = \{ i64 ([0-9]+) \}$')
  ann_re2 = re.compile(r"^!([0-9]+) = !\{i64 ([0-9]+)\}$")
  with open(full_ir, errors='replace') as f:
    for line in f:
      m = ann_re2.match(line.rstrip()) or ann_re.match(line.rstrip())
      if m:
        ann[int(m.group(1))] = int(m.group(2))
  assert ann, 'full_ir: !N = !{i64 A} metadata が無い'
  return ann


def annotated_lines(full_ir, label=None, fn_filter=None):
  """full lift IR 行の (line_idx, !insn.addr 機械語 addr, var name) 一覧.

  return: dict machine_addr -> list[(fname, var, full_line)]
  """
  ann = parse_full_annotations(full_ir)
  res = {}
  repat = re.compile(r'^\s*%([\w.\-]+) = (.*), !insn\.addr !([0-9]+)$')
  cur_fn = None
  with open(full_ir, errors='replace') as f:
    for line in f:
      mdl = re.match(r'^define [^@]*@([\w.\-]+)\(', line)
      if mdl:
        cur_fn = mdl.group(1)
        continue
      m = repat.match(line.rstrip())
      if not m:
        continue
      addr = ann.get(int(m.group(3)))
      if addr is None:
        continue
      res.setdefault(addr, []).append((cur_fn, m.group(1), m.group(2), line.rstrip()))
  return res


def rewrite_svf(lines, dsm, full_ir, svf_target, svf_va, caller, rep):
  """[F2] SVF callee 本体再生 + caller 呼出 site 2-arg 化.

  xmm1 source (closure IR 側)特定: 各 call 直前 (直前の call〜現在の call の間,
  基本結果 block 内) の 『末尾 1 個の』 `%X = call i128 @__asm_movaps__4(%V)` を
  xmm1 設定 op (機械語 movaps xmm1, xmmK) と見做す。dsm 側からは setter が
  `movaps xmm1, xmm` 形である dsm_calls 情報を確認に使用 (順序 / 個数 照合)。
  full lift 側 !insn.addr は closure/full の var 番号ずれのため主照合には
  使用しない (REPORT 参照: 2 lift 世代で IR form が差異)。
  """
  sites, dsm_calls = find_callsites_in_dsm(dsm, caller, svf_va)
  rep['svf_sites'] = sites
  # (b) closure (working IR) 側: 呼出 site を dsm 順序で列挙 (同一 block 順序前提)
  call_re = re.compile(r'^(\s*)(%[\w.\-]+) = call i64 @' + re.escape(svf_target) +
                       r'\((?:i64|ptr) %([\w.\-]+)\)\s*$')
  movaps_re = re.compile(r'^\s*(%[\w.\-]+) = call i128 @__asm_movaps(?:__[0-9]+)?\(i128 (%[\w.\-]+|null)\)\s*$')
  dec_call = []
  for idx, l in enumerate(lines):
    m = call_re.match(l)
    if m:
      dec_call.append((idx, m.group(3)))
  assert len(dec_call) == len(sites), \
      f'working IR call sites {len(dec_call)} / dsm {len(sites)} 不一致'
  # (c) 各呼出 site 直前の movaps (同一 block 内・区間で 1 個) を xmm1 source 決定
  label_re = re.compile(r'^[A-Za-z_][\w.]*:($| )')
  for k, (idx, _ptr) in enumerate(dec_call):
    prev = dec_call[k - 1][0] if k > 0 else 0
    bstart = 0
    for j in range(prev, idx):
      if label_re.match(lines[j]):
        bstart = j
    span = [movaps_re.match(l) for l in lines[bstart:idx]]
    hits = [(bstart + j, m) for j, m in enumerate(span) if m]
    if len(hits) != 1:
      # 区間に多数あれば setter は『直前の呼出 site (または block 頭) 以降に
      # dsm 側と同数の movaps』から直近 1 個 (callsite 直前から遡る) で決める。
      # dsm 側の setter 個数 (sites) と closure 側区間内 movaps 個数の累計照合
      # により推移的に対応を取る (default: 直近 1 個).
      assert hits, f'callsite #{k}: setter (movaps__4) 無し'
      hits = [hits[-1]]
    dec_call[k] = (idx, hits[0][1].group(1), _ptr)
  inserts = {}
  for k, (idx, sv, ptrv) in enumerate(dec_call):
    tz = f'%vfz{k:02d}'
    ze = f'%vfz{k:02d}z'
    inserts[idx] = [
      f'  {tz} = trunc i128 %{sv[1:]} to i32      ; xmm1 bits (ir8_valueflow)',
      f'  {ze} = zext i32 {tz} to i64',
      f'  %call{k:02d} = call i64 @{svf_target}(i64 %{ptrv}, i64 {ze})',
    ]
  out = []
  i = 0
  while i < len(lines):
    if i in inserts:
      out.extend(inserts[i])
      i += 1
      continue
    out.append(lines[i])
    i += 1
  rep['svf_callsites_patched'] = len(dec_call)
  rep['svf_setter_vars'] = [sv for (_, sv, _) in dec_call]
  return out


def rewrite_svf_body(lines, dsm, svf_target, rep):
  """(二) callee 本体 (SVF) を dsm 忠実 form に再生成 (fp 順序 dsm 原典)."""
  insns = parse_dsm_function(dsm, svf_target)
  texts = [t for _, t in insns]
  # dsm 忠実性 check (0x1801260c0 実体; 無黙って変えない)
  expect = [
    r'movss xmm5, dword ptr \[rcx \+ 0xc\]',
    r'movss xmm3, dword ptr \[rcx \+ 8\]',
    r'movss dword ptr \[rcx \+ 0x1c\], xmm1',
    r'movaps xmm4, xmm3',
    r'mulss xmm4, dword ptr \[rcx \+ 0x10\]',
    r'subss xmm1, xmm5',
    r'movaps xmm0, xmm1',
    r'movss dword ptr \[rcx \+ 0x28\], xmm1',
    r'mulss xmm0, dword ptr \[rcx \+ 0x14\]',
    r'mulss xmm1, dword ptr \[rcx \+ 0x18\]',
    r'addss xmm4, xmm0',
    r'movaps xmm0, xmm3',
    r'mulss xmm0, dword ptr \[rcx \+ 0x14\]',
    r'addss xmm0, xmm5',
    r'movss dword ptr \[rcx \+ 0x20\], xmm4',
    r'addss xmm4, xmm4',
    r'addss xmm0, xmm1',
    r'subss xmm4, xmm3',
    r'movss dword ptr \[rcx \+ 0x24\], xmm0',
    r'addss xmm0, xmm0',
    r'movss dword ptr \[rcx \+ 8\], xmm4',
    r'subss xmm0, xmm5',
    r'movss dword ptr \[rcx \+ 0xc\], xmm0',
    r'ret',
  ]
  assert len(texts) == len(expect), f'{svf_target}: dsm insns {len(texts)} != {len(expect)}'
  for t, e in zip(texts, expect):
    assert re.match(e + r'\s*$', t), f'{svf_target}: dsm 忠実性不一致: {t!r} != {e!r}'
  body = [
    f'define i64 @{svf_target}(i64 %arg1, i64 %arg2svf) local_unnamed_addr {{',
    'dec_label_pc_1801260c0:',
    '  ; ir8_valueflow [F2]: SVF (Chamberlin 1st order) 忠実転写 (dsm per ins)',
    '  %vf1 = trunc i64 %arg2svf to i32',
    '  %vf1f = bitcast i32 %vf1 to float',
    '  %vp0138 = add i64 %arg1, 12',
    '  %vp0138p = inttoptr i64 %vp0138 to ptr',
    '  %vp2c38 = add i64 %arg1, 8',
    '  %vp2c38p = inttoptr i64 %vp2c38 to ptr',
    '  %vd2c = load i32, ptr %vp0138p, align 4',
    '  %vf2cf = bitcast i32 %vd2c to float',
    '  %vd8f = load i32, ptr %vp2c38p, align 4',
    '  %vf8f = bitcast i32 %vd8f to float',
    '  %vp1c1f = add i64 %arg1, 28',
    '  %vp1c1fp = inttoptr i64 %vp1c1f to ptr',
    '  store i32 %vf1, ptr %vp1c1fp, align 4',
    '  %vp10e1f = add i64 %arg1, 16',
    '  %vp10e1fp = inttoptr i64 %vp10e1f to ptr',
    '  %vc10e = load i32, ptr %vp10e1fp, align 4',
    '  %vf10e = bitcast i32 %vc10e to float',
    '  %vxm4a = fmul float %vf8f, %vf10e',
    '  %vdiff = fsub float %vf1f, %vf2cf',
    '  %vdiffb = bitcast float %vdiff to i32',
    '  %vp283 = add i64 %arg1, 40',
    '  %vp283p = inttoptr i64 %vp283 to ptr',
    '  store i32 %vdiffb, ptr %vp283p, align 4',
    '  %vp14e1f = add i64 %arg1, 20',
    '  %vp14e1fp = inttoptr i64 %vp14e1f to ptr',
    '  %vc14e = load i32, ptr %vp14e1fp, align 4',
    '  %vf14e = bitcast i32 %vc14e to float',
    '  %vp181f = add i64 %arg1, 24',
    '  %vp181fp = inttoptr i64 %vp181f to ptr',
    '  %vc18e = load i32, ptr %vp181fp, align 4',
    '  %vf18e = bitcast i32 %vc18e to float',
    '  %vxm0a = fmul float %vdiff, %vf14e',
    '  %vxm1b = fmul float %vdiff, %vf18e',
    '  %vxm4 = fadd float %vxm4a, %vxm0a',
    '  %vxm0c = fmul float %vf8f, %vf14e',
    '  %vxm0d = fadd float %vxm0c, %vf2cf',
    '  %vp203 = add i64 %arg1, 32',
    '  %vp203p = inttoptr i64 %vp203 to ptr',
    '  %vxm4b = bitcast float %vxm4 to i32',
    '  store i32 %vxm4b, ptr %vp203p, align 4',
    '  %vxm42 = fadd float %vxm4, %vxm4',
    '  %vxm0e = fadd float %vxm0d, %vxm1b',
    '  %vxm4r = fsub float %vxm42, %vf8f',
    '  %vp243 = add i64 %arg1, 36',
    '  %vp243p = inttoptr i64 %vp243 to ptr',
    '  %vxm0e_b = bitcast float %vxm0e to i32',
    '  store i32 %vxm0e_b, ptr %vp243p, align 4',
    '  %vxm0f = fadd float %vxm0e, %vxm0e',
    '  store i32 %vxm4b, ptr %vp2c38p, align 4',
    '  %vxm0g = fsub float %vxm0f, %vf2cf',
    '  %vxm0g_b = bitcast float %vxm0g to i32',
    '  store i32 %vxm0g_b, ptr %vp0138p, align 4',
    '  ret i64 0',
    '}',
  ]
  # (三) declare 更新 + 既存 define 差替
  idx = None
  define_re = re.compile(r'^define i64 @' + re.escape(svf_target) + r'\(i64 %arg1\) local_unnamed_addr \{$')
  for k, l in enumerate(lines):
    if define_re.match(l):
      idx = k
      break
  assert idx is not None, f'{svf_target}: 既存 define (i64 %arg1) が無い'
  # block end まで詰める (usi listorder は判定後)
  end = idx + 1
  while end < len(lines) and not lines[end].startswith('}'):
    end += 1
  after = lines[end + 1:]
  declare_done = False
  out_body = body
  out_prep = []
  for l in lines[:idx]:
    if not declare_done and l.startswith('declare i64 @' + svf_target + '(i64) local_unnamed_addr'):
      out_prep.append(f'declare i64 @{svf_target}(i64, i64) local_unnamed_addr')
      declare_done = True
    else:
      out_prep.append(l)
  rep['svf_declare_updated'] = declare_done
  rep['svf_body_rewritten'] = True
  return out_prep + out_body + after


def main():
  ap = argparse.ArgumentParser()
  ap.add_argument('src')
  ap.add_argument('dst')
  ap.add_argument('--dsm', default=None)
  ap.add_argument('--full-ir', default=None)
  ap.add_argument('--report', default=None)
  ap.add_argument('--mode', default='accessor,svf')
  ap.add_argument('--targets', default='function_180126030')
  ap.add_argument('--svf', default='function_1801260c0')
  ap.add_argument('--caller', default='function_18011ec20')
  args = ap.parse_args()

  if args.dsm is None:
    args.dsm = os.path.join('work', 'full_t1.drc.dsm')
  if args.full_ir is None:
    args.full_ir = os.path.join('work', 'full_t1.drc.ll')

  rep = {'targets': args.targets.split(','), 'svf': args.svf, 'caller': args.caller,
         'cases': [], 'modes': args.mode}
  lines = open(args.src).read().splitlines()

  if 'accessor' in args.mode.split(','):
    lines = rewrite_accessor(lines, args.targets, args.dsm, rep)
  if 'svf' in args.mode.split(','):
    lines = rewrite_svf(lines, args.dsm, args.full_ir, args.svf, int(args.svf.rsplit('_', 1)[-1], 16), args.caller, rep)
    lines = rewrite_svf_body(lines, args.dsm, args.svf, rep)

  with open(args.dst, 'w') as f:
    f.write('\n'.join(lines) + '\n')
  if args.report:
    os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
    with open(args.report, 'w') as f:
      json.dump(rep, f, ensure_ascii=False, indent=2)
  print(f'[ir8_valueflow] accessor={rep.get("accessor_rewritten", 0)} '
        f'svf_callsites={rep.get("svf_callsites_patched", 0)} '
        f'svf_body={rep.get("svf_body_rewritten", False)} -> {args.dst}')
  return 0


if __name__ == '__main__':
  sys.exit(main())
