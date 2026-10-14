#!/usr/bin/env python3
# SR-5 (#73) / SR-47 (#2414): 参照 WAV の sha256 と基本メトリクスを JSON に書く (WAV 本体は commit しない)。
# usage: python3 ref_manifest.py <render_f32.wav> <out.json> [full|empty]
#   full (既定): installer 全展開 content dir (Tables あり) の参照。正の参照として主エントリ (sha256_file 等) を書き直す。
#   empty        : 専用の空 content dir (Tables 無し) の参照。out.json の content_empty (variant) だけを更新する。
import hashlib, json, os, struct, sys

src, dst = sys.argv[1], sys.argv[2]
cond = sys.argv[3] if len(sys.argv) > 3 else "full"
assert cond in ("full", "empty"), "condition must be full|empty"
raw = open(src, "rb").read()
assert raw[:4] == b"RIFF" and raw[8:12] == b"WAVE", "not a RIFF/WAVE file"
p = 12
fmt = data = None
while p + 8 <= len(raw):
    cid = raw[p:p + 4]
    size = struct.unpack_from("<I", raw, p + 4)[0]
    body = raw[p + 8:p + 8 + size]
    if cid == b"fmt ":
        tag, ch, rate, _, _, bits = struct.unpack_from("<HHIIHH", body, 0)
        fmt = dict(tag=tag, ch=ch, rate=rate, bits=bits)
    elif cid == b"data":
        data = body
    p += 8 + size + (size & 1)
assert fmt and data is not None, "missing fmt/data"
assert fmt["tag"] == 3 and fmt["bits"] == 32, "expected IEEE float32"
n = len(data) // 4
samples = struct.unpack("<%df" % n, data[: n * 4])
peak = max(abs(x) for x in samples)
rms = (sum(x * x for x in samples) / n) ** 0.5
nonzero = sum(1 for x in samples if x != 0.0)
metrics = {
    "peak": round(peak, 6),
    "rms": round(rms, 6),
    "nonzero_samples": nonzero,
    "total_samples": n,
}
CONTENT = {
    "full": "work/content_full (installer 全展開 = host/ref_content.sh・7,370 files・Tables あり)。既定。env S2REF_CONTENT で変更可",
    "empty": "work/ref_content (専用の空 dir・Tables 無し)。env S2REF_CONTENT=<dir> で指定する variant",
}
entry = {
    "content": CONTENT[cond],
    "sha256_data": hashlib.sha256(data).hexdigest(),
    "sha256_file": hashlib.sha256(raw).hexdigest(),
    "metrics": metrics,
}
if cond == "full":
    out = {
        "file": "render_f32.wav (本体は work/ で gitignore・commit しない)",
        "sha256_data": entry["sha256_data"],
        "sha256_file": entry["sha256_file"],
        "format": {"tag": "IEEE float", "bits": fmt["bits"], "channels": fmt["ch"], "sample_rate": fmt["rate"]},
        "frames": n // fmt["ch"],
        "metrics": metrics,
        "render": {
            "content": CONTENT["full"],
            "dll": "work/Serum2_win64.vst3 (実 DLL, 無改変 unpatched, sha256 501e7bb3…5283)",
            "state": "plugin 既定 (Init, setState なし)",
            "midi": "NoteOn pitch=60 (S2HOST_PITCH 既定) block 0 / NoteOff block 24",
            "blocks": 64,
            "block_frames": 128,
            "sample_rate": 48000,
            "runner": "wine64 (apt wine 9.0), Actions runner",
            "command": "bash tools/targets/serum2/host/ref_render.sh <outdir> 60",
        },
    }
    if os.path.exists(dst):
        prev = json.load(open(dst))
        if "content_empty" in prev:
            out["content_empty"] = prev["content_empty"]
else:
    out = json.load(open(dst))
    out["content_empty"] = entry
json.dump(out, open(dst, "w"), indent=2, ensure_ascii=False)
open(dst, "a").write("\n")
print(json.dumps(metrics, ensure_ascii=False))
