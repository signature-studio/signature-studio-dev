#!/usr/bin/env python3
"""PE 構造表: セクション(entropy)・exports・imports(DLL別)・pdata関数数・認証/ネット系import検出。
usage: pe_inspect.py <pe> [...]   (JSON は work/pe_*.json にも書く)"""
import sys, math, json, os, collections, pefile

AUTH_DLLS = {"wininet.dll","winhttp.dll","ws2_32.dll","wsock32.dll","urlmon.dll","crypt32.dll","bcrypt.dll",
             "ncrypt.dll","wintrust.dll","iphlpapi.dll","netapi32.dll","secur32.dll","mswsock.dll"}
AUTH_FUNCS = ("RegOpenKey","RegQueryValue","RegGetValue","GetVolumeInformation","GetAdaptersInfo",
              "GetComputerName","CryptAcquireContext","CertOpenStore","InternetOpen","WinHttpOpen","connect","getaddrinfo",
              "WinVerifyTrust","GetUserName","DeviceIoControl","CreateToolhelp32Snapshot","IsDebuggerPresent",
              "CheckRemoteDebuggerPresent","NtQueryInformationProcess","LoadLibrary","GetProcAddress","VirtualProtect",
              "CreateThread","ShellExecute")

def ent(b):
    if not b: return 0.0
    c = collections.Counter(b); n = len(b)
    return -sum(v/n*math.log2(v/n) for v in c.values())

def inspect(path):
    pe = pefile.PE(path, fast_load=False)
    d = {"path": path, "size": os.path.getsize(path),
         "machine": hex(pe.FILE_HEADER.Machine), "ts": pe.FILE_HEADER.TimeDateStamp,
         "imagebase": hex(pe.OPTIONAL_HEADER.ImageBase), "entry": hex(pe.OPTIONAL_HEADER.AddressOfEntryPoint),
         "sections": [], "exports": [], "imports": {}}
    for s in pe.sections:
        data = s.get_data()
        d["sections"].append({"name": s.Name.rstrip(b"\0").decode(errors="replace"), "va": hex(s.VirtualAddress),
            "vsize": s.Misc_VirtualSize, "rawsize": s.SizeOfRawData, "entropy": round(ent(data), 3),
            "chars": hex(s.Characteristics)})
    if hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
        d["exports"] = [(e.name.decode() if e.name else f"#{e.ordinal}") for e in pe.DIRECTORY_ENTRY_EXPORT.symbols]
    if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
        for imp in pe.DIRECTORY_ENTRY_IMPORT:
            d["imports"][imp.dll.decode().lower()] = sorted((i.name.decode() if i.name else f"#{i.ordinal}") for i in imp.imports)
    if hasattr(pe, "DIRECTORY_ENTRY_DELAY_IMPORT"):
        for imp in pe.DIRECTORY_ENTRY_DELAY_IMPORT:
            d["imports"]["(delay)" + imp.dll.decode().lower()] = sorted((i.name.decode() if i.name else f"#{i.ordinal}") for i in imp.imports)
    pd = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
    d["pdata_funcs"] = pd.Size // 12 if pd.VirtualAddress else 0
    d["has_cert"] = pe.OPTIONAL_HEADER.DATA_DIRECTORY[4].Size > 0
    d["cert_size"] = pe.OPTIONAL_HEADER.DATA_DIRECTORY[4].Size
    d["net_dlls"] = sorted(k for k in d["imports"] if k.replace("(delay)", "") in AUTH_DLLS)
    d["suspicious_funcs"] = sorted({f for fl in d["imports"].values() for f in fl for a in AUTH_FUNCS if f.startswith(a)})
    return d

if __name__ == "__main__":
    out = {}
    for p in sys.argv[1:]:
        d = inspect(p); out[p] = d
        print("=" * 78); print(p, d["size"], "B  machine", d["machine"], "ts", d["ts"], "entry", d["entry"], "pdata funcs", d["pdata_funcs"], "authenticode", d["cert_size"])
        for s in d["sections"]:
            print("  %-8s va=%-9s vsz=%-9d raw=%-9d ent=%.2f chars=%s" % (s["name"], s["va"], s["vsize"], s["rawsize"], s["entropy"], s["chars"]))
        print("  exports(%d): %s" % (len(d["exports"]), d["exports"][:30]))
        print("  import dlls:", {k: len(v) for k, v in d["imports"].items()})
        print("  net/crypto dlls:", d["net_dlls"])
        print("  notable funcs:", d["suspicious_funcs"])
    json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "work", "pe_inspect.json"), "w"), indent=1)
