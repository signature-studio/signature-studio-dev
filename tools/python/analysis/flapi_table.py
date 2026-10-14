#!/usr/bin/env python3
"""flapi_extract.py の結果 + 公開 API stubs (IL-Group/FL-Studio-API-Stubs, 参照のみ) + MCP 使用状況を統合して
FL 26.1.7 の組込 Python API 面の表を作る。
  python3 analysis/flapi_table.py   -> analysis/flapi/flapi_table.json, analysis/flapi/FLAPI.md, flapi_ids.json

入力 (環境変数で差し替え可。既定値は従来どおり。tools/shared/env.sh と同じ流儀):
  FL_WIN64_DIR       win64 展開先。win PE = $FL_WIN64_DIR/extracted/block00031_PE.bin (FL_WIN_PE で直接指定も可)
  FL_STUBS_DIR       IL-Group/FL-Studio-API-Stubs の clone (既定 tools/python/work/fl-stubs。fetch_inputs.sh が作る)
  FL_ENGINE_DYLIB    mac FLEngine_x64.dylib (既定 $FL_MAC_DIR/pkg_extract/.../FLEngine_x64.dylib)。
                     無ければ midi_script_callbacks_in_binary は出力先の既存 flapi_table.json の値を引き継ぐ (stderr に WARN)
  FLAPI_OUT_DIR      出力先 (既定 analysis/flapi)。raw_mac_*.json / raw_win64.json は同ディレクトリから読む
必須入力 (win PE / stubs / raw_*.json / mcp_tools.json) が欠けている・空のときは理由を stderr に出して exit 2 (成果物は書かない)。
"""
import ast
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "..", "work")
OUT = os.environ.get("FLAPI_OUT_DIR") or os.path.join(HERE, "flapi")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared"))
from paths import FL_MAC_DIR, FL_WIN64_DIR  # noqa: E402

WIN_PE = os.environ.get("FL_WIN_PE") or f"{FL_WIN64_DIR}/extracted/block00031_PE.bin"
STUBS_DIR = os.environ.get("FL_STUBS_DIR") or os.path.join(WORK, "fl-stubs")
MAC_DYLIB = os.environ.get("FL_ENGINE_DYLIB") or \
    f"{FL_MAC_DIR}/pkg_extract/payload_out/Applications/FL Studio 2026.app/Contents/Libs/FLEngine_x64.dylib"
STUBS_JSON = os.path.join(STUBS_DIR, "data/fl_stubs.json")
RAW_X64, RAW_ARM = os.path.join(OUT, "raw_mac_x86_64.json"), os.path.join(OUT, "raw_mac_arm64.json")
MCP_JSON = os.path.join(HERE, "mcp/mcp_tools.json")


def die(msg):
    print(f"flapi_table.py: ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


# 入力欠落を黙って空扱いにしない (win_pair_verified が全 false の表を緑で出さない)
if not os.path.isfile(WIN_PE) or os.path.getsize(WIN_PE) == 0:
    die(f"win PE が無い/空: {WIN_PE} (FL_WIN64_DIR=<fl-win64 展開先> か FL_WIN_PE を指定。Actions は oc_artifacts: fl-win64)")
if not os.path.isfile(STUBS_JSON):
    die(f"stubs が無い: {STUBS_JSON} (FL_STUBS_DIR=<FL-Studio-API-Stubs の clone> を指定、または bash tools/python/fetch_inputs.sh)")
if not os.path.isdir(os.path.join(STUBS_DIR, "src/midi_controller_scripting")):
    die(f"stubs の src/midi_controller_scripting が無い: {STUBS_DIR}")
for f in (RAW_X64, RAW_ARM, MCP_JSON):
    if not os.path.isfile(f):
        die(f"入力が無い: {f}")

raw = json.load(open(RAW_X64))
raw_arm = json.load(open(RAW_ARM))
stubs_json = json.load(open(STUBS_JSON))
mcp = json.load(open(MCP_JSON))
pe = open(WIN_PE, "rb").read()


def stub_sigs(mod):
    base = os.path.join(STUBS_DIR, "src/midi_controller_scripting", mod)
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
                pos = a.posonlyargs + a.args
                names = [x.arg for x in pos]
                defaults = [None] * (len(names) - len(a.defaults)) + [ast.unparse(d) for d in a.defaults]
                params = [{"name": n, "type": ast.unparse(x.annotation) if x.annotation else None, "default": d}
                          for n, x, d in zip(names, pos, defaults)]
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
    if not os.path.exists(MAC_DYLIB):
        prev = os.path.join(OUT, "flapi_table.json")
        if not os.path.isfile(prev):
            die(f"mac dylib が無く引き継ぎ元 {prev} も無い: {MAC_DYLIB} (FL_ENGINE_DYLIB を指定)")
        got = json.load(open(prev)).get("midi_script_callbacks_in_binary") or []
        if not got:
            die(f"mac dylib が無く {prev} にも midi_script_callbacks_in_binary が無い: {MAC_DYLIB}")
        print(f"flapi_table.py: WARN: mac dylib なし ({MAC_DYLIB}): midi_script_callbacks_in_binary は {prev} の既存値 {len(got)} 件を引き継ぐ",
              file=sys.stderr)
        return got
    b = open(MAC_DYLIB, "rb").read()
    return sorted({m.group(1).decode() for m in re.finditer(rb"pycb(On[A-Za-z]+?)(?=[\x00-\x1f]|pycb|$)", b)})


def stub_callbacks():
    f = os.path.join(STUBS_DIR, "src/midi_controller_scripting/callbacks/__init__.py")
    out = {}
    if os.path.exists(f):
        for node in ast.parse(open(f).read()).body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("On") and node.name not in out:
                out[node.name] = [a.arg for a in node.args.args]
    return out


# PE が読めても中身が違う (別ファイル・破損) と照合が 0 件になる。緑で空の表を出さない
n_win = sum(1 for v in modules.values() for e in v.values() if e["win_pair_verified"])
if n_win == 0:
    die(f"win PE と (名前,doc) ペアが 1 件も一致しない: {WIN_PE} ({len(pe)} B)。FL 26.1.7 の block00031_PE.bin ではない可能性")


def pe_arity(sig, kw):
    """stub 署名の個数が FLEngine の書式 (kwsig の required/max) と違うとき、PE の個数で params を作り直す (PY-102 / #2927)。
    PyArg_ParseTupleAndKeywords が受け付ける個数が正で、C 側の検査 (np/nmin) もこれに従う。
    名前は kwlist (バイナリ由来) を優先し、無ければ stub の同位置。型と既定値は同名の stub 引数のものだけ引き継ぐ。
    PE が省略可能とする位置で既定値が不明なら `PE_OPTIONAL` (リテラルでない記号。bind は C 側の既定値に任せる)。"""
    ps, req, mx, kl = sig["params"], kw["required"], kw["max"], kw.get("kwlist")
    by = {p["name"]: p for p in ps}
    params = []
    for i in range(mx):
        n = kl[i] if kl else (ps[i]["name"] if i < len(ps) else f"arg{i}")
        st = by.get(n)
        d = None if i < req else (st["default"] if st and st["default"] is not None else "PE_OPTIONAL")
        params.append({"name": n, "type": st["type"] if st else None, "default": d})
    return {"params": params, "returns": sig["returns"], "arity_from": "kwsig"}


# 実バイナリ由来の引数仕様 (flapi_kwargs.py の出力。無ければ付けない)
_kwp = os.path.join(OUT, "flapi_kwargs.json")
if os.path.exists(_kwp):
    sys.path.insert(0, HERE)
    from flapi_kwargs import kwsig_of  # noqa: E402
    for _m, _fs in json.load(open(_kwp))["modules"].items():
        for _n, _e in _fs.items():
            if _n in modules.get(_m, {}):
                _ent = modules[_m][_n]
                _ent["kwsig"] = kwsig_of(_e)
                _kw = _ent["kwsig"]
                if _ent["sig"] and _kw.get("max") is not None and len(_ent["sig"]["params"]) != _kw["max"]:
                    _ent["sig"] = pe_arity(_ent["sig"], _kw)

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
lines = ["# 自動生成: `tools/python/analysis/flapi/` 抽出 driver\n",
         "> **人手編集禁止** (生成元を直す)。本ファイルは測定・抽出結果の**単一の正本**。\n",
         "# FL 26.1.7 組込 Python API 面 (FLEngine rodata 抽出; mac x86_64/arm64 一致、win は ペア一致で照合)",
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
