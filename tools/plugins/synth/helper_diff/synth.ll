; fix_avx256 / m11_simd2 の入力 (RetDec が出す疑似 helper 呼出の形。 work/batch/23738/p.final.ll の function_745c00 と同じ署名・同じ store 形)。 薄い関数は ptr 経由。
declare i128 @__asm_cmpnltps(i128, i128) local_unnamed_addr
declare i32 @__asm_movmskps(i128) local_unnamed_addr
declare void @__asm_prefetcht0(i8) local_unnamed_addr
declare void @__asm_rep_movsd_memcpy(ptr, ptr, i64) local_unnamed_addr
declare void @__asm_rep_stosb_memset(ptr, i8, i64) local_unnamed_addr
declare i256 @__asm_vmovaps(i256) local_unnamed_addr
declare i256 @__asm_vaddps(i256, i256) local_unnamed_addr
declare i256 @__asm_vsubps(i256, i256) local_unnamed_addr
declare i256 @__asm_vmulps(i256, i256) local_unnamed_addr
declare i256 @__asm_vdivps(i256, i256) local_unnamed_addr
declare i256 @__asm_vminps(i256, i256) local_unnamed_addr
declare i256 @__asm_vmaxps(i256, i256) local_unnamed_addr
declare i128 @__asm_vextractf128(i256, i8) local_unnamed_addr
declare void @__asm_vmovaps__9(i128, i128) local_unnamed_addr
declare void @__asm_vmovaps__10(i256, i256) local_unnamed_addr

define i128 @w_cmpnltps(i128 %a, i128 %b) { %r = call i128 @__asm_cmpnltps(i128 %a, i128 %b) ret i128 %r }
define void @t_vmovaps(ptr %a, ptr %o) {
  %x = load i256, ptr %a, align 8
  %r = call i256 @__asm_vmovaps(i256 %x)
  store i256 %r, ptr %o, align 8
  ret void
}
define void @t_vaddps(ptr %a, ptr %b, ptr %o) {
  %x = load i256, ptr %a, align 8
  %y = load i256, ptr %b, align 8
  %r = call i256 @__asm_vaddps(i256 %x, i256 %y)
  store i256 %r, ptr %o, align 8
  ret void
}
define void @t_vsubps(ptr %a, ptr %b, ptr %o) {
  %x = load i256, ptr %a, align 8
  %y = load i256, ptr %b, align 8
  %r = call i256 @__asm_vsubps(i256 %x, i256 %y)
  store i256 %r, ptr %o, align 8
  ret void
}
define void @t_vmulps(ptr %a, ptr %b, ptr %o) {
  %x = load i256, ptr %a, align 8
  %y = load i256, ptr %b, align 8
  %r = call i256 @__asm_vmulps(i256 %x, i256 %y)
  store i256 %r, ptr %o, align 8
  ret void
}
define void @t_vdivps(ptr %a, ptr %b, ptr %o) {
  %x = load i256, ptr %a, align 8
  %y = load i256, ptr %b, align 8
  %r = call i256 @__asm_vdivps(i256 %x, i256 %y)
  store i256 %r, ptr %o, align 8
  ret void
}
define void @t_vminps(ptr %a, ptr %b, ptr %o) {
  %x = load i256, ptr %a, align 8
  %y = load i256, ptr %b, align 8
  %r = call i256 @__asm_vminps(i256 %x, i256 %y)
  store i256 %r, ptr %o, align 8
  ret void
}
define void @t_vmaxps(ptr %a, ptr %b, ptr %o) {
  %x = load i256, ptr %a, align 8
  %y = load i256, ptr %b, align 8
  %r = call i256 @__asm_vmaxps(i256 %x, i256 %y)
  store i256 %r, ptr %o, align 8
  ret void
}
define void @t_vext0(ptr %a, ptr %o) {
  %x = load i256, ptr %a, align 8
  %r = call i128 @__asm_vextractf128(i256 %x, i8 0)
  store i128 %r, ptr %o, align 8
  ret void
}
define void @t_vext1(ptr %a, ptr %o) {
  %x = load i256, ptr %a, align 8
  %r = call i128 @__asm_vextractf128(i256 %x, i8 1)
  store i128 %r, ptr %o, align 8
  ret void
}
; RetDec の store 形: 書込前の値を load して第 1 引数に渡す
define void @t_vstore256(ptr %p, ptr %a) {
  %new = load i256, ptr %a, align 8
  %old = load i256, ptr %p, align 8
  call void @__asm_vmovaps__10(i256 %old, i256 %new)
  ret void
}
define void @t_vstore128(ptr %p, ptr %a) {
  %new = load i128, ptr %a, align 8
  %old = load i128, ptr %p, align 8
  call void @__asm_vmovaps__9(i128 %old, i128 %new)
  ret void
}
