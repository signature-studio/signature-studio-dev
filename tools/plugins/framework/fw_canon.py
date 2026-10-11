#!/usr/bin/env python3
"""fw_canon.py — canon 段の IR 正規化 (CAB-269). fw_stage2.sh step 14 から分離した 1 実装.

背景 (CAB-194 検収 REPORT §12.3 の S1-S4): fw_stage2.sh にインラインだった 3 つの python
heredoc (A: fw_flat3→fw_flat4 / B: fw_flat4→fw_flat4 / C: fw_flat4_canon→canon2) はほぼ同じ
処理の重複実装で, **採番 (uid) と declare の扱いが pass 間で不整合** だった。

  * S2: B と C がどちらも `uid[0] = 0` から採番するため, C が同一関数内で `ceclone1` を
        再定義 → clang `multiple definition of local value named 'ceclone1'` (function_4076b0)
  * S3/S4: `__asm_fldenv` の rename (call は `fw_fldenv(ptr)`) は A/B の正規表現が実名に
        マッチせず無効で, simd gen 後の C 段 (`__asm_fldenv__vg224`) になって初めて成立する。
        その C 段は declare を**削除**していたため `use of undefined value '@fw_fldenv'`

本 script はその 1 実装にする。stage で適用範囲を変える:

  python3 fw_canon.py fw_flat3.ll fw_flat4.ll --stage flat4              # simd gen 前
  python3 fw_canon.py fw_flat4_canon.ll fw_flat4_canon2.ll --stage canon  # simd gen 後

共通 (両 stage):
  1. `call void @__asm_vmovups__3(i256, i256)` → `store i256` (ptr を定義後方 160 行→前方 14 行で探索)
     (flat4 は「後方のみ」を先に適用し、そのリトライで前方探索も行う = 旧 A→B の順序を維持)
  2. ymm store の ptr dominance 修復 (定義が使用より後ろにあるとき、使用直前に定義 chain を clone)
     採番は `max(10000, 入力内の最大 ceclone 番号 + 1)`: pass を跨越しても ceclone が衝突しない (S2)
  3. fn-ptr 戻り型正規化 (`T ()*` → `ptr`) / BLENDFUNCTION・tagPOINT 構造体引数 → i64
flat4 のみ: `declare i256 @__asm_vmovups__*` を IR identity define 化 (C stub を不要にする)
canon のみ: `__asm_fldenv__vg224(i224 %v)` → `fw_fldenv(ptr %p)` + declare を**置き換える**

fldenv の rename が gen 後 (canon) でなければならない理由: liftlib simd gen は i224 形を
正規名 `__asm_fldenv__vg224` にリネームし未サポート mnemonic の trap stub を fw_simd.c に
出力する。gen 前に rename するとその stub が生成されず、ビルド成果物が変わる。

  python3 fw_canon.py IN.ll OUT.ll --stage {flat4|canon} [--report counts.json]
"""
import argparse
import json
import re
import sys

# --- 正規表現 (旧 fw_stage2.sh インライン実装と同一) ---
VMOV_CALL_RE = re.compile(r'^(\s*)call void @__asm_vmovups__3\(i256 ([^,]+), i256 (%[\w.-]+)\)\s*$')
VMOV_LOAD_RE = re.compile(r'^\s*(%[\w.-]+) = load i256, (?:ptr|[^ ]+\*) (%[\w.-]+)')
YM_STORE_RE = re.compile(r'^(\s*)store i256 (%[\w.-]+), ptr (%[\w.-]+), align 1\s*$')
DEF_RE = re.compile(r'\s*(%[\w.-]+) = ')
I256_DECL_RE = re.compile(r'^declare (i256) @(__asm_[\w]+)\((i256)\) local_unnamed_addr$', re.M)
FLDENV_CALL_RE = re.compile(r'^(\s*)call void @__asm_fldenv__[\w.]*\(i224 (%[\w.-]+)\)\s*$')
FLDENV_LOAD_RE = re.compile(r'^\s*(%[\w.-]+) = load i224, (?:ptr|[^ ]+\*) (%[\w.-]+)')
FLDENV_DECL_RE = re.compile(r'^declare void @__asm_fldenv__[\w.]*\(i224\) local_unnamed_addr$', re.M)
CE_NUM_RE = re.compile(r'%ceclone(\d+)')

UID_BASE = 10000          # ceclone 採番の下限 (旧 A/B は 0、旧 C は sandbox で 10000)
BACK_DEPTH = 160          # ptr 定義の後方探索行数
FWD_DEPTH = 14            # 前方探索行数


def norm_vmovups(lines, forward):
    """`call void @__asm_vmovups__3(i256 <load proxy>, i256 <value>)` → `store i256 <value>, ptr <ptr>`.

    lift は `movups [ptr], ymm` を「ptr からのダミー load (第 1 引数) + 格納値 (第 2 引数)」の
    call にしている。したがって第 1 引数の load 定義から ptr を復元して store にする。
    """
    out = []
    for idx, l in enumerate(lines):
        m = VMOV_CALL_RE.match(l)
        if m:
            ptr = None
            for k in range(idx - 1, max(-1, idx - BACK_DEPTH), -1):
                mm = VMOV_LOAD_RE.match(lines[k])
                if mm and mm.group(1) == m.group(2):
                    ptr = mm.group(2)
                    break
            if ptr is None and forward:
                for k in range(idx + 1, min(len(lines), idx + FWD_DEPTH)):
                    mm = VMOV_LOAD_RE.match(lines[k])
                    if mm:
                        ptr = mm.group(2)
                        break
            if ptr:
                out.append('%sstore i256 %s, ptr %s, align 1' % (m.group(1), m.group(3), ptr))
                continue
        out.append(l)
    return out


def next_uid(lines):
    """ceclone 採番の開始値 = max(10000, 入力内の最大番号)。pass 間の衝突を避ける (S2)"""
    nums = [int(x) for x in CE_NUM_RE.findall('\n'.join(lines))]
    return max([UID_BASE] + nums) if nums else UID_BASE


def norm_dominance(lines):
    """ymm store の ptr が定義より後ろにある箇所を、使用直前に clone して挿入 (dominance 修復)"""
    uid = [next_uid(lines)]
    fixed = 0
    starts = [i for i, l in enumerate(lines) if l.startswith('define ')]
    starts.append(len(lines))
    for si in range(len(starts) - 1):
        lo, hi = starts[si], starts[si + 1]
        defs = {}
        for j in range(lo, hi):
            m = DEF_RE.match(lines[j])
            if m and m.group(1) not in defs:
                defs[m.group(1)] = j
        i = lo
        while i < hi:
            m = YM_STORE_RE.match(lines[i])
            if not m:
                i += 1
                continue
            dj = defs.get(m.group(3))
            if dj is None or dj < i:
                i += 1
                continue
            dm = re.match(r'\s*%[\w.-]+ = inttoptr i64 (%[\w.-]+) to ptr', lines[dj])
            if not dm:
                i += 1
                continue
            chain, seen, stack = [], set(), [dm.group(1)]
            while stack:
                nm = stack.pop()
                if nm in seen:
                    continue
                seen.add(nm)
                dj2 = defs.get(nm)
                if dj2 is None:
                    continue
                dl = lines[dj2].lstrip()
                mm = re.match(r'%[\w.-]+ = (inttoptr i64 |ptrtoint ptr |add i64 )(.*)$', dl)
                if not mm:
                    continue
                chain.append((nm, dl.split(' = ', 1)[1]))
                for d in re.findall(r'%[\w.-]+', mm.group(2)):
                    stack.append(d)
            pre, ren = [], {}
            for nm, rhs in reversed(chain):
                uid[0] += 1
                nn = '%%ceclone%d' % uid[0]
                for old, new in reversed(list(ren.items())):
                    rhs = rhs.replace(old + ' ', new + ' ').replace(', ' + old, ', ' + new).replace(' ' + old + ',', ' ' + new + ',')
                ren[nm] = nn
                pre.append('  %s = %s' % (nn, rhs))
            top = ren.get(dm.group(1))
            top_i = '%%ceclone%d' % (uid[0] + 1)
            uid[0] += 1
            pre.append('  %s = inttoptr i64 %s to ptr' % (top_i, top))
            lines[i] = '  store i256 %s, ptr %s, align 1' % (m.group(2), top_i)
            for k, pl in enumerate(pre):
                lines.insert(i + k, pl)
            i += len(pre) + 1
            fixed += 1
    return lines, fixed


def norm_i256_declares(text):
    """`declare i256 @__asm_vmovups__vyy(i256)` を IR identity define に (C stub を不要にする)"""
    decls = I256_DECL_RE.findall(text)
    for ret, nm, args in decls:
        text = text.replace('declare %s @%s(%s) local_unnamed_addr\n' % (ret, nm, args), '')
        d = 'define i256 @%s(i256 %%v) {\n  ret i256 %%v\n}' % nm
        idx = text.index('\ndefine ')
        text = text[:idx] + '\n' + d + '\n' + text[idx:]
    return text, len(decls)


def norm_fldenv(text):
    """`call void @__asm_fldenv__<tags>(i224 %v)` → `call void @fw_fldenv(ptr %p)`.
    declare は削除せず `declare void @fw_fldenv(ptr)` に**置き換える** (S3: declare 欠落)"""
    lines = text.split('\n')
    out = []
    n = 0
    for idx, l in enumerate(lines):
        m = FLDENV_CALL_RE.match(l)
        if m:
            ptr = None
            for k in range(idx - 1, max(-1, idx - BACK_DEPTH), -1):
                mm = FLDENV_LOAD_RE.match(lines[k])
                if mm and mm.group(1) == m.group(2):
                    ptr = mm.group(2)
                    break
            if ptr is None:
                raise SystemExit('[fw_canon] FATAL: %s の load が %d 行以内に見つからない (%s)'
                                 % (m.group(2), BACK_DEPTH, m.group(0).strip()))
            out.append('%scall void @fw_fldenv(ptr %s)' % (m.group(1), ptr))
            n += 1
            continue
        out.append(l)
    text = '\n'.join(out)
    text, nd = FLDENV_DECL_RE.subn('declare void @fw_fldenv(ptr) local_unnamed_addr', text)
    if n and not nd:
        idx = text.index('\ndefine ')
        text = text[:idx] + '\ndeclare void @fw_fldenv(ptr) local_unnamed_addr' + text[idx:]
        nd = 1
    return text, n, nd


def norm_common(text):
    text = re.sub(r'\b(?:i\d+|void|ptr|float|double) \(\)\* ', 'ptr ', text)
    text = text.replace('%_BLENDFUNCTION %', 'i64 %').replace('%_BLENDFUNCTION)', 'i64)').replace('%_BLENDFUNCTION,', 'i64,')
    text = text.replace('%tagPOINT %', 'i64 %').replace('%tagPOINT)', 'i64)').replace('%tagPOINT,', 'i64,')
    return text


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--stage', choices=['flat4', 'canon'], required=True)
    ap.add_argument('--report', default='')
    a = ap.parse_args(argv)

    lines = open(a.src, errors='replace').read().split('\n')
    c = {'stage': a.stage, 'src': a.src, 'lines_in': len(lines), 'ymm_store': 0,
         'dominance_fixed': 0, 'i256_identity': 0, 'fldenv_calls': 0, 'fldenv_declares': 0,
         'vmovaps_left': 0}
    # 1. ymm store 化 (旧 A: 後方のみ → 旧 B: 前方探索リトライ)
    lines = norm_vmovups(lines, forward=False)
    if a.stage == 'flat4':
        text, c['i256_identity'] = norm_i256_declares('\n'.join(lines))
        lines = text.split('\n')
    lines = norm_vmovups(lines, forward=True)
    c['ymm_store'] = sum(1 for l in lines if YM_STORE_RE.match(l))
    # 2. dominance 修復
    lines, c['dominance_fixed'] = norm_dominance(lines)
    # 3. 共通正規化
    text = norm_common('\n'.join(lines))
    if a.stage == 'canon':
        text, c['fldenv_calls'], c['fldenv_declares'] = norm_fldenv(text)
    c['lines_out'] = len(text.split('\n'))
    c['vmovaps_left'] = len(VMOV_CALL_RE.findall(text))
    c['ceclone_max'] = max([int(x) for x in CE_NUM_RE.findall(text)] or [0])
    open(a.dst, 'w').write(text)
    print('[fw_canon:%s] ymm_store=%d dominance_fixed=%d i256_identity=%d fldenv=%d/%d vmovaps_left=%d ceclone_max=%d'
          % (a.stage, c['ymm_store'], c['dominance_fixed'], c['i256_identity'],
             c['fldenv_calls'], c['fldenv_declares'], c['vmovaps_left'], c['ceclone_max']))
    if a.report:
        open(a.report, 'w').write(json.dumps(c, indent=2) + '\n')
    # 後続 (emcc) を止めないための最終 check
    if c['vmovaps_left']:
        print('[fw_canon:%s] WARN: __asm_vmovups__3 呼出が %d 件残存 (store 化できなかった)' % (a.stage, c['vmovaps_left']))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
