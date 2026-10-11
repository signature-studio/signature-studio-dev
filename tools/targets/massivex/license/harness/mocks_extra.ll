; MX-2 harness: ドット付き名 (C 識別子化不可) のみここで定義。
; それ以外 (__asm_movups 等ドット無し) は mx_mocks_gen.py が生成する。
define void @__asm_movups.1(i128 %a, i128 %b) {
  ret void
}
