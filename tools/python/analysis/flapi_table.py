#!/usr/bin/env python3
"""flapi_extract.py の結果 + 公開 API stubs (IL-Group/FL-Studio-API-Stubs, 参照のみ) + MCP 使用状況を統合して
FL 26.1.7 の組込 Python API 面の表を作る。
  python3 analysis/flapi_table.py   -> analysis/flapi/flapi_table.json, analysis/flapi/FLAPI.md
"""
import ast
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "..", "work")
OUT = os.path.join(HERE, "flapi")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared"))
from paths import FL_MAC_DIR, FL_WIN64_DIR  # noqa: E402

WIN_PE = f"{FL_WIN64_DIR}/extracted/block00031_PE.bin"

raw = json.load(open(os.path.join(OUT, "raw_mac_x86_64.json")))
raw_arm = json.load(open(os.path.join(OUT, "raw_mac_arm64.json")))
stubs_json = json.load(open(os.path.join(WORK, "fl-stubs/data/fl_stubs.json")))
mcp = json.load(open(os.path.join(HERE, "mcp/mcp_tools.json")))
pe = open(WIN_PE, "rb").read() if os.path.exists(WIN_PE) else b""


def stub_sigs(mod):
    base = os.path.join(WORK, "fl-stubs/src/midi_controller_scripting", mod)
    sigs = {}
    if not os.path.isdir(base):
        return sigs
    for fn in sorted(os.listdir(base)):
        if not fn.endswith(".py"):
            continue
        tree = ast.parse(open(os.path.join(base, fn)).read())
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                a = node.args
                names = [x.arg for x in a.args]
                defaults = [None] * (len(names) - len(a.defaults)) + [ast.unparse(d) for d in a.defaults]
                params = [{"name": n, "type": ast.unparse(x.annotation) if x.annotation else None, "default": d}
                          for n, x, d in zip(names, a.args, defaults)]
                sigs[node.name] = {"params": params, "returns": ast.unparse(node.returns) if node.returns else None}
    return sigs


mcp_used = {}
for t in mcp["tools"]:
    for api in t["api_calls_transitive"]:
        mcp_used.setdefault(api, set()).add(t["name"])

modules = {}
for m, blocks in raw["modules"].items():
    if m == "ilmcp":
        continue
    funcs = {}
    for b in blocks:
        for n, d in b["functions"]:
            funcs[n] = d
        for n in b.get("name_only", []):
            funcs.setdefault(n, "")
    arm = {n for b in raw_arm["modules"].get(m, []) for n, _ in b["functions"]} | \
          {n for b in raw_arm["modules"].get(m, []) for n in b.get("name_only", [])}
    sigs = stub_sigs(m)
    ent = {}
    for n, d in sorted(funcs.items()):
        win = bool(d) and (b"\x00" + n.encode() + b"\x00" + d.encode() + b"\x00") in pe
        ent[n] = {
            "doc": d,
            "sig": sigs.get(n),
            "new_vs_stubs": n not in stubs_json.get(m, {}),
            "win_pair_verified": win if d else None,
            "arm64_same": n in arm,
            "mcp_tools": sorted(mcp_used.get(f"{m}.{n}", [])),
        }
    modules[m] = ent

# ilmcp (docs 無し): rodata の直前トークン列から確定
ilmcp = ["showHighlight", "forwardTutorialEvent", "storePRScript", "runPRScript", "addChannel", "removeChannel",
         "getBrowserNames", "getHighlightNames", "addEffect"]
modules["ilmcp"] = {n: {"doc": "", "sig": None, "new_vs_stubs": True, "win_pair_verified": None, "arm64_same": True,
                        "mcp_tools": sorted(mcp_used.get(f"ilmcp.{n}", []))} for n in ilmcp}

objects = {
    "flpianoroll": {
        "note": "ピアノロール scripting (.pyscript)。Note/Marker は値オブジェクト、score は現ピアノロールの Pattern",
        "classes": {
            "Note": ["number", "time", "length", "pan", "velocity", "color", "fcut", "fres", "pitchofs", "slide",
                     "porta", "group", "muted", "selected", "release", "repeats", "clone()"],
            "Marker": ["time", "mode", "tsnum", "tsden", "scale_root", "name", "scale_helper"],
            "score(Pattern)": ["getNote", "addNote", "deleteNote", "getMarker", "addMarker", "deleteMarker", "clear",
                               "clearNotes", "clearMarkers", "getTimelineSelection", "setTimelineSelection",
                               "getDefaultNoteProperties", "getNextFreeGroupIndex", "loadScoreFromFile",
                               "noteCount", "markerCount", "PPQ", "length", "tsnum", "tsden", "snap_scale_helper",
                               "snap_root_note"],
            "Utils(TUtils)": ["ProgressMsg", "ShowMessage", "log"],
            "ScriptDialog": ["Execute", "AddInput", "AddInputKnob", "AddInputKnobInt", "AddInputCombo",
                             "AddInputText", "AddInputCheckbox", "AddInputSurface", "GetInputValue", "SetText",
                             "SetNormalizedValue", "addGroup", "endGroup", "restoreFormValues", "DialogParams"],
        },
        "entrypoints": ["createDialog()", "apply(form)"],
    },
    "flcpt": {"note": "Chord Progression Tool 用 (System/Tools/Chord progression の pyc 群が使用)",
              "classes": {"CPT": ["addChordMarker", "getChordMarker", "clearChordMarkers", "chordMarkerCount",
                                  "(+ ~70 attr: style1/style2/temperature/repeats/... )"],
                          "ChordMarker": ["time", "length", "name", "alternativeCount", "getAlternative", "..."],
                          "ChordAlternative": ["name", "note_classes", "extensions", "locked"]}},
    "flrack": {"note": "Channel rack/score ツール用", "classes": {"Channel": ["channel_id", "channel_type", "name", "tool_type", "ui_params", "seed", "preset", "volume", "pitch_shift", "..."],
                                                               "Channels": ["channels", "pattern_id", "rack_initialised", "sample_rate", "pattern_length"]}},
    "fl": {"note": "stdout/stderr 差替え", "classes": {"FLTextOutput": ["write"]}},
    "_ilmeta": {"note": "インタプリタ側メタ (内部)", "classes": {}},
}

def binary_callbacks():
    """FLEngine rodata の `pycbOn*` 表 (Delphi 側 Python callback 名)。"""
    D = f"{FL_MAC_DIR}/pkg_extract/payload_out/Applications/FL Studio 2026.app/Contents/Libs/FLEngine_x64.dylib"
    if not os.path.exists(D):
        return []
    b = open(D, "rb").read()
    return sorted({m.group(1).decode() for m in re.finditer(rb"pycb(On[A-Za-z]+?)(?=[\x00-\x1f]|pycb|$)", b)})


def stub_callbacks():
    f = os.path.join(WORK, "fl-stubs/src/midi_controller_scripting/callbacks/__init__.py")
    out = {}
    if os.path.exists(f):
        for node in ast.parse(open(f).read()).body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("On") and node.name not in out:
                out[node.name] = [a.arg for a in node.args.args]
    return out


# 実バイナリ由来の引数仕様 (flapi_kwargs.py の出力。無ければ付けない)
_kwp = os.path.join(OUT, "flapi_kwargs.json")
if os.path.exists(_kwp):
    sys.path.insert(0, HERE)
    from flapi_kwargs import kwsig_of  # noqa: E402
    for _m, _fs in json.load(open(_kwp))["modules"].items():
        for _n, _e in _fs.items():
            if _n in modules.get(_m, {}):
                modules[_m][_n]["kwsig"] = kwsig_of(_e)

tot = sum(len(v) for v in modules.values())
res = {"fl_version": "26.1.7", "python": "3.12.1", "function_total": tot,
       "function_counts": {m: len(v) for m, v in modules.items()}, "modules": modules, "objects": objects,
       "midi_script_callbacks": stub_callbacks(),
       "midi_script_callbacks_in_binary": binary_callbacks(),
       "py_modules_from_files": {"midi": "Shared/Python/Lib/midi.py (定数のみ)", "utils": "Shared/Python/Lib/utils.py (純Python helper)"}}
json.dump(res, open(os.path.join(OUT, "flapi_table.json"), "w"), indent=1, ensure_ascii=False)

# fn_id 割当 (fl_api.install と JS ホストで共有する正本: modules の列挙順)
ids = [f"{m}.{n}" for m, v in modules.items() for n in v]
json.dump(ids, open(os.path.join(OUT, "flapi_ids.json"), "w"))

# markdown
lines = ["# FL 26.1.7 組込 Python API 面 (FLEngine rodata 抽出; mac x86_64/arm64 一致、win は ペア一致で照合)\n",
         "| module | 関数数 | stubs(旧)に無い新規 | win ペア一致 | MCP 使用 |", "|---|---|---|---|---|"]
for m, v in modules.items():
    new = [n for n, e in v.items() if e["new_vs_stubs"]]
    win = sum(1 for e in v.values() if e["win_pair_verified"])
    wtot = sum(1 for e in v.values() if e["win_pair_verified"] is not None)
    mc = [n for n, e in v.items() if e["mcp_tools"]]
    lines.append(f"| {m} | {len(v)} | {len(new)} ({', '.join(new[:8])}{'…' if len(new) > 8 else ''}) | {win}/{wtot} | {len(mc)} |")
lines.append(f"| **合計** | **{tot}** | | | |\n")
open(os.path.join(OUT, "FLAPI.md"), "w").write("\n".join(lines))
print(json.dumps(res["function_counts"]), tot)
