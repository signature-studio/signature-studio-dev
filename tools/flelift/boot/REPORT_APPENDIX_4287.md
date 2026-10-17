# tools/flelift/boot — FLE-22 (#4287) 付録: f_6cd520 の mode (obj+0xc4) の設定元

> 親 REPORT: `tools/flelift/boot/REPORT.md`。前提の付録 `REPORT_APPENDIX_3868.md` は main に無いため、本付録は `REPORT_APPENDIX_3771.md` §C〜§G の監視 (`wval_lift.py`) を土台にした。
> 既知類型との関係: 該当なし (書込み元の特定のみ。類型の追加は行わない)。

## A. 結論 (部分達成)

- `f_6ba1f0` 内で `rbx` (R[3]) は**書かれない** (入口の push と出口の pop のみ)。issue 本文の「`f_6ba1f0` 内の `rbx`」は、実際には `f_6cd520` 入口の `rbx = rcx` (`0x6cd527`) の出所を指す。
- `f_6cd520` の rcx (= obj) は、`f_6ba1f0` の `0x6ba38a` 直前の `mov rcx, [rbp+0xe0]` で決まる。`[rbp+0xe0]` は入口の rcx (`0x6ba202`) と、`f_410320` の戻り値 (`0x6ba254`) で書かれる。実測の obj は `0x12d6a090` (両 route 同じ)。
- obj+0xc4 への store は、監視範囲 (lifted C の全幅 store・宛先一致) で **`f_6bc010` の `0x6bc010` 1 件だけ** (`mov byte [rcx+0xc4], dl`)。その値は `dl = 0`。
- つまり `f_6cd520` が読む時点で mode は既に **0** で、その 0 を書いた lifted の store は無い。0 の出所 (obj の確保時の 0 埋め・ホスト C の書込み・未監視の store のいずれか) は**未特定**。受入条件 1 は未達。

## B. 測定 (工程と実測)

| 項目 | 値 |
|---|---|
| 測定 commit | `a49255dc0` (監視の追加を含み、コードを変えた最後の commit) |
| base | `e3f55dc40` (main 上の commit。監視の追加は含まない) |
| 素材 | `fl-win64` / `toolchain-emsdk` を `$RUNNER_TEMP/ss4287` に展開 (repo 外) |
| baseline (root `0x6a7b70` 無) | units_run **209** / stopped_at 209 / `unlifted 0x6bbc20` (REPORT_APPENDIX_3771 §B と同値) |
| 監視版 (`WVAL_OBJWATCH=1`) | units_run **209** / 停止点 同じ / `[wval]` 1 件 (0x6bbc20) / `[wobj]` 1 件 (obj+0xc4 への store) |
| 既定経路 (root `0x6a7b70` 有) | units_run **209** / `boot_threw: "exit"` / `px6bbc20.calls_all` 0 / rc=3 (IPP チェック NG)。baseline と停止の仕方が異なる |
| 既定経路の監視版 | 同じ連鎖: `f_6cd520` で mode=0・`f_6bc010` が `[obj+0xc4]=0` を書く。`0x6bbc20` への store は 0 件 |

KPI (起動に関わる PR): FLEngine 起動の units_run は **前 209 / 後 209**。最初のウィンドウ: **無し**。既定の build・lift 経路は変えていない (監視は `--objwatch` の時だけ挿入)。

## C. 監視の出力 (baseline 系・`run_wval.log` 抜粋)

```
[wobj-enter] va=0x6ba1f0 rcx=0x6b80d8 dl=0xffffff01 ret=0x6cf0fc
[wobj-set] va=0x6ba25b obj=0x12d6a090
[wobj-enter] va=0x6cd520 rcx=0x12d6a090 dl=0x100000 ret=0x6ba38f
[wobj-read] va=0x6cd520 obj=0x12d6a090 mode(+0xc4)=0 0x70=0
[wobj] va=0x6bc010 a=0x12d6a154 n=1 v=0 obj=0x12d6a090 R0=0x12d6af10 R1=0x12d6a090 R2=0 R3=0x12d6a090 R5=0x1158b468 ret=0x6cd5d6
```

- `[wobj]` の `a = 0x12d6a154 = obj+0xc4` (一致)。`ret=0x6cd5d6` は `f_6cd520` の `call 0x6bc010` の戻り番地。
- `[wobj-read]` の `mode=0` は、`f_6cd520` 入口 (`0x6cd520`) の時点で obj+0xc4 が 0 であることを示す。

## D. 監視の仕組み・限界

- `wval_lift.py --objwatch`: lifted C の全 store (ST8〜STY) を `WO_*` に置換し、宛先が `obj+0xc4` に一致したものを出す。値の比較はしない (1/2/4/8/16 byte 全て)。obj は `f_6cd520` 入口 (`rcx`) と、`f_6ba1f0` の `L_6ba25b` 直後で `[rbp+0xe0]` から更新する。`rt/` と `x64c.py` は変えない。
- 限界 (未観測): (1) ホスト側 C (`fle_boot.c`・shimx・`rt/fle_glue.c`) からの書込み。(2) `f_410320` と getmem の 0 埋め (lifted 外・ホスト側のため見えない)。(3) obj の確保が `f_6ba1f0` の前にあるかの確認。
- 1 run・n=1。決定的な boot のため同一 commit の再実行は同値と見る。

## E. 再現

```sh
FL_WIN64_DIR=<fl-win64 展開先> FLE_EXTRA_ROOTS= FLE_BOOT_WORK=<work> FLE_BOOT_TAG=wv0 FLE_BOOT_RUNS=diag_shim bash tools/flelift/boot/fle6_measure.sh
FL_WIN64_DIR=<fl-win64 展開先> FLE_BOOT_WORK=<work> WVAL_OBJWATCH=1 bash tools/flelift/boot/wval_measure.sh
```

- 注意: `wval_measure.sh` の既定 `WVAL_FIXOBJ` は `0x12d7a090` (§G で更新)。§A〜§F の `0x12d6a090` の結果を再現するには `WVAL_FIXOBJ=0x12d6a090` を付ける。

素材: `oc_artifacts: fl-win64 toolchain-emsdk`。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| obj+0xc4 の初期値 0 の出所 (確保時の 0 埋め・ホスト C の書込み) | mode の設定元の確定 (受入条件 1) | #4287 (本 issue・部分達成のため残す) |
| `f_6cd5f0` 経由の `f_6cd520` 呼出し (実行時の呼出元) | 呼出し連鎖の上流 | #4287 |
| 既定経路で boot が `exit` で止まる原因 (IPP 判定 NG) | 既定経路の書込み元の比較 | #4806 (本 PR では扱わない。#3868 は CLOSED で IPP 判定は扱っていない) |

## F. 追補 (FLE-22 再実行): 確保内の store と getmem の戻り値

- 監視の穴: `wo_obj_` は `f_6ba1f0` の `L_6ba25b` (確保の後) で初めて設定されるため、確保内 (`f_410320` → 仮想 NewInstance `0x40f960` → `getmem` `0x409410` → 初期化 `0x40fb40`) の store は見えていなかった。固定値 `--fixobj 0x12d6a090` (前回実測の obj) で確保内も監視した。
- 結果: 確保内を含めても `obj+0xc4` への lifted の store は `f_6bc010` の `0x6bc010` **1 件** (`v=0`) のみ。確保・初期化の区間で 0 を書く lifted の store は無い。
- `fle_ov_getmem` の戻り時の実測 (`fle_boot.c` の `[wobj-getmem]`、obj を含む確保のみ出力): `p=0x12d6a090 size=320 obj+0xc4=0`。`size=70` の行は `+0xc4` が確保領域の外なので参照値にならない。
- 判断: obj の mode の 0 は、lifted の store ではなく **host の getmem (FastMM) が返した領域の初期値** に由来する見込み。ただし「FastMM が 0 埋めしたのか、解放済みの 0 の領域の再利用か」は、確保前の値を測っていないため未確定。
- 受入条件 1 (設定元の VA) は、lifted コード内の VA としては特定できない (設定元はホスト側の getmem)。部分達成。

## G. 追補 (FLE-22 3 回目): 解放・再確保の前後の値

- 前提の修正: main が進んで obj は `0x12d7a090` (前回の `0x12d6a090` から変化)。診断の固定値と `wval_lift.py --fixobj` の既定値を `0x12d7a090` に合わせた。
- 追跡表 (`BLKDIAG_MAX`=768) は序盤で飽和し、以降の解放は `NOT TRACKED` になる。このため解放の判定は表に依らず、obj を含みうる近傍 (`fp <= obj < fp+0x1000`) の解放で記録する (`[wobj-free]`)。
- 結果 (commit `d8420c54d`・diag_shim):
  - `[wobj-free] p=0x12d7a090 obj+0xc4=0` が 3 回 (seq 2297・2307・2308)。解放時点で obj+0xc4 は常に 0。
  - 再確保 `[wobj-getmem] p=0x12d7a090 size=320 obj+0xc4=0 freed_before=1 freed_val=0`。解放済み領域の再利用である。
  - 以降 `[wobj] va=0x6bc010 ... v=0` の 1 件のみ (lifted の store は 0 を書く 1 件のみ)。
- 既定経路 (root 0x6a7b70 有・`WVAL_IPP= WVAL_NULLFILL=0`): `boot_threw: exit`・`px6bbc20.calls_all` 0。`[wobj-free]`・`[wobj-getmem]` は出るが、`0x6bc010` の store は出ない。「同じ連鎖」とは書けない (`f_6cd520` 系の入口に届いたかの確認が無かったため)。訂正は `REPORT_APPENDIX_6219.md` §B・§D (既定 route の入口 0 件)。
- 結論: obj+0xc4 の 0 は、解放時点の値が既に 0 の領域を再利用した結果。**0 がどこで最初に書かれたか (最初の確保時の 0 埋めか、ホスト C の書込みか) は、解放・確保の区間の観測では特定できない**。最初の確保 (解放より前) の値は本測定の対象外。
- 診断の入り方: `fle_boot.c` の `fle_ov_getmem` (`[wobj-getmem]`) と `fle_ov_freemem` (`[wobj-free]`) は既定 build にも入る (`boot_e2e.sh` は全 variant で同じ `fle_boot.c` を cc する)。環境変数による分岐は無い。obj を含む範囲に当たったときだけ stderr に出る。制御フローは変えていない (記録変数の更新と出力のみ)。
- KPI: FLEngine 起動 units 前 209 / 後 209 (baseline・既定)。最初のウィンドウ: 無し。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 最初の確保時の obj+0xc4 の値 (0 埋めか未初期化の 0 か) | 受入条件 1 の確定 | #4287 |
| 既定経路で boot が `exit` で止まる原因 (IPP 判定 NG) | 既定経路の比較 | #4806 |
