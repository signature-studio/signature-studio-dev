# ildsp REPORT 付録: WaveformColouring vtable slot 1–5 の host 前提 (#4169 / T-SH-99)

親 #3274 (T-SH-57) の no_pr 停止報告を受けた検証。slot 1–5 を元の機械語 (native) だけで呼び、落ちる入力と動く入力を切り分けた。
実験は 1 プロセス 1 実験 (CreateInstance の直後に slot を 1 回呼ぶ)。

測定 commit (コードを変えた最後の commit): `d0480f2c1` (`test(ildsp): add slot 1/4 frame-0 and null-pointer runs to slot_probe (#4169)`)。
slot の測定値は `d0480f2c1` の HEAD で再実行した (§3)。`c37267725` の時点の出力と全 15 run が一致し、追加の 2 run を加えた。
検証起点: `origin/main` `292549785`。

## 1. 結論

- **slot 1・4 の落ちる原因は確定した。** 出力先ポインタが null のとき落ちる (slot 1 は 3 番目の引数 `r8`、slot 4 は 5 番目の引数。位置は §2 注)。`this+0x20` は関係しない (旧推定 `REPORT_APPENDIX_3216.md` §7-5 の「this+0x20 が null」は誤り)。
  - slot 1 の `r8` (出力) は frame 数に関係なく必須。`rdx` (入力) は frame 0 では不要 (§3)。
  - slot 4 の 5 番目 (出力) は frame 数に関係なく必須。`rdx` (入力) は frame 0 では不要 (§3)。
- **native で動く host 前提は確定した。** 呼出側 (FL 本体) が実際に渡す値は**未確認**。call-site を fl-win64 内で見つけられなかった (§5)。
- slot 2・3・5 は、全引数 0 でも native で完走する (slot 2 の `xmm1` は未制御。§3)。

## 2. 引数の意味 (逆アセンブル + native 実験)

| slot | RVA | 引数の使われ方 (逆アセンブル) | 落ちる条件 (native 実測) | 完走する条件 |
|---|---|---|---|---|
| 1 | 0x1a9f10 | `rcx`=this。`this+0x20`・`+0x34`・`+0x3c`・`+0x40` を読む。`rdx`=入力 (`rsi` に退避し 読みに使う)。`r8`=出力 (`rdi` に退避し `(%r8)` に書く)。`r9`=frame 数 (`rbx = (r10=2 or 3) * r9`)。5 番目 (`0x28(%rsp)` 相当) は `neg` されて channel 数の判定に使われる | `r8=0` で落ちる (addr=0)。`rdx=0` かつ frame>0 で落ちる (addr=0) | `rdx`・`r8` が有効、frame 0 または 4 で完走 (rax=0) |
| 2 | 0x1a9e10 | `rcx`=this。先頭で `call [rax+0x18]` (vcall = slot 3) を呼ぶ。`xmm1` (浮動小数) を使う | 落ちる入力は見つからず | 全引数 0 で完走 (rax=1)。`xmm1` は harness で制御していない |
| 3 | 0x1a9de0 | `rcx`=this。`this+0x20` から 2 要素を 0 で初期化するだけ | 落ちる入力は見つからず | 全引数 0 で完走 (rax=0x30500028) |
| 4 | 0x1aa0b0 | `rcx`=this。`rdx`=入力。`r8`=frame 数 (`r9 = (r10=2 or 3) * r8`)。`r9`=channel 系フラグ。5 番目 (`0x60(%rsp)`、§2 注) が出力先 `r8'` で、`(r8')`・`+8` に書く | 5 番目 (出力) が 0 のとき落ちる (frame 16 でも frame 0 でも addr=0)。`rdx=0` かつ frame 4 で落ちる (addr=0) | 出力が有効、frame 0・4・16 で完走 (rax=0)。`rdx=0` かつ frame 0 は出力が有効なら完走 (§3) |
| 5 | 0x1ac460 | `mov edx,0x228; jmp 0x1ac9b0` (ヒープ確保 (alloc) への tail jump)。`this` は使わない | 落ちる入力は見つからず | 全引数 0 で完走 (rax=1)。戻り値は alloc の結果 |

注: slot 5 (0x1ac460) は `mov edx,0x228` の tail jump で、`this` の内容を読まない。`REPORT_APPENDIX_3401.md` の slot 役割表は vtable 0x3e0030 (PSOLA 側) の記述で、本件の vtable 0x3e01b0 とは別物。

注 (5 番目の引数の位置): 5 番目の引数は、slot 1・4 とも **entry 時 (call 直後、戻りアドレスが `(%rsp)`) は `0x28(%rsp)`** にある。prologue が `push %rdi` (+8) と `sub` を行うため、prologue 後の逆アセンブル上の位置は slot 4 が `0x60(%rsp)` (`0x28+8+0x30`)、slot 1 が `0x90(%rsp)` (`0x28+8+0x60`) になる。表の `0x60`・`0x90` は prologue 後の位置で、§2 の表の slot 4 行は `0x60(%rsp)` (prologue 後) と読む。

## 3. 測定 (HEAD `d0480f2c1`・native のみ・`slot_probe.sh`)

`bash tools/shared/lift/ildsp/slot_probe.sh` (`FL_WIN64_DIR` = fl-win64 展開先) の出力をそのまま貼る。

```
## slot 1 (rdx=入力, r8=出力, r9=frame 数, 5 番目=channel フラグ)
slot1 in out frames=0 flag=0                 RESULT completed slot=1 rax=0x0 rc=0
slot1 in out frames=4 flag=0                 RESULT completed slot=1 rax=0x0 rc=0
slot1 in out frames=4 flag=1                 RESULT completed slot=1 rax=0x0 rc=0
slot1 r8=0 (出力 null)                     RESULT crashed slot=1 sig=11 addr=0x0 rc=4
slot1 rdx=0 (入力 null)                    RESULT crashed slot=1 sig=11 addr=0x0 rc=4
slot1 rdx=0 frames=0 (入力 null)           RESULT completed slot=1 rax=0x0 rc=0
slot1 r8=0 frames=0 (出力 null)            RESULT crashed slot=1 sig=11 addr=0x0 rc=4
## slot 4 (rdx=入力, r8=frame 数, r9=channel フラグ, 5 番目=出力)
slot4 in frames=0 flag=0 out                 RESULT completed slot=4 rax=0x0 rc=0
slot4 in frames=4 flag=0 out                 RESULT completed slot=4 rax=0x0 rc=0
slot4 in frames=16 flag=1 out                RESULT completed slot=4 rax=0x0 rc=0
slot4 out=0 (5 番目 null)                  RESULT crashed slot=4 sig=11 addr=0x0 rc=4
slot4 out=0 frames=0 (5 番目 null)         RESULT crashed slot=4 sig=11 addr=0x0 rc=4
slot4 rdx=0 frames=4 out                     RESULT crashed slot=4 sig=11 addr=0x0 rc=4
slot4 rdx=0 frames=0 out                     RESULT completed slot=4 rax=0x0 rc=0
## slot 2・3・5 (全引数 0)
slot2 all zero                               RESULT completed slot=2 rax=0x1 rc=0
slot3 all zero                               RESULT completed slot=3 rax=0x30500028 rc=0
slot5 all zero                               RESULT completed slot=5 rax=0x1 rc=0
```

上の追加 2 run (`rdx=0 frames=0` の slot 1 と `out=0 frames=0` の slot 4) と、その他の 2 run (`r8=0 frames=0` の slot 1、`rdx=0` の slot 4 の 2 run) は、`c37267725` の時点では無かった。`d0480f2c1` の HEAD で追加して再実行したもの。

測定の限界: 上記は「落ちない入力の 1 組」の確認で、分岐の網羅ではない。`xmm1` (slot 2) と浮動小数の入力は制御していない。

## 4. host 前提 (native で動かすための値)

- `CreateInstance` の直後に呼ぶ。`this` は CreateInstance が設定した値のまま (this+0x20 は 0 のままで問題ない)。
- slot 1: `r8` = 有効な出力 buffer (frame 数に関係なく必須)。`rdx` = 有効な入力 buffer (frame 0 なら 0 でもよい)。frame 数 (`r9`) は 0 または正の数。5 番目は任意のフラグ。
- slot 4: `rdx` = 有効な入力 buffer (frame 0 なら 0 でもよい)、`r8` = frame 数、`r9` = フラグ、5 番目 = 有効な出力 buffer (frame 数に関係なく必須)。
- slot 2・3・5: 引数は 0 でよい (slot 2 は `xmm1` の値が未制御のまま完走)。

この前提は**native が落ちない最小条件**であり、FL 本体が実際に渡す値ではない。

## 5. 未確認 (受入条件の残り)

| 項目 | 状態 | 理由・次に要るもの |
|---|---|---|
| FL 本体の呼出側 (slot 1・4 の実引数: 出力 buffer の番地・frame 数・フラグ・5 番目の値) | **未確認** | 名前 `WaveformColouring` を fl-win64 の全ファイルで検索したところ、`block24360_PE.bin` の export 以外に無かった。間接呼出 (`call [reg+disp]`) の走査は `block24360` の `.text` 内だけで、他の PE では行っていない。呼出元の候補は未検証 (vtable を介した host 側の生成か、別の DLL)。確定には実行時 trace (FL 本体の起動と WC 呼出の計測) が要る |
| slot 1・4 の 5 番目 (stack 引数) の実値 | **未確認** | 上と同じ。逆アセンブルから「出力先ポインタ」と読めるが、実値は未取得 |
| 出力先 buffer の大きさ | **未確認** | native 実験では arena 内の 0x4000 以上を使った。実際に必要な長さは frame 数と呼出側の定義に依る |
| 旧 `REPORT_APPENDIX_3216.md` §7-5 の「slot 1 は this+0x20 が null」 | 誤りを確認 | 落ちる原因は `r8` (出力) の null。this+0x20 は関係しない |

## 6. 検証

- `lift_wc.sh all` (HEAD `c37267725`): ALL OK。本検査 PASS 64/64 (elapsed 1.61s)、ネガコン FAIL 64/64 (elapsed 1.57s)。load 0.22 0.28 0.21 (開始・終了とも)。
- 測定 commit を `d0480f2c1` に進めた。`c37267725` から `d0480f2c1` の差分は `slot_probe.sh` (run 行の追加のみ) で、lift 経路 (`x64c` / `wc_image.py` / `wc_cases.py` / `lift_wc.sh`) は変えていない。`lift_wc.sh` の結果は `c37267725` 時点のままで有効。
- `slot_probe.sh` の再実行は HEAD `d0480f2c1` で行い、§3 に貼った (exit 0・約 1.4 秒)。
- 素材: `fl-win64` (block24360_PE.bin) と `toolchain-emsdk` を `$RUNNER_TEMP` に展開して使った。

## 7. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| FL 本体の呼出側の実引数 (slot 1・4) の確定 | 受入条件 (呼出側から確定) の残り。native で動く前提は §4 のとおり | 本 issue の残件。実行時 trace は [T-SH-57] #3274 の gate に依る |
| slot 2 の `xmm1` (浮動小数) の入力の網羅 | slot 2 の完走条件の網羅性 | 親 #4169 への提案 (xmm1 を変えた入力の網羅は本 issue では行わない) |
