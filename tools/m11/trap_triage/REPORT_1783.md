# #1783 (LD-63): m11 0x5ac308 (410320 の間接 call スロット) の書き込み元 — 途中報告

**判定: 受入条件 1・2 は未達。受入条件 3 は部分達成 (手順のスクリプトを commit、全 unit 完走は未実測)。`Refs #1783` (Closes しない)。**

親: #1588。前提の結論は `REPORT_1588.md` §4.5 を正とする (`0x5ac308` は実行時に書き換わり、静的参照 0 件)。

## 0. 検証環境

- 測定 base: `origin/main` `6e001233` (worktree `ws-1783`、branch `1783-m11-slot-5ac308-writer`)。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (6.2 s)。`work-m11` / `work-liftdiff` は repo 直下に展開 (gitignore)。`toolchain-emsdk` は `/opt/emsdk` で `emcc 6.0.12` を確認。
- 注意: `toolchain-emsdk` の `tar --zstd -xf ... -C /` は rc=2 だったが、`/opt/emsdk/emsdk_env.sh` と `emcc` は動作を確認した。展開先の差は未調査。
- `m11_gen_ir2.sh`: rc 0、34.7 s、`boot_final.ll` 490,733 行、`ldfix=applied`。`ir_conditions.json` を生成。
- `m11_build.sh`: rc 0、17.5 s、`wasm-ld signature mismatch: 0, undefined symbol: 0`。

## 1. 計装 (追加したもの)

- `tools/m11/trap_triage/store_watch_1783.sh`: `watch_store_682.py` の全 store 計装と、既存の `watch_addr_1046.c` (固定番地版) を流用する。監視番地は `M11_WATCH_1783` (既定 `0x1ac308` = wasm 側の `0x5ac308` に対応)。survey は `survey_units.mjs` を使う。
- 計装 IR は `boot_sw.ll` (54,041 store を計装)。IR の値と分岐は変えない。

## 2. 実測 (run1)

- `store_watch_1783.sh run1` を foreground で実行したが、survey が **unit 145 で打ち切られ完走しなかった** (run 上限 900 s の tool timeout)。
- `[aw]` 行 (書込み検出) は **0 件**。ただし unit 0〜145 の範囲のみで、全 942 unit を見ていない。0 件を「書込みなし」の根拠にしてはならない。
- 完走には survey の所要 (全 unit) を別 run で測る必要がある。本 run では所要時間を実測できていない。

## 3. 受入条件の判定

| # | 条件 | 判定 |
|---|---|---|
| 1 | `0x5ac308` へのストアを実行時に捕まえる (書込み命令アドレスと値を native / wasm で採取) | **未達**。wasm 側は計装済みだが完走せず。native 側の書込み捕捉方式は未実装 (`rt/ld_native.c` に store 監視は無い) |
| 2 | 書込み元関数と、両側で値が分かれる最初の地点を実測で記録 | **未達** |
| 3 | 手順を repo 内スクリプトで実行可能にし commit | **部分達成**。`store_watch_1783.sh` を commit。全 unit の完走は未確認 |

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| wasm 側の全 unit survey の完走と、`[aw]` の書込み元 (site → fn・IR 行) の特定 | 書込み元の一方の側が未確定 | 子 issue (本 PR 後に起票) |
| native 側の `0x5ac308` 書込み捕捉 (ld_native の store 監視が無い) | 両側の比較ができない | 本 issue #1783 の残り (子 issue に含める) |

## 5. 再現

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64
bash tools/m11/m11_gen_ir2.sh
bash tools/m11/m11_build.sh
bash tools/m11/trap_triage/store_watch_1783.sh run1   # 全 unit 完走まで要時間 (本 run では unit 145 で打ち切り)
```
