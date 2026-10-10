#!/usr/bin/env python3
"""gen_adapt.py — m11 IR の GUI declare と shim exports の突合 + wasm32 署名 adapter の生成 (CAB-156 / GUI-3a)。

入力 : IR (既定 integ/fixtures/boot_final_gui_declares.ll = m11 boot_final.ll の GUI declare 抜粋; 実 IR は --ir で指定、--refresh-fixture で更新)
       build/gui_reach_tab.json (gen_api.py 産: shim の全 API 名/arity/stub/優先度), analysis/imports_all.json (GUI import 名)
出力 : build/gui_adapt_w32.c        wasm32 署名 adapter (IR の declare 署名 -> shim の int64 ABI)
       integ/INTEGRATION_XCHECK.md 突合表 (a 実装済み / b fail-fast stub / c 署名不一致と変換方針)
       integ/fixtures/boot_final_gui_declares.ll  (--refresh-fixture 時) IR から GUI declare だけ抜いた再現用 fixture

変換方針 (c の解消; IR 署名は wasm32: ptr=i32, WPARAM/LPARAM/LONG_PTR=i32):
  引数 ptr -> zero-extend (<2^31 のハンドル/ポインタ、< 0x10000 は MAKEINTRESOURCE/atom としてそのまま)
  引数 i32 -> sign-extend / i16,i8,i1 -> zero-extend / i64 -> そのまま
  引数 8 byte 以下の struct 値渡し (例 %tagPOINT) -> x64 ABI 同様 1 個の int64 へ詰める (wasm 側は要素ごとの scalar 引数)
  戻り値は IR の型へ切詰め (ptr は 32bit zero-extend 値、i1 は !=0)
reach ログ: -DGUI_REACH_LOG でビルドした adapter は入口で gui_reach_hit(idx) を呼ぶ。
usage: gen_adapt.py [--ir PATH] [--native] [--no-md] [--refresh-fixture]
"""
import argparse, json, os, re, sys, subprocess, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
GUI = os.path.dirname(HERE)
BUILD = os.path.join(GUI, "build")
FIXTURE = os.path.join(HERE, "fixtures", "boot_final_gui_declares.ll")
DEFAULT_IR = FIXTURE  # 決定的にするため既定は fixture。実 IR で検証するときは --ir tools/m11/work/boot_final.ll
GUI_DLLS = ["user32.dll", "gdi32.dll", "comctl32.dll", "comdlg32.dll", "opengl32.dll", "uxtheme.dll", "imm32.dll",
            "msimg32.dll", "dwmapi.dll", "winspool.drv", "oleacc.dll", "wtsapi32.dll", "shcore.dll"]
INT_BITS = {"i1": 1, "i8": 8, "i16": 16, "i32": 32, "i64": 64}


def split_top(s):
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch in "({<[": depth += 1
        elif ch in ")}>]": depth -= 1
        if ch == "," and depth == 0: out.append(cur.strip()); cur = ""
        else: cur += ch
    if cur.strip(): out.append(cur.strip())
    return out


def parse_ir(path):
    src = open(path, encoding="utf-8", errors="replace").read()
    structs = {m.group(1): [x.strip() for x in m.group(2).split(",")] for m in re.finditer(r"^%([\w.$-]+) = type \{ ([^}]*) \}", src, re.M)}
    decl = {}
    for m in re.finditer(r"^declare\s+(?:\w+\s+)*?(void|i\d+|ptr|float|double|%[\w.$-]+)\s+@([\w.$-]+)\(([^)]*)\)", src, re.M):
        ret, name, args = m.group(1), m.group(2), m.group(3)
        params = [] if args.strip() in ("", "void") else split_top(args)
        va = any(p == "..." for p in params)
        types = [p.split()[0] for p in params if p != "..."]
        decl[name] = (ret, types, va)
    return src, structs, decl


def struct_scalars(t, structs):
    """%name -> [scalar types] (入れ子は未対応 = None)"""
    if not t.startswith("%"): return None
    f = structs.get(t[1:])
    if f is None or any(x not in INT_BITS for x in f): return None
    return f


def plan(ret, types, structs):
    """adapter の C 引数列と、shim へ渡す int64 引数式の列を作る。戻り: (c_params[(ctype,name)], shim_args[expr], c_ret, unsupported)"""
    cp, sa = [], []
    for i, t in enumerate(types):
        n = "a%d" % i
        if t == "ptr": cp.append(("void *", n)); sa.append("GUI_PIN(%s)" % n)
        elif t == "i64": cp.append(("int64_t", n)); sa.append(n)
        elif t == "i32": cp.append(("int32_t", n)); sa.append("(int64_t)%s" % n)
        elif t in ("i16", "i8"): cp.append(("uint%d_t" % INT_BITS[t], n)); sa.append("(int64_t)%s" % n)
        elif t == "i1": cp.append(("_Bool", n)); sa.append("(int64_t)%s" % n)
        elif t in ("float", "double"): return None, None, None, "float arg"
        else:
            sc = struct_scalars(t, structs)
            if not sc: return None, None, None, "aggregate arg %s" % t
            tot = sum(INT_BITS[x] for x in sc)
            if tot > 64: return None, None, None, "aggregate %s > 8 bytes" % t
            names = ["%s_%d" % (n, k) for k in range(len(sc))]
            for x, nn in zip(sc, names): cp.append(("int%d_t" % max(8, INT_BITS[x]), nn))
            expr, sh = [], 0
            for x, nn in zip(sc, names):
                expr.append("((uint64_t)(uint%d_t)%s << %d)" % (INT_BITS[x], nn, sh)); sh += INT_BITS[x]
            sa.append("(int64_t)(%s)" % " | ".join(expr))
    if ret == "void": cr = "void"
    elif ret == "ptr": cr = "void *"
    elif ret == "i64": cr = "int64_t"
    elif ret == "i32": cr = "int32_t"
    elif ret in ("i16", "i8"): cr = "uint%d_t" % INT_BITS[ret] if False else "int%d_t" % INT_BITS[ret]
    elif ret == "i1": cr = "_Bool"
    else: return None, None, None, "ret %s" % ret
    return cp, sa, cr, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ir"); ap.add_argument("--native", action="store_true"); ap.add_argument("--no-md", action="store_true")
    ap.add_argument("--refresh-fixture", action="store_true")
    ap.add_argument("--probe", help="IR の GUI declare を全て参照する .ll を出力 (sigprobe.sh 用)")
    ap.add_argument("--out", default=os.path.join(BUILD, "gui_adapt_w32.c"))
    a = ap.parse_args()
    ir = a.ir or (DEFAULT_IR if os.path.exists(DEFAULT_IR) else FIXTURE)
    if not os.path.exists(os.path.join(BUILD, "gui_reach_tab.json")):
        subprocess.run([sys.executable, os.path.join(GUI, "gen_api.py")], check=True, stdout=subprocess.DEVNULL)
    tab = json.load(open(os.path.join(BUILD, "gui_reach_tab.json")))
    names, stubs, prio, arity = tab["names"], set(tab["stub"]), tab["prio"], tab["arity"]
    idx = {n: i for i, n in enumerate(names)}
    imp = json.load(open(os.path.join(GUI, "analysis", "imports_all.json")))
    guiset = {r["name"] for r in imp["imports"] if r["dll"] in GUI_DLLS}
    xref = {r["name"]: r["xref"] for r in imp["imports"] if r["dll"] in GUI_DLLS}
    src, structs, decl = parse_ir(ir)
    if a.refresh_fixture:
        os.makedirs(os.path.dirname(FIXTURE), exist_ok=True)
        with open(FIXTURE, "w") as f:
            f.write("; boot_final.ll から GUI import 名の declare と参照 struct 型だけ抜いた再現用 fixture (gen_adapt.py --refresh-fixture)\n")
            used = set()
            lines = []
            for m in re.finditer(r"^declare\s+(?:\w+\s+)*?(?:void|i\d+|ptr|float|double|%[\w.$-]+)\s+@([\w.$-]+)\(([^)]*)\)[^\n]*$", src, re.M):
                if m.group(1) in guiset:
                    lines.append(m.group(0)); used.update(re.findall(r"%[\w.$-]+", m.group(0)))
            for t in sorted(used):
                if t[1:] in structs: f.write("%s = type { %s }\n" % (t, ", ".join(structs[t[1:]])))
            f.write("\n".join(sorted(lines)) + "\n")
        print("[adapt] fixture refreshed:", FIXTURE, len(lines), "declares")
    if a.probe:
        gl = []; used = set()
        for m in re.finditer(r"^declare\s+(?:\w+\s+)*?(?:void|i\d+|ptr|float|double|%[\w.$-]+)\s+@([\w.$-]+)\(([^)]*)\)[^\n]*$", src, re.M):
            if m.group(1) in guiset: gl.append((m.group(1), m.group(0))); used.update(re.findall(r"%[\w.$-]+", m.group(0)))
        with open(a.probe, "w") as f:
            for t in sorted(used):
                if t[1:] in structs: f.write("%s = type { %s }\n" % (t, ", ".join(structs[t[1:]])))
            f.write("\n".join(l for _, l in gl) + "\n")
            callers = []
            for i, (n, l) in enumerate(gl):   # 直接 call も置く (wasm-ld の署名検査は call/参照の型付き relocation に対して働く)
                ret, types, _va = decl[n]
                f.write("define void @gui_probe_%d() {\n  %s@%s(%s)\n  ret void\n}\n" % (
                    i, "call void " if ret == "void" else "%r = call " + ret + " ",
                    n, ", ".join("%s undef" % t for t in types)))
                callers.append("gui_probe_%d" % i)
            f.write("@gui_probe_tab = constant [%d x ptr] [%s]\n@gui_probe_keep = global ptr @gui_probe_tab\n" % (len(gl), ", ".join("ptr @%s" % n for n, _ in gl)))
            f.write("@gui_probe_calls = constant [%d x ptr] [%s]\n@gui_probe_keep2 = global ptr @gui_probe_calls\n" % (len(callers), ", ".join("ptr @%s" % c for c in callers)))
    rows = []   # (name, status, detail)
    adapters = []
    for n in sorted(decl):
        if n not in guiset: continue
        ret, types, va = decl[n]
        sig = "%s(%s)" % (ret, ", ".join(types))
        st = "stub" if n in stubs else ("impl" if n in arity else "none")
        if st == "none":
            rows.append((n, "d", st, sig, "shim に存在しない", xref.get(n, 0))); continue
        cp, sa, cr, why = plan(ret, types, structs)
        if why or va:
            rows.append((n, "c", st, sig, why or "variadic", xref.get(n, 0))); continue
        if len(sa) != arity[n]:
            rows.append((n, "c", st, sig, "arity IR=%d shim=%d" % (len(sa), arity[n]), xref.get(n, 0))); continue
        note = []
        if any(t.startswith("%") for t in types): note.append("struct 値渡し -> int64 詰め")
        if any(t == "i1" for t in types): note.append("i1")
        rows.append((n, "a" if st == "impl" else "b", st, sig, "; ".join(note), xref.get(n, 0)))
        adapters.append((n, cp, sa, cr))
    # ---- C 生成
    with open(a.out, "w") as f:
        f.write("/* generated by integ/gen_adapt.py from %s — wasm32 署名 adapter (手編集禁止)\n"
                " * shim 本体は gui_rename.h (-include) で gui_impl_<Name> に改名してビルドし、ここが公開名 <Name> を IR の署名で提供する */\n"
                % os.path.relpath(ir, GUI))
        f.write("#include <stdint.h>\nextern void gui_reach_hit(int idx);\n")
        f.write("#if defined(__wasm32__) || defined(__EMSCRIPTEN__)\n#define GUI_PIN(p) ((int64_t)(uint32_t)(uintptr_t)(p))\n#define GUI_POUT(v) ((void *)(uintptr_t)(uint32_t)(v))\n")
        f.write("#else   /* native 検証 (wiring のみ; 32bit 化は検証しない) */\n#define GUI_PIN(p) ((int64_t)(uintptr_t)(p))\n#define GUI_POUT(v) ((void *)(uintptr_t)(v))\n#endif\n")
        f.write("#ifdef GUI_REACH_LOG\n#define GUI_HIT(i) gui_reach_hit(i)\n#else\n#define GUI_HIT(i) ((void)0)\n#endif\n\n")
        for n, cp, sa, cr in adapters:
            ar = arity[n]
            f.write("extern int64_t gui_impl_%s(%s);\n" % (n, ", ".join(["int64_t"] * ar) if ar else "void"))
            ps = ", ".join("%s %s" % (t, nn) for t, nn in cp) if cp else "void"
            call = "gui_impl_%s(%s)" % (n, ", ".join(sa))
            if cr == "void": body = "%s; " % call
            elif cr == "void *": body = "return GUI_POUT(%s); " % call
            elif cr == "_Bool": body = "return %s != 0; " % call
            else: body = "return (%s)%s; " % (cr, call)
            f.write("%s %s(%s) { GUI_HIT(%d); %s}\n" % (cr, n, ps, idx[n], body))
    na = sum(1 for r in rows if r[1] in "ab"); nc = sum(1 for r in rows if r[1] == "c"); nd = sum(1 for r in rows if r[1] == "d")
    print("[adapt] ir=%s declares(GUI)=%d adapters=%d (impl %d / stub %d) c=%d d=%d -> %s" % (
        os.path.relpath(ir, GUI), len(rows), na, sum(1 for r in rows if r[1] == "a"), sum(1 for r in rows if r[1] == "b"), nc, nd, a.out))
    if a.no_md: return
    # ---- md
    rows.sort(key=lambda r: (r[2] != "stub", -r[5], r[0]))
    gui_missing = sorted(n for n in guiset if n not in decl)
    reached_stub = [r for r in rows if r[2] == "stub"]
    with open(os.path.join(HERE, "INTEGRATION_XCHECK.md"), "w") as f:
        w = f.write
        w("# m11 IR の GUI declare ↔ shim exports 突合表 (自動生成)\n\n")
        w("生成: `python3 tools/gui/integ/gen_adapt.py` / 入力 IR: `%s` (%d B, sha1 %s)。shim 側は `build/gui_reach_tab.json` (gen_api.py 産; 実装 %d + stub %d)。\n\n"
          % (os.path.relpath(ir, GUI) if ir != FIXTURE else "integ/fixtures/boot_final_gui_declares.ll (m11 boot_final.ll の GUI declare 抜粋)",
             os.path.getsize(ir), hashlib.sha1(open(ir, "rb").read()).hexdigest()[:10], len(arity) - len(stubs), len(stubs)))
        w("## 1. 要約\n\n| 区分 | 件数 | 意味 |\n|---|---|---|\n")
        w("| IR が declare する GUI 系 import 名 | %d | FLEngine の GUI import %d 名のうち m11 IR(boot 到達閉包)に現れるもの |\n" % (len(rows), len(guiset)))
        w("| (a) 実装済み・adapter 生成可 | %d | `gui_adapt_w32.c` の wrapper で署名一致 |\n" % sum(1 for r in rows if r[1] == "a"))
        w("| (b) fail-fast stub・adapter 生成可 | %d | 署名は合うが到達すると `FAIL-FAST: unimplemented Win32 API` で停止 (**実到達 API ログで優先度見直し対象**) |\n" % sum(1 for r in rows if r[1] == "b"))
        w("| (c) 署名不一致 (adapter 不能) | %d | 下記変換方針で **0 件**であることが完了条件 |\n" % nc)
        w("| (d) shim に存在しない | %d | gen_api.py の arity 表(mingw ヘッダ+手動表)が全 import を網羅しているため 0 の想定 |\n" % nd)
        w("| IR 未 declare (まだ lift 閉包に現れない) | %d | 実結合で lift 範囲が広がると declare される。同じ adapter 生成で追従 |\n\n" % len(gui_missing))
        w("## 2. 変換方針 (署名不一致 0 の根拠)\n\n"
          "shim は全 API を `int64_t NAME(int64_t...)` (lift ABI) で公開、m11 IR は wasm32 型 (`ptr`=i32、WPARAM/LPARAM/LONG_PTR=i32、`i1`/`i16`/`%tagPOINT` 値渡しも出現)。"
          "wasm-ld は同名で型が違う関数を結合すると trap thunk を作るため、**shim 本体を `gui_impl_<Name>` へ改名し、IR 署名の adapter が公開名を定義**する"
          " (`build/gui_rename.h` を shim TU に `-include`)。\n\n"
          "| IR 型 | 引数の int64 化 | 戻り値 |\n|---|---|---|\n| ptr | zero-extend (shim は 2^31 未満のハンドル/ポインタを発行、< 0x10000 は atom/MAKEINTRESOURCE) | 32bit zero-extend 値を ptr に |\n"
          "| i32 | sign-extend (`GWL_STYLE=-16` 等が負で来る) | 下位 32bit |\n| i16/i8/i1 | zero-extend | 切詰め / `!=0` |\n"
          "| i64 | そのまま (`POINT` 詰め値など) | そのまま |\n| 8 byte 以下 struct 値渡し | wasm 側は要素ごとの scalar 引数 -> adapter が 1 個の int64 に詰める (x64 ABI 相当; `WindowFromPoint`) | - |\n\n")
        w("コールバック (`WNDPROC`/`TIMERPROC`/`EnumWindowsProc`) の呼出は `gui_set_icall_hook()` で m11 の `m11_icall` (VA -> trampoline, 8×u64 統一署名) に委譲するので、"
          "lifted 側 WNDPROC の署名が 4 引数でなくても `call_indirect` 署名不一致は起きない (INTEGRATION.md §3)。\n\n")
        w("## 3. 到達しうる fail-fast stub (b) — %d 件\n\n" % len(reached_stub))
        if reached_stub:
            w("| API | xref | IR 署名 | 備考 |\n|---|---|---|---|\n")
            for r in reached_stub: w("| %s | %d | `%s` | %s |\n" % (r[0], r[5], r[3], r[4]))
        else:
            w("なし (IR が declare する GUI API はすべて実装済み)。\n")
        w("\n## 4. 全突合表 (xref 降順; stub を先頭)\n\n| API | 区分 | shim | P | IR 署名 | 備考 |\n|---|---|---|---|---|---|\n")
        for r in rows:
            w("| %s | %s | %s | %s | `%s` | %s |\n" % (r[0], r[1], r[2], ("P%d" % prio[r[0]]) if r[0] in prio and prio[r[0]] >= 0 else "-", r[3], r[4]))
        w("\n## 5. IR 未 declare の GUI import (%d 名; 実結合で出現しうる)\n\n" % len(gui_missing))
        stat = lambda n: "stub" if n in stubs else "impl"
        w("実装済み %d / stub %d。stub の内訳 (P 別): " % (sum(1 for n in gui_missing if stat(n) == "impl"), sum(1 for n in gui_missing if stat(n) == "stub")))
        w(", ".join("P%d=%d" % (p, sum(1 for n in gui_missing if stat(n) == "stub" and prio.get(n, 9) == p)) for p in range(4)) + "\n")
    print("[adapt] wrote", os.path.join(HERE, "INTEGRATION_XCHECK.md"))


if __name__ == "__main__":
    main()
