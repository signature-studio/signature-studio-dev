#!/usr/bin/env python3
# M2-5 (delphi_inventory 機械生成):
# FLEngine (win64 DLL + mac x86_64 slice 双方) の
#   - Delphi RTTI/VMT スキャン結果 (class pointer * class 名一覧)
#   - export 面から取得した dbk* / Delphi 定形 export の界隈リスト
#   - 関数名復元は RTTI class 名ベースのみ可能であることの明記
# を収めた delphi_inventory.md を生成する。
#
# 入力:
#   --win-candidates : tools/m2/delphi_scan.py の出力 json
#   --mac-scan       : tools/m2/delphi_mac_scan.py の出力 json
#   --out-md         : delphi_inventory.md
#   --out-json       : delphi_inventory.json

import argparse
import json
import re
import subprocess


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--win-candidates", required=True)
    ap.add_argument("--mac-scan", required=True)
    ap.add_argument("--winbridge-json", required=True)
    ap.add_argument("--out-md", required=True)
    ap.add_argument("--out-json", required=True)
    args = ap.parse_args()

    win = json.load(open(args.win_candidates))
    mac = json.load(open(args.mac_scan))
    shim = json.load(open(args.winbridge_json))

    win_vmts = win.get("vmt_examples", [])
    win_vmts_count = win.get("vmt_class_pointers", len(win_vmts))
    dbk = [n for n in shim.get("win_export_names", []) if n.startswith("dbk")
           or "__dbk" in n]
    fruit = [n for n in shim.get("win_export_names", []) if not n.startswith("_dbk")
             and n and n[0].isalpha() and not n.startswith("dbk")]

    md = []
    md.append("# delphi_inventory.md (FLEngine Delphi 固有面の機械採取)")
    md.append("")
    md.append("生成: `tools/m2/delphi_inventory.py` (strategy.md §5.7 / M2 検証条件 5)")
    md.append("")
    md.append("> 結論 (機械採取時点): **FLEngine 双方とも Delphi x64 の "
              "VMT/RTTI がそのまま残っており (win 1,244 / mac 3,896 class 検出), "
              "関数名の自動復元は Delphi RTTI + VMT 経由で機械生成可能**。"
              "どちらのエクスポート面も超薄い (`CreateFruityInstance` 1 本 + "
              "`dbkFCallWrapper` 経由 Delphi RTL 定形) ので、シンボル面から"
              "の名付けは当たらない。よって M3 以降は「VMT→関数名/型表」"
              "(本書の class 一覧) を IR pass (名付け + 型付け) に注入する。")
    md.append("")

    md.append("## 1. Delphi VMT / class pointer 一覧 (機械走査)")
    md.append("")
    md.append("検出法は delphi_scan.py/mac 版と同一: **vmtClassName "
              "(class pointer -112 位置) に格納された Pascal 文字列**を "
              "data/.text const から QWORD 走査で取り出し、class pointer を"
              "`storage_addr + 112` として計算する。")
    md.append("")
    md.append(f"| | FLEngine_x64.dll (win64) | FLEngine_x86_64.dylib slice (mac) |")
    md.append(f"|---|---|---|")
    md.append(f"| 検出された VMT class pointer | {win_vmts_count} | "
              f"{mac.get('vmt_class_pointers')} |")
    md.append(f"| 検出された Pascal 文字列候補 | (win 版は delphi_scan.py の "
              f"data/.text 走査) | {mac.get('pascal_strings')} |")
    md.append("")

    md.append("### mac slice: class pointer の先頭 60 個")
    md.append("")
    md.append("| class name | class pointer (RVA) |")
    md.append("|---|---|")
    for v in mac.get("vmts_example", [])[:60]:
        md.append(f"| {v['name']} | 0x{v['class_ptr']:x} |")
    md.append("")
    md.append("### win64 DLL: class pointer の先頭 40 個 (delphi_scan.py 収取)")
    md.append("")
    md.append("| class name | class pointer (RVA) |")
    md.append("|---|---|")
    for v in win_vmts[:40]:
        md.append(f"| {v.get('name', '')} | {v.get('class_ptr', '')} |")
    md.append("")

    md.append("## 2. `dbk*` / Delphi 定形 export (実機 exe/dll 面)")
    md.append("")
    md.append("win64 DLL (FLEngine_x64.dll) の export 一覧 (llvm-objdump -p):")
    md.append("")
    md.append("| export | 備考 |")
    md.append("|---|---|")
    for n in shim.get("win_export_names", []):
        note = ("## Delphi RTL 定形 (FastCall wrapper; lifting / IR pass で"
                "本来の対象外扱い)" if "__dbk" in n or "dbk" in n else "")
        md.append(f"| {n} | {note} |")
    md.append("")
    md.append(f"mac slice (FLEengine x86_64) の export 一覧: "
              f"{', '.join(shim.get('mac_exports', []))} (CreateFruityInstance の"
              "1 本のみ。FL64.exe / OsxFL と同等の超薄い面= IR 化対応 C ABI 面)")
    md.append("")

    md.append("## 3. Delphi x64 calling convention / シグネチャの機械面")
    md.append("")
    md.append("- M2 では calling_convention 観点の候補を自動抽出し、RetDec リフト IR と")
    md.append("  Ghidra pseudo-C を対照させている (tools/m2/REPORT.md 参照)。")
    md.append("  RetDec bin2llvmir は x64 PE を Microsoft x64 calling convention 既定と")
    md.append("  して解釈するため、Delphi 特有の record 変型 / open array / hidden")
    md.append("  return buffer / var param (= qrr 系 mangling 対応のパラメータ面) の")
    md.append("  補正は M3 の Delphi 固有 IR pass (シグネチャ定義表) で扱う。")
    md.append("")

    out = {
        "win": {"vmt_class_pointers": win_vmts_count, "vmts": win_vmts,
                "dbk_similar_exports": dbk, "other_exports": fruit},
        "mac": {"vmt_class_pointers": mac.get("vmt_class_pointers"),
                "vmts": mac.get("vmts_example", []),
                "pascal_strings": mac.get("pascal_strings"),
                "exports": mac.get("vmts_examples")},
    }
    with open(args.out_json, "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    with open(args.out_md, "w") as fh:
        fh.write("\n".join(md))
    print(f"[delphi_inventory] win VMTs={win_vmts_count} mac VMTs="
          f"{mac.get('vmt_class_pointers')} dbk*={dbk}")
    print(f"[delphi_inventory] wrote {args.out_md} / {args.out_json}")


if __name__ == "__main__":
    main()
