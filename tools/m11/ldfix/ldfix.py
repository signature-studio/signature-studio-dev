#!/usr/bin/env python3
"""ldfix.py — RetDec IR の load 取り違え (値↔アドレス / 1 段 deref 脱落) 修復 pass (CAB-231)。

正本 = capstone による実機械語 (.pdata 区間の線型逆アセンブル)。IR 側の壊れた形を
機械語と突合し、一致した site だけを書き換える (site 単位で機械検証、不一致は触らない)。

修復パターン (詳細は REPORT.md):
  F1 load_dropped (RMW 定数化):
    `add dword [g],1` が `store i32 (&g+1), [g]` に化ける (load 脱落 + 即値がアドレス定数側へ)。
    機械語の rip 相対 RMW `add/sub dword [rip+D], imm` (target = g) と突合し
    load → add/sub → store に復元。同一 (&g±imm) 定数を「値」として読む後続形 (cmp 等) も復元。
    Delphi unit 初期化/終了 proc (liftdiff load_dropped 892 関数) が主対象。
  F2 spill_slot_deref:
    レジスタ退避 alloca (%rcx 等) 自体を bitcast して load/store する
    (`movups xmm0,[rcx]` → `load i128, ptr %rcx_alloca` = スタック slot を読む)。
    alloca の内容 (= その時点のレジスタ値) を inttoptr したアドレスへ張り替える。
  F3a 旧値 load 復元 (D7 値↔アドレス, _UStrAsg 系):
    `mov rax,[rbx]; mov [rbx],rsi; test rax,rax` の旧値 load が IR で消えて dest ポインタ
    自身に化けた site を機械語シグネチャ (3 命令連続 + rB≡arg1) で検出し、store 前 の
    load を挿入して icmp / 単一 pred 連鎖の派生値 / thread 系ブロックの slot store に配線する。
  F3b 件数 load 復元 (D7 zero-disp live-in load, 4123c0 系):
    `mov edi,[rcx]` が `xor i64 0,0` に化けた site を「ブロック内の zero-disp load が 1 本・
    IR の xor i64 0,0 が 1 本・機械語に自己 xor 無し・load 先ベースが argN と解決」の
    厳密条件が揃ったときだけ復元する。

使い方: python3 ldfix.py IN.ll OUT.ll --pe PE.bin [--report OUT.json] [--only 4133f0,...] [--dry-run]
"""
import argparse
import bisect
import collections
import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ldmach import Machine, FnMach  # noqa: E402

BASE = 0x400000
DEF_RE = re.compile(r'^define (?P<ret>[^@]*?)@(?P<name>function_[0-9a-f]+)\((?P<args>[^)]*)\)(?P<rest>[^{]*)\{', re.M)
BLK_RE = re.compile(r'^dec_label_pc_(?P<va>[0-9a-f]+):', re.M)
XOR0_RE = re.compile(r'^(\s*)(%[\w.$-]+) = xor i64 0, 0\s*$', re.M)
CE_PT_RE = re.compile(r'^\s*(%[\w.$-]+) = ptrtoint ptr inttoptr \(i64 (\d+) to ptr\) to i64\s*$')
CE_TRUNC_RE = re.compile(r'^\s*(%[\w.$-]+) = trunc i64 (%[\w.$-]+) to i32\s*$')
CE_STORE_RE = re.compile(r'^\s*store i32 (%[\w.$-]+), ptr inttoptr \(i64 (\d+) to ptr\), align 4\s*$')
BITCAST_RE = re.compile(r'^(\s*)(%[\w.$-]+) = bitcast ptr (%(?:rax|rbx|rcx|rdx|rsi|rdi|rbp|rsp|r8|r9|r1[0-5])) to ptr\s*$')
HOME_ALLOCA_RE = re.compile(r'^\s*(%(?:rax|rbx|rcx|rdx|rsi|rdi|rbp|rsp|r8|r9|r1[0-5])) = alloca (?:i64|\[ ?\d+ x i64\])')
STORE_ARG1_RE = re.compile(r'^(\s*)store i64 (%[\w.$-]+), ptr (%[\w.$-]+|inttoptr \(i64 %arg1 to ptr\))(, align \d+)?\s*$')
ICMP_EQ0_RE = re.compile(r'^(\s*)(%[\w.$-]+) = icmp eq (i64 (%[\w.$-]+)|ptr (%[\w.$-]+)), (0|null)\s*$')
ARGREG_ARG = {'rcx': 1, 'rdx': 2, 'r8': 3, 'r9': 4}


def arg1_ptr_names(lines):
    """dest (= arg1) を指す ptr SSA 名の集合: %arg1 と `inttoptr i64 %arg1 to ptr` の結果"""
    names = {'%arg1'}
    for l in lines:
        m = re.match(r'^\s*(%[\w.$-]+) = inttoptr i64 %arg1 to ptr\s*$', l)
        if m:
            names.add(m.group(1))
    return names


def find_arg1_stores(lines, ptrs):
    out = []
    for i, l in enumerate(lines):
        m = re.match(r'^(\s*)store i64 (%[\w.$-]+), ptr (%[\w.$-]+)((?:, align \d+)?)\s*$', l)
        if m and m.group(3) in ptrs:
            out.append((i, m))
    return out


def log(msg):
    print('[ldfix] %s' % msg, file=sys.stderr)


def gprnorm(cs, rid):
    n = cs.reg_name(rid)
    if not n:
        return None
    n = n.lower()
    G = {'eax': 'rax', 'ebx': 'rbx', 'ecx': 'rcx', 'edx': 'rdx', 'esi': 'rsi', 'edi': 'rdi',
         'rax': 'rax', 'rbx': 'rbx', 'rcx': 'rcx', 'rdx': 'rdx', 'rsi': 'rsi', 'rdi': 'rdi',
         'rbp': 'rbp', 'rsp': 'rsp',
         'al': 'rax', 'bl': 'rbx', 'cl': 'rcx', 'dl': 'rdx', 'ah': 'rax', 'bh': 'rbx',
         'ch': 'rcx', 'dh': 'rdx', 'ax': 'rax', 'bx': 'rbx', 'cx': 'rcx', 'dx': 'rdx',
         'si': 'rsi', 'di': 'rdi', 'bp': 'rbp', 'sp': 'rsp',
         'sil': 'rsi', 'dil': 'rdi', 'bpl': 'rbp', 'spl': 'rsp'}
    if n in G:
        return G[n]
    m = re.match(r'^r(\d+)[dwb]$', n)
    if m:
        return 'r' + m.group(1)
    if re.match(r'^r\d+$', n):
        return n
    return None


class Fn:
    """IR 関数 1 個分 (define 行を含む本文)"""

    def __init__(self, name, va, body):
        self.name = name
        self.va = va
        self.body = body

    def blocks(self):
        """[(block_va | None, [行])] — 本文を行ブロックに分割"""
        out = []
        cur_va = None
        cur = []
        for l in self.body.split('\n'):
            m = BLK_RE.match(l)
            if m:
                if cur:
                    out.append((cur_va, cur))
                cur_va = int(m.group('va'), 16)
                cur = [l]
            elif re.match(r'^[\w.$-]+:\s*$', l):
                if cur:
                    out.append((cur_va, cur))
                cur_va = None
                cur = [l]
            else:
                cur.append(l)
        if cur:
            out.append((cur_va, cur))
        return out


def fn_mach_blocks(fv, va, block_vas):
    ins = fv.ins
    if not ins:
        return None, []
    bvs = sorted(set(block_vas))
    out = {}
    for i in ins:
        k = bisect.bisect_right(bvs, i.address)
        if k:
            out.setdefault(bvs[k - 1], []).append(i)
    return out, ins


# ---------------------------------------------------------------------------
# F1: load_dropped (RMW 定数化)
# ---------------------------------------------------------------------------

def fix_f1(fn, mach, rep, ctr):
    lines = fn.body.split('\n')
    pt_at = {}
    for i, l in enumerate(lines):
        m = CE_PT_RE.match(l)
        if m:
            pt_at[m.group(1)] = (i, int(m.group(2)))
    tr_src = {}
    for i, l in enumerate(lines):
        m = CE_TRUNC_RE.match(l)
        if m and m.group(2) in pt_at:
            tr_src[m.group(1)] = (i, m.group(2))
    rewrites = {}
    fixed = 0
    for i, l in enumerate(lines):
        m = CE_STORE_RE.match(l)
        if not m or i in rewrites:
            continue
        t = tr_src.get(m.group(1))
        if not t:
            continue
        c0 = int(m.group(2))
        pt_i, c1 = pt_at[t[1]]
        tr_i = t[0]
        delta = c1 - c0
        rmw = find_rip_rmw(mach, c0)
        if rmw is None:
            rep['f1_no_machine_match'] = rep.get('f1_no_machine_match', 0) + 1
            continue
        mnem, imm = rmw
        want = imm if mnem == 'add' else -imm
        if delta != want:
            rep['f1_imm_mismatch'] = rep.get('f1_imm_mismatch', 0) + 1
            continue
        if store_to_target(mach, c0):
            rep['f1_other_store'] = rep.get('f1_other_store', 0) + 1
            continue
        ctr[0] += 1
        nm = 'ldfxr%d' % ctr[0]
        ld = '  %%%s = load i32, ptr inttoptr (i64 %d to ptr), align 4' % (nm, c0)
        op = '  %%%s_v = add i32 %%%s, %d' % (nm, nm, imm if mnem == 'add' else -imm)
        st = '  store i32 %%%s_v, ptr inttoptr (i64 %d to ptr), align 4' % (nm, c0)
        rewrites[pt_i] = None
        rewrites[tr_i] = None
        rewrites[i] = [ld, op, st]
        extra = restore_following_value_uses(lines, i, c1, '%%%s_v' % nm, rewrites)
        if extra:
            rep['f1_following_value_uses'] = rep.get('f1_following_value_uses', 0) + extra
        fixed += 1
    if not fixed:
        return 0
    out = []
    for i, l in enumerate(lines):
        if i in rewrites:
            r = rewrites[i]
            if r is not None:
                out.extend(r)
        else:
            out.append(l)
    fn.body = '\n'.join(out)
    return fixed


def find_rip_rmw(mach, c0):
    want = c0 + BASE
    for m in mach.iter_memops():
        if m['kind'] != 'rmw' or m['size_bits'] != 32 or m.get('rip_rva') != want:
            continue
        ins = m['ins']
        if ins.mnemonic in ('add', 'sub') and len(ins.operands) == 2 and ins.operands[1].type == 2:
            return (ins.mnemonic, ins.operands[1].imm)
    return None


def has_any_store(mach):
    return any(m['kind'] == 'store' for m in mach.iter_memops())


def store_to_target(mach, c0):
    """同一ターゲット (c0+BASE) への rip 相対 store があるか (RMW 修復と競合)"""
    want = c0 + BASE
    for m in mach.iter_memops():
        if m['kind'] == 'store' and m.get('rip_rva') == want:
            return True
    return False


def restore_following_value_uses(lines, store_i, c1, newval, rewrites):
    """store 行以降の同一ブロック内で ptrtoint(inttoptr C1)→trunc を「値」として使う形を復元。"""
    n = 0
    for j in range(store_i + 1, len(lines)):
        l = lines[j]
        if re.match(r'^dec_label|^[\w.$-]+:\s*$|^}', l):
            break
        m = CE_PT_RE.match(l)
        if not m or int(m.group(2)) != c1 or j in rewrites:
            continue
        pname = m.group(1)
        for k in range(j + 1, min(j + 6, len(lines))):
            m2 = CE_TRUNC_RE.match(lines[k])
            if m2 and m2.group(2) == pname:
                xv = m2.group(1)
                nn = replace_value_uses(lines, k + 1, xv, newval)
                rewrites[j] = None
                rewrites[k] = None
                n += 1 + nn
                break
        break
    return n


def replace_value_uses(lines, start, name, newval):
    n = 0
    pat = re.compile(r'(?<![\w.$-])' + re.escape(name) + r'(?![\w.$-])')
    for j in range(start, len(lines)):
        l = lines[j]
        if re.match(r'^dec_label|^[\w.$-]+:\s*$|^}', l):
            break
        if name not in l:
            continue
        if re.search(r', ptr ' + re.escape(name) + r'(?![\w.$-])', l):
            continue
        if re.search(r'inttoptr \(i64 ' + re.escape(name) + r'(?![\w.$-])', l):
            continue
        new = pat.sub(newval, l)
        if new != l:
            lines[j] = new
            n += 1
    return n


# ---------------------------------------------------------------------------
# F2: spill_slot_deref
# ---------------------------------------------------------------------------

def fix_f2(fn, mach, rep, ctr):
    """bitcast(レジスタ home alloca) の deref を修復。
    - 同一ブロック内の load/store アドレス用途 → bitcast 行を load ペアに置換 (共有)
    - ブロック外のアドレス用途 → 使用箇所ごとに load ペアを挿入
    - それ以外の用途が残る場合は bitcast 行を残す (部分修復を避けて安全側へ)"""
    lines = fn.body.split('\n')
    homes = set()
    for l in lines:
        m = HOME_ALLOCA_RE.match(l)
        if m:
            homes.add(m.group(1))
    if not homes:
        return 0
    blk_ranges = []
    start = None
    for i, l in enumerate(lines):
        if BLK_RE.match(l) or re.match(r'^[\w.$-]+:\s*$', l):
            if start is not None:
                blk_ranges.append((start, i))
            start = i
    if start is not None:
        blk_ranges.append((start, len(lines)))

    def blk_of(li):
        for (a, b) in blk_ranges:
            if a <= li < b:
                return (a, b)
        return None

    fixed = 0
    edits = {}                     # line_idx -> [行] (置換/挿入)
    drop = set()                   # 削除行 (bitcast)
    for i, l in enumerate(lines):
        m = BITCAST_RE.match(l)
        if not m or i in edits or i in drop:
            continue
        bname, reg = m.group(2), m.group(3)
        if reg not in homes:
            continue
        if not mach.has_reg_memop(reg[1:], zero_disp=True):
            rep['f2_no_machine_match'] = rep.get('f2_no_machine_match', 0) + 1
            continue
        myblk = blk_of(i)
        same_uses = []
        cross_uses = []
        other_uses = 0
        for j in range(i + 1, len(lines)):
            ln = lines[j]
            if bname not in ln:
                continue
            mm = re.match(r'^(\s*)((?:%[\w.$-]+ = )?)(load) ([i]\d+|float|double), ptr ' + re.escape(bname) + r'((?:, align \d+)?)\s*$', ln)
            ms = re.match(r'^(\s*)store ([i]\d+|float|double) ([\w.%$]+|zeroinitializer|null|true|false), ptr ' + re.escape(bname) + r'((?:, align \d+)?)\s*$', ln)
            if mm:
                (same_uses if myblk and myblk[0] <= j < myblk[1] else cross_uses).append((j, 'load', mm.group(2), mm.group(3), mm.group(4), mm.group(5), mm.group(1)))
            elif ms:
                (same_uses if myblk and myblk[0] <= j < myblk[1] else cross_uses).append((j, 'store', '', ms.group(2), ms.group(3), ms.group(4), ms.group(1)))
            else:
                other_uses += 1
        if not same_uses and not cross_uses:
            rep['f2_unused_bitcast'] = rep.get('f2_unused_bitcast', 0) + 1
            continue
        ctr[0] += 1
        nm = 'ldfxb%d' % ctr[0]

        def pair(name):
            return ['  %%%s_v = load i64, ptr %s, align 8' % (name, reg),
                    '  %%%s_p = inttoptr i64 %%%s_v to ptr' % (name, name)]

        if other_uses:
            rep['f2_other_use_kept'] = rep.get('f2_other_use_kept', 0) + 1
        if same_uses:
            edits[i] = ('after', pair(nm))   # bitcast 行の直後に挿入 (他用途があれば bitcast 自体は生かす)
        for (j, kind, lhs, ty, val, al, ws) in same_uses:
            if kind == 'load':
                lines[j] = '%s%s%s %s, ptr %%%s_p%s' % (ws, lhs, ty, val, nm, al or '')
            else:
                lines[j] = '%sstore %s %s, ptr %%%s_p%s' % (ws, ty, val, nm, al or '')
        cidx = 0
        for (j, kind, lhs, ty, val, al, ws) in sorted(cross_uses):
            cidx += 1
            cnm = '%s_c%d' % (nm, cidx)
            edits.setdefault(j, ('before', []))
            edits[j][1].extend(pair(cnm))
            if kind == 'load':
                lines[j] = '%s%s%s %s, ptr %%%s_p%s' % (ws, lhs, ty, val, cnm, al or '')
            else:
                lines[j] = '%sstore %s %s, ptr %%%s_p%s' % (ws, ty, val, cnm, al or '')
        fixed += 1
    if not fixed:
        return 0
    out = []
    for i2, l in enumerate(lines):
        if i2 in edits:
            pos, ls = edits[i2]
            if pos == 'before':
                out.extend(ls)
        out.append(l)
        if i2 in edits:
            pos, ls = edits[i2]
            if pos == 'after':
                out.extend(ls)
    fn.body = '\n'.join(out)
    return fixed

# ---------------------------------------------------------------------------
# F3a: 旧値 load 復元 (_UStrAsg 系)
# ---------------------------------------------------------------------------

def usstrasg_site(mach):
    ins = mach.ins
    for k in range(len(ins) - 2):
        a, b, c = ins[k], ins[k + 1], ins[k + 2]
        if a.mnemonic != 'mov' or b.mnemonic != 'mov' or c.mnemonic != 'test':
            continue
        try:
            oa, ob = a.operands
            if len(a.operands) != 2 or oa.type != 1 or ob.type != 3:
                continue
            if ob.mem.index or ob.mem.disp or ob.size * 8 != 64 or not ob.mem.base:
                continue
            oc, od = b.operands
            if len(b.operands) != 2 or oc.type != 3 or od.type != 1:
                continue
            if oc.mem.index or oc.mem.disp or oc.size * 8 != 64 or oc.mem.base != ob.mem.base:
                continue
            if od.reg == oa.reg:
                continue
            if not (len(c.operands) == 2 and c.operands[0].type == 1 and c.operands[1].type == 1
                    and c.operands[0].reg == oa.reg and c.operands[1].reg == oa.reg):
                continue
            rd = gprnorm(mach.cs, oa.reg)
            rb = gprnorm(mach.cs, ob.mem.base)
        except Exception:
            continue
        if rd != 'rax':
            continue
        if rb != 'rcx':
            ok = any(e.mnemonic == 'mov' and len(e.operands) == 2 and e.operands[0].type == 1
                     and gprnorm(mach.cs, e.operands[0].reg) == rb and e.operands[1].type == 1
                     and gprnorm(mach.cs, e.operands[1].reg) == 'rcx' for e in ins[:8])
            if not ok:
                continue
        return (a.address, rd, rb)
    return None


def fix_f3a(fn, mach, rep, ctr):
    site = usstrasg_site(mach)
    if site is None:
        return 0
    lines = fn.body.split('\n')
    ptrs = arg1_ptr_names(lines)
    stores = find_arg1_stores(lines, ptrs)
    if not stores or len(stores) > 3:
        rep['f3a_many_stores'] = rep.get('f3a_many_stores', 0) + 1
        return 0
    # test を含む IR ブロック中の arg1-store = main
    blk_list = fn.blocks()
    cum = 0
    blk_at = []
    for (bva, ls) in blk_list:
        blk_at.append((bva, cum, cum + len(ls)))
        cum += len(ls)
    main_i = None
    for (bva, ia, ib) in blk_at:
        if bva is not None and bva <= site[0]:
            cands = [k for k in range(ia, ib)
                     if any(mm.group(0) and lines[k] == mm.group(0) for mm in [])]
            cands = [k for k in range(ia, ib)
                     if re.match(r'^\s*store i64 ', lines[k]) and store_ptr_of(lines[k]) in ptrs]
            if cands:
                main_i = cands[0]
    if main_i is None:
        rep['f3a_no_main_store'] = rep.get('f3a_no_main_store', 0) + 1
        return 0
    ctr[0] += 1
    nm = 'ldfxo%d' % ctr[0]
    body0 = fn.body
    m = re.match(r'^(\s*)store i64 (%[\w.$-]+), ptr (%[\w.$-]+)((?:, align \d+)?)\s*$', lines[main_i])
    ptr_expr = m.group(3)
    lines[main_i:main_i] = ['  %%%s = load i64, ptr %s, align 8' % (nm, ptr_expr)]
    main_store_i = main_i + 1
    # main ブロック内の icmp (store の後, ブロック末尾まで)
    icmp_i = None
    icmp_m = None
    for j in range(main_store_i + 1, len(lines)):
        l = lines[j]
        if re.match(r'^dec_label|^[\w.$-]+:\s*$|^}', l):
            break
        mm = ICMP_EQ0_RE.match(l)
        if mm:
            icmp_i = j
            icmp_m = mm
            break
    if icmp_i is None:
        rep['f3a_no_icmp'] = rep.get('f3a_no_icmp', 0) + 1
        return 0
    val_set = set()
    drop = []
    if icmp_m.group(4):
        old = icmp_m.group(4)
        lines[icmp_i] = '%s%s = icmp eq i64 %%%s, 0' % (icmp_m.group(1), icmp_m.group(2), nm)
        val_set.add(old)
    else:
        old = icmp_m.group(5)
        lines[icmp_i] = '%s%s = icmp eq i64 %%%s, 0' % (icmp_m.group(1), icmp_m.group(2), nm)
        if old == '%arg1':
            # 旧値 SSA の化け先 = ptrtoint ptr %arg1 (main ブロック内) を alias する
            for k in range(max(0, main_store_i - 8), main_store_i + 1):
                mp = re.match(r'^\s*(%[\w.$-]+) = ptrtoint ptr %arg1 to i64\s*$', lines[k]) if (k < len(lines) and lines[k]) else None
                if mp:
                    # 全使用が main_store_i 以降 (単一 pred 連鎖内) であることを確認
                    uses_ok = True
                    for kk, ll in enumerate(lines):
                        if kk <= main_store_i or not ll:
                            continue
                        if re.search(r'(?<![\w.$-])' + re.escape(mp.group(1)) + r'(?![\w.$-])', ll):
                            ia2 = block_index(blk_at, kk)
                            if ia2 is None:
                                uses_ok = False
                    if uses_ok:
                        val_set.add(mp.group(1))
                        drop.append(k)
        else:
            val_set.add(old)
    if not val_set:
        rep['f3a_no_oldval_ssa'] = rep.get('f3a_no_oldval_ssa', 0) + 1
        return 0
    # 感染伝播 (main ブロック残り + 単一 pred 連鎖)
    fixed_slots = {}
    n = propagate(lines, icmp_i + 1, val_set, nm, fixed_slots)
    # arg1 ptrtoint alias 行の削除 (全使用が置換済みの場合のみ drop に入る)
    for k in drop:
        lines[k] = None
    # thread 系ブロックの修復
    t = repair_threads(lines, stores, main_i, fixed_slots, nm)
    # 整合確認: fixed slot への全 store が修復済み値か (他 path から未修復 store が来たら revert)
    ok_vals = set()
    for k, l in enumerate(lines):
        if l and ('%%%s ' % nm in l or re.search(r'%%%s_t\d+' % nm, l)):
            md = re.match(r'^\s*(%[\w.$-]+) = ', l)
            if md:
                ok_vals.add(md.group(1))
    ok_vals.add('%' + nm)
    bad = None
    # thread ブロック (= arg1-store を含み main でないブロック) 内の未修復 store のみ問題
    thread_ranges = []
    for (si, _sm) in stores:
        if si == main_i:
            continue
        adj = si + 1 if si > main_i else si
        a = adj
        while a > 0 and not (re.match(r'^dec_label', lines[a - 1] or '')):
            a -= 1
        b = adj
        while b < len(lines) and not re.match(r'^dec_label|^}', lines[b]):
            b += 1
        thread_ranges.append((a, b))
    for k, l in enumerate(lines):
        if not l:
            continue
        ms3 = re.match(r'^\s*store (i64|ptr) ([\w.%$]+|zeroinitializer), ptr (%[\w.$-]+)((?:, align \d+)?)\s*$', l)
        if ms3 and ms3.group(3) in fixed_slots and ms3.group(2) not in ok_vals:
            if any(a <= k < b for (a, b) in thread_ranges):
                bad = (k, l.strip())
                break
    if bad:
        log('f3a slot other store in %s: %s' % (fn.name, bad[1]))
        fn.body = body0
        rep['f3a_slot_other_store'] = rep.get('f3a_slot_other_store', 0) + 1
        return 0
    if any(l is None for l in lines):
        lines = [l for l in lines if l is not None]
    fn.body = '\n'.join(lines)
    if n:
        rep['f3a_propagated'] = rep.get('f3a_propagated', 0) + n
    if t:
        rep['f3a_thread_fixes'] = rep.get('f3a_thread_fixes', 0) + t
    return 1


def store_ptr_of(line):
    m = re.match(r'^\s*store [^,]+, ptr (%[\w.$-]+|inttoptr \(i64 %arg1 to ptr\))', line)
    return m.group(1) if m else None


def block_index(blk_at, line_i):
    for (bva, ia, ib) in blk_at:
        if ia <= line_i < ib:
            return bva
    return None


def propagate(lines, start, val_set, nm, fixed_slots):
    """val_set (= 旧値) の使用を %nm へ置換。単一 pred 連鎖のみ。派生 def の operand 置換で
    意味は保たれるため、派生値自身は val_set に入れない (使われ方が別値のため)。
    slot store を検出したら fixed_slots に記録 (thread 修復用)。"""
    n = 0
    off_map = {}      # def SSA → old からの offset (add i64 %old, K)
    ptr_map = {}      # def SSA → offset (inttoptr i64 %d) : ptr of old+K
    i = start
    cur_blk_first = None
    in_start_blk = True
    while i < len(lines):
        l = lines[i]
        if l is None:
            i += 1
            continue
        if re.match(r'^dec_label', l) or re.match(r'^[\w.$-]+:\s*$', l):
            cur_blk_first = i
            in_start_blk = False
            i += 1
            continue
        if l.startswith('}'):
            break
        if not in_start_blk and cur_blk_first is not None:
            mp = re.search(r'; preds = (.+)$', lines[cur_blk_first])
            if not mp or len(mp.group(1).split(',')) != 1:
                break
        # store i64 %v → slot
        ms = re.match(r'^(\s*)store i64 (%[\w.$-]+), ptr (%[\w.$-]+)((?:, align \d+)?)\s*$', l)
        if ms and ms.group(2) in val_set and ms.group(3).endswith('.reg2mem'):
            slot = ms.group(3)
            if slot not in fixed_slots:
                fixed_slots[slot] = ('i64', 0)
                lines[i] = '%sstore i64 %%%s, ptr %s%s' % (ms.group(1), nm, slot, ms.group(4) or '')
                n += 1
            i += 1
            continue
        # store ptr %p → slot (p は旧値派生ポインタ)
        ms2 = re.match(r'^(\s*)store ptr (%[\w.$-]+), ptr (%[\w.$-]+)((?:, align \d+)?)\s*$', l)
        if ms2 and ms2.group(2) in ptr_map and ms2.group(3).endswith('.reg2mem'):
            slot = ms2.group(3)
            if slot not in fixed_slots:
                fixed_slots[slot] = ('ptr', ptr_map[ms2.group(2)])
            i += 1
            continue
        # inttoptr i64 %d (d = 旧値 or 旧値+offset)
        mi = re.match(r'^\s*(%[\w.$-]+) = inttoptr i64 (%[\w.$-]+) to ptr\s*$', l)
        if mi and (mi.group(2) in val_set or mi.group(2) in off_map):
            K = off_map.get(mi.group(2), 0)
            new = l.replace(' ' + mi.group(2) + ' to ptr', ' %%%s to ptr' % nm)
            lines[i] = new
            ptr_map[mi.group(1)] = K
            n += 1
            i += 1
            continue
        # add/sub i64 %v, K (旧値の派生) — operand を張り替えて offset を記録
        ma = re.match(r'^(\s*%[\w.$-]+ = )((?:add|sub) i64) (%[\w.$-]+), (\d+|-?\d+)\s*$', l)
        if ma and ma.group(3) in val_set:
            K = int(ma.group(4)) * (1 if ma.group(2).startswith('add') else -1)
            d = ma.group(1).split('=')[0].strip()[1:]
            new = re.sub(r'(?<![\w.$-])' + re.escape(ma.group(3)) + r'(?![\w.$-])', '%%%s' % nm, l)
            lines[i] = new
            off_map['%' + d] = K
            n += 1
            i += 1
            continue
        # 汎用: val_set の値位置使用を置換
        new = l
        for v in val_set:
            if v == '%arg1':
                continue
            new = re.sub(r'(?<![\w.$-])' + re.escape(v) + r'(?![\w.$-])', '%%%s' % nm, new)
        if new != l:
            lines[i] = new
            n += 1
        i += 1
    return n


def repair_threads(lines, stores, main_i, fixed_slots, nm):
    """stores: [(line_idx, match)] のリスト (main 挿入前の index)"""
    if not fixed_slots:
        return 0
    n = 0
    tctr = 0
    for (si, _sm) in sorted(stores, key=lambda x: x[0]):
        if si == main_i:
            continue
        adj = si + 1 if si > main_i else si
        sm = re.match(r'^(\s*)store i64 (%[\w.$-]+), ptr (%[\w.$-]+)((?:, align \d+)?)\s*$', lines[adj])
        if not sm:
            continue
        tctr += 1
        tn = '%s_t%d' % (nm, tctr)
        lines[adj:adj] = ['  %%%s = load i64, ptr %s, align 8' % (tn, sm.group(3))]
        n += 1
        k = adj + 2
        done_slots = set()
        while k < len(lines) and not re.match(r'^dec_label|^[\w.$-]+:\s*$|^}', lines[k]):
            ms2 = re.match(r'^(\s*)store (i64|ptr) ([\w.%$]+|zeroinitializer), ptr (%[\w.$-]+)((?:, align \d+)?)\s*$', lines[k])
            if ms2 and ms2.group(4) in fixed_slots and ms2.group(4) not in done_slots:
                kind, K = fixed_slots[ms2.group(4)]
                done_slots.add(ms2.group(4))
                if kind == 'i64':
                    lines[k] = '%sstore i64 %%%s, ptr %s%s' % (ms2.group(1), tn, ms2.group(4), ms2.group(5) or '')
                    n += 1
                elif K == 0:
                    lines[k] = '%sstore ptr %%%s_p, ptr %s%s' % (ms2.group(1), tn, ms2.group(4), ms2.group(5) or '')
                    n += 1
                else:
                    lines[k:k] = ['  %%%s_a = add i64 %%%s, %d' % (tn, tn, K),
                                  '  %%%s_p = inttoptr i64 %%%s_a to ptr' % (tn, tn)]
                    lines[k + 2] = '%sstore ptr %%%s_p, ptr %s%s' % (ms2.group(1), tn, ms2.group(4), ms2.group(5) or '')
                    n += 3
                    k += 2
            k += 1
    return n


# ---------------------------------------------------------------------------
# F3b: xor i64 0,0 化した zero-disp load の復元 (4123c0 系)
# ---------------------------------------------------------------------------

def prologue_homes(mach):
    homes = {}
    cnt = 0
    for ins in mach.ins[:24]:
        if ins.mnemonic != 'mov':
            continue
        try:
            o0, o1 = ins.operands
        except Exception:
            continue
        if len(ins.operands) != 2 or o0.type != 3 or o1.type != 1:
            continue
        if o0.mem.index or o0.size * 8 != 64:
            continue
        basen = mach.cs.reg_name(o0.mem.base)
        if basen not in ('rbp', 'rsp'):
            continue
        r = mach.cs.reg_name(o1.reg)
        if r in ARGREG_ARG:
            homes[(basen, o0.mem.disp)] = ARGREG_ARG[r]
            cnt += 1
        if cnt > 8:
            break
    return homes


def base_resolves_to_arg(mach, blk_ins, base, homes, upto):
    """ブロック先頭〜upto 命令で base レジスタの値が argN に解決できるか"""
    cur = ARGREG_ARG.get(base)
    for ins in blk_ins[:upto]:
        if ins.mnemonic != 'mov':
            continue
        try:
            o0, o1 = ins.operands
        except Exception:
            continue
        if len(ins.operands) != 2 or o0.type != 1:
            continue
        if gprnorm(mach.cs, o0.reg) != base:
            continue
        if o1.type == 1:
            r1 = gprnorm(mach.cs, o1.reg)
            cur = ARGREG_ARG.get(r1, 'unk')
        elif o1.type == 3:
            b1 = gprnorm(mach.cs, o1.mem.base) if o1.mem.base else None
            if b1 in ('rbp', 'rsp') and not o1.mem.index and (b1, o1.mem.disp) in homes:
                cur = homes[(b1, o1.mem.disp)]
            else:
                cur = 'unk'
        else:
            cur = 'unk'
    return cur if isinstance(cur, int) else None


def fix_f3b(fn, mach, rep, ctr):
    lines = fn.body.split('\n')
    blocks = fn.blocks()
    cum = 0
    blk_meta = []
    for (bva, ls) in blocks:
        blk_meta.append((bva, cum, cum + len(ls), ls))
        cum += len(ls)
    mblk, _ins = fn_mach_blocks(mach, fn.va, [b[0] for b in blk_meta if b[0] is not None])
    if mblk is None:
        return 0
    homes = prologue_homes(mach)
    bvs_sorted = sorted(b for b in mblk if b is not None)
    # 自己 xor を含むブロックはゼロ化イディオムの可能性が高いので除外
    selfxor = set()
    for i in mach.ins:
        if i.mnemonic == 'xor' and len(i.operands) == 2 and i.operands[0].type == 1 and i.operands[0].reg == i.operands[1].reg:
            k = bisect.bisect_right(bvs_sorted, i.address)
            if k:
                selfxor.add(bvs_sorted[k - 1])
    fixed = 0
    edits = {}
    for (bva, ia, ib, ls) in blk_meta:
        if bva is None or bva in selfxor:
            continue
        xs = [(ia + k, XOR0_RE.match(l)) for k, l in enumerate(ls) if XOR0_RE.match(l)]
        if len(xs) != 1:
            continue
        xi, xm = xs[0]
        mins = mblk.get(bva, [])
        zl = []
        for ins in mins:
            if ins.mnemonic != 'mov':
                continue
            try:
                o0, o1 = ins.operands
            except Exception:
                continue
            if len(ins.operands) != 2 or o0.type != 1 or o1.type != 3:
                continue
            if o1.mem.index or o1.mem.disp or not o1.mem.base:
                continue
            bn = mach.cs.reg_name(o1.mem.base)
            if bn in ('rsp', 'rbp'):
                continue
            zl.append((gprnorm(mach.cs, o0.reg), bn, o1.size * 8, ins))
        if len(zl) != 1:
            continue
        rD, rB, bits, insL = zl[0]
        idx = mins.index(insL) + 1 if insL in mins else len(mins)
        argn = base_resolves_to_arg(mach, mins, rB, homes, idx)
        if argn is None:
            rep['f3b_base_unresolved'] = rep.get('f3b_base_unresolved', 0) + 1
            continue
        blk_text = '\n'.join(lines[ia:ib])
        if re.search(r'load [i0-9]+, ptr %%arg%d(?![\w.$-])' % argn, blk_text):
            rep['f3b_load_present'] = rep.get('f3b_load_present', 0) + 1
            continue
        xname = xm.group(2)
        truncm = re.search(r'^\s*(%[\w.$-]+) = trunc i64 ' + re.escape(xname) + r' to i32\s*$', blk_text, re.M)
        icmpm = re.search(r'icmp eq i32 (%[\w.$-]+), 0[\s\S]{0,200}?br i1', blk_text)
        shape_ok = bool(truncm and icmpm and truncm.group(1) == icmpm.group(1))
        slot = find_loop_slot(fn, lines, blk_meta, bva, rD)
        if not shape_ok and slot is None:
            rep['f3b_use_shape'] = rep.get('f3b_use_shape', 0) + 1
            continue
        ctr[0] += 1
        # 引数の型を確認 (ptr でない場合は inttoptr 命令を挟む)
        hd = re.match(r'^define [^@]*@function_[0-9a-f]+\(([^)]*)\)', fn.body)
        pty = 'ptr'
        if hd:
            ps = [p.strip().split() for p in hd.group(1).split(',') if p.strip()]
            if len(ps) >= argn and len(ps[argn - 1]) >= 1:
                pty = ps[argn - 1][0]
        aptr = '%%arg%d' % argn if pty == 'ptr' else None
        pre = []
        if aptr is None:
            nm0 = 'ldfxz%d' % ctr[0]
            pre = ['  %%%s_p = inttoptr %s %%arg%d to ptr' % (nm0, pty, argn)]
            aptr = '%%%s_p' % nm0
        if bits == 64:
            edits[xi] = pre + ['  %s = load i64, ptr %s, align 8' % (xname, aptr)]
        else:
            nm = 'ldfxz%d' % ctr[0]
            edits[xi] = pre + ['  %%%s = load i%d, ptr %s, align %d' % (nm, bits, aptr, max(bits // 8, 1)),
                               '  %s = zext i%d %%%s to i64' % (xname, bits, nm)]
        if slot is not None:
            edits[xi].append('  store i64 %s, ptr %s, align 8' % (xname, slot))
        fixed += 1
    if not fixed:
        return 0
    out = []
    for i, l in enumerate(lines):
        if i in edits:
            out.extend(edits[i])
        else:
            out.append(l)
    fn.body = '\n'.join(out)
    return fixed


def find_loop_slot(fn, lines, blk_meta, blk_va, rD):
    """rD レジスタ対応の reg2mem slot のうち、このブロックに store が無く、
    このブロックを pred に持つ (loop header の) ブロックで reload されるもの。"""
    rname = {'eax': 'rax', 'ecx': 'rcx', 'edx': 'rdx', 'esi': 'rsi', 'edi': 'rdi',
             'r8d': 'r8', 'r9d': 'r9'}.get(rD, rD)
    slots = []
    for (bva, ia, ib, ls) in blk_meta:
        for k, l in enumerate(ls):
            m = re.match(r'^\s*(%' + rname + r'[\w.]*\.reg2mem) = alloca i64', l)
            if m:
                slots.append(m.group(1))
    if not slots:
        return None
    body = '\n'.join(lines[blk_meta[[b[0] for b in blk_meta].index(blk_va)][1]:
                           blk_meta[[b[0] for b in blk_meta].index(blk_va)][2]])
    for s in slots:
        if (', ptr %s' % s) in body and 'store' in body:
            return None
    # このブロックを pred に持つブロックで reload されるか
    pred_tag = '%%dec_label_pc_%x' % blk_va
    for (bva, ia, ib, ls) in blk_meta:
        head = ls[0] if ls else ''
        mp = re.search(r'; preds = (.+)$', head)
        if not mp or pred_tag not in mp.group(1):
            continue
        for l in ls[1:8]:
            if re.match(r'^\s*%[\w.$-]+ = load i64, ptr ' + re.escape(s) + r'(, align \d+)?\s*$', l):
                return s
    return None


# ---------------------------------------------------------------------------
# F3c: zero-disp load 落ち → ベースレジスタ値の store 化 (`mov r8,[rcx]` → `store %arg1`)
# ---------------------------------------------------------------------------

def fix_f3c(fn, fv, rep, ctr):
    """機械語 `mov rD,[rB]` (zero-disp) の読みが IR で消え、ベースレジスタ (argN) の値が
    そのまま store されている形を復元する (_UStrAsg 409ca4 系 = D7 値↔アドレスの別形)。"""
    lines = fn.body.split('\n')
    blocks = fn.blocks()
    cum = 0
    blk_meta = []
    for (bva, ls) in blocks:
        blk_meta.append((bva, cum, cum + len(ls), ls))
        cum += len(ls)
    mblk, _ins = fn_mach_blocks(fv, fn.va, [b[0] for b in blk_meta if b[0] is not None])
    if mblk is None:
        return 0
    homes = prologue_homes(fv)
    # 引数型表
    hd = re.match(r'^define [^@]*@function_[0-9a-f]+\(([^)]*)\)', fn.body)
    pty = {}
    if hd:
        for idx, p in enumerate([p.strip() for p in hd.group(1).split(',') if p.strip()]):
            t = p.split()[0] if p.split() else 'i64'
            pty[idx + 1] = t
    fixed = 0
    edits = {}
    for (bva, ia, ib, ls) in blk_meta:
        if bva is None:
            continue
        mins = mblk.get(bva, [])
        zl = []
        for ins in mins:
            if ins.mnemonic != 'mov':
                continue
            try:
                o0, o1 = ins.operands
            except Exception:
                continue
            if len(ins.operands) != 2 or o0.type != 1 or o1.type != 3:
                continue
            if o1.mem.index or o1.mem.disp or not o1.mem.base:
                continue
            bn = fv.cs.reg_name(o1.mem.base)
            if bn not in ARGREG_ARG:
                continue
            zl.append((fv.cs.reg_name(o0.reg), bn, o1.size * 8, ins))
        if len(zl) != 1:
            continue
        rD, rB, bits, insL = zl[0]
        idx = mins.index(insL) + 1 if insL in mins else len(mins)
        argn = base_resolves_to_arg(fv, mins, rB, homes, idx)
        if argn is None:
            continue
        blk_text = '\n'.join(lines[ia:ib])
        # IR ブロック内に arg からの load が既にある → 落ちていない
        if re.search(r'load [i0-9]+, ptr [^,\n]*%%arg%d(?![\w.$-])' % argn, blk_text):
            continue
        # 機械語が rB をそのまま store している → ポインタ store は正当なので触らない
        reg_store = False
        for ins in mins:
            if ins.mnemonic != 'mov':
                continue
            try:
                o0, o1 = ins.operands
            except Exception:
                continue
            if len(ins.operands) == 2 and o0.type == 3 and o1.type == 1 and fv.cs.reg_name(o1.reg) == rB:
                reg_store = True
        if reg_store:
            rep['f3c_reg_store'] = rep.get('f3c_reg_store', 0) + 1
            continue
        # store の値が argN (生 / trunc / zext) の行を探す
        stores = []
        for k in range(ia, ib):
            l = lines[k]
            ms = re.match(r'^(\s*)store ([i]\d+) %arg' + str(argn) + r'(?:, |, ptr )(.*?)((?:, align \d+)?)\s*$', l)
            if ms and ms.group(3).startswith('ptr '):
                stores.append((k, ms, None))
                continue
            ms2 = re.match(r'^(\s*)store ([i]\d+) (%[\w.$-]+), ptr ', l)
            if ms2:
                for tline in lines[ia:ib]:
                    mt = re.match(r'^\s*(%[\w.$-]+) = trun[cz] i64 %arg' + str(argn) + ' to ' + re.escape(ms2.group(2)) + r'\s*$', tline)
                    if mt and mt.group(1) == ms2.group(2):
                        stores.append((k, ms2, tline))
        if not stores:
            rep['f3c_no_store'] = rep.get('f3c_no_store', 0) + 1
            continue
        # argN の ptr 式
        t = pty.get(argn, 'i64')
        aptr = '%%arg%d' % argn
        pre = []
        if t != 'ptr':
            nm0 = 'ldfxc%d' % (ctr[0] + 1)
            pre = ['  %%%s_p = inttoptr %s %%arg%d to ptr' % (nm0, t, argn)]
            aptr = '%%%s_p' % nm0
        ctr[0] += 1
        for (k, ms, tline) in stores:
            ty = ms.group(2)
            width = int(ty[1:])
            if bits != width:
                # 機械語の読み幅と store 幅が不一致 → 見送り (保守的)
                continue
            nm = 'ldfxc%d' % ctr[0]
            ld = '  %%%s = load %s, ptr %s, align %d' % (nm, ty, aptr, max(width // 8, 1))
            l = lines[k]
            newl = re.sub('(store ' + ty + ' )%arg' + str(argn) + '(?![\\w.$-])', lambda mm: mm.group(1) + '%' + nm, l, count=1)
            if newl == l:
                newl = l.replace(' ' + ms.group(3) + ',', ' %%%s,' % nm, 1)
            if newl != l:
                if tline is not None:
                    # trunc/zext 行は死ぬが残してよい (DCE)
                    pass
                edits[k] = ('before', pre + [ld]) if k not in edits else edits[k]
                # 複数 store がある場合は 2 つ目以降も同じ load を使う (block 内 dominant)
                lines[k] = newl
                fixed += 1
            break
    if not fixed:
        return 0
    out = []
    for i2, l in enumerate(lines):
        if i2 in edits:
            pos, els = edits[i2]
            if pos == 'before':
                out.extend(els)
        out.append(l)
    fn.body = '\n'.join(out)
    return fixed


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('infile')
    ap.add_argument('outfile')
    ap.add_argument('--pe', required=True)
    ap.add_argument('--report')
    ap.add_argument('--only', help='カンマ区切りの VA (16進) のみ修復')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    only = set(int(x, 16) for x in a.only.split(',')) if a.only else None
    text = open(a.infile, errors='replace').read()
    mach = Machine(a.pe)
    rep = collections.OrderedDict()
    ctr = [0]
    counts = collections.OrderedDict((k, 0) for k in ('f1', 'f2', 'f3a', 'f3b', 'f3c'))
    fn_lists = collections.OrderedDict((k, []) for k in ('f1', 'f2', 'f3a', 'f3b', 'f3c'))
    out_parts = []
    last = 0
    nfn = 0
    for m in DEF_RE.finditer(text):
        va = int(m.group('name')[len('function_'):], 16)
        if only and va not in only:
            continue
        end = text.index('\n}', m.end()) + 2
        out_parts.append(text[last:m.start()])
        fn = Fn(m.group('name'), va, text[m.start():end])
        nfn += 1
        blk_vas = [bva for (bva, _ls) in fn.blocks() if bva is not None]
        fv = FnMach(mach, va, blk_vas)
        try:
            for tag, func in (('f1', fix_f1), ('f2', fix_f2), ('f3a', fix_f3a), ('f3b', fix_f3b), ('f3c', fix_f3c)):
                if func(fn, fv, rep, ctr):
                    counts[tag] += 1
                    fn_lists[tag].append('%x' % va)
        except Exception as e:
            rep['errors'] = rep.get('errors', 0) + 1
            log('error in %s: %r' % (fn.name, e))
        out_parts.append(fn.body)
        last = end
    out_parts.append(text[last:])
    rep['functions_processed'] = nfn
    for k in counts:
        rep[k + '_fns'] = counts[k]
        rep[k + '_vas'] = fn_lists[k]
    log('F1(load_dropped)=%d F2(spill_slot)=%d F3a(old-value)=%d F3b(count-load)=%d F3c(store-arg)=%d (errors=%d)'
        % (counts['f1'], counts['f2'], counts['f3a'], counts['f3b'], counts['f3c'], rep.get('errors', 0)))
    if not a.dry_run:
        open(a.outfile, 'w').write(result := ''.join(out_parts))
    if a.report:
        json.dump(rep, open(a.report, 'w'), indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
