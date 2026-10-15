"""liftlib.passes.icall — 間接 call/jmp 脱落 (RetDec D1) の根絶: lift 前に PE を書換え (tools/icall/icall_rewrite.py), lift 後に復元 (ir_icall_restore.py).

cfg (JSON) の passes.icall:
  {"funcs": "work/xxx_F.txt" (必須: 書換え対象関数集合を書いたファイルのパス。inline の range 文字列 ("0xA-0xB,...") は不可 =
            pipeline.rpath() 経由で icall_rewrite.py が open() するため。閉包は tools/icall/closure.py で作れる),
   "rip_data": true, "derefix": true, "abi": true, "comis": true, "jtchain": true}      (全て既定 true; 個別 off 用)
効果: ① call/jmp [reg+off] / reg / [rip+data] / CFG thunk を memory-ABI stub 経由で IR に残し __icall_dispatch(site_va) へ復元
      ② RetDec D7 (zero-disp 参照が live-in reg 経由だと load が消える) を lea 補償で回避  ③ closure 内 ABI を BLK 経由に仮想化 (xmm/r8/r9 引数脱落 D3 を根絶)
      ④ comis/ucomis flag を stub+sahf 化  ⑤ jump table を cmp/je 列へ展開  ⑥ chained .pdata 断片を親へ inline
出力: 書換え済み PE (workdir/<name>.icall.dll), map.json, 復元済み raw ll。runtime 側は tools/icall/rt/icall_rt.c (BLK + __icall_dispatch + __icall_comis) を emcc sources に追加。
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
ICALL = os.path.join(ROOT, "tools", "icall")


def _py(script, *args):
    r = subprocess.run([sys.executable, os.path.join(ICALL, script)] + [str(a) for a in args], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("%s failed:\n%s" % (script, (r.stdout + r.stderr)[-2000:]))
    return r.stdout


def prelift(cfg, image, funcs_file, workdir, log):
    """書換え済み PE と RetDec ranges を作る。返値 (image', ranges_csv, map_path)"""
    pc = cfg.get("passes", {}).get("icall", {})
    out = os.path.join(workdir, cfg["name"] + ".icall.dll")
    mp = os.path.join(workdir, cfg["name"] + ".icall.map.json")
    args = ["--pe", image, "--funcs", funcs_file, "--out", out, "--map", mp]
    for k, flag in (("rip_data", "--no-rip-data"), ("derefix", "--no-derefix"), ("abi", "--no-abi"), ("comis", "--no-comis"), ("jtchain", "--no-jtchain")):
        if pc.get(k, True) is False:
            args.append(flag)
    log.append("icall.prelift: " + _py("icall_rewrite.py", *args).strip())
    m = json.load(open(mp))
    ranges = open(mp + ".ranges").read() + ",0x%x-0x%x,0x%x-0x%x" % (m["stub"], m["stub"] + m.get("stub_len", 78), m["comis_stub"], m["comis_stub"] + m.get("comis_stub_len", 29))
    return out, ranges, mp


def restore(raw_ll, map_path, workdir, log):
    """RetDec raw ll (書換え PE 由来) → 元 VA 体系 + __icall_dispatch へ。返値 restored ll path"""
    out = os.path.splitext(raw_ll)[0] + ".restored.ll"
    log.append("icall.restore: " + _py("ir_icall_restore.py", "--ir", raw_ll, "--map", map_path, "--out", out).strip())
    return out


BLK_GLOBAL = "@__icall_blk"
BLK_GLOBAL_SIZE = 0x200


def blk_global_text(text, blk):
    """#1269: BLK (icall の固定 block, 既定 VA 0x184308000) への inttoptr 定数を module-local global への GEP に張り替える。
    wasm32 では BLK VA が線形メモリ外へ切り詰められ load/store が trap するため。配置は wasm 内の global に任せる。
    対象は blk ..< blk+BLK_GLOBAL_SIZE の inttoptr のみ。返値 (text, 置換数)"""
    n = [0]

    def sub(m):
        v = int(m.group(1))
        if blk <= v < blk + BLK_GLOBAL_SIZE:
            n[0] += 1
            return "getelementptr inbounds i8, ptr %s, i64 %d" % (BLK_GLOBAL, v - blk)
        return m.group(0)
    text = re.sub(r"inttoptr i64 (\d+) to ptr", sub, text)
    if n[0]:
        decl = "%s = external global [%d x i8], align 16\n\n" % (BLK_GLOBAL, BLK_GLOBAL_SIZE)
        m = re.search(r"^(define|declare) ", text, flags=re.M)
        text = text[:m.start()] + decl + text[m.start():] if m else text + "\n" + decl
    return text, n[0]


# icall_rewrite.py の BLK_RCX / BLK_RDX / BLK_R8 / BLK_R9 → MS x64 の整数引数位置 (0 = rcx = 第 1 引数)
BLK_ARG_SLOT = {0x08: 0, 0x10: 1, 0x18: 2, 0x20: 3}


def entry_blk_args(fn):
    """#1270: leaf (harness が直接呼ぶ関数) の入口で BLK の rcx/rdx 読み (BLK+0x08/+0x10) を仮引数 %argN へ張り替える。
    harness は leaf の引数を wasm 引数 (%argN) で渡し BLK へは書かないため、BLK 読みは 0 になる (this=0 で値が合わない)。
    対象は入口ブロックで BLK への store・関数呼出し (asm helper を除く) より前にある load だけ。
    blk_global_text (@__icall_blk への GEP) と iargs (仮引数の補完) の後に呼ぶ。返値: 置換数。"""
    if not fn.blocks:
        return 0
    params = [(p[0], p[1]) for p in fn.params()]
    lines = fn.blocks[0].lines
    gep, n = {}, 0
    for ln in lines:
        g = re.match(r"^\s*(%\S+) = getelementptr inbounds i8, ptr @__icall_blk, i64 (\d+)\s*$", ln)
        if g:
            gep[g.group(1)] = int(g.group(2))
    for i, ln in enumerate(lines):
        if re.match(r"^\s*(store|br|ret|switch)\b", ln) or (re.match(r"^\s*(%\S+ = )?call\b", ln) and "@__asm_" not in ln):
            break
        ld = re.match(r"^(\s*)(%\S+) = load i64, ptr (%\S+), align \d+(.*)$", ln)
        if not ld or gep.get(ld.group(3)) not in BLK_ARG_SLOT:
            continue
        k = BLK_ARG_SLOT[gep[ld.group(3)]]
        if k >= len(params):
            continue
        ty, v = params[k]
        if ty == "i64":
            lines[i] = "%s%s = add i64 %s, 0%s" % (ld.group(1), ld.group(2), v, ld.group(4))
        else:
            lines[i] = "%s%s = zext %s %s to i64%s" % (ld.group(1), ld.group(2), ty, v, ld.group(4))
        n += 1
    return n
