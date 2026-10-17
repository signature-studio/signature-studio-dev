# tools/flelift/boot — FLE-53 (#6219) 付録: obj+0xc4 (mode) の 0 の書込み元 (確保直後の 0 埋め)

> 親: `tools/flelift/boot/REPORT_APPENDIX_4287.md` (FLE-22 の受入 1 の残件)。前回 (§F・§G) の監視は確保内の store を
> 取りこぼしていた (宛先の一致判定が `obj+0xc4` で始まる store だけだった)。本付録は重なり判定に直して測り直した。
> 既知類型との関係: 該当なし (書込み元の特定のみ。類型の追加は行わない)。

## A. 結論

- `f_6ba1f0` の入口の `rbx` (`f_6cd520` の `rbx = rcx = obj`) は mode の設定元ではない。`f_6cd520` は mode を読むだけで、`f_6bc010` は読んだ値をそのまま書き戻す (自己コピー)。
- mode `[obj+0xc4]` を 0 にする store は **`0x40d300`** (`f_40d210` 内の `movaps xmmword [rcx+rdx], xmm0` の 16 byte ループ)。宛先 `0x12d7a150` (obj+0xc0) の 16 byte が 0 を書き、`obj+0xc4` を含む。戻り番地 `0x40fb63` は `f_40fb40` の `call 0x40d210` の直後。
- `f_40fb40` は `NewInstance` の初期化 (`f_40f960` → getmem `0x409410` → 初期化 `0x40fb40`) の一部で、確保直後・`f_6ba1f0` が obj を確定する (`0x6ba25b`) より前に走る。したがって mode の 0 は、確保した領域を初期化する lifted の 0 埋めが書いたものである。
- 観測した範囲で、obj+0xc4 に 0 以外の値を書く store は無い。mode は確保時の初期値 0 のまま。

## B. 測定 (工程と実測)

| 項目 | 値 |
|---|---|
| 測定 commit | `6e2c7ec49` (`wval_lift.py` の重なり判定。コードを変えた最後の commit) |
| 素材 | `fl-win64` / `toolchain-emsdk` を `$RUNNER_TEMP` に展開 (repo 外) |
| 診断 route (root 無し・`FLE_BOOT_RUNS=diag_shim`) | units_run **209** / `unlifted 0x6bbc20` / getmem 2314 / freemem 1200 (前回と同値) |
| 監視版 (診断 route・`WVAL_OBJWATCH=1`) | units_run **209** / 停止点同じ / getmem 2314 / freemem 1200 (差 0) |
| 監視版 (既定 route・`WVAL_OBJWATCH=1 WVAL_IPP= WVAL_NULLFILL=0`) | units_run **895** / `boot_threw: exit` (前回の既定経路と同じ。#4806 の IPP 判定は別件) |
| 監視の一致 (診断 route) | `[wobj]` 10 件: `0x40d300` (0 書込み・16 byte)・`0x6bc010` (0 書込み・1 byte)・`[wobj-set]` 1 件 (`0x6ba25b`)・`[wobj-getmem]` 2 件・`[wobj-free]` 多数 |
| 監視の一致 (既定 route) | `[wobj]` の書込みは 0 件 (`[wobj-free]` `[wobj-getmem]` のみ)。既定経路で `0x40d300` を通ったかは未確認 (`wval-enter` は `f_40fb40` を対象にしていない) |
| 監視の穴の修正 | 前回の判定は `a == obj+0xc4` (store の開始位置一致) だった。`a <= obj+0xc4 < a+n` に直した (`wval_lift.py`) |

KPI (起動に関わる PR): FLEngine 起動の units_run は **前 209 / 後 209** (診断 route)。既定 route は前 895 / 後 895。最初のウィンドウ: **無し**。ビルド・lift 経路は変えていない (監視は `--objwatch` の時だけ挿入)。

## C. 監視の出力 (診断 route・`6e2c7ec49`)

```
[wobj] va=0x40d300 a=0x12d7a150 n=16 v=0 obj=0 R0=0 R1=0xffffffffffffff90 R2=0x12d7a1c0 R3=0x6b80d8 R5=0x1159f528 ret=0x40fb63
[wobj-set] va=0x6ba25b obj=0x12d7a090
[wobj] va=0x6bc010 a=0x12d7a154 n=1 v=0 obj=0 R0=0x12d7af10 R1=0x12d7a090 R2=0 R3=0x12d7a090 R5=0x1159f5d8 ret=0x6cd5d6
[wval-mode] obj=0x12d7a090 dl=0 [obj+0x70]=0x20 [obj+0xc4]=0
```

- `obj=0` の表示は、`[wobj-set]` より前は obj が未確定のため (宛先の判定は固定値 `--fixobj 0x12d7a090` で行う)。
- `0x40d300` の戻り番地 `0x40fb63` は `f_40fb40` の `call 0x40d210` (`0x40fb5e`) の直後。`f_40d210` の引数は `rcx`=宛先・`rdx`=`movsxd [rdi-0x80]` の値 (サイズの出所は未確認)。
- `0x6bc010` の 0 は `f_6cd520` が `movzx rdx, [rbx+0xc4]` で読んだ値 (`0x6cd5c9`) をそのまま書き戻したもの。

## D. 限界

- 1 run・n=1。決定的な boot のため同一 commit の再実行は同値と見る。
- 既定 route では `0x40d300` は出ていない (boot が 895 units で `exit` する)。既定経路での mode の設定元は未測定 (#4806 の IPP 判定が先)。
- ホスト側 C (`fle_boot.c`・shimx・`rt/fle_glue.c`) の書込みは監視していない (前回 §E と同じ)。確保領域の getmem (FastMM) の 0 埋めの有無はホスト側のため見えていない。
- `f_40fb40` の呼出元 (`NewInstance` の段) の VA は本付録の対象外。

## E. 再現

```sh
FL_WIN64_DIR=<fl-win64 展開先> FLE_EXTRA_ROOTS= FLE_BOOT_WORK=<work> FLE_BOOT_TAG=diag6219 FLE_BOOT_RUNS=diag_shim bash tools/flelift/boot/fle6_measure.sh
FL_WIN64_DIR=<fl-win64 展開先> FLE_BOOT_WORK=<work> WVAL_OBJWATCH=1 bash tools/flelift/boot/wval_measure.sh
```

素材: `oc_artifacts: fl-win64 toolchain-emsdk`。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 既定 route (895 units) の mode の設定元 | 既定経路での obj の書込み方式 | #4806 (IPP 判定 NG の解消後に測る) |
| ホスト側 C・getmem (FastMM) の 0 埋め | 監視の網羅性 | 本付録 D (未監視の限界として残す) |
