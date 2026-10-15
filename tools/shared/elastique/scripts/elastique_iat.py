#!/usr/bin/env python3
"""élastique (win elastique_x64.dll) の IAT (KERNEL32 77・WS2_32 2) の呼出元と到達性を実測する (T-SH-41 / #2614 受入 4).

入力: work/win/elastique_x64.dll (fl-win64 の extracted/block24357_PE.bin, docs/REFERENCES.md [WIN64])
出力: work/elastique/iat_callers.json (全件・呼出元の関数先頭 VA) と data/iat_policy.csv (置換方針の表) と標準出力の要約。
依存: python3 + capstone。PE 解析は elastique_facts.py の parse_pe / exports / pdata_funcs を流用する。
到達性は export の関数から直接 call/jmp を辿った下界 (dispatch 表経由の間接分岐は辿らない)。
"""
import bisect
import collections
import csv
import json
import os
import struct
import sys

from capstone import CS_ARCH_X86, CS_MODE_64, CS_OP_IMM, CS_OP_MEM, Cs
from capstone.x86 import X86_REG_RIP

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from elastique_facts import DEFAULT_DLL, OUT_DIR, cstr, exports, parse_pe, pdata_funcs  # noqa: E402

DATA_DIR = os.path.normpath(os.path.join(HERE, "..", "data"))
POLICY_CSV = os.path.join(DATA_DIR, "iat_policy.csv")

# 置換方針 (T-SH-41 受入 4)。分類ごとの方針は REPORT_2614.md §3。(分類, wasm 側の写像, 実測の根拠)
_A = "A メモリ"
_B = "B 同期・イベント (単一スレッド)"
_C = "C TLS/FLS (インスタンス内の表)"
_D = "D 例外・unwind (SEH 無し)"
_E = "E 動的ロード (常に失敗)"
_F = "F ファイル・コンソール (host 無し)"
_G = "G プロセス・エラー状態"
_H = "H 時刻・性能カウンタ"
_I = "I CPU・コードページ・文字列"
_J = "J バイトオーダ変換"
POLICY = {
    "HeapAlloc": (_A, "malloc (flags & 8 なら calloc)", "flags は xor 0 / mov 8"),
    "HeapFree": (_A, "free", "flags 0"),
    "HeapReAlloc": (_A, "realloc。ただし flags 0x10 (HEAP_REALLOC_IN_PLACE_ONLY) は同位置で伸ばせなければ NULL", "flags は xor 0 (0x1802d8c41) と edx = rax+0xf で 0x10 (0x1802da416・rax = 1)"),
    "HeapSize": (_A, "サイズ表 (malloc_usable_size 相当)", "flags 0"),
    "HeapQueryInformation": (_A, "固定値", ""),
    "GetProcessHeap": (_A, "非 NULL の固定ハンドル", ""),
    "CreateEventW": (_B, "固定の偽ハンドル", "export 非到達"),
    "SetEvent": (_B, "成功 (1) を返す", ""),
    "ResetEvent": (_B, "成功 (1) を返す", ""),
    "WaitForSingleObjectEx": (_B, "WAIT_OBJECT_0 を返す (要確認)", "戻り値の分岐は未確認"),
    "EnterCriticalSection": (_B, "no-op", "CreateThread 無し (単一スレッド)"),
    "LeaveCriticalSection": (_B, "no-op", ""),
    "InitializeCriticalSectionAndSpinCount": (_B, "no-op (0 を返す)", ""),
    "DeleteCriticalSection": (_B, "no-op", ""),
    "InitializeSListHead": (_B, "先頭を 0 に初期化", "thunk 1 本・呼出し 0 件 (未使用)"),
    "InterlockedFlushSList": (_B, "0 を返す", ""),
    "TlsAlloc": (_C, "インスタンス内の表 (TlsAlloc/Get/Set/Free)", ""),
    "TlsGetValue": (_C, "同上", ""),
    "TlsSetValue": (_C, "同上", ""),
    "TlsFree": (_C, "同上", ""),
    "FlsAlloc": (_C, "同上 (FLS)", "thunk のみ (pdata 外)。呼出元 1 関数"),
    "FlsGetValue": (_C, "同上 (FLS)", "thunk のみ (pdata 外)。export 到達"),
    "FlsSetValue": (_C, "同上 (FLS)", "thunk のみ (pdata 外)。export 到達"),
    "FlsFree": (_C, "同上 (FLS)", "thunk のみ (pdata 外)"),
    "RtlCaptureContext": (_D, "trap (SEH 経路は wasm に無い)", "export 到達"),
    "RtlLookupFunctionEntry": (_D, "trap", "export 到達"),
    "RtlVirtualUnwind": (_D, "trap", "export 到達"),
    "RtlUnwindEx": (_D, "trap", "export 非到達"),
    "RtlPcToFileHeader": (_D, "NULL を返す", "export 到達"),
    "RaiseException": (_D, "trap (fail-closed)", "ecx = 0xE06D7363 (C++ 例外) を設定するのは関数 0x1802caea8 内 (0x1802caf32)"),
    "UnhandledExceptionFilter": (_D, "0 を返す", "export 到達"),
    "SetUnhandledExceptionFilter": (_D, "NULL を返す (登録のみ)", "export 到達"),
    "IsDebuggerPresent": (_D, "0 を返す", "export 到達"),
    "GetModuleHandleW": (_E, "NULL を返す", "CRT の任意 API 探索。文字列 kernel32.dll・api-ms-win-core-synch-l1-2-0.dll"),
    "GetModuleHandleExW": (_E, "NULL を返す", "文字列 mscoree.dll (CorExitProcess 探索)"),
    "GetModuleFileNameW": (_E, "0 を返す", ""),
    "GetProcAddress": (_E, "NULL を返す", "探索名 SleepConditionVariableCS・CorExitProcess 等。失敗後の経路は要確認"),
    "LoadLibraryExW": (_E, "NULL を返す", "api-ms-/ext-ms- の解決 (API セット)"),
    "FreeLibrary": (_E, "成功 (1) を返す", ""),
    "CreateFileW": (_F, "INVALID_HANDLE_VALUE を返す", "文字列 CONOUT$ (出力先)。export 非到達"),
    "CloseHandle": (_F, "成功 (1) を返す", ""),
    "WriteConsoleW": (_F, "失敗を返す", "CONOUT$ 経路"),
    "WriteFile": (_F, "失敗を返す", ""),
    "FlushFileBuffers": (_F, "成功 (1) を返す", ""),
    "GetStdHandle": (_F, "NULL を返す", ""),
    "SetStdHandle": (_F, "成功 (1) を返す", ""),
    "GetFileType": (_F, "0 を返す", ""),
    "GetConsoleMode": (_F, "0 を返す", ""),
    "GetConsoleOutputCP": (_F, "固定値", ""),
    "SetFilePointerEx": (_F, "失敗を返す", ""),
    "FindFirstFileExW": (_F, "INVALID_HANDLE_VALUE を返す", ""),
    "FindNextFileW": (_F, "0 を返す", ""),
    "FindClose": (_F, "成功 (1) を返す", ""),
    "GetCurrentProcessId": (_G, "固定値", ""),
    "GetCurrentThreadId": (_G, "固定値", ""),
    "GetCurrentProcess": (_G, "擬似ハンドル (-1)", "export 到達"),
    "GetStartupInfoW": (_G, "0 埋め", ""),
    "GetCommandLineA": (_G, "空文字列", ""),
    "GetCommandLineW": (_G, "空文字列", ""),
    "GetEnvironmentStringsW": (_G, "空の環境ブロック", ""),
    "FreeEnvironmentStringsW": (_G, "成功 (1) を返す", ""),
    "GetLastError": (_G, "エラー状態の保持 (wasm 内の変数)", "export 到達"),
    "SetLastError": (_G, "同上", "export 到達"),
    "EncodePointer": (_G, "恒等写像", ""),
    "ExitProcess": (_G, "trap (終了の表明)", "引数 ebx"),
    "TerminateProcess": (_G, "trap (終了の表明)", "export 到達"),
    "QueryPerformanceCounter": (_H, "決定的な値 (要確認)。DSP 出力に影響しないことを確認", ""),
    "GetSystemTimeAsFileTime": (_H, "決定的な値 (要確認)", ""),
    "IsProcessorFeaturePresent": (_I, "0 を返す (baseline 経路)。CPU 機能の値は要確認", "引数 ecx = 0x17 固定。export 到達"),
    "GetACP": (_I, "固定値", ""),
    "GetOEMCP": (_I, "固定値", ""),
    "IsValidCodePage": (_I, "固定値", ""),
    "GetCPInfo": (_I, "固定値", ""),
    "MultiByteToWideChar": (_I, "UTF-8/ASCII の最小実装", "thunk 1 本・呼出し 0 件 (未使用)"),
    "WideCharToMultiByte": (_I, "同上", ""),
    "LCMapStringW": (_I, "入力をそのまま返す", ""),
    "GetStringTypeW": (_I, "固定値", ""),
    "ord8": (_J, "htonl = bswap32", "WS2_32 序数 8 (htonl)。"),
    "ord14": (_J, "ntohl = bswap32", "WS2_32 序数 14 (ntohl)。"),
}


def iat_slots(image, base, dd):
    rva, _ = dd["import"]
    out = []
    while True:
        oft, _, _, name, ft = struct.unpack_from("<IIIII", image, rva)
        if oft == 0 and name == 0 and ft == 0:
            break
        dll = cstr(image, name)
        i = 0
        while True:
            v, = struct.unpack_from("<Q", image, (oft or ft) + 8 * i)
            if v == 0:
                break
            api = "ord%d" % (v & 0xFFFF) if v & (1 << 63) else cstr(image, v + 2)
            out.append({"dll": dll, "api": api, "slot": base + ft + 8 * i})
            i += 1
        rva += 20
    return out


def main():
    dll = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DLL
    raw = open(dll, "rb").read()
    base, sections, image, dd = parse_pe(raw)
    sec = {s["name"]: s for s in sections}
    regions = [(base + sec[n]["va"], base + sec[n]["va"] + sec[n]["vsize"]) for n in (".text", "IPPCODE")]
    in_code = lambda x: any(lo <= x < hi for lo, hi in regions)  # noqa: E731

    slots = iat_slots(image, base, dd)
    slot_by_va = {s["slot"]: s for s in slots}
    funcs = sorted(pdata_funcs(image, base, dd))
    starts = [a for a, _ in funcs]
    ends = dict(funcs)

    def owner(va):
        i = bisect.bisect_right(starts, va) - 1
        if i >= 0 and va < ends[starts[i]]:
            return starts[i]
        return None

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    refs = collections.defaultdict(list)  # slot va -> [(kind, owner, site)] (pdata 関数内の直接参照)
    edges = collections.defaultdict(set)  # pdata 関数先頭 -> call/jmp の直接の飛び先 (VA)
    for a, b in funcs:
        if not in_code(a):
            continue
        for ins in md.disasm(bytes(image[a - base:b - base]), a):
            for op in ins.operands:
                if op.type == CS_OP_MEM and op.mem.base == X86_REG_RIP:
                    ea = ins.address + ins.size + op.mem.disp
                    if ea in slot_by_va:
                        kind = ins.mnemonic if ins.mnemonic in ("call", "jmp") else "data"
                        refs[ea].append((kind, a, ins.address))
            if ins.mnemonic in ("call", "jmp") and ins.operands and ins.operands[0].type == CS_OP_IMM:
                t = ins.operands[0].imm
                if in_code(t) and not (a <= t < b and ins.mnemonic == "jmp"):
                    edges[a].add(t)

    # pdata 外の thunk (jmp [IAT] の 1 命令。REX.W 接頭辞 48 を含む)。バイト走査で位置を求める
    thunk = collections.defaultdict(set)  # slot va -> thunk 先頭 VA
    byte_hits = collections.Counter()
    for lo, hi in regions:
        lo_r, hi_r = lo - base, hi - base
        for opc in (b"\xff\x15", b"\xff\x25"):
            p = image.find(opc, lo_r, hi_r)
            while p != -1 and p + 6 <= hi_r:
                t = base + p + 6 + struct.unpack_from("<i", image, p + 2)[0]
                if t in slot_by_va:
                    site = base + p - (1 if 0x40 <= image[p - 1] <= 0x4F else 0)
                    byte_hits[t] += 1
                    if owner(site) is None:
                        thunk[t].add(site)
                p = image.find(opc, p + 1, hi_r)
    thunk_at = {site: slot for slot, sites in thunk.items() for site in sites}

    # 呼出元: thunk への直接 call (pdata 内) も、その API の呼出元に数える
    via_thunk = collections.defaultdict(set)  # slot va -> caller pdata 関数先頭
    for a, tos in edges.items():
        for t in tos:
            if t in thunk_at:
                via_thunk[thunk_at[t]].add(a)
    # 下界の到達性: export 関数から call/jmp (直接) を辿る。thunk は辿った先として扱う
    exp = exports(image, dd)
    frontier = [base + frva for _, frva in exp]
    seen = set()
    while frontier:
        t = frontier.pop()
        f = owner(t) if owner(t) is not None else t
        if f in seen:
            continue
        seen.add(f)
        for u in edges.get(f, ()):
            if u not in seen:
                frontier.append(u)

    rows = []
    for s in slots:
        r = refs.get(s["slot"], [])
        callers = sorted({o for _, o, _ in r} | via_thunk.get(s["slot"], set()))
        reached = sorted({o for _, o, _ in r if o in seen} | {x for x in thunk.get(s["slot"], ()) if x in seen})
        rows.append({
            "dll": s["dll"],
            "api": s["api"],
            "iat_va": "0x%x" % s["slot"],
            "refs_pdata": len(r),
            "refs_call": sum(1 for k, _, _ in r if k == "call"),
            "refs_jmp": sum(1 for k, _, _ in r if k == "jmp"),
            "refs_data": sum(1 for k, _, _ in r if k == "data"),
            "thunks": len(thunk.get(s["slot"], ())),
            "callers_pdata": len(callers),
            "refs_bytes": byte_hits.get(s["slot"], 0),
            "reached_from_exports": len(reached),
            "callers": ["0x%x" % c for c in callers],
            "policy": POLICY.get(s["api"], ("", "", "")),
        })

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "iat_callers.json"), "w") as f:
        json.dump({"dll": os.path.basename(dll), "exports_reached_functions": len(seen), "rows": rows}, f, indent=1)

    with open(POLICY_CSV, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["dll", "api", "iat_va", "refs_pdata", "refs_call", "refs_jmp", "refs_data", "thunks",
                    "callers_pdata", "refs_bytes", "reached_from_exports", "category", "wasm_policy", "note"])
        for r in rows:
            cat, pol, note = r["policy"]
            w.writerow([r["dll"], r["api"], r["iat_va"], r["refs_pdata"], r["refs_call"], r["refs_jmp"],
                        r["refs_data"], r["thunks"], r["callers_pdata"], r["refs_bytes"], r["reached_from_exports"],
                        cat, pol, note])

    print("iat:", len(slots), collections.Counter(s["dll"] for s in slots))
    print("pdata functions in .text:", sum(1 for a, _ in funcs if regions[0][0] <= a < regions[0][1]))
    print("exports reached functions (direct call/jmp, lower bound):", len(seen))
    print("slots with 0 pdata refs:", sum(1 for r in rows if r["refs_pdata"] == 0), "(of which thunk-only:", sum(1 for r in rows if r["refs_pdata"] == 0 and r["thunks"]), ")")
    print("slots with 0 export-reached refs:", sum(1 for r in rows if r["reached_from_exports"] == 0))
    print("sites: pdata direct refs %d / thunk sites outside pdata %d / byte-scan total %d" % (
        sum(r["refs_pdata"] for r in rows), sum(r["thunks"] for r in rows), sum(r["refs_bytes"] for r in rows)))
    for r in rows:
        print("%-12s %-40s pd=%3d thunk=%d fn=%3d reach=%3d" % (
            r["dll"][:8], r["api"], r["refs_pdata"], r["thunks"], r["callers_pdata"], r["reached_from_exports"]))


if __name__ == "__main__":
    main()
