#!/usr/bin/env python3
"""ilmcp 実装 (host/ilmcp.mjs) が使う静的データを生成する。

  python3 analysis/ilmcp_catalog.py            # analysis/ilmcp/{plugin_catalog,highlight_names}.json を再生成

- plugin_catalog.json : ブラウザ "Plugin database" の木 (名前・カテゴリのみ)。
    * native: tools/flp/corpus/fst_manifest.json の `Data/Patches/Plugin database/{Effects,Generators}/<cat>/<name>.fst`
    * installed (VST/VST3): tools/hostbridge/nfo/specs/wasm_plugins.json (wasm ビルドが DB に見せるプラグイン)
- highlight_names.json: FLEngine (win PE) rodata の Delphi UnicodeString リテラル連続 (`TutorialHighlightForm`
    近傍, Toolbar: Show Piano Roll ... Toolbar: Song mode の 21 件)。FL_WIN64_DIR が無ければ既存 JSON を保持する。
"""
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "shared"))
from paths import FL_WIN64_DIR, REPO_ROOT  # noqa: E402

OUT = os.path.join(HERE, "ilmcp")
FST = os.path.join(REPO_ROOT, "tools/flp/corpus/fst_manifest.json")
SPECS = os.path.join(REPO_ROOT, "tools/hostbridge/nfo/specs/wasm_plugins.json")
FLENGINE = os.path.join(FL_WIN64_DIR, "extracted", "block00031_PE.bin")
ANCHOR = "Toolbar: Show Piano Roll".encode("utf-16le")
PREFIX = "Data/Patches/Plugin database/"
FMT_DIR = {"vst2": "VST", "vst3": "VST3", "clap": "CLAP"}


def catalog():
    entries = []
    for p in json.load(open(FST))["presets"]:
        rel = p["rel"]
        if not rel.startswith(PREFIX):
            continue
        parts = rel[len(PREFIX):].split("/")
        if len(parts) != 3 or parts[0] not in ("Effects", "Generators"):
            raise SystemExit(f"unexpected Plugin database layout: {rel}")
        entries.append({"kind": "generator" if parts[0] == "Generators" else "effect", "source": "native",
                        "path": parts[:2], "name": parts[2][:-4]})
    for s in json.load(open(SPECS))["plugins"]:
        entries.append({"kind": s["kind"], "source": "installed",
                        "path": ["Installed", "Generators" if s["kind"] == "generator" else "Effects", FMT_DIR[s["format"]]],
                        "name": s["name"]})
    entries.sort(key=lambda e: (e["path"], e["name"]))
    return entries


def highlight_names(blob):
    """`<u16 codepage><u16 elemsize=2><i32 refcnt=-1><i32 len><utf16 chars><u16 0>` が 4B 整列で並ぶ連続列を読む。"""
    at = blob.find(ANCHOR)
    if at < 0:
        raise SystemExit("anchor string not found in FLEngine")
    p, out = at - 12, []
    while True:
        for k in range(0, 16, 4):  # 次ヘッダまでの詰め物を許容
            cp, el, ref, ln = struct.unpack_from("<HHii", blob, p + k)
            if el == 2 and ref == -1 and 0 < ln < 200:
                p += k
                break
        else:
            break
        out.append(blob[p + 12:p + 12 + ln * 2].decode("utf-16le"))
        p = (p + 12 + ln * 2 + 2 + 3) & ~3
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    cat = catalog()
    json.dump({"entries": cat}, open(os.path.join(OUT, "plugin_catalog.json"), "w"), indent=1, ensure_ascii=False)
    print(f"plugin_catalog.json: {len(cat)} entries "
          f"(native {sum(e['source'] == 'native' for e in cat)} / installed {sum(e['source'] == 'installed' for e in cat)})")
    if os.path.exists(FLENGINE):
        names = highlight_names(open(FLENGINE, "rb").read())
        json.dump({"source": "FLEngine win64 rodata (block00031_PE.bin), UnicodeString literal run", "names": names},
                  open(os.path.join(OUT, "highlight_names.json"), "w"), indent=1, ensure_ascii=False)
        print(f"highlight_names.json: {len(names)} names")
    else:
        print("FLEngine not found -> highlight_names.json kept as is")


if __name__ == "__main__":
    main()
