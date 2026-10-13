; RetDec の declare 署名の揺れを再現する合成 fixture (SHX-T7 / #173)。実 IR は work-m11 / work-m6-ott 素材。
;  - acmMetrics / CoCreateInstance / GetComputerNameExW / GetFileAttributesExW / midiOutShortMsg: REPORT §4 の 5 件 (shimx は i64 第1/2引数)
;    ここでは逆向き (shimx と異なる ptr / i32 / 戻り i64) の揺れを入れ、adapter が両方向を吸収することを確かめる
;  - CreateEventW.1: 重複 declare (NAME.1) で戻り値 ptr・引数 i64 に揺れたもの
;  - GetLastError: 揺れ無し (adapter 不要であること)
target triple = "wasm32-unknown-emscripten"

declare i32 @acmMetrics(ptr, i32, ptr)
declare i32 @CoCreateInstance(ptr, ptr, i32, ptr, ptr)
declare i64 @GetComputerNameExW(i32, ptr, ptr)
declare i32 @GetFileAttributesExW(ptr, i32, ptr)
declare i32 @midiOutShortMsg(ptr, i32)
declare ptr @CreateEventW.1(ptr, i64, i1, ptr)
declare i32 @GetLastError()

@fp = global ptr @acmMetrics

define i32 @sigprobe_main() {
  %a = call i32 @acmMetrics(ptr null, i32 1, ptr null)
  %b = call i32 @CoCreateInstance(ptr null, ptr null, i32 1, ptr null, ptr null)
  %c = call i64 @GetComputerNameExW(i32 0, ptr null, ptr null)
  %d = call i32 @GetFileAttributesExW(ptr null, i32 0, ptr null)
  %e = call i32 @midiOutShortMsg(ptr null, i32 0)
  %f = call ptr @CreateEventW.1(ptr null, i64 1, i1 0, ptr null)
  %g = call i32 @GetLastError()
  ret i32 %g
}
