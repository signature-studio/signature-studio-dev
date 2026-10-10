#!/usr/bin/env python3
"""win64 extracted の全 PE (313 本) を走査し export / import / PDB / 内部名を data/win_pe_catalog.json に保存。
   FLEngine + 全プラグインが dsp_ippv2 から何を import しているかの実測元になる。"""
import sys, os, json, glob
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import pefile

def scan(path):
    out = {"file": os.path.basename(path), "size": os.path.getsize(path)}
    try:
        pe = pefile.PE(path, fast_load=True)
        pe.parse_data_directories(directories=[
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"],
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"],
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DEBUG"]])
        out["machine"] = "x64" if pe.FILE_HEADER.Machine == 0x8664 else "x86"
        out["dll"] = bool(pe.FILE_HEADER.Characteristics & 0x2000)
        exp = getattr(pe, "DIRECTORY_ENTRY_EXPORT", None)
        out["dllname"] = exp.name.decode(errors="replace") if exp and exp.name else ""
        out["exports"] = [(e.name.decode(errors="replace") if e.name else f"#{e.ordinal}") for e in exp.symbols] if exp else []
        imps = {}
        for attr in ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT"):
            for d in getattr(pe, attr, []):
                n = d.dll.decode(errors="replace").lower()
                imps.setdefault(n, []).extend((i.name.decode(errors="replace") if i.name else f"#{i.ordinal}") for i in d.imports)
        out["imports"] = imps
        pdb = ""
        for d in getattr(pe, "DIRECTORY_ENTRY_DEBUG", []):
            ent = getattr(d, "entry", None)
            if ent is not None and hasattr(ent, "PdbFileName"):
                pdb = ent.PdbFileName.rstrip(b"\0").decode(errors="replace")
        out["pdb"] = pdb
        out["ts"] = pe.FILE_HEADER.TimeDateStamp
    except Exception as e:
        out["error"] = str(e)
    return out

if __name__ == "__main__":
    files = sorted(glob.glob(f"{WIN_EXTRACTED}/block*_PE.bin"))
    with Pool(12) as p:
        res = p.map(scan, files, chunksize=4)
    json.dump(res, open(f"{RAW}/win_pe_catalog.json", "w"))
    print(len(res), "PE scanned;", sum(1 for r in res if "error" in r), "errors")
