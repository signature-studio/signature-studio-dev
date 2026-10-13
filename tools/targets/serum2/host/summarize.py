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
    ("patched+sentinel", "out_p_lsent"),
    ("unpatched+sentinel", "out_u_lsent"),
    ("patched+demo-payload", "out_p_dpl"),
    ("unpatched+demo-payload", "out_u_dpl"),
    ("patched+lowver", "out_p_lowver"),
    ("unpatched+lowver", "out_u_lowver"),
    ("patched+g1+lic_sent", "out_p_g1_lic_sent"),
    ("unpatched+g1+lic_sent", "out_u_g1_lic_sent"),
    ("patched+g1+lowver", "out_p_g1_lowver"),
    ("unpatched+g1+lowver", "out_u_g1_lowver"),
    ("patched+g1+demo_payload", "out_p_g1_demo_payload"),
    ("unpatched+g1+demo_payload", "out_u_g1_demo_payload"),
]
SENT_PBR, SENT_PRESET = 24, "SENTINEL"  # make_cases.py と一致


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
    if b"kAudioUnitParameterFlag_IsHighResolution" in d:
        return True
    # payload は zstd 圧縮のため生バイト検索では見えない (#341 で判明)。CBOR DOM の最上位キーも見る
    dom = saved_dom(work, run, "controller")
    return bool(dom) and "kAudioUnitParameterFlag_IsHighResolution" in dom


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
    jlen = struct.unpack("<Q", d[9:17])[0]
    try:
        return json.loads(d[17:17 + jlen])
    except Exception:
        return None


def saved_dom(work, run, side):
    """保存 state の payload (CBOR DOM)。無ければ None。"""
    p = os.path.join(work, run, f"saved_{side}_state.bin")
    if not os.path.exists(p):
        return None
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import payload_codec as pc
    try:
        return pc.split_state(open(p, "rb").read())[1]
    except Exception:
        return None


def sentinel_applied(work, run):
    """復元が payload を適用したか: processor mpePitchBendRange==24 / controller presetName==SENTINEL。"""
    pd, cd = saved_dom(work, run, "processor"), saved_dom(work, run, "controller")
    if pd is None or cd is None:
        return None
    return (pd.get("mpePitchBendRange") == SENT_PBR, cd.get("presetName") == SENT_PRESET)


def saved_pv(work, run):
    """保存 state の payload DOM 最上位 productVersion (proc, ctrl)。復元後に値が保たれたか/書換えられたかの観測。"""
    pd, cd = saved_dom(work, run, "processor"), saved_dom(work, run, "controller")
    if pd is None or cd is None:
        return None
    return (pd.get("productVersion"), cd.get("productVersion"))


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
            "sent": sentinel_applied(work, run),
            "saved_pv": saved_pv(work, run),
        }))

    # 表
    print("== CAB-68 E2E matrix (native wine host) ==")
    hdr = f"{'case':24} {'restore(c/cS/c)':22} {'0x800010':10} {'restart flags':16} {'bit':4} {'marker':7} {'audio nonzero':16} {'rt2':4}"
    hdr += f" {'sent(p/c)':10}"
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
              f"{str(r['saved_marker']):7} {nz:16} {str(r['roundtrip2']):4} {str(r['sent']):10}"
              f" pv={r['saved_pv']}")

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
    # 4b. payload 注入 A/B (#255)。sentinel 適用 = 復元が走った / 非適用 = 復元打切り (demo 分岐発火)
    for lbl in ("patched+sentinel", "unpatched+sentinel"):
        r = by.get(lbl)
        if r:
            chk(f"{lbl}: sentinel 対照 — 復元が適用 (proc,ctrl とも)", r["sent"] == (True, True))
    r = by.get("patched+demo-payload")
    if r:
        chk("patched+demo-payload: 復元が適用 (authstub が demo 分岐を無効化)", r["sent"] == (True, True))
        chk("patched+demo-payload: 3 setState 系が成功 (kResultOk=0)",
            r["restore_comp"] == 0 and r["restore_ctrl"] == 0)
    r = by.get("unpatched+demo-payload")
    if r:
        chk("unpatched+demo-payload: processor 復元が打切られ sentinel 非適用 (0x18004fad0 demo 分岐発火)",
            r["sent"] is not None and r["sent"][0] is False)
    # 4c. payload 側 productVersion 下げ A/B (#341)。
    def bit_n(label):
        r = by.get(label)
        return None if not r else r["demo_bit"]

    def has800010(label):
        return any(f == 0x800010 for f in flg(label))

    #   (i) 既定 (gate +0xdc==2): productVersion 比較に到達せず、下げても無変化 (4 run)
    for lbl in ("patched+lowver", "unpatched+lowver"):
        r = by.get(lbl)
        chk(f"{lbl}: run 存在", r is not None)
        if r:
            chk(f"{lbl}: gate==2 では pv 下げが無影響 (3 setState 成功・sentinel 適用・bit 0・0x800010 無し)",
                r["restore_comp"] == 0 and r["restore_ctrl"] == 0 and r["sent"] == (True, True)
                and r["demo_bit"] == 0 and not has800010(lbl))
    #   (ii) 強制 gate==1 (S2HOST_FORCE_GATE): #238 契約「pv>=2.0.20 → store 無し / pv<2.0.20 → demo bit=1 + 0x800010」
    for lbl in ("unpatched+g1+lic_sent", "unpatched+g1+lowver", "patched+g1+lowver", "patched+g1+lic_sent",
                "unpatched+g1+demo_payload", "patched+g1+demo_payload"):
        chk(f"{lbl}: run 存在", by.get(lbl) is not None)
    chk("unpatched+g1+lic_sent (pv 2.1.5 >= 2.0.20): demo bit 0・0x800010 無し (#238 契約と一致)",
        bit_n("unpatched+g1+lic_sent") == 0 and not has800010("unpatched+g1+lic_sent"))
    chk("unpatched+g1+lowver (pv 2.0.19 < 2.0.20): demo bit 1・0x800010 受信 (#238 契約と一致)",
        bit_n("unpatched+g1+lowver") == 1 and has800010("unpatched+g1+lowver"))
    chk("unpatched+g1+demo_payload (ctrl マーカ false): demo bit 1・0x800010 受信 (ctrl demo 分岐, マーカ経路)",
        bit_n("unpatched+g1+demo_payload") == 1 and has800010("unpatched+g1+demo_payload"))
    chk("patched+g1+lowver: demo bit 0・0x800010 無し (authstub が pv<2.0.20 経路も中和)",
        bit_n("patched+g1+lowver") == 0 and not has800010("patched+g1+lowver"))
    chk("patched+g1+demo_payload: demo bit 0・0x800010 無し (authstub がマーカ経路を中和)",
        bit_n("patched+g1+demo_payload") == 0 and not has800010("patched+g1+demo_payload"))
    # getState (0x1800c6090) のマーカ書込: bit==1 の run だけ保存 state にマーカが出る (DOM 判定。圧縮越しでも見える)
    chk("unpatched+g1+lowver: 保存 controller state にマーカ有り (bit 1 → getState が書込)",
        by.get("unpatched+g1+lowver") and by["unpatched+g1+lowver"]["saved_marker"] is True)
    chk("unpatched+g1+lic_sent: 保存 controller state にマーカ無し",
        by.get("unpatched+g1+lic_sent") and by["unpatched+g1+lic_sent"]["saved_marker"] is False)
    chk("patched+g1+lic_sent: 保存 controller state にマーカ無し (bit 1 でも N3 が書込を抑止)",
        by.get("patched+g1+lic_sent") and by["patched+g1+lic_sent"]["saved_marker"] is False)
    # 既知の不一致 (pin): mpatch N2a-1 `xor al,1→0` は demo bit = IR pass の「常時 0」ではなく「lookup 値そのまま」
    # (marker キー不在 = 既定 true → bit 1)。0x800010 は N2b-2 で抑止され、getState の marker 書込は N3 で抑止される。
    chk("[KNOWN-DIVERGENCE] patched+g1+lic_sent: demo bit == 1 (IR pass は 0 の設計。REPORT §3-6 の未解決 1)",
        bit_n("patched+g1+lic_sent") == 1 and not has800010("patched+g1+lic_sent"))
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
