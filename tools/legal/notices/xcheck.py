#!/usr/bin/env python3
"""別算法の検算 (LGL-3, #86): lib.mjs / record.mjs を使わずに records と registry の pin を再計算する。
  python3 tools/legal/notices/xcheck.py [--fl-tar $HOME/artifacts/fl-win64.tar.zst]
前提: 記録を生成した build.sh のソース (tools/shared/work/src, tools/python/work) が手元にあること。
  - 記録の upstream.sha256 = ソース tarball の sha256 (hashlib)
  - 記録のライセンス本文 sha256 = tarball 直読み (tarfile) / git show から正規化して再計算
  - 記録の git commit = git rev-parse HEAD、パッチ sha256 = ファイル直読み
  - --fl-tar 指定時: registry.flTexts の 15 本を tar から直接取り出して sha256 + サイズを再計算
"""
import glob, hashlib, json, os, subprocess, sys, tarfile, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "../../.."))
fl_tar = sys.argv[sys.argv.index("--fl-tar") + 1] if "--fl-tar" in sys.argv else None
SRCS = [f"{REPO}/tools/shared/work/src", f"{REPO}/tools/python/work"]
ok = bad = 0


def report(good, msg):
    global ok, bad
    ok += bool(good)
    bad += not good
    print(("OK  " if good else "NG  ") + msg)


def norm(b):  # decodeText と同じ正規化 (BOM 除去・CRLF→LF・末尾空白を 1 改行へ)
    s = b.decode("utf-8", "replace").lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").rstrip()
    return hashlib.sha256((s + "\n").encode()).hexdigest()


for path in sorted(glob.glob(f"{HERE}/records/*.json")):
    rid = os.path.basename(path)[:-5]
    r = json.load(open(path))
    u = r["upstream"]
    if "archive" in u:
        p = next((f"{d}/{u['archive']}" for d in SRCS if os.path.exists(f"{d}/{u['archive']}")), None)
        if p is None:
            report(False, f"{rid}: ソース {u['archive']} が手元に無い")
            continue
        report(hashlib.sha256(open(p, "rb").read()).hexdigest() == u["sha256"], f"{rid}: archive sha256")
        t = tarfile.open(p)
        top = t.getnames()[0].split("/")[0]
        for f in r["license"]["files"]:
            report(norm(t.extractfile(f"{top}/{f['path']}").read()) == f["sha256"], f"{rid}: {f['path']} (tarball 直読み)")
    else:
        name = "blend2d" if rid.startswith("blend2d") else "asmjit"
        repo = f"{SRCS[0]}/{name}"
        head = subprocess.check_output(["git", "-C", repo, "rev-parse", "HEAD"], text=True).strip()
        report(head == u["commit"], f"{rid}: git HEAD == commit")
        for f in r["license"]["files"]:
            report(norm(subprocess.check_output(["git", "-C", repo, "show", f"{head}:{f['path']}"])) == f["sha256"], f"{rid}: {f['path']} (git show)")
    for pt in r["build"]["patches"]:
        report(hashlib.sha256(open(f"{REPO}/{pt['path']}", "rb").read()).hexdigest() == pt["sha256"], f"{rid}: patch {pt['path']}")

if fl_tar:
    reg = json.load(open(f"{HERE}/registry.json"))
    with tempfile.TemporaryDirectory() as d:
        subprocess.check_call(["tar", "--zstd", "-xf", fl_tar, "-C", d] + [f"extracted/{p['block']}" for p in reg["flTexts"]])
        for p in reg["flTexts"]:
            b = open(f"{d}/extracted/{p['block']}", "rb").read()
            report(hashlib.sha256(b).hexdigest() == p["sha256"] and len(b) == p["size"], f"FL pin {p['file']} ({p['block']})")
print(f"RESULT ok={ok} bad={bad}")
sys.exit(1 if bad else 0)
