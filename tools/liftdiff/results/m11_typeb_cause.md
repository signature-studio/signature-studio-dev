<!-- 自動生成: python3 tools/liftdiff/tests/trace_fullcompare_typeb.py "$PWD/tools/liftdiff/targets/m11.json" の stdout を §3 に貼る (LD-27 / #1034)。FL_WIN64_DIR は block00031_PE.bin を含む展開先。入力 = tools/liftdiff/work/m11/batch_closure.jsonl (work-m11/work-liftdiff 展開物) -->
# m11 型 B 候補 34 case の完全 trace 再検証と戻り後の分岐 (LD-27, #1034)

入力: trace_head 基準の型 B 候補 34 case (`results/m11_unreachable_diverge.md` §2)。各 case を完全 trace で xfill=1 / xfill=0 の 2 条件で取り直した (68 行)。
L = 完全 trace で native/wasm が最後に一致する entry。caller = L の直前の entry (直接 call 命令を `call@` で確認)。

## 1. 類型 (xfill × class)

| xfill | X (xmm 引数脱落) | M (0x40a380 の stmxcsr 経路) | R (未特定) | 計 |
|---:|---:|---:|---:|---:|
| 1 | 28 | 1 | 5 | 34 |
| 0 | 25 | 3 | 6 | 34 |

- **X (xmm_arg_drop)**: 呼出元 (または L) の entry で「xmm0 を書かれる前に読む」関数があり、その entry の x0 が native ≠ wasm。IR では該当関数の xmm0 入力が `call i64 @__asm_movsd(i128 0)` (`xor i128 0, 0`) に置き換わる (例: `function_40c1d0`)。既存類型 `xmm_arg_drop` (`tools/liftdiff/docs/FORMAT.md` の類型表 107 行)。修復は #547 (PLG-F2-4) の接続で行う。
- **M (0x40a380 経路)**: L = 0x40a380 (`stmxcsr`/`ldmxcsr`)。直前の entry は 0x40a3b0 (`stmxcsr` で MXCSR を rax に返す leaf)。L の後、native は戻って終了し、wasm は `call 0x409730` 側へ進んで trap する。0x40a1c0 が MXCSR 例外フラグを判定する (`test eax, 0x20/0x10/8/4` → `call 0x409730`) ため、この分岐の候補だが、wasm 側の MXCSR の値と分岐の確定は未確認 (#1034 に残す)。
- **R (未特定)**: X にも M にも入らない。戻り後の分岐は下記 §3 の行に出ている (L 0x12f9ed0 / 0xfea6a0 / 0x40ae30 / 0x40a3b0 ほか)。個別原因は未特定。

## 2. 0x40a3d0 (leaf `movzx rax, word [rcx+rdx*2]; ret`) の戻り値 rax

呼出元 0x40c1d0 は `movsd [rbp+0x28], xmm0` の後に `rcx = &[rbp+0x28]`, `edx = 3` で 0x40a3d0 を呼ぶ。よって rax = (x0 の上位 16 bit) で、x0 は呼出元 entry の trace (`TN[i-1][10]`)。wasm 側 x0 は常に 0 (§1 X)。

| xfill | rax native | rax wasm | 件数 |
|---:|---|---|---:|
| 0 | 0x3f84 | 0x0000 | 1 |
| 0 | 0x3fe2 | 0x0000 | 1 |
| 0 | 0x3fe6 | 0x0000 | 1 |
| 0 | 0x3ff0 | 0x0000 | 2 |
| 0 | 0x4000 | 0x0000 | 3 |
| 0 | 0x403b | 0x0000 | 3 |
| 0 | 0x4049 | 0x0000 | 2 |
| 0 | 0x408f | 0x0000 | 3 |
| 0 | 0x40b8 | 0x0000 | 1 |
| 0 | 0x40c3 | 0x0000 | 2 |
| 0 | 0x40d5 | 0x0000 | 1 |
| 0 | 0x7ff0 | 0x0000 | 1 |
| 1 | 0x3f84 | 0x0000 | 1 |
| 1 | 0x3fe2 | 0x0000 | 1 |
| 1 | 0x3fe6 | 0x0000 | 1 |
| 1 | 0x3ff0 | 0x0000 | 2 |
| 1 | 0x3ff4 | 0x0000 | 3 |
| 1 | 0x4000 | 0x0000 | 3 |
| 1 | 0x403b | 0x0000 | 3 |
| 1 | 0x4049 | 0x0000 | 2 |
| 1 | 0x4071 | 0x0000 | 1 |
| 1 | 0x408f | 0x0000 | 3 |
| 1 | 0x40b8 | 0x0000 | 1 |
| 1 | 0x40c3 | 0x0000 | 2 |
| 1 | 0x40d5 | 0x0000 | 1 |

注: rax は leaf の戻り値を直接ダンプしたものではない (runner に戻り値の記録は無い)。trace の x0 と逆アセンブルから導出した値。直接の実測は runner の計装が要る (#1034 の残り)。
xfill=0 でも native の x0 は非ゼロ (例: 0x3ff0・0x403b) で、wasm は 0 のまま。よって X の差は xfill の人工値だけでは説明できない。

## 3. 全件 (完全 trace・xfill 1 と 0)

`class`: X/M/R (§1)、`L_full`: 完全 trace の L、`typeB_full`: L が ret まで call 無しか、`next(native,wasm)`: L の次 entry、`L_x0`/`caller_x0`: entry の x0 (native,wasm)、`post`: caller の call 直後の命令、`jcc`: その先の最初の条件分岐。

```
# 型 B 候補 34 case (trace_head 基準の L が leaf)
fn=0x476930 pat=z xfill=1 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x3ff4000000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x3ff4000000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x476930 pat=z xfill=0 class=M L_full=0x40a380 typeB_full=B next(native,wasm)=('-', '0x409730') native=ok wasm=trap
   L_x0(native,wasm)=0x0,0x0 caller=0x40a3b0 call@- caller_x0(native,wasm)=0x0,0x0 post=[-] jcc=-
fn=0x117bca0 pat=z xfill=1 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x403b000000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x403b000000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x117bca0 pat=z xfill=0 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x403b000000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x403b000000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x11860d0 pat=z xfill=1 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x4000000000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x4000000000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x11860d0 pat=z xfill=0 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x4000000000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x4000000000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x6a2e70 pat=z xfill=1 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x3ff0000000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x3ff0000000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x6a2e70 pat=z xfill=0 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x3ff0000000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x3ff0000000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x117bb80 pat=z xfill=1 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x403b000000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x403b000000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x117bb80 pat=z xfill=0 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x403b000000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x403b000000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x132dea0 pat=z xfill=1 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x4000000000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x4000000000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x132dea0 pat=z xfill=0 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x4000000000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x4000000000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0xba0490 pat=z xfill=1 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x40716c71c0000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x40716c71c0000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0xba0490 pat=z xfill=0 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c1d0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x7ff0000000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x7ff0000000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x66e9a0 pat=z xfill=1 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x3f847ae147ae147b,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x3f847ae147ae147b,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x66e9a0 pat=z xfill=0 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x3f847ae147ae147b,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x3f847ae147ae147b,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0xba0520 pat=z xfill=1 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x40c3888000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x40c3888000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0xba0520 pat=z xfill=0 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x40c3888000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x40c3888000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0xea8c80 pat=z xfill=1 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x3fe6e00480000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x3fe6e00480000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0xea8c80 pat=z xfill=0 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x3fe6e00480000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x3fe6e00480000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x9823d0 pat=z xfill=1 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x4049800000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x4049800000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x9823d0 pat=z xfill=0 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x4049800000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x4049800000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x12d83a0 pat=z xfill=1 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=segv wasm=trap
   L_x0(native,wasm)=0x3fe212a8e0000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x3fe212a8e0000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x12d83a0 pat=z xfill=0 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=segv wasm=trap
   L_x0(native,wasm)=0x3fe212a8e0000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x3fe212a8e0000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x69fcd0 pat=z xfill=1 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x4049800000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x4049800000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x69fcd0 pat=z xfill=0 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x4049800000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x4049800000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x6a6890 pat=z xfill=1 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x4000000000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x4000000000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x6a6890 pat=z xfill=0 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x4000000000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x4000000000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x40c1d0 pat=z xfill=1 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x3ff4000000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x3ff4000000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x40c1d0 pat=z xfill=0 class=M L_full=0x40a380 typeB_full=B next(native,wasm)=('-', '0x409730') native=ok wasm=trap
   L_x0(native,wasm)=0x0,0x0 caller=0x40a3b0 call@- caller_x0(native,wasm)=0x0,0x0 post=[-] jcc=-
fn=0xcd1c20 pat=p0 xfill=1 class=R L_full=0xcd1a70 typeB_full=notB next(native,wasm)=('0xcb9eb0', '0x823c30') native=ok wasm=trap
   L_x0(native,wasm)=0xb,0x0 caller=0xcd1c20 call@0xcd1c5a caller_x0(native,wasm)=0x3ff4000000000000,0x0 post=[add rsp, 0x48 ; ret  ; int3  ; int3 ] jcc=-
fn=0xcd1c20 pat=p0 xfill=0 class=X L_full=0x40c660 typeB_full=B next(native,wasm)=('0x40c660', '0xcb9e00') native=ok wasm=trap
   L_x0(native,wasm)=0x7ff0000000000000,0x0 caller=0x40c660 call@- caller_x0(native,wasm)=0x7ff0000000000000,0x0 post=[-] jcc=-
fn=0xfea1e0 pat=p0 xfill=1 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x403b000000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x403b000000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0xfea1e0 pat=p0 xfill=0 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x403b000000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x403b000000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x12e5d80 pat=p0 xfill=1 class=X L_full=0x40ae30 typeB_full=B next(native,wasm)=('0x40c750', '0x40c1d0') native=ok wasm=trap
   L_x0(native,wasm)=0x3ff0000000000000,0x0 caller=0x476c30 call@0x476c96 caller_x0(native,wasm)=0x3f9c1c1c3ce0e0e1,0x0 post=[ucomisd xmm0, qword ptr [rip + 0x8d] ; jp 0x476cd8 ; jne 0x476cd8 ; cvtss2sd xmm0, xmm7] jcc=jp 0x476cd8
fn=0x12e5d80 pat=p0 xfill=0 class=X L_full=0x40ae30 typeB_full=B next(native,wasm)=('0x40c750', '0x40c1d0') native=ok wasm=trap
   L_x0(native,wasm)=0x3ff0000000000000,0x0 caller=0x476c30 call@0x476c96 caller_x0(native,wasm)=0x3f9c1c1c3ce0e0e1,0x0 post=[ucomisd xmm0, qword ptr [rip + 0x8d] ; jp 0x476cd8 ; jne 0x476cd8 ; cvtss2sd xmm0, xmm7] jcc=jp 0x476cd8
fn=0x9ce950 pat=p01 xfill=1 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x408f480000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x408f480000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x9ce950 pat=p01 xfill=0 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x408f480000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x408f480000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x9ce890 pat=p0 xfill=1 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x40b8cb0000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x40b8cb0000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x9ce890 pat=p0 xfill=0 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x40b8cb0000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x40b8cb0000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x12c5e70 pat=z xfill=1 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x3ff0000000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x3ff0000000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x12c5e70 pat=z xfill=0 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x3ff0000000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x3ff0000000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0xba03d0 pat=p0 xfill=1 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x40c3888000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x40c3888000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0xba03d0 pat=p0 xfill=0 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x40c3888000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x40c3888000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x9cec20 pat=p0 xfill=1 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x408f480000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x408f480000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x9cec20 pat=p0 xfill=0 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x408f480000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x408f480000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0xf3c7b0 pat=z xfill=1 class=R L_full=0x12f9ed0 typeB_full=B next(native,wasm)=('-', '0x12f9ec0') native=ok wasm=trap
   L_x0(native,wasm)=0x3ff4000000000000,0x0 caller=0xf3c7b0 call@0xf3c7c3 caller_x0(native,wasm)=0x3ff4000000000000,0x0 post=[xor ecx, ecx ; mov r14d, eax ; sub r14d, 1 ; mov r13d, ecx] jcc=jg 0xf3c807
fn=0xf3c7b0 pat=z xfill=0 class=R L_full=0x12f9ed0 typeB_full=B next(native,wasm)=('-', '0x12f9ec0') native=ok wasm=trap
   L_x0(native,wasm)=0x0,0x0 caller=0xf3c7b0 call@0xf3c7c3 caller_x0(native,wasm)=0x0,0x0 post=[xor ecx, ecx ; mov r14d, eax ; sub r14d, 1 ; mov r13d, ecx] jcc=jg 0xf3c807
fn=0xe24ee0 pat=z xfill=1 class=R L_full=0x12f9ed0 typeB_full=B next(native,wasm)=('-', '0x12f9ec0') native=ok wasm=trap
   L_x0(native,wasm)=0x3ff4000000000000,0x0 caller=0xe24ee0 call@0xe24ef3 caller_x0(native,wasm)=0x3ff4000000000000,0x0 post=[xor ecx, ecx ; mov r13d, eax ; sub r13d, 1 ; mov eax, ecx] jcc=jg 0xe24f89
fn=0xe24ee0 pat=z xfill=0 class=R L_full=0x12f9ed0 typeB_full=B next(native,wasm)=('-', '0x12f9ec0') native=ok wasm=trap
   L_x0(native,wasm)=0x0,0x0 caller=0xe24ee0 call@0xe24ef3 caller_x0(native,wasm)=0x0,0x0 post=[xor ecx, ecx ; mov r13d, eax ; sub r13d, 1 ; mov eax, ecx] jcc=jg 0xe24f89
fn=0x9ce9e0 pat=p0 xfill=1 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x408f480000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x408f480000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x9ce9e0 pat=p0 xfill=0 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x408f480000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x408f480000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x40ef40 pat=p1 xfill=1 class=R L_full=0x40a3b0 typeB_full=B next(native,wasm)=('0x40a360', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x3ff4000000000000,0x0 caller=0x40a2c0 call@0x40a2d1 caller_x0(native,wasm)=0x3ff4000000000000,0x0 post=[mov edi, eax ; mov eax, esi ; not eax ; mov ecx, edi] jcc=-
fn=0x40ef40 pat=p1 xfill=0 class=R L_full=0x40a3b0 typeB_full=B next(native,wasm)=('0x40a360', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x0,0x0 caller=0x40a2c0 call@0x40a2d1 caller_x0(native,wasm)=0x0,0x0 post=[mov edi, eax ; mov eax, esi ; not eax ; mov ecx, edi] jcc=-
fn=0xcb9eb0 pat=p0 xfill=1 class=X L_full=0x40c660 typeB_full=B next(native,wasm)=('0xcc32f0', '0x40c1d0') native=ok wasm=trap
   L_x0(native,wasm)=0x224b,0x0 caller=0x40c660 call@- caller_x0(native,wasm)=0x2247,0x0 post=[-] jcc=-
fn=0xcb9eb0 pat=p0 xfill=0 class=X L_full=0x40c660 typeB_full=B next(native,wasm)=('0xcc32f0', '0x40c1d0') native=ok wasm=trap
   L_x0(native,wasm)=0x224b,0x0 caller=0x40c660 call@- caller_x0(native,wasm)=0x2247,0x0 post=[-] jcc=-
fn=0x4769f0 pat=z xfill=1 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x3ff4000000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x3ff4000000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x4769f0 pat=z xfill=0 class=R L_full=0x4769f0 typeB_full=notB next(native,wasm)=('-', '0x40ae30') native=ok wasm=trap
   L_x0(native,wasm)=0x0,0x0 caller=- call@- caller_x0(native,wasm)=- post=[-] jcc=-
fn=0xe26510 pat=z xfill=1 class=R L_full=0x12f9ed0 typeB_full=B next(native,wasm)=('-', '0x12f9ec0') native=ok wasm=trap
   L_x0(native,wasm)=0x3ff4000000000000,0x0 caller=0xe26510 call@0xe2652b caller_x0(native,wasm)=0x3ff4000000000000,0x0 post=[xor ecx, ecx ; mov r13d, eax ; sub r13d, 1 ; mov eax, ecx] jcc=jg 0xe265eb
fn=0xe26510 pat=z xfill=0 class=R L_full=0x12f9ed0 typeB_full=B next(native,wasm)=('-', '0x12f9ec0') native=ok wasm=trap
   L_x0(native,wasm)=0x0,0x0 caller=0xe26510 call@0xe2652b caller_x0(native,wasm)=0x0,0x0 post=[xor ecx, ecx ; mov r13d, eax ; sub r13d, 1 ; mov eax, ecx] jcc=jg 0xe265eb
fn=0x40a1c0 pat=s xfill=1 class=M L_full=0x40a380 typeB_full=B next(native,wasm)=('-', '0x409730') native=ok wasm=trap
   L_x0(native,wasm)=0x3ff4000000000000,0x0 caller=0x40a3b0 call@- caller_x0(native,wasm)=0x3ff4000000000000,0x0 post=[-] jcc=-
fn=0x40a1c0 pat=s xfill=0 class=M L_full=0x40a380 typeB_full=B next(native,wasm)=('-', '0x409730') native=ok wasm=trap
   L_x0(native,wasm)=0x0,0x0 caller=0x40a3b0 call@- caller_x0(native,wasm)=0x0,0x0 post=[-] jcc=-
fn=0xff0600 pat=p0 xfill=1 class=X L_full=0xfea6a0 typeB_full=B next(native,wasm)=('0x412e40', '0x11860d0') native=ok wasm=trap
   L_x0(native,wasm)=0x3ff4000000000000,0x0 caller=0xff0600 call@0xff0652 caller_x0(native,wasm)=0x3ff4000000000000,0x0 post=[mov rcx, qword ptr [rbp + 0x38] ; mov byte ptr [rcx + 0x6f1], al ; test al, al ; je 0xff0967] jcc=je 0xff0967
fn=0xff0600 pat=p0 xfill=0 class=R L_full=0xfea6a0 typeB_full=B next(native,wasm)=('0x412e40', '0x11860d0') native=ok wasm=trap
   L_x0(native,wasm)=0x0,0x0 caller=0xff0600 call@0xff0652 caller_x0(native,wasm)=0x0,0x0 post=[mov rcx, qword ptr [rbp + 0x38] ; mov byte ptr [rcx + 0x6f1], al ; test al, al ; je 0xff0967] jcc=je 0xff0967
fn=0x6a0760 pat=p01 xfill=1 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x40d5888000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x40d5888000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0x6a0760 pat=p01 xfill=0 class=X L_full=0x40a3d0 typeB_full=B next(native,wasm)=('0x40c0e0', '0x40a1c0') native=ok wasm=trap
   L_x0(native,wasm)=0x40d5888000000000,0x0 caller=0x40c1d0 call@0x40c1ee caller_x0(native,wasm)=0x40d5888000000000,0x0 post=[mov ecx, eax ; cmp cx, 0x8000 ; jb 0x40c24c ; movabs rax, 0x8000000000000000] jcc=jb 0x40c24c
fn=0xcd1a70 pat=p0 xfill=1 class=X L_full=0x40c660 typeB_full=B next(native,wasm)=('0xcc32f0', '0x40c1d0') native=ok wasm=trap
   L_x0(native,wasm)=0x224b,0x0 caller=0x40c660 call@- caller_x0(native,wasm)=0x2247,0x0 post=[-] jcc=-
fn=0xcd1a70 pat=p0 xfill=0 class=X L_full=0x40c660 typeB_full=B next(native,wasm)=('0xcc32f0', '0x40c1d0') native=ok wasm=trap
   L_x0(native,wasm)=0x224b,0x0 caller=0x40c660 call@- caller_x0(native,wasm)=0x2247,0x0 post=[-] jcc=-
## 集計 (xfill, class): [((0, 'M'), 3), ((0, 'R'), 6), ((0, 'X'), 25), ((1, 'M'), 1), ((1, 'R'), 5), ((1, 'X'), 28)]
```
