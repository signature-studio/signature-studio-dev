#!/usr/bin/env python3
# M5 ir5_patch 出力の post-fix: sig-fix に沿わない ptr/i32 引数形の define と call site を
# i64 形に統一する (c_main.ll 用; body 内作り替えは [] ミニスクリプトとして閉じる)。
#
#   python3 c1c_fix.py work/c_main.ll
#
# 変換 (native asm 対照: tools/m5/work/natlog.md):
#   - function_414ad0: (ptr, i32) → (i64,i64)  + prologue inttoptr/trunc
#   - function_409ef0: (i64, ptr) → (i64,i64)  + prologue inttoptr
#   - function_412d60: (ptr, i64) → (i64,i64)  + prologue inttoptr + null 判定 i64 化
#   - call sites の整合 (409fe0 内 stack_var_-16 → i64 ptrtoint 化)
import re
import sys

def stage(tag, msg):
    print(f"[c1c_fix]   [{tag}] {msg}", file=sys.stderr)


def fix(path):
    t = open(path).read()

    # ---- 414ad0 -------------------------------------------------------
    t = t.replace(
        "define i64 @function_414ad0(ptr %arg1, i32 %arg2) local_unnamed_addr {\ndec_label_pc_414ad0:",
        "define i64 @function_414ad0(i64 %arg1i, i64 %arg2i) local_unnamed_addr {\ndec_label_pc_414ad0:\n"
        "  %arg1 = inttoptr i64 %arg1i to ptr\n  %arg2 = trunc i64 %arg2i to i32")

    # ---- 409ef0 -------------------------------------------------------
    t = t.replace(
        "define i64 @function_409ef0(i64 %arg1, ptr %arg2) local_unnamed_addr {\ndec_label_pc_409ef0:",
        "define i64 @function_409ef0(i64 %arg1, i64 %arg2i) local_unnamed_addr {\ndec_label_pc_409ef0:\n"
        "  %arg2 = inttoptr i64 %arg2i to ptr")

    # ---- 412d60 -------------------------------------------------------
    t = t.replace(
        "define i64 @function_412d60(ptr %arg1, i64 %arg2) local_unnamed_addr {\ndec_label_pc_412d60:\n"
        "  %0 = ptrtoint ptr %arg1 to i64\n  %1 = icmp eq ptr %arg1, null\n"
        "  br i1 %1, label %dec_label_pc_412d99, label %dec_label_pc_412d70:\n",
        "")
    m = re.search(r"define i64 @function_412d60\(ptr %arg1, i64 %arg2\)([^\n]*)\n(dec_label_pc_412d60:\n)"
                  r"(  %0 = ptrtoint ptr %arg1 to i64\n  %1 = icmp eq ptr %arg1, null\n)"
                  r"(  br i1 %1, [^\n]*[^\n]*\n\n)(dec_label_pc_412d70:[^\n]*\n)(  store i64 0, ptr %arg1, align 8\n)", t)
    if m:
        tail = m.group(1)
        newdef = (f"define i64 @function_412d60(i64 %arg1i, i64 %arg2){tail}\n"
                  "dec_label_pc_412d60:\n"
                  "  %arg1 = inttoptr i64 %arg1i to ptr\n"
                  "  %0 = ptrtoint ptr %arg1 to i64\n"
                  "  %1 = icmp eq i64 %arg1i, 0\n"
                  "  br i1 %1, label %dec_label_pc_412d99, label %dec_label_pc_412d70\n\n"
                  "dec_label_pc_412d70:" + (m.group(5)[len('dec_label_pc_412d70:'):] if False else "") + "\n"
                  "  store i64 0, ptr %arg1, align 8\n")
        t = t[:m.start()] + newdef + t[m.end():]

    # ---- [C13] 414af3 的 nil 判定: arg1 (var ptr) 自身ではなく [arg1] の読み出し ----
    # (native 実測 0x414b64: mov rax,[rbx]; test rax,rax — RetDec は load を落とした)
    t = t.replace("""define i64 @function_414ad0(i64 %arg1i, i64 %arg2i) local_unnamed_addr {
dec_label_pc_414ad0:""",
"""define i64 @function_414ad0(i64 %arg1i, i64 %arg2i) local_unnamed_addr {
dec_label_pc_414ad0:""")      # no-op 保険 (pattern 応答用)
    t = t.replace("""  %7 = zext i32 %arg2 to i64
  %8 = icmp eq ptr %arg1, null
  br i1 %8, label %dec_label_pc_414b5a, label %dec_label_pc_414afb""",
"""  %7 = zext i32 %arg2 to i64
  %arg1v = load i64, ptr %arg1, align 8
  %8 = icmp eq i64 %arg1v, 0
  br i1 %8, label %dec_label_pc_414b5a, label %dec_label_pc_414afb""")
    # 409ef0 内側回り: block 414afb (~:%9 = ptrtoint %arg1 …) の add -8 をそのまま (滅り: [var-8] 読みに対応 — IR 原文のまま許容)


    # ---- [C13b] 414b6c block のポインタ読みの復元 (native asm 0x414b69 対照) ----
    # native: `mov rax,[rbx]; test rax; je…;` + `mov r13d,[rax-4]; …; mov rcx,[rbx]` 等。
    # IR 側は %7 (len) を pointer に見立てて *default で* データを走査してしまう —
    # (RetDec drop-out — M2 既知 (d) 型の第 3 例)。ここでは len/pointer の混在を機械修正:
    t = t.replace("""dec_label_pc_414b6c:                              ; preds = %dec_label_pc_414b5a
  %41 = add nsw i64 %7, -4
  %42 = inttoptr i64 %41 to ptr
  %43 = load i32, ptr %42, align 4
  %44 = icmp ult i32 %43, %arg2
  %spec.select2 = select i1 %44, i32 %43, i32 %arg2
  %45 = zext i32 %spec.select2 to i64
  %46 = call i64 @mm_nilex(i64 %7)
  %47 = mul i64 %45, 8589934592
  %48 = ashr exact i64 %47, 32
  %49 = call i64 @mm_stub_c80(i64 %46, i64 %40, i64 %48)
  %50 = call i64 @function_412d60(i64 %arg1i, i64 %40)
  store i64 %40, ptr %rax.0.reg2mem
  br label %dec_label_pc_414b9c""",
"""dec_label_pc_414b6c:                              ; preds = %dec_label_pc_414b5a
  %blkold = load i64, ptr %arg1, align 8       ; 旧 data ptr (native: mov rax,[rbx])
  %41 = add nsw i64 %blkold, -4
  %42 = inttoptr i64 %41 to ptr
  %43 = load i32, ptr %42, align 4             ; native: mov r13d,[rax-4]
  %44 = icmp ult i32 %43, %arg2
  %spec.select2 = select i1 %44, i32 %43, i32 %arg2
  %45 = zext i32 %spec.select2 to i64
  %46 = call i64 @mm_nilex(i64 %40)
  %47 = mul i64 %45, 8589934592
  %48 = ashr exact i64 %47, 32
  %49 = call i64 @mm_stub_c80(i64 %46, i64 %40, i64 %48)
  %50 = call i64 @function_412d60(i64 %arg1i, i64 %40)
  store i64 %40, ptr %rax.0.reg2mem
  br label %dec_label_pc_414b9c""")

    # ---- [C13c] 414afb の refcount 読み: var-内 data から (native 太0x414b6c..) ----
    t = t.replace("""dec_label_pc_414afb:                              ; preds = %dec_label_pc_414af3
  %9 = ptrtoint ptr %arg1 to i64
  %10 = add i64 %9, -8""",
"""dec_label_pc_414afb:                              ; preds = %dec_label_pc_414af3
  %blkc = load i64, ptr %arg1, align 8
  %blkcp = inttoptr i64 %blkc to ptr
  %9 = ptrtoint ptr %blkcp to i64
  %10 = add i64 %9, -8""")

    # ---- [C13d] 414b5a 直後の分岐: arg2==0 ではなく [arg1]==0 (native 実測 je 414b9c) ----
    t = t.replace("""  %40 = call i64 @mm_allocw(i64 %7)
  store i64 0, ptr %rax.0.reg2mem
  br i1 %0, label %dec_label_pc_414b9c, label %dec_label_pc_414b6c""",
"""  %40 = call i64 @mm_allocw(i64 %7)
  store i64 0, ptr %rax.0.reg2mem
  %blkold2 = load i64, ptr %arg1, align 8
  %blktest = icmp eq i64 %blkold2, 0
  br i1 %blktest, label %dec_label_pc_414b9c, label %dec_label_pc_414b6c""")

    # ---- [C13e] 414b2b の NUL store 経路: %29 を slot から値として read に (native mov rcx,[rbx] 対照) ----
    t = t.replace("""  %29 = ptrtoint ptr %stack_var_-48 to i64
  %30 = call i64 @mm_resz(ptr nonnull %stack_var_-48, i64 %21)""",
"""  %c29v = load i64, ptr %stack_var_-48, align 8
  %30 = call i64 @mm_resz(ptr nonnull %stack_var_-48, i64 %21)""")
    # [C14b] native 実測 0x414b49-49c: rcx=[rbx](var=data) → 414850 → rax+minLen*2 に NUL
    t = t.replace("%36 = call i64 @mm_nilex(i64 %29)",
                  "%blkv = load i64, ptr %arg1, align 8\n  %36 = call i64 @mm_nilex(i64 %blkv)")

    # ---- [C13g] 414b5a fresh path の rax.0 store: store 0 → store %40 (data ptr) ----
    t = t.replace("""  %40 = call i64 @mm_allocw(i64 %7)
  store i64 0, ptr %rax.0.reg2mem""",
"""  %40 = call i64 @mm_allocw(i64 %7)
  store i64 %40, ptr %rax.0.reg2mem""")
    # ---- [C14] 412d60 本体: native asm 0x412d60 実測語義 (var content load 復元) ----
    c14_new = """define i64 @function_412d60(i64 %arg1, i64 %arg2) local_unnamed_addr {
dec_label_pc_412d60:
  %arg1c = inttoptr i64 %arg1 to ptr
  %mmv = load i64, ptr %arg1c, align 8
  %mz = icmp eq i64 %mmv, 0
  br i1 %mz, label %dec_label_pc_412d99, label %dec_label_pc_412d70

dec_label_pc_412d70:                              ; preds = %dec_label_pc_412d60
  store i64 0, ptr %arg1c, align 8
  %sub8 = sub i64 %mmv, 8
  %rcp = inttoptr i64 %sub8 to ptr
  %4 = load i32, ptr %rcp, align 4
  %5 = icmp slt i32 %4, 1
  %6 = icmp eq i1 %5, false
  br i1 %6, label %dec_label_pc_412d81, label %dec_label_pc_412d99

dec_label_pc_412d81:                              ; preds = %dec_label_pc_412d70
  %inc = add i32 %4, -1
  store i32 %inc, ptr %rcp, align 4
  %7 = icmp eq i32 %4, 1
  %8 = icmp eq i1 %7, false
  br i1 %8, label %dec_label_pc_412d99, label %dec_label_pc_412d91

dec_label_pc_412d91:                              ; preds = %dec_label_pc_412d81
  %sub16 = sub i64 %mmv, 16
  %10 = call i64 @mm_free_inner(i64 %sub16)
  br label %dec_label_pc_412d99

dec_label_pc_412d99:                              ; preds = %dec_label_pc_412d91, %dec_label_pc_412d81, %dec_label_pc_412d70, %dec_label_pc_412d60
  ret i64 %arg1
}
"""
    m412 = re.search(r"define i64 @function_412d60\(i64 %arg1, i64 %arg2\)[\s\S]*?\n\}\n", t)
    if m412:
        t = t[:m412.start()] + c14_new + t[m412.end():]
        stage("C14", "function_412d60 本体を native 実測語義で置換 (var content load 復元)")

    # ---- call sites ---------------------------------------------------
    t = t.replace("%2 = call i64 @function_409ef0(i64 %1, ptr nonnull %stack_var_-16)",
                  "%2 = call i64 @function_409ef0(i64 %1, i64 %stack_var_-16p)")
    t = t.replace("%3 = call i64 @function_409ef0(i64 %rax.0.reload, ptr nonnull %stack_var_-16)",
                  "%3 = call i64 @function_409ef0(i64 %rax.0.reload, i64 %stack_var_-16p)")
    t = t.replace("%37 = call i64 @function_414ad0(ptr %arg2, i32 %36)",
                  "%c37ext = zext i32 %36 to i64\n  "
                  "%37 = call i64 @function_414ad0(i64 %arg2i, i64 %c37ext)")
    t = t.replace("%6 = call i64 @function_412d60(ptr %arg1, i64 %5)",
                  "%6 = call i64 @function_412d60(i64 %arg1i, i64 %5)")
    t = t.replace("%50 = call i64 @function_412d60(ptr %arg1, i64 %40)",
                  "%50 = call i64 @function_412d60(i64 %arg1i, i64 %40)")
    t = t.replace("%8 = call i64 @function_412d60(ptr nonnull %stack_var_-16, i64 %7)",
                  "%8 = call i64 @function_412d60(i64 %stack_var_-16p, i64 %7)")

    # 409fe0 側: %stack_var_-16 の i64 への ptrtoint 前前置
    if "stack_var_-16p = ptrtoint" not in t:
        t = t.replace("%stack_var_-16 = alloca i64, align 8",
                      "%stack_var_-16 = alloca i64, align 8\n"
                      "  %stack_var_-16p = ptrtoint ptr %stack_var_-16 to i64",
                      1)


    # ---- 412d60 (ir5 sig-fix 済み (i64,i64) 形の場合の後処理) -------------
    m = re.search(r"define i64 @function_412d60\(i64 %arg1, i64 %arg2\)([^\n]*)\n(dec_label_pc_412d60:\n)"
                  r"(  %0 = ptrtoint ptr %arg1 to i64\n  %1 = icmp eq ptr %arg1, null\n)", t)
    if m:
        body = (f"  %arg1c = inttoptr i64 %arg1 to ptr\n"
                f"  %0 = ptrtoint ptr %arg1c to i64\n"
                f"  %1 = icmp eq i64 %arg1, 0\n")
        t = t[:m.start(3)] + body + t[m.end(3):]
        t = t.replace("  store i64 0, ptr %arg1, align 8", "  store i64 0, ptr %arg1c, align 8")

    # 409eef0/side 他 "%argXp/n" 変数の命名衝突の消し:
    open(path, "w").write(t)
    print(f"[c1c_fix] patched {path}")

if __name__ == "__main__":
    fix(sys.argv[1])
