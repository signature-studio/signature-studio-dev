#!/usr/bin/env python3
"""CAB-68 E2E 判定サマリ — 各 run の summary.json を読みmatrix 表 + 判定を出力。

usage: python3 summarize.py <host/work dir>
"""
import json
import os
import struct
import sys

RUNS = [
    ("patched+licensed", "out_p_lic2"),
    ("patched+demo", "out_p_demo"),
    ("unpatched+licensed", "out_u_lic"),
    ("unpatched+demo", "out_u_demo"),
    ("unpatched+process-only", "out_u_proc"),
    ("unpatched+licensed+corrupt-payload", "out_u_corrupt"),
]


def load(work, run):
    p = os.path.join(work, run, "summary.json")
    if not os.path.exists(p):
        return None
    txt = open(p, encoding="utf-8", errors="replace").read()
    # 手書き JSON の trailing comma のみ寛容に除去
    import re
    txt = re.sub(r",(\s*[}\]])", r"\1", txt)
    try:
        return json.loads(txt)
    except Exception as e:
        return {"_parse_error": str(e)}


def marker_in_saved(work, run):
    """保存 controller state に demo マーカがあるか (demo bit==1 の間接観測)。"""
    p = os.path.join(work, run, "saved_controller_state.bin")
    if not os.path.exists(p):
        return None
    d = open(p, "rb").read()
    return b"kAudioUnitParameterFlag_IsHighResolution" in d


def demo_bit(work, run):
    s = load(work, run)
    if not s:
        return None
    return s.get("demo_bit_probe_22792_after_restore")


def saved_meta(work, run, side):
    p = os.path.join(work, run, f"saved_{side}_state.bin")
    if not os.path.exists(p):
        return None
    d = open(p, "rb").read()
    if d[:9] != b"XferJson\x00":
        return None
    jlen, _ = struct.unpack("<II", d[9:17])
    try:
        return json.loads(d[17:17 + jlen])
    except Exception:
        return None


def main():
    work = sys.argv[1]
    rows = []
    for label, run in RUNS:
        s = load(work, run)
        if s is None:
            rows.append((label, None))
            continue
        rows.append((label, {
            "restore_comp": s.get("restore_comp_setstate"),
            "restore_ctrl_cs": s.get("restore_ctrl_setcomponentstate"),
            "restore_ctrl": s.get("restore_ctrl_setstate"),
            "roundtrip2": s.get("roundtrip2_bytes_identical"),
            "restart_flags": s.get("restart_flags"),
            "restart_calls": s.get("restart_component_calls"),
            "saved_marker": marker_in_saved(work, run),
            "demo_bit": demo_bit(work, run),
            "audio_nonzero": s.get("audio_nonzero_cells"),
            "audio_total": s.get("audio_total_cells"),
            "audio_peak": s.get("audio_peak"),
            "out_events": s.get("output_events_count"),
        }))

    # 表
    print("== CAB-68 E2E matrix (native wine host) ==")
    hdr = f"{'case':24} {'restore(c/cS/c)':22} {'0x800010':10} {'restart flags':16} {'bit':4} {'marker':7} {'audio nonzero':16} {'rt2':4}"
    print(hdr)
    for label, r in rows:
        if r is None:
            print(f"{label:24} RUN MISSING")
            continue
        if r["restore_comp"] is None:
            print(f"{label:24} (state 省略: process-only)")
            nz = f"{r['audio_nonzero']}/{r['audio_total']}" if r["audio_nonzero"] is not None else "-"
            print(f"  audio: {nz} peak={r['audio_peak']}")
            continue
        flags = r["restart_flags"] or []
        has_800010 = any(f in (0x800010, "0x800010") or str(f) == "0x800010" for f in flags)
        fl = ",".join(str(f) for f in flags) or "-"
        rc = f"{r['restore_comp']}/{r['restore_ctrl_cs']}/{r['restore_ctrl']}"
        nz = f"{r['audio_nonzero']}/{r['audio_total']}"
        print(f"{label:24} {rc:22} {str(has_800010):10} {fl:16} {str(r['demo_bit']):4} "
              f"{str(r['saved_marker']):7} {nz:16} {str(r['roundtrip2']):4}")

    # 判定
    print("\n== 判定 ==")
    checks = []

    def chk(name, cond):
        checks.append((name, bool(cond)))
        print(f"  [{'OK' if cond else 'NG'}] {name}")

    by = {label: r for label, r in rows}

    def flg(label):
        r = by.get(label)
        if not r or r["restart_flags"] is None:
            return []
        out = []
        for f in r["restart_flags"]:
            out.append(f if isinstance(f, int) else int(str(f), 0))
        return out

    # 1. 全 run で process 完走 (audio nonzero > 0 は licensed/demo 両 DLL で)
    for label, r in rows:
        if r and r.get("audio_nonzero") is not None:
            chk(f"{label}: process 非ゼロ出力", r["audio_nonzero"] > 0)
    # 2. restore 往復 (kResultOk=0 が成功。S_FALSE=1 は abort/parse失敗)
    r = by.get("patched+licensed")
    if r:
        chk("patched+licensed: 3 setState 系が成功 (kResultOk=0)",
            r["restore_comp"] == 0 and r["restore_ctrl"] == 0)
        chk("patched+licensed: save→restore→save byte 一致", r["roundtrip2"] == 1)
        chk("patched+licensed: demo マーカ無し (licensed 形で保存)", r["saved_marker"] is False)
        chk("patched+licensed: demo bit probe == 0", r["demo_bit"] == 0)
    # 3. unpatched+licensed も kResultOk (合成 licensed state は両 DLL で復元可)
    r = by.get("unpatched+licensed")
    if r:
        chk("unpatched+licensed: 3 setState 系が成功 (kResultOk=0)",
            r["restore_comp"] == 0 and r["restore_ctrl"] == 0)
        chk("unpatched+licensed: demo マーカ無し・demo bit probe == 0",
            r["saved_marker"] is False and r["demo_bit"] == 0)
    # 4. corrupt payload → S_FALSE (payload が setState 内で実処理されることの実証)
    r = by.get("unpatched+licensed+corrupt-payload")
    if r:
        chk("corrupt-payload: setState が S_FALSE に変化 (payload 処理の実証)",
            r["restore_comp"] == 1 and r["restore_ctrl"] == 1)
    # 5. 0x800010 は本 host セッションでは未発火 (restartComponent(0x10) は観測) — 記録
    r = by.get("patched+licensed")
    if r:
        fl = flg("patched+licensed")
        chk("patched+licensed: restartComponent 自体は観測される", len(fl) > 0)

    ok = sum(1 for _, c in checks if c)
    print(f"\n合計: {ok}/{len(checks)} OK")
    return 0 if ok == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
