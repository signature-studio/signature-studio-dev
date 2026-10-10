#!/usr/bin/env python3
"""m11_alloca.py — RetDec 集成体ローカル縮退 (alloca 縮退) の機械検出 + 拡幅 pass (CAB-129 正式修正).

RetDec は Delphi の集成体ローカル (record / OSVERSIONINFOEXW 等) を `alloca i64` (8B) に潰して出力する
(実測: 44bb70 の 0x188=392B record → `alloca i64` + `__asm_rep_stosq_memset(ptr,0,49)`)。
潰れた alloca への記録域書込み (rep stos / FillChar / Win32 API の出力パラメータ) は shadow stack を
破壊し、unit survey の OOB / halt0 の主要因だった (tools/m11/REPORT.md §4, tools/m11/shimx_link/REPORT.md §3)。

本 pass は closure IR (boot_final.ll, 全 7,421 定義) を走査し、**使用箇所の要求サイズが alloca 実体積を
超える場合だけ** alloca を [K x i64] に拡幅する。ポインタ値・他の IR は一切変更しない (idempotent:
既に要求サイズ以上なら不変)。

検出規則 (証拠 → 要求バイト数):
  R1 rep stos  : __asm_rep_stos{b,w,d,q}_memset(dst, v, N)   → dst >= N*幅      (定数 N のみ)
  R2 rep movs  : __asm_rep_movs{b,w,d,q}_memcpy(dst, src, N) → dst >= N*幅      (定数 N のみ)
  R3 FillChar  : function_40d210(dst, len, val, _) (Delphi System.@FillChar) → dst >= len (定数 len のみ)
  R4 llvm.mem* : llvm.memset/memcpy/memmove(dst, _, len, ..) → dst >= len       (定数 len のみ)
  R5 Win32 出力パラメータ表 (API_OUT): 構造体を受け取る API の引数 → 表の最小バイト数
  R6 Win32 (buf, count) 表 (COUNT_BUF): count が定数の呼出し → buf >= count*要素幅
      (GetLocaleInfoW の cch*2 等。halt0 53 unit × GetLocaleInfoW 相関の対策)
  R7 直接広 store: store T, ptr %bc (root が alloca) で sizeof(T) > alloca 実体積 → sizeof(T)

dst/%bc は bitcast 連鎖 (RetDec が多段に出す) を辿って alloca に帰着させ、GEP/ptrtoint+add 経由の
参照は closure 実測 0 件であることを確認済み (pass 実行時に検出したら警告を出す)。

使い方: m11_alloca.py <in.ll> <out.ll> [--report report.json]
"""
import json
import re
import sys

# ---- R5: Win32 出力パラメータ API (引数 index: 最小バイト)。tools/m11/shimx_link/fix_alloca.py と同表
# (shimx_link では計測用回避 --fix だったものを正式化。サイズは Win32 API 仕様どおり)
API_OUT = {
    'GetVersionExW': {0: 284}, 'GetVersionExA': {0: 156}, 'GetStartupInfoW': {0: 104}, 'GetStartupInfoA': {0: 68},
    'GetSystemInfo': {0: 48}, 'GetNativeSystemInfo': {0: 48}, 'GetLocalTime': {0: 16}, 'GetSystemTime': {0: 16},
    'GetTimeZoneInformation': {0: 172}, 'GetCPInfo': {1: 20}, 'GetCPInfoExW': {2: 560},
    'FindFirstFileW': {1: 592}, 'FindNextFileW': {1: 592}, 'GetFileAttributesExW': {2: 36},
    'GlobalMemoryStatusEx': {0: 64}, 'GlobalMemoryStatus': {0: 32}, 'VirtualQuery': {1: 48},
    'GetSystemTimeAsFileTime': {0: 8}, 'QueryPerformanceCounter': {0: 8},
    'QueryPerformanceFrequency': {0: 8}, 'GetFileTime': {1: 8}, 'GetFileInformationByHandle': {1: 52},
    'GetDiskFreeSpaceExW': {1: 8}, 'GetOverlappedResult': {2: 4},
}
# ---- R6: (buf, count, 要素幅) を持つ API。count が定数のとき buf >= count*要素幅 (Win32 仕様)
COUNT_BUF = {
    'GetLocaleInfoW': [(2, 3, 2)], 'GetLocaleInfoA': [(2, 3, 1)],
    'LCMapStringW': [(4, 5, 2)], 'LCMapStringA': [(4, 5, 1)],
    'GetEnvironmentVariableW': [(1, 2, 2)], 'GetEnvironmentVariableA': [(1, 2, 1)],
    'GetTempPathW': [(1, 0, 2)],
    'GetModuleFileNameW': [(1, 2, 2)], 'GetModuleFileNameA': [(1, 2, 1)],
    'MultiByteToWideChar': [(4, 5, 2)],
    'WideCharToMultiByte': [(4, 5, 1)],
    'GetVolumeInformationW': [(1, 2, 2), (6, 7, 2)],
    'GetUserDefaultLangID': [],
}
STOS = {'__asm_rep_stosb_memset': 1, '__asm_rep_stosw_memset': 2, '__asm_rep_stosd_memset': 4, '__asm_rep_stosq_memset': 8}
MOVS = {'__asm_rep_movsb_memcpy': 1, '__asm_rep_movsw_memcpy': 2, '__asm_rep_movsd_memcpy': 4, '__asm_rep_movsq_memcpy': 8}
FILLCHAR = 'function_40d210'   # Delphi System.@FillChar(dst, len, val, _) — 逆アセンブル突合済 (tools/m11/m11_ov.c 同流儀)
SZ = {'i1': 1, 'i8': 1, 'i16': 2, 'i32': 4, 'i64': 8, 'float': 4, 'double': 8, 'i128': 16, 'ptr': 8}
MAX_WIDEN = 1 << 20            # 1 alloca の拡幅上限 (安全弁。実測最大は FillChar 188416B @ 408b60)


def tsize(t):
    t = t.strip()
    if t in SZ:
        return SZ[t]
    m = re.match(r'^\[(\d+) x ([\w]+)\]$', t)
    if m and m.group(2) in SZ:
        return int(m.group(1)) * SZ[m.group(2)]
    return None


def split_args(s):
    out, depth, cur = [], 0, ''
    for ch in s:
        if ch in '([{<':
            depth += 1
        elif ch in ')]}>':
            depth -= 1
        if ch == ',' and depth == 0:
            out.append(cur.strip()); cur = ''
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def reg_of(arg):
    """引数文字列 ('ptr nonnull %35' 等) から末尾の %reg を取り出す"""
    m = re.search(r'(%[\w.$-]+)\s*$', arg)
    return m.group(1) if m else None


def num_of(arg):
    m = re.search(r'(?:i\d+|i64)\s+(-?\d+)\s*$', arg)
    return int(m.group(1)) if m else None


def main():
    src_path, dst_path = sys.argv[1], sys.argv[2]
    rep_path = sys.argv[sys.argv.index('--report') + 1] if '--report' in sys.argv else None
    src = open(src_path, errors='replace').read()
    funcs = list(re.finditer(r'^define [^\n]*@([\w.$-]+)\([^\n]*\{\n.*?^\}\n', src, re.S | re.M))
    det = {'R1_rep_stos': 0, 'R2_rep_movs': 0, 'R3_fillchar': 0, 'R4_llvm_mem': 0, 'R5_api_out': 0, 'R6_count_buf': 0, 'R7_wide_store': 0}
    widened, over_cap, gep_warn = [], [], []
    pieces, last = [], 0
    for fm in funcs:
        body = fm.group(0)
        name = fm.group(1)
        if 'alloca' not in body:
            continue
        allocas = {}   # %v -> (bytes, type)
        for m in re.finditer(r'^(\s*)(%[\w.$-]+) = alloca ([^,\n]+?)(, align \d+)?\s*$', body, re.M):
            allocas[m.group(2)] = (tsize(m.group(3)), m.group(3))
        if not allocas:
            continue
        cast = {m.group(1): m.group(2) for m in re.finditer(r'^\s*(%[\w.$-]+) = bitcast ptr (%[\w.$-]+) to ptr', body, re.M)}

        def root(v, d=0):
            while v in cast and d < 10:
                v = cast[v]; d += 1
            return v

        # GEP / ptrtoint 経由の参照は実測 0 件 — 発生したら検出漏れ防止のため警告
        for m in re.finditer(r'getelementptr [\w]+, ptr (%[\w.$-]+)[^\n]*', body):
            if root(m.group(1)) in allocas:
                gep_warn.append((name, m.group(0).strip()[:120]))

        need = {}
        rule_of = {}

        def require(v, sz, rule):
            r = root(v)
            if r in allocas and sz > 0:
                if sz > need.get(r, 0):
                    need[r] = sz
                    rule_of[r] = rule
                det[rule] += 1

        for m in re.finditer(r'^\s*(?:%[\w.$-]+ = )?call [^@]*@([\w.$-]+)\(([^;\n]*)\)', body, re.M):
            callee, argtxt = m.group(1), m.group(2)
            args = split_args(argtxt)
            if callee in STOS and len(args) >= 3:                       # R1
                v, n = reg_of(args[0]), num_of(args[2])
                if v and n:
                    require(v, n * STOS[callee], 'R1_rep_stos')
            elif callee in MOVS and len(args) >= 3:                     # R2
                v, n = reg_of(args[0]), num_of(args[2])
                if v and n:
                    require(v, n * MOVS[callee], 'R2_rep_movs')
            elif callee == FILLCHAR and len(args) >= 2:                 # R3
                v, n = reg_of(args[0]), num_of(args[1])
                if v and n and n > 0:
                    require(v, n, 'R3_fillchar')
            elif callee.startswith('llvm.memset') and len(args) >= 3:   # R4
                v, n = reg_of(args[0]), num_of(args[2])
                if v and n:
                    require(v, n, 'R4_llvm_mem')
            elif (callee.startswith('llvm.memcpy') or callee.startswith('llvm.memmove')) and len(args) >= 3:
                v, n = reg_of(args[0]), num_of(args[2])
                if v and n:
                    require(v, n, 'R4_llvm_mem')
            elif callee in API_OUT:                                     # R5
                for idx, sz in API_OUT[callee].items():
                    if idx < len(args):
                        v = reg_of(args[idx])
                        if v:
                            require(v, sz, 'R5_api_out')
            elif callee in COUNT_BUF:                                   # R6
                for (bi, ci, el) in COUNT_BUF[callee]:
                    if bi < len(args) and ci < len(args):
                        v, n = reg_of(args[bi]), num_of(args[ci])
                        if v and n and n > 0:
                            require(v, n * el, 'R6_count_buf')

        for m in re.finditer(r'^\s*store ([\w]+) [^,]+, ptr (%[\w.$-]+)(?:, align \d+)?\s*$', body, re.M):  # R7
            sz = SZ.get(m.group(1))
            if sz:
                require(m.group(2), sz, 'R7_wide_store')

        nb = body
        for v, sz in sorted(need.items()):
            cur = allocas[v][0]
            if cur is None or cur >= sz:
                continue
            if sz > MAX_WIDEN:
                over_cap.append({'function': name, 'alloca': v, 'was_bytes': cur, 'need_bytes': sz})
                continue
            k = (sz + 7) // 8
            widened.append({'function': name, 'alloca': v, 'was_bytes': cur, 'now_bytes': k * 8, 'need_bytes': sz,
                            'was_type': allocas[v][1], 'rule': rule_of.get(v)})
            nb = re.sub(r'(^\s*%s = alloca )[^,\n]+?(, align )\d+(\s*)$' % re.escape(v),
                        lambda mm: '%s[%d x i64]%s8%s' % (mm.group(1), k, mm.group(2), mm.group(3)),
                        nb, count=1, flags=re.M)
        if nb != body:
            pieces.append((fm.start(), fm.end(), nb))

    out, pos = [], 0
    for s, e, nb in pieces:
        out.append(src[pos:s]); out.append(nb); pos = e
    out.append(src[pos:])
    open(dst_path, 'w').write(''.join(out))

    total_add = sum(w['now_bytes'] - w['was_bytes'] for w in widened)
    print('[m11_alloca] 検出 (証拠サイト): %s' % det)
    print('[m11_alloca] 拡幅 alloca %d 個 / %d 関数, 追加 stack %d B (最大 1件 %d B)' % (
        len(widened), len({w['function'] for w in widened}), total_add,
        max((w['now_bytes'] - w['was_bytes']) for w in widened), ) if widened else '[m11_alloca] 拡幅 0 個 (idempotent / 証拠無し)')
    if over_cap:
        print('[m11_alloca] 上限超過で skip: %d 件' % len(over_cap))
    if gep_warn:
        print('[m11_alloca] 警告: alloca への GEP 参照 %d 件 (想定外パターン, 未対応): %s' % (len(gep_warn), gep_warn[:3]))
    if rep_path:
        byrule = {}
        for w in widened:
            byrule[w.get('rule', '?')] = byrule.get(w.get('rule', '?'), 0) + 1
        json.dump({'detector_counts': det, 'functions_patched': len({w['function'] for w in widened}),
                   'widened_count': len(widened), 'widened_by_rule': byrule, 'total_added_bytes': total_add,
                   'widened': widened, 'over_cap': over_cap, 'gep_warn': gep_warn},
                  open(rep_path, 'w'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
