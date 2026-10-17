import json, os, sys, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
LL = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, LL)
os.chdir(LL)
from liftlib import pipeline

W = os.environ.get("RUNNER_TEMP", "/tmp/opencode") + "/ott_getparam"
cfg = pipeline.load_cfg("targets/ott_getparam.json")
cfg["exports"] = cfg.get("exports", []) + ["probe_dispatch"]
cfg["emcc"]["sources"] = cfg["emcc"].get("sources", []) + [os.path.join(HERE, "probe.c")]

ll = os.path.join(W, "ott_getparam_fixed.ll")
h = os.path.join(W, "ott_getparam_simd.c")
s = os.path.join(W, "ott_getparam_stubs.c")

full_dir = os.path.join(W, "probe_full")
empty_dir = os.path.join(W, "probe_empty")
os.makedirs(full_dir, exist_ok=True)
os.makedirs(empty_dir, exist_ok=True)

text = open(s).read()
assert text.count("const unsigned icall_tbl_n = 105;") == 1
open(os.path.join(empty_dir, "ott_getparam_stubs.c"), "w").write(
    text.replace("const unsigned icall_tbl_n = 105;", "const unsigned icall_tbl_n = 0;"))

out_full = pipeline.emit(cfg, (ll, h, s), full_dir, profile="dev")
out_empty = pipeline.emit(cfg, (ll, h, os.path.join(empty_dir, "ott_getparam_stubs.c")), empty_dir, profile="dev")
print("full:", out_full)
print("empty:", out_empty)
