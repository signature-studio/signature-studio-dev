#!/usr/bin/env python3.12
"""MCPTools.pyc (FL Studio 26.1.7 System/Tools/MCP) の構造抽出。

必ず CPython 3.12 (FL 同梱は 3.12.1) で実行すること (marshal/dis 互換のため)。
  work/build-native/install/bin/python3.12 analysis/mcp_extract.py > analysis/mcp/mcp_tools.json

出力: tools[] = {name, description, params[{name,type,desc,required}], api_calls[], helpers[],
                 api_calls_transitive[], unknown_modules[]}
"""
import dis
import json
import marshal
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
PYC = os.path.join(HERE, "..", "work", "MCPTools.pyc")
MIDI_PY = os.path.join(HERE, "..", "work", "midi.py")

FL_MODS = ["transport", "ui", "midi", "channels", "playlist", "patterns", "plugins",
           "arrangement", "general", "device", "mixer", "ilmcp"]


def load_code():
    data = open(PYC, "rb").read()
    import importlib.util
    assert data[:4] == importlib.util.MAGIC_NUMBER, "pyc magic が実行中の Python と不一致 (3.12 を使うこと)"
    return marshal.loads(data[16:])


def walk_code(co):
    yield co
    for c in co.co_consts:
        if isinstance(c, types.CodeType):
            yield from walk_code(c)


def api_refs(co, known_helpers):
    """code object 内の (module, attr) 参照と helper 関数呼出を抽出。"""
    apis, helpers = set(), set()
    ins = list(dis.get_instructions(co))
    for i, x in enumerate(ins):
        if x.opname in ("LOAD_GLOBAL", "LOAD_NAME") and x.argval in FL_MODS:
            nxt = ins[i + 1] if i + 1 < len(ins) else None
            if nxt and nxt.opname in ("LOAD_ATTR", "LOAD_METHOD"):
                apis.add(f"{x.argval}.{nxt.argval}")
            else:
                apis.add(f"{x.argval}.<module>")
        elif x.opname in ("LOAD_GLOBAL", "LOAD_NAME") and x.argval in known_helpers:
            helpers.add(x.argval)
    return apis, helpers


def main():
    top = load_code()
    # --- 1) FL 組込 API をモックして実行し、FL と同じ get_mcp_tools_json() の出力を得る ---
    sys.path.insert(0, os.path.dirname(MIDI_PY))
    import midi  # 実物 midi.py (FL Shared/Python/Lib)
    for m in FL_MODS:
        if m == "midi":
            continue
        mod = types.ModuleType(m)
        mod.__getattr__ = lambda name, _m=m: (lambda *a, **k: 0)
        sys.modules[m] = mod
    main_mod = types.ModuleType("__main__")
    main_mod.__file__ = "./MCPTools.py"
    sys.modules["__main__"] = main_mod
    exec(top, main_mod.__dict__)
    schema = json.loads(main_mod.get_mcp_tools_json())

    # --- 2) 静的解析 (dis) ---
    funcs = {k: v for k, v in main_mod.__dict__.items() if isinstance(v, types.FunctionType)}
    fapi, fhelp = {}, {}
    for name, fn in funcs.items():
        a, h = set(), set()
        for co in walk_code(fn.__code__):
            aa, hh = api_refs(co, set(funcs) - {name})
            a |= aa
            h |= hh
        fapi[name], fhelp[name] = a, h

    def closure(name):
        seen, stack, apis = set(), [name], set()
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            apis |= fapi.get(n, set())
            stack.extend(fhelp.get(n, ()))
        return apis, seen - {name}

    tools = []
    for t in schema:
        n = t["name"]
        props = t["inputSchema"].get("properties", {})
        req = set(t["inputSchema"].get("required", []))
        direct = sorted(fapi[n])
        trans, hs = closure(n)
        tools.append({
            "name": n,
            "description": t["description"][:160],  # FL 原文は長大なプロンプト文 → 先頭のみ保持 (全文は work/ で再生成可)
            "description_chars": len(t["description"]),
            "params": [{"name": p, "type": v["type"], "desc": v["description"], "required": p in req}
                       for p, v in props.items()],
            "api_calls": direct,
            "helpers": sorted(fhelp[n]),
            "api_calls_transitive": sorted(trans),
            "helpers_transitive": sorted(hs),
        })
    helpers_all = {n: {"api_calls": sorted(fapi[n]), "helpers": sorted(fhelp[n])}
                   for n in funcs if n not in {t["name"] for t in tools} and n not in ("mcp_tool", "get_mcp_tools_json")}
    imports = sorted({i.argval for co in walk_code(top) for i in dis.get_instructions(co) if i.opname == "IMPORT_NAME"})
    json.dump({"python": sys.version.split()[0], "tool_count": len(tools), "imports": imports, "tools": tools,
               "helpers": helpers_all}, sys.stdout, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
