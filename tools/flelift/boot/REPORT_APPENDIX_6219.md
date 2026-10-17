# tools/flelift/boot — FLE-53 (#6219) 付録: obj+0xc4 (mode) の 0 の書込み元 (確保直後の 0 埋め)

> 親: `tools/flelift/boot/REPORT_APPENDIX_4287.md` (FLE-22 の受入 1 の残件)。前回 (§F・§G) の監視は確保内の store を
> 取りこぼしていた (宛先の一致判定が `obj+0xc4` で始まる store だけだった)。本付録は重なり判定に直して測り直した。
> 既知類型との関係: 該当なし (書込み元の特定のみ。類型の追加は行わない)。

## A. 結論

- `f_6ba1f0` の入口の `rbx` (`f_6cd520` の `rbx = rcx = obj`) は mode の設定元ではない。`f_6cd520` は mode を読むだけで、`f_6bc010` は読んだ値をそのまま書き戻す (自己コピー)。
- mode `[obj+0xc4]` を 0 にする store は **`0x40d300`** (`f_40d210` 内の `movaps xmmword [rcx+rdx], xmm0` の 16 byte ループ)。宛先 `0x12d7a150` (obj+0xc0) の 16 byte が 0 を書き、`obj+0xc4` を含む。戻り番地 `0x40fb63` は `f_40fb40` の `call 0x40d210` の直後。
- `f_40fb40` は `NewInstance` の初期化 (`f_40f960` → getmem `0x409410` → 初期化 `0x40fb40`) の一部で、確保直後・`f_6ba1f0` が obj を確定する (`0x6ba25b`) より前に走る。したがって mode の 0 は、確保した領域を初期化する lifted の 0 埋めが書いたものである。
- 観測した範囲で、obj+0xc4 に 0 以外の値を書く store は無い。mode は確保時の初期値 0 のまま。
- 受入の達成範囲: **診断 route (`FLE_EXTRA_ROOTS=`) で達成** (設定元 VA `0x40d300`・戻り `0x40fb63` を特定)。**既定 route は未達**: `f_6ba1f0` の入口 (`[wval-enter]`) に届かず、既定 route の設定元は測れていない (監視は n=1)。既定 route の設定元は #6220 に残す。このため PR 本文は `Refs #6219` (#6219 は merge 後も open のまま)。

## B. 測定 (工程と実測)

| 項目 | 値 |
|---|---|
| 測定 commit | **`a6a1af90e`** (本 PR の最終 HEAD)。既定 route (通常版・監視版) と診断 route (通常版・監視版) をすべて `a6a1af90e` で再測定した。`720ada7de` からの実行コードの差分は §B-diff (`fle_boot.c` の `wobj_hw_` と、main 取り込み (#6220) の `wval_lift.py` の rep hook・`fle_boot.mjs` の読出し)。`wval_lift.py` の重なり判定は `6e2c7ec49` から変えていない。`fle_boot.c` の監視 slot (#5415) は main 取り込みで入った計測のみの差分 |
| 素材 | `fl-win64` (`$ARTIFACTS_DIR`) / `toolchain-emsdk` (上流 `emsdk install 6.0.12`) を `$RUNNER_TEMP` に展開 (repo 外) |
| 診断 route (root 無し・`FLE_BOOT_RUNS=diag_shim`・`a6a1af90e`) | units_run **209** / `boot_threw: unlifted` (`0x6bbc20`) / getmem **2314** / freemem **1200** / `IPP_CHECK mode:1 ok:true`。n=2 (`fle6_measure.sh` 1 回 + 同じ C から boot を再実行 1 回。2 回とも同値) |
| 監視版 (診断 route・`WVAL_OBJWATCH=1`・`a6a1af90e`) | units_run **209** / 停止点同じ / getmem 2314 / freemem 1200 (通常版と同値)。`[wval]` 一致 **6 件**。n=1 |
| 既定 route 通常版 (`FLE_EXTRA_ROOTS` 未指定・root `0x6a7b70` 有・`a6a1af90e`) | units_run **895** / `boot_threw: exit` / `IPP_CHECK mode:3 ok:true` / getmem **3680** / freemem **1499**。`fle6_measure.sh`・`FLE_BOOT_RUNS=default` で 1 回 + 同じ C から boot 再実行 1 回 (2 回とも同値) |
| 既定 route 監視版 (`WVAL_OBJWATCH=1 WVAL_IPP= WVAL_NULLFILL=0`・`a6a1af90e`) | units_run **895** / `boot_threw: exit` / getmem 3680 / freemem 1499 (通常版と同値)。`fle6_measure.sh` (上の行と同じ lift) → `wval_measure.sh` の順。n=1 |
| 既定 route の過去測定 (`949ec634a`・`6e2c7ec49`) | 両方 units 895 / `boot_threw: exit`。`6e2c7ec49` は監視版 (`WVAL_OBJWATCH=1`) で測った記録。`949ec634a` は本文に `WVAL_OBJWATCH=1` の記載が無く、監視の有無は未確認 (`[wobj]` 0 件の根拠には使わない) |
| 監視の一致 (診断 route・`a6a1af90e`) | `[wobj]` **2 件**: `0x40d300` (0 書込み・16 byte)・`0x6bc010` (0 書込み・1 byte)。`[wobj-set]` 1 件 (`0x6ba25b`)・`[wobj-getmem]` 2 件・`[wobj-free]` 多数。`[wval-enter]` は `f_6ba1f0`・`f_6cd520`・`f_6bc010`・`f_6c9280` の 4 種すべて出る |
| 監視の一致 (既定 route・`a6a1af90e`・n=1) | `[wobj]` (lifted の store) は **0 件** (`grep -c '^\[wobj\] va='` = 0)。`0x40d300`・`0x6bc010` は出ていない。出たのは `[wobj-free]` 7 件・`[wobj-getmem]` 1 件 (`p=0x12d7a090 size=70 obj+0xc4=0 freed_before=0 freed_val=0` の 1 件のみ・obj が確定していないため)。`[wval-enter]`・`[wval-mode]`・`[wval-call]`・`[wobj-set]` は **0 件** (入口 `f_6ba1f0` / `f_6bc010` / `f_6cd520` / `f_6c9280` の入口フックに届いていない) |
| ホスト C の監視 (`[wobj-host]`・`wobj_hw_`) | 既定 route・診断 route とも **0 件**。`wobj_hw_` (ippsZero_8u 分岐・imp_memset) の範囲判定に obj+0xc4 を含む呼出しは無かった |
| 監視の穴の修正 | 前回の判定は `a == obj+0xc4` (store の開始位置一致) だった。`a <= obj+0xc4 < a+n` に直した (`wval_lift.py`) |

KPI (起動に関わる PR): FLEngine 起動の units_run は **前 209 / 後 209** (診断 route・`a6a1af90e` で再測定)。既定 route は **前 895 / 後 895** (`a6a1af90e` で再測定)。最初のウィンドウ: **無し**。既定 build の起動結果 (units・exit・getmem・freemem) は変わらない。`wobj_hw_` は読むだけで、範囲に入らなかった (`[wobj-host]` 0 件)。

## C. 監視の出力 (`a6a1af90e`・診断 route)

```
[wval-enter] fn=0x6ba1f0 ret=0x6cf0fc R1=0x6b80d8 R2=0xffffff01 R3=0x100000
[wobj] va=0x40d300 a=0x12d7a150 n=16 v=0 obj=0 R0=0 R1=0xffffffffffffff90 R2=0x12d7a1c0 R3=0x6b80d8 R5=0x1159f5c8 ret=0x40fb63
[wobj-set] va=0x6ba25b obj=0x12d7a090
[wval-enter] fn=0x6cd520 ret=0x6ba38f R1=0x12d7a090 R2=0x100000 R3=0x100000
[wval-enter] fn=0x6bc010 ret=0x6cd5d6 R1=0x12d7a090 R2=0 R3=0x12d7a090
[wval-mode] obj=0x12d7a090 dl=0 [obj+0x70]=0x20 [obj+0xc4]=0
[wobj] va=0x6bc010 a=0x12d7a154 n=1 v=0 obj=0 R0=0x12d7af10 R1=0x12d7a090 R2=0 R3=0x12d7a090 R5=0x1159f678 ret=0x6cd5d6
[wval-enter] fn=0x6c9280 ret=0x815bc7 R1=0x12d7a090 R2=0x1159f9d4 R3=0x100000
```

- `obj=0` の表示は、`[wobj-set]` より前は obj が未確定のため (宛先の判定は固定値 `--fixobj 0x12d7a090` で行う)。
- `0x40d300` の戻り番地 `0x40fb63` は `f_40fb40` の `call 0x40d210` (`0x40fb5e`) の直後。`f_40d210` の引数は `rcx`=宛先・`rdx`=`movsxd [rdi-0x80]` の値 (サイズの出所は未確認)。
- `0x6bc010` の 0 は `f_6cd520` が `movzx rdx, [rbx+0xc4]` で読んだ値 (`0x6cd5c9`) をそのまま書き戻したもの。

## D. 限界

- 既定 route は `a6a1af90e` で通常版と監視版をそれぞれ測った (units 895 / `[wobj]` 0 件 / 入口フック 0 件)。boot の再実行 (n=2) は通常版のみ。監視版は n=1。過去の `6e2c7ec49` (監視版) と `949ec634a` (監視の有無は未確認) の 895 は同値。
- lift は各 route で 1 回ぶんしか測っていない (lift の再現性は未測定)。診断 route の n=2 は同じ C から boot だけを再実行したもの。
- 既定 route では `0x40d300` は出ていない。ただし既定 route は `f_6ba1f0` の入口 (`[wval-enter]`) にも届いていない (`[wval-enter]` 0 件) ため、「既定 route で `f_6cd520` / `0x6bc010` に届いていない」ことの根拠は、入口フックの 0 件 (`run_wval_default_6219.log`) である。`f_40fb40` の入口は `wval_lift.py` の `ENTER_FN` 対象外のため、既定 route で `f_40fb40` / `0x40d300` に届いたかは、この測定では判定できない (monitor の対象外)。既定経路での mode の設定元は未測定 (#4806 の IPP 判定が先)。
- ホスト側 C の書込みは `wobj_hw_` で memset 系 (`imp_memset`・`ippsZero_8u`) だけを見ている。FastMM の getmem 0 埋め・他の C 関数の書込みは見ていない (前回 §E と同じ)。既定 route・診断 route とも `[wobj-host]` は 0 件。
- `f_40fb40` の呼出元 (`NewInstance` の段) の VA は本付録の対象外。

## E. 再現

```sh
FL_WIN64_DIR=<fl-win64 展開先> FLE_EXTRA_ROOTS= FLE_BOOT_WORK=<work> FLE_BOOT_TAG=diag6219 FLE_BOOT_RUNS=diag_shim bash tools/flelift/boot/fle6_measure.sh
FL_WIN64_DIR=<fl-win64 展開先> FLE_BOOT_WORK=<work> WVAL_OBJWATCH=1 bash tools/flelift/boot/wval_measure.sh
```

既定 route (§B の表と同じ条件・既定 root `0x6a7b70` 有の lift):

```sh
FL_WIN64_DIR=<fl-win64 展開先> FLE_BOOT_WORK=<work> bash tools/flelift/boot/fle6_measure.sh
FL_WIN64_DIR=<fl-win64 展開先> FLE_BOOT_WORK=<work> WVAL_OBJWATCH=1 WVAL_IPP= WVAL_NULLFILL=0 bash tools/flelift/boot/wval_measure.sh
```

素材: `oc_artifacts: fl-win64 toolchain-emsdk`。`toolchain-emsdk` は上流から `git clone --depth 1 https://github.com/emscripten-core/emsdk.git` → `./emsdk install 6.0.12` → `./emsdk activate 6.0.12` で得て `SS_EMSDK_ENV` に指定する (REFERENCES `toolchain-emsdk`)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 既定 route (895 units) の mode の設定元 | 既定経路での obj の書込み方式 | #6220 (親 #4287 の残件・受入 2。既定 route で `f_6ba1f0` の入口に届かない (§B) ため、設定元の測り方から見直す) |
| ホスト側 C・getmem (FastMM) の 0 埋め | 監視の網羅性 | 本付録 D (未監視の限界として残す) |
