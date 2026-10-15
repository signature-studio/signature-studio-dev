#!/usr/bin/env python3
"""FLEngine_x64.dll のスレッド生成・同期・待機 API の呼出面を静的に実測する (AU-8 #194)。

worklet 内 (ブロッキング不可) で FL ミキサを走らせるときに再設計が要る箇所の見積り根拠。
  1. IAT から「スレッド生成 / ブロッキング待機 / 非ブロッキング同期 / TLS・優先度」の API を分類
  2. `jmp [rip+IAT]` thunk と、IAT への `call [rip+disp]` 直呼びの参照元 (call 箇所) を数える
  3. 参照元の関数を .pdata で解決し distinct 関数数を数える
判定 (gate): 各クラスで期待する下限を満たさなければ exit 1。--negctl は対象 PE を差し替えて gate が FAIL することを確認する
  (exit 0 = 「negctl で期待どおり FAIL した」)。
使い方: FL_WIN64_DIR=<fl-win64 展開先> python3 fl_thread_surface.py [--json out.json] [--negctl]
依存: pefile (uv pip install pefile)"""
import sys, os, re, struct, json, bisect, collections
import pefile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared"))
from paths import FL_WIN64_DIR

NEG = "--negctl" in sys.argv
# 対象 PE: FLEngine_x64.dll。negctl は同ディレクトリの別 PE (スレッド API をほぼ使わない小さな PE) に差し替える
MAIN_PE = os.path.join(FL_WIN64_DIR, "extracted", "block00031_PE.bin")
NEG_PE = os.environ.get("NEG_PE")

from thread_api import CLASSES, API2CLASS
# gate: FLEngine は FL ミキサ/ASIO/MIDI/ファイル I/O スレッドを持つ DAW。これらが 0 件ならスキャナ (または対象 PE) が壊れている
GATE = [("thread_create", "CreateThread", 1), ("blocking_wait", "WaitForSingleObject", 1),
        ("nonblocking_sync", "SetEvent", 1), ("blocking_wait", "Sleep", 1)]

path = NEG_PE if (NEG and NEG_PE) else MAIN_PE
# 出力 (stdout / JSON) に絶対パスを残さない: FL_WIN64_DIR 配下なら相対, それ以外は basename
shown = (os.path.relpath(path, FL_WIN64_DIR) if os.path.abspath(path).startswith(os.path.abspath(FL_WIN64_DIR) + os.sep)
         else os.path.basename(path))
if NEG and not NEG_PE:
    # 既定の negctl: 同じスキャナを「実在しない API 名」に向けた gate (期待 FAIL) — 名前照合が空振りしていないことの確認
    GATE = [(c, n + "__negctl_nonexistent", m) for c, n, m in GATE]
pe = pefile.PE(path)
img = pe.get_memory_mapped_image()
base = pe.OPTIONAL_HEADER.ImageBase
text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
t0, t1 = text.VirtualAddress, text.VirtualAddress + text.Misc_VirtualSize
pd = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".pdata"][0]
pdd = img[pd.VirtualAddress:pd.VirtualAddress + pd.Misc_VirtualSize]
funcs = []
for i in range(0, len(pdd) - 11, 12):
    b, e, _ = struct.unpack_from("<III", pdd, i)
    if b == 0:
        break
    funcs.append((b, e))
funcs.sort()
fstarts = [f[0] for f in funcs]


def func_of(rva):
    k = bisect.bisect_right(fstarts, rva) - 1
    return funcs[k] if k >= 0 and funcs[k][0] <= rva < funcs[k][1] else None


iat = {}   # slot rva -> (dll, name)
for e in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
    for imp in e.imports:
        if imp.name:
            iat[imp.address - base] = (e.dll.decode().lower(), imp.name.decode())
for e in getattr(pe, "DIRECTORY_ENTRY_DELAY_IMPORT", []):
    for imp in e.imports:
        if imp.name:
            iat[imp.address - base] = (e.dll.decode().lower(), imp.name.decode())

code = img[t0:t1]
thunks = {}     # thunk rva -> (dll, name)  : `jmp [rip+IAT]`
sites = collections.defaultdict(list)   # (dll,name) -> [call site rva]
for m in re.finditer(rb"\xff\x25", code):
    i = m.start()
    tgt = t0 + i + 6 + struct.unpack_from("<i", code, i + 2)[0]
    if tgt in iat:
        thunks[t0 + i] = iat[tgt]
for m in re.finditer(rb"\xff\x15", code):    # call [rip+IAT] 直呼び
    i = m.start()
    tgt = t0 + i + 6 + struct.unpack_from("<i", code, i + 2)[0]
    if tgt in iat:
        sites[iat[tgt]].append(t0 + i)
for m in re.finditer(rb"[\xe8\xe9]", code):  # call/jmp thunk
    i = m.start()
    if i + 5 > len(code):
        continue
    tgt = t0 + i + 5 + struct.unpack_from("<i", code, i + 1)[0]
    if tgt in thunks:
        sites[thunks[tgt]].append(t0 + i)

imports_by_dll = collections.Counter(d for d, _ in iat.values())
rows = []
for (dll, name), ss in sites.items():
    cls = API2CLASS.get(name)
    if cls:
        fs = {func_of(s) for s in ss if func_of(s)}
        rows.append({"class": cls, "api": name, "dll": dll, "call_sites": len(ss), "distinct_functions": len(fs)})
present = {n for _, n in iat.values()}
for cls, apis in CLASSES.items():   # import はあるが参照元が見つからない API も記録 (スキャン漏れの検知)
    for a in sorted(apis & present):
        if not any(r["api"] == a for r in rows):
            d = next(d for d, n in iat.values() if n == a)
            rows.append({"class": cls, "api": a, "dll": d, "call_sites": 0, "distinct_functions": 0})
rows.sort(key=lambda r: (r["class"], -r["call_sites"], r["api"]))

summary = {}
for cls in CLASSES:
    rs = [r for r in rows if r["class"] == cls]
    allf = set()
    for (dll, name), ss in sites.items():
        if API2CLASS.get(name) == cls:
            allf |= {func_of(s) for s in ss if func_of(s)}
    summary[cls] = {"imported_apis": len(rs), "call_sites": sum(r["call_sites"] for r in rs), "distinct_functions": len(allf)}

gate_res = []
for cls, name, mn in GATE:
    r = next((r for r in rows if r["api"] == name), None)
    got = r["call_sites"] if r else 0
    gate_res.append({"class": cls, "api": name, "min_call_sites": mn, "got": got, "ok": got >= mn})
ok = all(g["ok"] for g in gate_res)

print(f"PE: {shown}  (ImageBase {base:#x}, functions(.pdata)={len(funcs)}, imports={len(iat)}, dlls={len(imports_by_dll)})")
print(f"{'class':17s} {'api':34s} {'dll':26s} sites funcs")
for r in rows:
    print(f"{r['class']:17s} {r['api']:34s} {r['dll']:26s} {r['call_sites']:5d} {r['distinct_functions']:5d}")
print("\n## class summary (distinct_functions = クラス内のいずれかの API を呼ぶ関数の和集合)")
for cls, s in summary.items():
    print(f"  {cls:17s} apis={s['imported_apis']:3d} call_sites={s['call_sites']:5d} distinct_functions={s['distinct_functions']:5d}")
print("\n## gate")
for g in gate_res:
    print(f"  {'PASS' if g['ok'] else 'FAIL'} {g['api']} call_sites={g['got']} (want >= {g['min_call_sites']})")
if "--json" in sys.argv:
    json.dump({"pe": shown, "negctl": NEG, "functions": len(funcs), "imports": len(iat), "summary": summary, "rows": rows, "gate": gate_res, "ok": ok},
              open(sys.argv[sys.argv.index("--json") + 1], "w"), indent=1)
if NEG:
    print(f"\nnegctl: gate {'FAIL (期待どおり)' if not ok else 'PASS (= 検出能力なし)'}")
    sys.exit(0 if not ok else 1)
sys.exit(0 if ok else 1)
