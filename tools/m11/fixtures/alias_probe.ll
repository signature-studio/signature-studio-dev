; m11_global_store_alias の制御 IR (#5449 / M11-N244)。対象 VA 0x15e3a70 (8 バイト)。
; 判定: va_hit = 対象 VA と重なる store, const_other = 定数アドレスだが重ならない,
;       const_var_offset = 定数 inttoptr が基底だが GEP index が非定数, alloca = reg2mem スロット。

define void @probe() {
entry:
  %a = alloca i64
  store i64 1, ptr inttoptr (i64 22952560 to ptr), align 8
  store i64 2, ptr getelementptr (i8, ptr inttoptr (i64 22952560 to ptr), i64 0), align 8
  %p3 = inttoptr i64 22952544 to ptr
  %q3 = getelementptr i64, ptr %p3, i64 2
  store i64 3, ptr %q3, align 8
  store i64 4, ptr getelementptr (i8, ptr inttoptr (i64 22952544 to ptr), i64 16), align 8
  store i32 5, ptr getelementptr ([4 x i8], ptr inttoptr (i64 22952560 to ptr), i64 0), align 4
  store i64 6, ptr inttoptr (i64 22952552 to ptr), align 8
  store i8 7, ptr inttoptr (i64 22952567 to ptr), align 1
  %p8 = inttoptr i64 22952544 to ptr
  %n = load i64, ptr %a, align 8
  %q8 = getelementptr i64, ptr %p8, i64 %n
  store i64 8, ptr %q8, align 8
  store i64 9, ptr %a, align 8
  ret void
}
