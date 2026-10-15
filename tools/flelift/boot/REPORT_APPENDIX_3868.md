# tools/flelift/boot — FLE-17 (#3868) 付録: 0x6bbc20 の書込み経路の上流

> 親: `tools/flelift/boot/REPORT_APPENDIX_3771.md` (FLE-16)。本付録は #3868 の測定の全文。
> 既知類型との関係: 該当なし (`docs/DEFECTS.md` D1a〜D23 を照合。上流の特定のみ)。

## A. 結論

- **実行時の呼出し連鎖 (診断 route・実測)**: `f_6ba1f0` (戻り `0x6cf0fc`) → `f_6cd520` (呼出元 `0x6ba38f`・`f_6ba1f0` 内) → `f_6bc010` (戻り `0x6cd5d6`) → 書込み `0x6bc1af`。`f_6ba1f0` より上の段と、`f_6cd5f0` の実行時の有無は未計測 (入口フックを張っていない)。
- **既定経路 (root `0x6a7b70` 有) でも同じ書込み `0x6bc1af` が起きる** (同じ obj `0x12d6a090`・`dl=0`・`[obj+0x70]=0x20`)。既定経路は `exit` で停止し、`[obj+0x118]` の呼出しには届かない。
- **0x6bbc20 を指す参照の静的走査**: rip 相対 `lea` が 1 件 (`0x6bc1a8`)。`call 0x6bbc20` の直接呼出しが 3 件 (`0x7ae52a`・`0x7aeaa7`・`0x10312ac`。実行は未確認)。
- **未解決**: `[obj+0xc4]` (mode) の設定元。`f_6cd520` は `movzx rdx,[rbx+0xc4]` で mode を読むため、`rbx` の出所 (`f_6ba1f0` 内) の追跡が要る。今回の実測では mode は `0` (入口の `dl`)。

## B. 測定 (工程と実測)

| 項目 | 値 |
|---|---|
| 測定 commit | 基底 `origin/main` e3f55dc40 (rebase 後の基底)。コード変更は `tools/flelift/boot/wval_lift.py`・`wval_measure.sh`・`wval_scan_3868.py` のみ (rt/・x64c.py・lift/build 経路は不変)。HEAD の測定 commit は最終節 H |
| 既定 route | `FL_WIN64_DIR=<fl-win64> FLE_BOOT_WORK=<work> FLE_BOOT_TAG=def FLE_BOOT_RUNS=default bash tools/flelift/boot/fle6_measure.sh` → units_run **209** / stopped_at 209 / `boot_threw: exit` / getmem **1891** / freemem **776** / ipp_ok なし (exit 1) |
| 診断 route (ベースライン) | `FLE_EXTRA_ROOTS= FLE_BOOT_RUNS=diag_shim fle6_measure.sh` → units_run **209** / `unlifted 0x6bbc20` / getmem 2314 / freemem 1200 |
| 監視版 (診断 route) | `wval_measure.sh` → units_run **209** / 停止点 同じ / getmem 2314 / freemem 1200 (差 0) |
| 監視版 (既定 route) | `WVAL_IPP= WVAL_NULLFILL=0 wval_measure.sh` → units_run **209** / `boot_threw: exit`。書込み `0x6bc1af` は 1 件 |
| ネガコン (`WVAL_VALUE=0x6bbc21`) | `[wval]` 一致 **0 件** / `[wval-call]` 0 件 |
| 静的走査 | `FL_WIN64_DIR=<fl-win64> python3 boot/wval_scan_3868.py` → 命令 5,022,299 / rip 相対 1 件 / 即値 3 件 (全て direct call) |

KPI (起動に関わる PR): FLEngine 起動の units_run は **前 209 / 後 209**。最初のウィンドウ: **無し** (診断 route は `unlifted 0x6bbc20`、既定 route は `exit`)。ビルド・lift 経路は変えていない。

## C. 実行時の呼出し連鎖 (監視版・`run_wval.log` 抜粋・診断 route)

```
[wval-enter] fn=0x6ba1f0 ret=0x6cf0fc R1=0x6b80d8 R2=0xffffff01 R3=0x100000
[wval-enter] fn=0x6cd520 ret=0x6ba38f R1=0x12d6a090 R2=0x100000 R3=0x100000
[wval-enter] fn=0x6bc010 ret=0x6cd5d6 R1=0x12d6a090 R2=0 R3=0x12d6a090
[wval-mode] obj=0x12d6a090 dl=0 [obj+0x70]=0x20 [obj+0xc4]=0
[wval] va=0x6bc1af a=0x12d6a1a8 n=8 v=0x6bbc20 ... ret=0x6cd5d6
[wval-enter] fn=0x6c9280 ret=0x815bc7 R1=0x12d6a090 R2=0x1158b784 R3=0x100000
[wval-call] va=0x6c937a target=0x6bbc20 R1=0x12d6a090 R3=0x12d6a090 R5=0x1158b4f8
```

- 戻り番地は store 時点と入口の `[RSP]`。`0x6ba38f` は `f_6ba1f0` の中 (lift 出力 `fle_lifted_s3.c` の `f_6cd520();` 呼出し)。
- `f_6cd520` の入口 `R2=0x100000` は `f_6ba1f0` が渡した値。`f_6bc010` の入口 `dl=0`。

## D. 静的走査 (受入条件 4)

- `gen_boot.py` の `.text` 走査 (root 候補) は qword 値を 8 byte 単位で見る。`0x6bc1a8` の `lea` (命令内の rip 相対) を拾えない型の走査だと、コード上から読み取れる。ただし見落としの正確な機構は未検証 (走査条件の修正の要否は未判定)。
- `wval_scan_3868.py` は capstone で `.text` を逆アセンブルし、rip 相対の memory operand と即値の両方を見る。`0x6bc1a8: lea rax,[rip-0x58f]` を検出。
- `REPORT_APPENDIX_3771.md` §D の「PE 内の rip 相対 lea に 0x6bbc20 は無い」は誤り (本付録で訂正)。

## E. 監視の範囲 (受入条件 3・5)

- **ST8・ST16 (受入条件 5)**: 値比較付きに変更した (`wv_chk_` の `n < 4` 分岐で、下位 n byte を監視値の下位 n byte と比較)。診断 route の実測: 1 byte 19 件・2 byte 0 件・8 byte 1 件 (`0x6bc1af`)。1 byte の一致 19 件は全て低位 1 byte が `0x20` の一致で、宛先は `0x15e6a3c`〜`0x15e6a4d`・`0x65efa2`・`0x15f43f8` (`obj+0x118` = `0x12d6a1a8` ではない)。narrow store は 8 byte の値の書込みを示せないため、一致は雑音として扱う。
- **ホスト側 C (受入条件 3)**: **未監視のまま残す**。理由: 監視は lift 出力の store 文にだけ挿入する仕組み (`wval_lift.py`)。`fle_boot.c`・shimx・`rt/fle_glue.c` は lift 対象外で、同じ仕組みでは覆えない。覆うには C 側へ別の hook が要り、`rt/` を変えずに済ませる範囲を超える。今回の 1 件は lifted C 側の store。

## F. 検証範囲と限界

- 範囲内: 診断 route と既定 route の lifted C の store (`ST8`・`ST16`・`ST32`・`ST64`・`STF32`・`STF64`・`STX`・`STY`) と間接呼出し・関数入口。
- 範囲外: ホスト側 C の書込み (E)。`[obj+0xc4]` の設定元 (A の未解決)。`f_6ba1f0` より上の段 (未フック)。
- 入口の `[obj+0xc4]=0` は `f_6bc010` が `[obj+0xc4]` を書く前の値。`dl=0` と同値。書込み後の mode は未記録。

## H. 測定 commit と差分

- 測定 commit (コードを変えた最後の commit): `ea21f4f5b`。以後の commit は REPORT・DOC_MAP のみ。
- 既定 route の監視版 (表 B の行) は、ST8/ST16 の値比較を入れる前の `wval_lift.py` で測った (store `0x6bc1af` の 8 byte 一致の結果は同じ。narrow store の件数は未測定)。診断 route の全表は `ea21f4f5b` で再測定済み。
- `git diff ea21f4f5b HEAD -- tools/flelift/boot/wval_lift.py tools/flelift/boot/wval_measure.sh tools/flelift/boot/wval_scan_3868.py` は出力なし (差分 0)。
- 1 run・n=1。決定的な boot のため同一 commit の再実行は同値と見る。

## G. 再現

```sh
FL_WIN64_DIR=<fl-win64 展開先> FLE_BOOT_WORK=<work> bash tools/flelift/boot/wval_measure.sh                       # 診断 route (0x6bbc20)
FL_WIN64_DIR=<fl-win64 展開先> FLE_BOOT_WORK=<work> WVAL_IPP= WVAL_NULLFILL=0 bash tools/flelift/boot/wval_measure.sh  # 既定 route
FL_WIN64_DIR=<fl-win64 展開先> FLE_BOOT_WORK=<work> WVAL_VALUE=0x6bbc21 bash tools/flelift/boot/wval_measure.sh   # ネガコン
FL_WIN64_DIR=<fl-win64 展開先> python3 tools/flelift/boot/wval_scan_3868.py                                         # 静的走査
```

素材: `oc_artifacts: fl-win64 toolchain-emsdk`。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `[obj+0xc4]` (mode) の設定元 (`f_6ba1f0` 内の `rbx` の出所) | obj の書込み方式の決まり方 | 子 issue (本 PR で起票) |
| ホスト側 C の書込みは未監視 | 監視の網羅性 | 本付録 E (未監視の限界として残す) |
| `call 0x6bbc20` の direct 呼出し 3 件 (`0x7ae52a`・`0x7aeaa7`・`0x10312ac`) の実行時の到達 | 0x6bbc20 の別経路の有無 | 本付録 A (未測定) |
| 本修復 (buf = 0 の上流原因) | 範囲外 | #3112 (既存) |
