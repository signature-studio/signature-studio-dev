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
  F3d 入口の型タグ読みの復元 (LD-127 #2745・既定無効、`--passes f3d` で有効):
    入口ブロックの `movzx r16, word ptr [argN]` (VARIANT の型タグ読み) が `xor i64 0,0` に化けた site を
    `load i16` + zext に戻す。入口 xor のうち trunc i16 / and で使われるものが 1 本のときだけ。

  F4 frame_read_dropped (escape 済み stack_var 内部の read, #564 / function_52a7f0):
    `cmp [rbp+0x70], rcx` の被 read は callee (GetClassInfoW) が書く escape 済み `%stack_var_-96` の +8 だが、RetDec が
    store 無しの別 alloca の load (= undef) にし、m5 ir5_patch B1 が `xor i64 0, 0` に固定する (比較が定数に畳まれ分岐が消える)。
    ブロック内 xor-0-0 が 1 本・機械語のその区間に自己 xor 無し・frame read が 1 本で escape 済み stack_var の gap 内に解決・
    その slot への機械語 store 無し・B1 の残骸 (使用ゼロの無名 alloca) 有り、が揃ったとき stack_var + 偏移の load に置換する。

使い方: python3 ldfix.py IN.ll OUT.ll --pe PE.bin [--report OUT.json] [--only 4133f0,...] [--passes f3c] [--no-f4] [--dry-run]
"""
import argparse
import bisect
import collections
import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ldmach import Machine, FnMach, memops_of  # noqa: E402
from ldframe import is_write_only, frame_model, escaped_stack_vars  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lb_base import LB, IMG_BASE  # noqa: E402

BASE = IMG_BASE - LB   # IR の LVA 定数 c0 → rip_rva(VA) は c0 + BASE (M11_LB_BASE 補正込み)
DEF_RE = re.compile(r'^define (?P<ret>[^@]*?)@(?P<name>function_[0-9a-f]+)\((?P<args>[^)]*)\)(?P<rest>[^{]*)\{', re.M)
BLK_RE = re.compile(r'^dec_label_pc_(?P<va>[0-9a-f]+)(?:\.[\w.$-]+)?:', re.M)   # .thread / .dec_label_pc_*_crit_edge 接尾ラベルも VA 付きブロック
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
            elif re.match(r'^[\w.$-]+:\s*(;.*)?$', l):   # `; preds = ...` 付きラベルも新ブロック
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
# F1v: load_dropped 変種 (CAB-131) — F1 の 3 連形 (pt→trunc→store 直接) から外れる
# 3 変種を吸収する。いずれも機械語の rip 相対 RMW (add/sub dword [g], imm) が正本:
#   (a) direct  : store i32 %tv, [c0] は直接だが, 関数内の別 path に同一 target への
#                 store があり従来の f1_other_store guard で除外されていた (108ec70)
#   (b) select  : %tv が select の operand に合流し, select 結果が [c0] へ store
#                 (106d220: add +1 / sub -1 の両 RMW path の合流)
#   (c) slot    : %tv が reg2mem slot に退避され, merge block の reload が [c0] へ
#                 store (10d35b0: RMW の書込効果が merge store で実現される)
# 修復は値の張替え (load→add を挿入し %tv の全 value use を置換) で, store 自体は
# 増減しない。書込効果の証人として「%tv (直接/select結果/reload値) → [c0] への store」
# を必須条件にする (無い場合は RMW の write が IR から落ちている別欠陥なので触らない)。
# ---------------------------------------------------------------------------

F1V_TRUNC_RE = re.compile(r'^\s*(%[\w.$-]+) = trunc i64 (%[\w.$-]+) to i32\s*$')
F1V_SELECT_RE = re.compile(r'^\s*(%[\w.$-]+) = select i1 (%[\w.$-]+), i32 (%[\w.$-]+), i32 (%[\w.$-]+)\s*$')
F1V_SLOT_ALLOCA_RE = re.compile(r'^\s*(%[\w.$-]+) = alloca i32\s*$')
F1V_SLOT_LOAD_RE = re.compile(r'^\s*(%[\w.$-]+) = load i32, ptr (%[\w.$-]+)\s*$')


def f1v_rip_rmws(fv, c0):
    """target (c0+BASE) への 32bit add/sub RMW を全列挙 → [(mnem, imm, addr)]"""
    out = []
    want = c0 + BASE
    for m in fv.iter_memops():
        if m['kind'] != 'rmw' or m['size_bits'] != 32 or m.get('rip_rva') != want:
            continue
        ins = m['ins']
        if ins.mnemonic in ('add', 'sub') and len(ins.operands) == 2 and ins.operands[1].type == 2:
            out.append((ins.mnemonic, ins.operands[1].imm, ins.address))
    return out


def f1v_mach_block_of(fv, addr):
    import bisect as _bs
    k = _bs.bisect_right(fv.block_starts, addr)
    return fv.block_starts[k - 1] if k else None


def f1v_same_blk(lines, a, b):
    """行 a..b が同一 IR ブロック内か (境界をまたいだら False)"""
    if a > b:
        a, b = b, a
    for l in lines[a + 1:b]:
        if re.match(r'^dec_label|^[\w.$-]+:\s*$|^}', l):
            return False
    return True


def f1v_value_use_lines(lines, name):
    """name の行リスト。アドレス用途 (ptr operand / inttoptr) を含む行があれば None (保守中止)"""
    pat_ptr = re.compile(r', ptr ' + re.escape(name) + r'(?![\w.$-])')
    pat_itp = re.compile(r'inttoptr \(i64 ' + re.escape(name) + r'(?![\w.$-])')
    out = []
    for i, l in enumerate(lines):
        if name not in l:
            continue
        if pat_ptr.search(l) or pat_itp.search(l):
            return None
        out.append(i)
    return out


def f1v_classify(lines, tv, slots):
    """%tv の消費形を分類 → (kind, c0, witness_i) | None"""
    # (a) direct: store i32 %tv, ptr inttoptr (i64 c0 to ptr)
    for i, l in enumerate(lines):
        m = CE_STORE_RE.match(l)
        if m and m.group(1) == tv:
            return ('direct', int(m.group(2)), i)
    # (b) select: %sel = select i1 c, i32 X, i32 %tv (どちらの operand でも) → store %sel, [c0]
    for i, l in enumerate(lines):
        m = F1V_SELECT_RE.match(l)
        if not m or tv not in (m.group(3), m.group(4)):
            continue
        sel = m.group(1)
        tgts = set()
        wi = None
        for j, l2 in enumerate(lines):
            m2 = CE_STORE_RE.match(l2)
            if m2 and m2.group(1) == sel:
                tgts.add(int(m2.group(2)))
                wi = j
        if len(tgts) == 1 and wi is not None and f1v_same_blk(lines, i, wi):
            return ('select', tgts.pop(), wi)
    # (c) slot: store i32 %tv, ptr %slot → (別 block) %rl = load i32, ptr %slot → store %rl, [c0]
    for i, l in enumerate(lines):
        ms = re.match(r'^\s*store i32 ' + re.escape(tv) + r', ptr (%[\w.$-]+)\s*$', l)
        if not ms or ms.group(1) not in slots:
            continue
        slot = ms.group(1)
        for j, l2 in enumerate(lines):
            ml = F1V_SLOT_LOAD_RE.match(l2)
            if not ml or ml.group(2) != slot:
                continue
            rl = ml.group(1)
            for k, l3 in enumerate(lines):
                m3 = CE_STORE_RE.match(l3)
                if m3 and m3.group(1) == rl:
                    if f1v_same_blk(lines, j, k):
                        return ('slot', int(m3.group(2)), k)
    return None


def fix_f1v(fn, fv, rep, ctr):
    lines = fn.body.split('\n')
    slots = set()
    for l in lines:
        m = F1V_SLOT_ALLOCA_RE.match(l)
        if m:
            slots.add(m.group(1))
    pt_at = {}
    for i, l in enumerate(lines):
        m = CE_PT_RE.match(l)
        if m:
            pt_at[m.group(1)] = (i, int(m.group(2)))
    if not pt_at:
        return 0
    tr_of = {}
    for i, l in enumerate(lines):
        m = F1V_TRUNC_RE.match(l)
        if m and m.group(2) in pt_at:
            tr_of.setdefault(m.group(2), []).append((i, m.group(1)))
    fixed = 0
    for pname, (pi, c1) in sorted(pt_at.items(), key=lambda kv: kv[1][0]):
        trs = tr_of.get(pname)
        if not trs or len(trs) != 1:
            continue
        ti, tv = trs[0]
        if ti < pi:
            continue
        uses = f1v_value_use_lines(lines, tv)
        if uses is None:
            rep['f1v_addr_use'] = rep.get('f1v_addr_use', 0) + 1
            continue
        if tv == pname:
            continue
        # pt の使用は trunc のみ (他に value use があれば保守的に見送り)
        pt_use_ok = True
        for j, l in enumerate(lines):
            if j in (pi, ti) or pname not in l:
                continue
            if re.search(r'(?<![\w.$-])' + re.escape(pname) + r'(?![\w.$-])', l):
                pt_use_ok = False
                break
        if not pt_use_ok:
            rep['f1v_pt_other_use'] = rep.get('f1v_pt_other_use', 0) + 1
            continue
        cls = f1v_classify(lines, tv, slots)
        if cls is None:
            rep['f1v_no_consumer'] = rep.get('f1v_no_consumer', 0) + 1
            continue
        kind, c0, wi = cls
        delta = c1 - c0
        rmws = [r for r in f1v_rip_rmws(fv, c0)
                if (r[1] if r[0] == 'add' else -r[1]) == delta]
        if not rmws:
            rep['f1v_no_rmw'] = rep.get('f1v_no_rmw', 0) + 1
            continue
        mnem, imm, raddr = rmws[0]
        if kind == 'direct':
            # 別 path の同一 target store があっても値の張替えは競合しない。
            # ただし store が RMW と同一機械語ブロックにある場合は従来どおり見送り
            # (同一 path で RMW と生 store が混在 = RetDec の別意味の可能性)。
            conflict = False
            for m in fv.iter_memops():
                if (m['kind'] == 'store' and m.get('rip_rva') == c0 + BASE
                        and f1v_mach_block_of(fv, m['addr']) == f1v_mach_block_of(fv, raddr)):
                    conflict = True
                    break
            if conflict:
                rep['f1v_same_blk_store'] = rep.get('f1v_same_blk_store', 0) + 1
                continue
        ctr[0] += 1
        nm = 'ldfxv%d' % ctr[0]
        ld = '  %%%s = load i32, ptr inttoptr (i64 %d to ptr), align 4' % (nm, c0)
        op = '  %%%s_v = add i32 %%%s, %d' % (nm, nm, imm if mnem == 'add' else -imm)
        lines[pi] = ld + '\n' + op
        lines[ti] = None
        pat = re.compile(r'(?<![\w.$-])' + re.escape(tv) + r'(?![\w.$-])')
        ptr_re = re.compile(r', ptr ' + re.escape(tv) + r'(?![\w.$-])')
        itp_re = re.compile(r'inttoptr \(i64 ' + re.escape(tv) + r'(?![\w.$-])')
        nrep = 0
        for j in range(ti + 1, len(lines)):
            l = lines[j]
            if not l or tv not in l:
                continue
            if ptr_re.search(l) or itp_re.search(l):
                continue
            new = pat.sub('%%%s_v' % nm, l)
            if new != l:
                lines[j] = new
                nrep += 1
        lines = [l for l in lines if l is not None]
        rep['f1v_kind_' + kind] = rep.get('f1v_kind_' + kind, 0) + 1
        rep['f1v_value_uses'] = rep.get('f1v_value_uses', 0) + nrep
        fixed += 1
    if fixed:
        fn.body = '\n'.join(lines)
    return fixed


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


# ---------------------------------------------------------------------------
# F3d: 入口の型タグ読み (movzx word [argN]) の xor i64 0,0 化の復元 (LD-127 #2745)
# ---------------------------------------------------------------------------

def fix_f3d(fn, mach, rep, ctr):
    """入口ブロックの 16 bit 型タグ読み `movzx r, word ptr [B]` (B は argN に解決) が
    `xor i64 0,0` に化けた site を load に戻す。lift 段 (boot0.lift.ll) で入った置換が F3b
    (mov 限定・入口 xor 1 本限定) の外に残るため、型タグ読みの形に限った別 pass にする。
    厳密条件 (全て満たすときだけ): 入口ブロック (VA == fn.va) の機械語に movzx word の zero-disp
    load が 1 本 (rsp/rbp 基底は除外)・IR の入口ブロックの xor i64 0,0 のうち結果が
    `trunc i64 %x to i16` か `and i64 %x, <imm>` で使われるものがちょうど 1 本・B が argN に解決。
    """
    lines = fn.body.split('\n')
    blocks = fn.blocks()
    cum = 0
    ent = None
    for (bva, ls) in blocks:
        if bva == fn.va and ent is None:
            ent = (cum, cum + len(ls), ls)
        cum += len(ls)
    if ent is None:
        return 0
    ia, ib, ls = ent
    mblk, _ins = fn_mach_blocks(mach, fn.va, [b for (b, _l) in blocks if b is not None])
    if mblk is None:
        return 0
    mins = mblk.get(fn.va, [])
    tags = []
    for ins in mins:
        if ins.mnemonic != 'movzx' or len(ins.operands) != 2:
            continue
        o0, o1 = ins.operands
        if o0.type != 1 or o1.type != 3 or o1.size != 2:
            continue
        if o1.mem.index or o1.mem.disp or not o1.mem.base:
            continue
        if mach.cs.reg_name(o1.mem.base) in ('rsp', 'rbp'):
            continue
        tags.append((mach.cs.reg_name(o1.mem.base), ins))
    if len(tags) != 1:
        return 0
    rB, insL = tags[0]
    argn = base_resolves_to_arg(mach, mins, rB, prologue_homes(mach), mins.index(insL) + 1)
    if argn is None:
        rep['f3d_base_unresolved'] = rep.get('f3d_base_unresolved', 0) + 1
        return 0
    blk_text = '\n'.join(lines[ia:ib])
    if re.search(r'load [i0-9]+, ptr %%arg%d(?![\w.$-])' % argn, blk_text):
        rep['f3d_load_present'] = rep.get('f3d_load_present', 0) + 1
        return 0
    cands = []
    for k, l in enumerate(ls):
        m = XOR0_RE.match(l)
        if not m:
            continue
        x = re.escape(m.group(2))
        if re.search(r'= trunc i64 %s to i16\s*$' % x, blk_text, re.M) or re.search(r'= and i64 %s, ' % x, blk_text):
            cands.append((ia + k, m))
    if len(cands) != 1:
        rep['f3d_ambiguous'] = rep.get('f3d_ambiguous', 0) + 1
        return 0
    xi, xm = cands[0]
    xname = xm.group(2)
    hd = re.match(r'^define [^@]*@function_[0-9a-f]+\(([^)]*)\)', fn.body)
    ps = [p.strip().split() for p in hd.group(1).split(',') if p.strip()] if hd else []
    if len(ps) < argn or len(ps[argn - 1]) < 1:
        rep['f3d_arg_missing'] = rep.get('f3d_arg_missing', 0) + 1
        return 0
    pty = ps[argn - 1][0]
    aptr = '%%arg%d' % argn if pty == 'ptr' else None
    pre = []
    ctr[0] += 1
    if aptr is None:
        nm0 = 'ldfxt%d' % ctr[0]
        pre = ['  %%%s_p = inttoptr %s %%arg%d to ptr' % (nm0, pty, argn)]
        aptr = '%%%s_p' % nm0
    nm = 'ldfxt%d' % ctr[0]
    edit = pre + ['  %%%s = load i16, ptr %s, align 2' % (nm, aptr),
                  '  %s = zext i16 %%%s to i64' % (xname, nm)]
    out = []
    for i, l in enumerate(lines):
        if i == xi:
            out.extend(edit)
        else:
            out.append(l)
    fn.body = '\n'.join(out)
    return 1


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

F3C_STORE_RE = re.compile(r'^(\s*)store (i\d+|ptr) (%[\w.$-]+), ptr ([^,\n]+)((?:, align \d+)?)\s*$')
F3C_END = ('ret', 'retn', 'ud2', 'int3', 'hlt')
F3C_VOLATILE = ('rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11')
F3C_SAVED = ('rbx', 'rsi', 'rdi', 'r12', 'r13', 'r14', 'r15')
F3C_ARITY = {}      # 関数 VA → IR の define の引数個数 (main が埋める)。直接 call の引数 reg を何本読むかに使う


def _f3c_is_branch(i):
    return i.mnemonic.startswith('j') or i.mnemonic.startswith('loop') or i.mnemonic in F3C_END


def _f3c_leaders(ins):
    """機械語の基本ブロック先頭 (分岐先 / 分岐・ret の直後)。IR ラベルには依存しない"""
    addrs = {i.address for i in ins}
    lead = {ins[0].address}
    for k, i in enumerate(ins):
        if not _f3c_is_branch(i):
            continue
        if k + 1 < len(ins):
            lead.add(ins[k + 1].address)
        if i.operands and i.operands[0].type == 2 and i.operands[0].imm in addrs:
            lead.add(i.operands[0].imm)
    return lead


def _f3c_note_uses(cs, i, st, uses):
    """argN を持つ reg の「使用」を記録する: ('deref', addr, n, 幅, 出所) = zero-disp 64/32bit load の base (出所 'arg' | 'argv') / ('raw', addr, n) = それ以外の読み。
    reg→reg の 64bit コピーと frame への spill は使用に数えない (call の引数 reg・ret の rax は数える)"""
    mn, ops = i.mnemonic, i.operands
    if mn == 'mov' and len(ops) == 2:
        o0, o1 = ops
        if o0.type == 1 and o1.type == 1 and o0.size == 8 and o1.size == 8:
            return
        if o0.type == 1 and o1.type == 3:
            mb = gprnorm(cs, o1.mem.base) if o1.mem.base else None
            if not o1.mem.index and mb in ('rbp', 'rsp'):
                return
            if not o1.mem.index and not o1.mem.disp and mb and o1.size in (4, 8):
                sv = st.get(mb)
                if sv and sv[0] in ('arg', 'argv'):
                    uses.append(('deref', i.address, sv[1], o1.size * 8, sv[0]))
                    return
        if o0.type == 3 and o1.type == 1:
            mb = gprnorm(cs, o0.mem.base) if o0.mem.base else None
            if mb in ('rbp', 'rsp') and not o0.mem.index and o0.size == 8:
                return
    regs = set()
    try:
        for rid in i.regs_access()[0]:
            r = gprnorm(cs, rid)
            if r:
                regs.add(r)
    except Exception:
        pass
    if mn == 'call':
        tgt = ops[0].imm if ops and ops[0].type == 2 else None
        regs.update(list(ARGREG_ARG)[:F3C_ARITY.get(tgt, 4)])
    if mn in ('ret', 'retn'):
        regs.add('rax')
    for r in sorted(regs):
        sv = st.get(r)
        if sv and sv[0] == 'arg':
            uses.append(('raw', i.address, sv[1]))


def _f3c_step(cs, i, st, lsf, ptr, uses=None):
    """命令 1 個の記号実行。値 = ('arg', n) | ('ld', n, 幅) (argN を base にした zero-disp load の値)。
    lsf: load した値を同幅でそのまま store する site → (addr, n, 幅)。ptr: argN 自身の非 frame 宛 store → Counter[(n, 幅)]"""
    mn, ops = i.mnemonic, i.operands
    if uses is not None:
        _f3c_note_uses(cs, i, st, uses)
    dest = newv = None
    if mn == 'mov' and len(ops) == 2:
        o0, o1 = ops
        if o0.type == 1 and o1.type == 1:
            dest = gprnorm(cs, o0.reg)
            if o0.size == 8 and o1.size == 8:
                newv = st.get(gprnorm(cs, o1.reg))
        elif o0.type == 1 and o1.type == 3:
            dest = gprnorm(cs, o0.reg)
            mb = gprnorm(cs, o1.mem.base) if o1.mem.base else None
            if not o1.mem.index and mb in ('rbp', 'rsp'):
                if o1.size == 8:
                    newv = st.get(('m', mb, o1.mem.disp))
            elif not o1.mem.index and not o1.mem.disp and mb and o1.size in (4, 8):
                sv = st.get(mb)
                if sv and sv[0] == 'arg':
                    newv = ('ld', sv[1], o1.size * 8)
        elif o0.type == 3 and o1.type == 1:
            sv = st.get(gprnorm(cs, o1.reg))
            mb = gprnorm(cs, o0.mem.base) if o0.mem.base else None
            w = o0.size * 8
            frame = mb in ('rbp', 'rsp') and not o0.mem.index
            if frame:
                if sv and w == 64:
                    st[('m', mb, o0.mem.disp)] = sv
                else:
                    st.pop(('m', mb, o0.mem.disp), None)
            if lsf is not None and sv:
                if sv[0] == 'ld' and sv[2] == w:
                    lsf.append((i.address, sv[1], w))
                elif sv[0] == 'arg' and not frame:
                    ptr[(sv[1], w)] += 1
    if mn == 'call':
        for r in F3C_VOLATILE:
            st.pop(r, None)
    else:
        try:
            wr = i.regs_access()[1]
        except Exception:
            wr = ()
        for rid in wr:
            r = gprnorm(cs, rid)
            if r:
                st.pop(r, None)
    if dest and newv:
        st[dest] = newv


def _f3c_static_state(cs, ins):
    """entry の直線部分 (最初の分岐/ret まで) で argN から 1 回だけ代入される callee-saved reg と、1 回だけ書かれる frame slot
    (`mov [rbp+d], rcx` の home)。→ (regdef: {reg: (n, def の addr)}, slotdef: {(base, disp): n})。
    ブロック単位の記号実行へ持ち込む (base を reg コピー・frame slot 経由まで追跡する G2 の拡張)"""
    st = {r: ('arg', n) for r, n in ARGREG_ARG.items()}
    regdef, slotdef = {}, {}
    for i in ins:
        if _f3c_is_branch(i):
            break
        before = dict(st)
        _f3c_step(cs, i, st, None, None)
        for k, v in st.items():
            if v[0] != 'arg' or before.get(k) == v:
                continue
            if isinstance(k, tuple):
                slotdef.setdefault(k[1:], []).append(v[1])
            elif k in F3C_SAVED:
                regdef.setdefault(k, []).append((v[1], i.address))
    nslot, leas = collections.Counter(), []
    for i in ins:
        ops = i.operands
        if i.mnemonic == 'lea' and len(ops) == 2 and ops[1].type == 3 and ops[1].mem.base:
            b = gprnorm(cs, ops[1].mem.base)
            if b in ('rbp', 'rsp'):
                leas.append((b, ops[1].mem.disp))
        if ops and ops[0].type == 3 and i.mnemonic not in ('cmp', 'test', 'push'):
            b = gprnorm(cs, ops[0].mem.base) if ops[0].mem.base else None
            if b in ('rbp', 'rsp'):
                nslot[(b, ops[0].mem.disp)] += 1
    sreg = {r: v[0] for r, v in regdef.items() if len(v) == 1}
    sslot = {k: v[0] for k, v in slotdef.items()
             if len(v) == 1 and nslot[k] == 1 and not any(k[0] == b and k[1] <= d < k[1] + 8 for (b, d) in leas)}
    return sreg, sslot


def _f3c_bump_slots(cs, ins, sslot):
    """引数ポインタを写し、ループ内で `add/sub [slot], imm` だけで前進させる frame slot → argN (#1324)。
    slot への書き込みが「argN の reg からの 64bit mov」1 本と bump だけの slot を採る。値は argN+可変なので、
    deref 記録 ('argv') にだけ使い、lsf/ptr/raw/fix_f3c_use の門 (出所 'arg' の deref だけ数える) には使わない"""
    st = {r: ('arg', n) for r, n in ARGREG_ARG.items()}
    plain, bump = collections.defaultdict(list), collections.Counter()
    for i in ins:
        ops = i.operands
        if ops and ops[0].type == 3 and i.mnemonic not in ('cmp', 'test', 'push'):
            b = gprnorm(cs, ops[0].mem.base) if ops[0].mem.base else None
            if b in ('rbp', 'rsp') and not ops[0].mem.index:
                k = (b, ops[0].mem.disp)
                if i.mnemonic in ('add', 'sub') and len(ops) == 2 and ops[1].type == 2:
                    bump[k] += 1
                else:
                    sv = st.get(gprnorm(cs, ops[1].reg)) if i.mnemonic == 'mov' and len(ops) == 2 and ops[1].type == 1 else None
                    plain[k].append(sv[1] if sv and sv[0] == 'arg' and ops[0].size == 8 else None)
        _f3c_step(cs, i, st, None, None)
    out = {}
    for k, srcs in plain.items():
        if bump[k] and len(srcs) == 1 and srcs[0] is not None and k not in sslot:
            out[k] = srcs[0]
    return out


def _f3c_regs_by_block(cs, blocks, sreg):
    """各ブロック先頭で argN をそのまま持っている reg: 引数 reg (rcx/rdx/r8/r9) と、entry で 1 回代入された callee-saved reg (sreg)。
    reg を書く命令 (def 自身を除く。call は volatile 全部を書く) があるブロックの後続へ到達閉包を取り、その外側だけを残す"""
    bidx = {b[0].address: k for k, b in enumerate(blocks)}
    succ = []
    for k, b in enumerate(blocks):
        last = b[-1]
        mn = last.mnemonic
        tgt = last.operands[0].imm if last.operands and last.operands[0].type == 2 else None
        nxt = [k + 1] if k + 1 < len(blocks) else []
        if mn == 'jmp':
            succ.append([bidx[tgt]] if tgt in bidx else [])
        elif mn.startswith('j') or mn.startswith('loop'):
            succ.append(([bidx[tgt]] if tgt in bidx else []) + nxt)
        elif mn in F3C_END:
            succ.append([])
        else:
            succ.append(nxt)
    track = {r: (ARGREG_ARG[r], None) for r in ARGREG_ARG}
    track.update({r: (n, a) for r, (n, a) in sreg.items()})
    writers = {r: set() for r in track}
    for k, b in enumerate(blocks):
        for i in b:
            if i.mnemonic == 'call':
                for r in F3C_VOLATILE:
                    if r in writers:
                        writers[r].add(k)
                continue
            try:
                wr = i.regs_access()[1]
            except Exception:
                wr = ()
            for rid in wr:
                r = gprnorm(cs, rid)
                if r in writers and track[r][1] != i.address:
                    writers[r].add(k)
    keep = [set(track) for _ in blocks]
    for r, ws in writers.items():
        seen, todo = set(), [x for w in ws for x in succ[w]]
        while todo:
            x = todo.pop()
            if x in seen:
                continue
            seen.add(x)
            todo.extend(succ[x])
        for x in seen:
            keep[x].discard(r)
    keep[0] = set(ARGREG_ARG)
    return keep, {r: v[0] for r, v in track.items()}


def f3c_track(fv):
    """F3c 機械語側。→ (lsf: [(addr, n, 幅)], ptr: Counter[(n, 幅)], uses, entry ブロックの命令 addr 集合)。ブロック間の join は使わず、各ブロックを
    「到達するどの経路でも書き換えられていない引数 reg / entry で 1 回代入された callee-saved reg / 1 回だけ書かれる frame home」から
    記号実行する (関数単位の個数収支で IR と突合するため IR ブロックとの対応は不要)"""
    ins = fv.ins
    if not ins:
        return None
    lead = _f3c_leaders(ins)
    sreg, sslot = _f3c_static_state(fv.cs, ins)
    blocks, cur = [], []
    for i in ins:
        if i.address in lead and cur:
            blocks.append(cur)
            cur = []
        cur.append(i)
    blocks.append(cur)
    keep, argof = _f3c_regs_by_block(fv.cs, blocks, sreg)
    lsf, ptr, uses = [], collections.Counter(), []
    bumps = _f3c_bump_slots(fv.cs, ins, sslot)
    for k, b in enumerate(blocks):
        st = {r: ('arg', argof[r]) for r in keep[k]}
        for (bs, d), n in sslot.items():
            st[('m', bs, d)] = ('arg', n)
        for (bs, d), n in bumps.items():
            st[('m', bs, d)] = ('argv', n)
        for i in b:
            _f3c_step(fv.cs, i, st, lsf, ptr, uses)
    return lsf, ptr, uses, {i.address for i in blocks[0]}


def f3c_ir_stores(lines):
    """IR 側: `store iW %argN` (trunc/zext 経由含む、alloca 宛を除く) の行 → {(n, 幅): [行 index]}"""
    allocas, alias = set(), {}
    for l in lines:
        m = re.match(r'^\s*(%[\w.$-]+) = alloca ', l)
        if m:
            allocas.add(m.group(1))
        m = re.match(r'^\s*(%[\w.$-]+) = (?:trunc|zext) i64 %arg(\d+) to i(\d+)\s*$', l)
        if m:
            alias[m.group(1)] = (int(m.group(2)), int(m.group(3)))
    out = collections.defaultdict(list)
    for k, l in enumerate(lines):
        m = F3C_STORE_RE.match(l)
        if not m or m.group(4).strip() in allocas:
            continue
        w = 64 if m.group(2) == 'ptr' else int(m.group(2)[1:])
        ma = re.fullmatch(r'%arg(\d+)', m.group(3))
        if ma:
            out[(int(ma.group(1)), w)].append(k)
        elif m.group(3) in alias and alias[m.group(3)][1] == w:
            out[(alias[m.group(3)][0], w)].append(k)
    return out


def fix_f3c_block(fn, fv, rep, ctr):
    """F3c-block (従来の block-local 門 G1〜G5。#509 前と比べ、#736 で読んだ値 rD が同幅で store されない site を見送る `f3c_no_val_store` を追加): 機械語 `mov rD,[rB]` (zero-disp) の読みが IR で消え、
    ベースレジスタ (argN) の値がそのまま store されている形を復元する (_UStrAsg 409ca4 系 = D7 値↔アドレスの別形)。"""
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
        # #736: 読んだ値 rD そのものが同幅で memory に store されていなければ見送る。
        # 戻り値 reg へのコピー (`mov rax,rcx`) や call 先 (`call [rbx+0x18]`) は値の store ではない
        val_store = False
        for ins in mins:
            if ins.mnemonic != 'mov':
                continue
            try:
                o0, o1 = ins.operands
            except Exception:
                continue
            if len(ins.operands) == 2 and o0.type == 3 and o1.type == 1 and fv.cs.reg_name(o1.reg) == rD and o0.size * 8 == bits:
                val_store = True
        if not val_store:
            rep['f3c_no_val_store'] = rep.get('f3c_no_val_store', 0) + 1
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
            rep.setdefault('f3c_no_store_vas', [])
            if '%x' % fn.va not in rep['f3c_no_store_vas']:
                rep['f3c_no_store_vas'].append('%x' % fn.va)
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




def fix_f3c_fn(fn, fv, rep, ctr):
    """機械語 `mov rD,[rB]` (zero-disp, rB は argN に解決) の値がそのまま `mov [m],rD` される site の IR が、load を落として
    `store %argN` (ポインタ自身) を書いている形を復元する (_UStrAsg 409ca4 系 = D7 値↔アドレスの別形 / D4 の store 形)。
    #509 で門を拡張: G2 = rB を load 直前まで (自己上書き `mov rcx,[rcx]` を許す) かつ reg コピー・frame slot 経由まで追跡 /
    G4 = 「rB の store が機械語にある」でなく argN 自身の非 frame 宛 store (正当なポインタ store) の関数内個数で判定 /
    G5 = 同一 IR ブロックの store でなく、関数単位の `store %argN` 収支で対応 (IR のブロック複製 `.thread` と無関係)"""
    tr = f3c_track(fv)
    if tr is None:
        return 0
    lsf, ptr = tr[0], tr[1]
    if not lsf:
        return 0
    lines = fn.body.split('\n')
    cand = f3c_ir_stores(lines)
    hd = re.match(r'^define [^@]*@function_[0-9a-f]+\(([^)]*)\)', fn.body)
    pty = {}
    if hd:
        for idx, p in enumerate([p.strip() for p in hd.group(1).split(',') if p.strip()]):
            pty[idx + 1] = p.split()[0] if p.split() else 'i64'
    edits = {}
    fixed = 0
    for key in sorted({(n, w) for (_a, n, w) in lsf}):
        n, w = key
        if ptr[key]:
            rep['f3c_fn_ptr_store'] = rep.get('f3c_fn_ptr_store', 0) + 1
            continue
        if not cand.get(key):
            rep['f3c_fn_no_store'] = rep.get('f3c_fn_no_store', 0) + 1
            continue
        t = pty.get(n, 'i64')
        for k in cand[key]:
            m = F3C_STORE_RE.match(lines[k])
            ctr[0] += 1
            nm = 'ldfxn%d' % ctr[0]
            pre = []
            aptr = '%%arg%d' % n
            if t != 'ptr':
                pre = ['  %%%s_p = inttoptr %s %%arg%d to ptr' % (nm, t, n)]
                aptr = '%%%s_p' % nm
            ty = m.group(2)
            ld = '  %%%s = load %s, ptr %s, align %d' % (nm, ty, aptr, max(w // 8, 1))
            st = '%sstore %s %%%s, ptr %s%s' % (m.group(1), ty, nm, m.group(4), m.group(5))
            edits[k] = pre + [ld, st]
            fixed += 1
    if not fixed:
        return 0
    out = []
    for i2, l in enumerate(lines):
        out.extend(edits[i2]) if i2 in edits else out.append(l)
    fn.body = '\n'.join(out)
    rep['f3c_fn_stores'] = rep.get('f3c_fn_stores', 0) + fixed
    return 1


def ir_succ(blocks):
    """IR の行ブロック列 → 後続ブロックの index 列。終端命令 (br/switch/ret/unreachable) のラベル参照で結ぶ。終端が無い block は次へ落ちる"""
    name2idx = {}
    for k, ls in enumerate(blocks):
        m = re.match(r'^([\w.$-]+):', ls[0]) if ls else None
        if m:
            name2idx[m.group(1)] = k
    succ = []
    for k, ls in enumerate(blocks):
        term = None
        for l in ls:
            if re.match(r'^\s*(br|switch|ret|unreachable|indirectbr)\b', l):
                term = l
        if term is None:
            succ.append([k + 1] if k + 1 < len(blocks) else [])
        elif re.match(r'^\s*(ret|unreachable)\b', term):
            succ.append([])
        else:
            succ.append(sorted({name2idx[x] for x in re.findall(r'label %([\w.$-]+)', term) if x in name2idx}))
    return succ


def ir_dominators(succ):
    """entry = 0 からの支配集合 (反復データフロー)。dom[x] = x を支配する block の index 集合 (x 自身を含む)"""
    n = len(succ)
    pred = [[] for _ in range(n)]
    for a in range(n):
        for b in succ[a]:
            pred[b].append(a)
    dom = [set(range(n)) for _ in range(n)]
    dom[0] = {0}
    changed = True
    while changed:
        changed = False
        for x in range(1, n):
            if not pred[x]:
                continue
            new = set.intersection(*[dom[p] for p in pred[x]]) | {x}
            if new != dom[x]:
                dom[x] = new
                changed = True
    return dom


def f3c_use_dom_at(fn, fv, first, rep_idx):
    """機械語の最初の deref (entry 外) の IR ブロック B が、置換対象の全使用 rep_idx (行 index) を支配するなら、B の先頭 (label の直後) の行 index を返す。
    B が無い・phi を含む・支配されない使用がある場合は None。修復 load を B の先頭へ置く根拠 (#1325)"""
    lead = _f3c_leaders(fv.ins)
    bstart = max([x for x in lead if x <= first], default=None)
    blocks = fn.blocks()
    starts, off = [], 0
    for _bva, ls in blocks:
        starts.append(off)
        off += len(ls)
    cands = [k for k, (bva, _ls) in enumerate(blocks) if bva == bstart]
    if bstart is None or not cands:
        return None
    bi = cands[0]
    if any(re.match(r'^\s*%[\w.$-]+ = phi ', l) for l in blocks[bi][1]):
        return None
    dom = ir_dominators(ir_succ([ls for _bva, ls in blocks]))
    for k in rep_idx:
        bk = max(j for j in range(len(blocks)) if starts[j] <= k)
        if bi not in dom[bk]:
            return None
    return starts[bi] + 1


ctr_f3cu = [0]             # fix_f3c_use 専用 counter


def fix_f3c_use(fn, fv, rep, ctr):
    """F3c-use (#509): 消費者が store でない D4 (load した値が address base や演算の operand に流れる形)。
    条件 (全部): (a) 機械語の argN を base にした zero-disp load が全て 64bit で、最初の 1 本が entry ブロックにある /
    (b) argN の生の使用 (call 引数・ptr store など) が全て最初の load より前にある / (c) IR に argN からの zero-offset load が 1 本も無い (= load は全滅) /
    (d) argN は i64 引数。→ IR の %argN の使用のうち、(b) の生の使用の数だけ先頭側を残し、残りを `load i64, [%argN]` の値に置換する
    (load は置換する最初の行の直前。生の使用が無ければ entry ブロックの alloca 群の直後)。417b70 (arg4 = count の pointer) / 666a60 (r14 = *arg1) 型"""
    tr = f3c_track(fv)
    if tr is None:
        return 0
    _lsf, _ptr, uses, blk0 = tr
    lines = fn.body.split('\n')
    hd = re.match(r'^define [^@]*@function_[0-9a-f]+\(([^)]*)\)', fn.body)
    pty = {}
    if hd:
        for idx, p in enumerate([p.strip() for p in hd.group(1).split(',') if p.strip()]):
            pty[idx + 1] = p.split()[0] if p.split() else 'i64'
    edits = {}
    done = 0
    for n in sorted({u[2] for u in uses if u[0] == 'deref' and u[4] == 'arg'}):
        derefs = [u for u in uses if u[0] == 'deref' and u[2] == n and u[4] == 'arg']
        first = min(u[1] for u in derefs)
        raws = [u for u in uses if u[0] == 'raw' and u[2] == n]
        if not all(u[3] == 64 for u in derefs) or any(u[1] > first for u in raws):
            continue
        ptrarg = pty.get(n, 'i64') != 'i64'
        argre = re.compile(r'(?<![\w.$-])%arg' + str(n) + r'(?![\w.$-])')
        ptr_alias = set()
        for l in lines[1:]:
            m = re.match(r'^\s*(%[\w.$-]+) = inttoptr i64 %arg' + str(n) + r' to ptr\s*$', l)
            if m:
                ptr_alias.add(m.group(1))
        loaded = False
        for l in lines[1:]:
            m = re.match(r'^\s*%[\w.$-]+ = load [^,]+, ptr ([^,\s]+)', l)
            if m and (m.group(1) == '%%arg%d' % n or m.group(1) in ptr_alias):
                loaded = True
                break
        if loaded:
            continue
        idx = [k for k in range(1, len(lines)) if argre.search(lines[k])]
        keep = len(raws)
        rep_idx = idx[keep:]
        if not rep_idx:
            continue
        if first in blk0:
            entry_end = next((k for k in range(2, len(lines)) if re.match(r'^[\w.$-]+:', lines[k])), len(lines))
            if rep_idx[0] >= entry_end:
                rep['f3c_use_not_entry'] = rep.get('f3c_use_not_entry', 0) + 1
                continue
            if keep == 0:
                at = 2
                while at < len(lines) and re.match(r'^\s*%[\w.$-]+ = alloca ', lines[at]):
                    at += 1
            else:
                at = rep_idx[0]
        else:
            at = f3c_use_dom_at(fn, fv, first, rep_idx)
            if at is None:
                rep['f3c_use_not_dom'] = rep.get('f3c_use_not_dom', 0) + 1
                continue
            rep['f3c_use_dom'] = rep.get('f3c_use_dom', 0) + 1
        ctr[0] += 1
        nm = 'ldfxu%d' % ctr[0]
        for k in rep_idx:
            lines[k] = argre.sub('%' + nm, lines[k])
        if ptrarg:
            # ptr 型引数: %argN は既にアドレス。機械語の [rB] は %argN への直接の load、値は ptr 消費者へ inttoptr で渡す (#734)
            edits.setdefault(at, []).extend(['  %%%s_l = load i64, ptr %%arg%d, align 8' % (nm, n),
                                              '  %%%s = inttoptr i64 %%%s_l to ptr' % (nm, nm)])
            rep['f3c_use_ptrarg'] = rep.get('f3c_use_ptrarg', 0) + 1
        else:
            edits.setdefault(at, []).extend(['  %%%s_p = inttoptr i64 %%arg%d to ptr' % (nm, n),
                                              '  %%%s = load i64, ptr %%%s_p, align 8' % (nm, nm)])
        rep['f3c_use_replaced'] = rep.get('f3c_use_replaced', 0) + len(rep_idx)
        done += 1
    if not done:
        return 0
    out = []
    for i2, l in enumerate(lines):
        out.extend(edits.get(i2, []))
        out.append(l)
    fn.body = '\n'.join(out)
    return 1


ctr_f3cn = [0]             # fix_f3c_fn 専用 counter (F1〜F3 の SSA 名採番を不変に保つ)


def fix_f3c(fn, fv, rep, ctr):
    """F3c = 従来の block-local 門 (fix_f3c_block) → 関数単位の個数収支門 (fix_f3c_fn, #509)。後者は前者が直した行を見ない"""
    a = fix_f3c_block(fn, fv, rep, ctr)
    u = fix_f3c_use(fn, fv, rep, ctr_f3cu)
    b = fix_f3c_fn(fn, fv, rep, ctr_f3cn)
    return a or u or b


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# F4: frame_read_dropped (escape 済み stack_var 内部の read が undef → B1 で xor 0,0 になった, #564)
# ---------------------------------------------------------------------------

XORZ_RE = re.compile(r'^(\s*)(%[\w.$-]+) = xor i(8|16|32|64) 0, 0\s*$')
UNNAMED_ALLOCA_RE = re.compile(r'^  (%\d+) = alloca ', re.M)


def f4_candidates(fn, fv, rep):
    """[(ir_line_index, xname, type_bits, stack_var, offset, width_bits, addr)] を返す (rep に棄却理由を数える)。"""
    lines = fn.body.split('\n')
    # B1 の残骸 = 使用ゼロの無名 alloca が無ければ対象外
    unused = [a for a in UNNAMED_ALLOCA_RE.findall(fn.body)
              if len(re.findall(re.escape(a) + r'(?![\w.$-])', fn.body)) == 1]
    if not unused:
        return []
    blocks = fn.blocks()
    cum = 0
    meta = []
    for (bva, ls) in blocks:
        meta.append((bva, cum, cum + len(ls), ls))
        cum += len(ls)
    mblk, _ = fn_mach_blocks(fv, fn.va, [b[0] for b in meta if b[0] is not None])
    if mblk is None:
        return []
    svars = None
    fm = None
    out = []
    for (bva, ia, ib, ls) in meta:
        if bva is None:
            continue
        xs = [(ia + k, XORZ_RE.match(l)) for k, l in enumerate(ls) if XORZ_RE.match(l)]
        if len(xs) != 1:
            continue
        entry = bva == next((b[0] for b in meta if b[0] is not None), None) and len([1 for l in lines if XORZ_RE.match(l)]) == 1
        # B1 の xor は関数入口ブロックへ hoist されることがある (71dd80: read は後続ブロック)。入口ブロックで IR 中の xor-0-0 が
        # その 1 本だけのときは、own-block に read が無ければ機械語側を関数全体で突合する (read / 自己 xor / store 衝突も関数全体)。
        mins = mblk.get(bva, [])
        if entry and not any(mo['base'] in ('rbp', 'rsp') for i in mins if not is_write_only(i) for mo in memops_of(fv.cs, i) if mo['kind'] in ('load', 'rmw', 'other')):
            mins = list(fv.ins)
        if any(i.mnemonic == 'xor' and len(i.operands) == 2 and i.operands[0].type == 1 and i.operands[0].reg == i.operands[1].reg for i in mins):
            rep['f4_selfxor_block'] = rep.get('f4_selfxor_block', 0) + 1
            continue
        if fm is None:
            fm = frame_model(fv.cs, fv.ins)
            esc = escaped_stack_vars(fn.body)
            svars = {n: e for n, e in esc.items() if e}
            order = sorted(esc)
            gap = {n: n - (order[i - 1] if i else 0) for i, n in enumerate(order)}
        xi, xm = xs[0]
        bits = int(xm.group(3))
        reads = []
        for i in mins:
            if is_write_only(i):
                continue
            for mo in memops_of(fv.cs, i):
                if mo['kind'] in ('load', 'rmw', 'other') and mo['base'] in ('rbp', 'rsp') and not mo['index'] and mo.get('rip_rva') is None:
                    reads.append((i, mo))
        if len(reads) != 1:
            rep['f4_read_count'] = rep.get('f4_read_count', 0) + 1
            continue
        i, mo = reads[0]
        rs, rb = fm.get(i.address, (None, None))
        basev = rs if mo['base'] == 'rsp' else rb
        w = mo['size_bits']
        if basev is None or not w or w > bits or w not in (8, 16, 32, 64):
            rep['f4_unresolved'] = rep.get('f4_unresolved', 0) + 1
            continue
        o = basev + mo['disp']
        cover = [n for n in svars if -n <= o]
        n = min(cover) if cover else None
        if n is None or o + n + w // 8 > gap[n]:
            rep['f4_not_in_escaped_gap'] = rep.get('f4_not_in_escaped_gap', 0) + 1
            continue
        # 同じ frame 番地への機械語 store があれば IR が store を持つはず (= 脱落でない): 曖昧なので触らない
        clash = False
        for j in fv.ins:
            if j is i:
                continue
            for m2 in memops_of(fv.cs, j):
                if m2['base'] in ('rbp', 'rsp') and not m2['index'] and m2.get('rip_rva') is None and (m2['write'] or is_write_only(j)):
                    rs2, rb2 = fm.get(j.address, (None, None))
                    b2 = rs2 if m2['base'] == 'rsp' else rb2
                    w2 = m2['size_bits'] or 64
                    if b2 is not None and b2 + m2['disp'] < o + w // 8 and o < b2 + m2['disp'] + w2 // 8:
                        clash = True
        if clash:
            rep['f4_frame_store_clash'] = rep.get('f4_frame_store_clash', 0) + 1
            continue
        # load の置き場: B1 の xor は関数入口側に置かれるため、そこでは stack_var への callee 書込み前になる。
        # 最初の使用行の直前に置く。全使用が最初の使用と同一 IR ブロック内で、stack_var を渡す call が同ブロックのその前にあること。
        xname = xm.group(2)
        anyuse = [k for k, l in enumerate(lines) if k != xi and re.search(re.escape(xname) + r'(?![\w.$-])', l)]
        ub = next(((ba, bb) for (_v, ba, bb, _l) in meta if anyuse and ba <= min(anyuse) < bb), None)
        if not anyuse or ub is None or not all(ub[0] <= k < ub[1] for k in anyuse):
            rep['f4_use_shape'] = rep.get('f4_use_shape', 0) + 1
            continue
        first = min(anyuse)
        al = {'%%stack_var_-%d' % n}
        for k, l in enumerate(lines):
            bm = re.match(r'^  (%[\w.$-]+) = bitcast ptr (%[\w.$-]+) to ptr', l)
            if bm and bm.group(2) in al:
                al.add(bm.group(1))
        esc_before = any(re.match(r'^\s*(?:%[\w.$-]+ = )?call ', lines[k]) and any(re.search(re.escape(a) + r'(?![\w.$-])', lines[k]) for a in al)
                         for k in range(ub[0], first))
        if not esc_before:
            rep['f4_no_escape_before_use'] = rep.get('f4_no_escape_before_use', 0) + 1
            continue
        nxt = None
        for k, j in enumerate(fv.ins):
            if j is i and k + 1 < len(fv.ins):
                nj = fv.ins[k + 1]
                if nj.mnemonic in ('je', 'jne') and nj.operands and nj.operands[0].type == 2:
                    nxt = (nj.mnemonic, nj.operands[0].imm)
        out.append((xi, xname, bits, n, o + n, w, i.address, xm.group(1), first, nxt))
    return out


NO_CONSUMER = [False]


def fix_f4(fn, fv, rep, ctr):
    cands = f4_candidates(fn, fv, rep)
    if not cands:
        return 0
    lines = fn.body.split('\n')
    edits = {}
    drop = set()
    ren = []
    andfix = []
    for (xi, xname, bits, n, off, w, addr, ind, first, nxt) in cands:
        ctr[0] += 1
        nm = 'ldf4_%d' % ctr[0]
        # LLVM の無名値 (%N) は番号が連続でなければならない。xor 行は (使用ゼロの dead 値として) 残し、使用箇所だけを名前付き値へ置換する。
        pre = ['%s%%%s_i = ptrtoint ptr %%stack_var_-%d to i64' % (ind, nm, n),
               '%s%%%s_a = add i64 %%%s_i, %d' % (ind, nm, nm, off),
               '%s%%%s_p = inttoptr i64 %%%s_a to ptr' % (ind, nm, nm)]
        if w == bits:
            edits[first] = pre + ['%s%%%s_v = load i%d, ptr %%%s_p, align 1' % (ind, nm, bits, nm)]
        else:
            edits[first] = pre + ['%s%%%s_l = load i%d, ptr %%%s_p, align 1' % (ind, nm, w, nm),
                                  '%s%%%s_v = zext i%d %%%s_l to i%d' % (ind, nm, w, nm, bits)]
        ren.append((xi, xname, '%%%s_v' % nm))
        andfix.append((xname, nxt, addr))
        rep.setdefault('f4_sites', []).append('%x@%x->stack_var_-%d+%d' % (fn.va, addr, n, off))
    out = []
    for i, l in enumerate(lines):
        if i in drop:
            continue
        if i in edits:
            out.extend(edits[i])
        out.append(l)
    body = '\n'.join(out)
    ls2 = body.split('\n')
    for (_xi, old_n, new_n) in ren:
        pat = re.compile(re.escape(old_n) + r'(?![\w.$-])')
        defn = re.compile(r'^\s*' + re.escape(old_n) + r' = ')
        ls2 = [l if defn.match(l) else pat.sub(new_n, l) for l in ls2]
    body = '\n'.join(ls2)
    # consumer 復元: RetDec は undef の自由度で `skip = registered && (v == K)` を `icmp eq i1 (v == K), registered` に畳んでいた
    # (v を正しく load しても未登録+不一致で skip が真になる)。`cmp [frame], K; je T` の直後が je T で、
    # `%C = icmp eq iN v, K` → `%oc = icmp eq i1 %C, %X` → `br i1 %oc, label %T` の形のときだけ `and i1 %C, %X` に戻す。
    for (xname, nxt, addr) in ([] if NO_CONSUMER[0] else andfix):
        if not nxt or nxt[0] != 'je':
            continue
        vn = [r for r in ren if r[1] == xname][0][2]
        cm = re.search(r'^  (%[\w.$-]+) = icmp eq i\d+ ' + re.escape(vn) + r', -?\d+\s*$', body, re.M)
        if not cm:
            continue
        ec = re.escape(cm.group(1))
        om = re.search(r'^(  (%[\w.$-]+) = )icmp eq i1 (?:' + ec + r', (%[\w.$-]+)|(%[\w.$-]+), ' + ec + r')\s*$', body, re.M)
        if not om:
            continue
        ocn = om.group(2)
        brm = re.findall(r'^\s*br i1 ' + re.escape(ocn) + r', label %dec_label_pc_([0-9a-f]+), label %\S+', body, re.M)
        if len(brm) != 1 or int(brm[0], 16) != nxt[1] or len(re.findall(re.escape(ocn) + r'(?![\w.$-])', body)) != 2:
            rep['f4_consumer_shape'] = rep.get('f4_consumer_shape', 0) + 1
            continue
        other = om.group(3) or om.group(4)
        body = body.replace(om.group(0), om.group(1) + 'and i1 ' + cm.group(1) + ', ' + other, 1)
        rep.setdefault('f4_consumer_and', []).append('%x@%x' % (fn.va, addr))
    fn.body = body
    return len(cands)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('infile')
    ap.add_argument('outfile')
    ap.add_argument('--pe', required=True)
    ap.add_argument('--report')
    ap.add_argument('--only', help='カンマ区切りの VA (16進) のみ修復')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--passes', help='カンマ区切りで pass を限定 (f1,f1v,f2,f3a,f3b,f3c,f3d,f4)。既に ldfix 済みの IR へ F3c だけを重ねる用 (#509)。F3d は既定で無効 (--passes f3d で有効化・LD-127 #2745)')
    ap.add_argument('--f4-no-consumer', action='store_true', help='F4 の consumer 復元 (and i1) だけ外す (ネガコン, #564)')
    ap.add_argument('--no-f4', action='store_true', help='F4 (#564) を無効化 (ネガコン / 旧出力との差分確認)')
    a = ap.parse_args()
    passes = set(a.passes.split(',')) if a.passes else None
    only = set(int(x, 16) for x in a.only.split(',')) if a.only else None
    NO_CONSUMER[0] = a.f4_no_consumer
    text = open(a.infile, errors='replace').read()
    mach = Machine(a.pe)
    for m in DEF_RE.finditer(text):
        F3C_ARITY[int(m.group('name')[len('function_'):], 16)] = len([x for x in m.group('args').split(',') if x.strip()])
    rep = collections.OrderedDict()
    ctr = [0]
    counts = collections.OrderedDict((k, 0) for k in ('f1', 'f1v', 'f2', 'f3a', 'f3b', 'f3c', 'f3d', 'f4'))
    fn_lists = collections.OrderedDict((k, []) for k in ('f1', 'f1v', 'f2', 'f3a', 'f3b', 'f3c', 'f3d', 'f4'))
    ctr_f1v = [0]               # F1v は専用 counter (F1〜F3 の SSA 名採番を不変に保つ)
    ctr_f4 = [0]                # F4 も専用 counter
    ctr_f3d = [0]               # F3d も専用 counter
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
        if blk_vas and hasattr(mach, 'cover'):
            mach.cover(va, max(blk_vas))
        fv = FnMach(mach, va, blk_vas)
        try:
            for tag, func in (('f1', fix_f1), ('f1v', fix_f1v), ('f2', fix_f2), ('f3a', fix_f3a), ('f3b', fix_f3b), ('f3c', fix_f3c), ('f3d', fix_f3d), ('f4', fix_f4)):
                if passes is not None and tag not in passes:
                    continue
                if tag == 'f4' and a.no_f4:
                    continue
                if tag == 'f3d' and passes is None:
                    continue
                c = ctr_f1v if tag == 'f1v' else ctr_f4 if tag == 'f4' else ctr_f3d if tag == 'f3d' else ctr
                if func(fn, fv, rep, c):
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
    log('F1(load_dropped)=%d F1v(variant)=%d F2(spill_slot)=%d F3a(old-value)=%d F3b(count-load)=%d F3c(store-arg)=%d F3d(type-tag)=%d F4(frame-read)=%d (errors=%d)'
        % (counts['f1'], counts['f1v'], counts['f2'], counts['f3a'], counts['f3b'], counts['f3c'], counts['f3d'], counts['f4'], rep.get('errors', 0)))
    if not a.dry_run:
        open(a.outfile, 'w').write(result := ''.join(out_parts))
    if a.report:
        json.dump(rep, open(a.report, 'w'), indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
