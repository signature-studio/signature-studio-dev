# tools/flelift/boot — #6220 付録: obj+0xc4 の 0 の最初の書込み元の探索 (FLE-53)

> 親 REPORT: `tools/flelift/boot/REPORT.md`。前提: `REPORT_APPENDIX_4287.md` §A〜§G (`f_6cd520` の mode の設定元)。
> 既知類型との関係: 該当なし (書込み元の探索のみ。類型の追加は行わない)。

## A. 結論 (部分達成・受入 1 は VA を特定できず・受入 2 は未確認)

- 観測範囲 (下表の 4 経路) で、obj+0xc4 (= `f_6cd520` が読む mode) への **書込みは `f_6bc010` の `0x6bc010` 1 件 (`v=0`) だけ**。
- 確保・初期化・解放・再確保の区間で obj+0xc4 に書く者は、観測範囲に **1 件も無い**。最初の確保 (`size=70` の `[wobj-getmem]`) の時点で既に 0。
- よって「mode の設定元の VA」は lifted のコード内に存在しない (0 は書かれず、未書込みの領域が 0 のまま使われる)。受入 1 の「VA の特定」は達成できない。
- 受入 2 (既定経路で同じ設定元か) は、既定経路 (`FLE_IPP` 未指定) が **units 895** で `f_6ba1f0` に入らず、§G の経路 (units 209) と条件が違うため、同一性を確かめられなかった。

## B. 測定 (工程と実測)

| 項目 | 値 |
|---|---|
| 測定 commit | `2dd69b94b` (main 取り込み merge。コードを変えた最後の commit。`git diff 2dd69b94b HEAD -- tools/flelift/boot` の `.c`・`.py`・`.sh` は空) |
| base | `ca8500c7b` (origin/main。取り込み元。#5415 の `py_watch(9, ...)` と `InitContext.InitTable` の slot を含む) |
| 素材 | `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開。`toolchain-emsdk` は `$HOME/artifacts` に無いため、上流 emsdk 6.0.12 を REFERENCES §4 の手順で `$RUNNER_TEMP/emsdk-src` に取得 (repo 外) |
| 工程 (diag_shim・既存 `fle6_measure.sh`・HEAD 再測定) | 全体 2 分 57 秒: lift 69 s / clang 80 s / boot 21 s。開始時 load 1.16 |
| 監視版 build (`wval_measure.sh`・`WVAL_OBJWATCH=1`・HEAD 再測定) | build 75 s / 全体 1 分 39 秒。`[wobj]` 9 件 (うち `[wobj]` の書込み 1 件、他は確保・解放の観測) |
| diag_shim (既定 `FLE_IPP=1` の監視版) | units_run **209** / stopped_at 209 / `unlifted`・`[wobj]` 1 件 (`v=0`)・`[wval]` 6 件 |
| 既定経路 (`FLE_IPP` 未指定・root `0x6a7b70` 有・HEAD 再測定) | units_run **895** / `boot_threw: exit` / `[wval]` 0 件 / `[wobj-enter]`・`[wobj-set]` 0 件 (`f_6ba1f0` 未到達)。`[wobj-free]`・`[wobj-getmem]` のみ 8 件 |

- 取り込み元 (#5415) の `py_watch` 追加で、diag_shim の `py_events` は 6 → 20 件に増えた (`results/boot_summary_wv0_diag_shim.json`)。units 209 と `[wobj]` 1 件 (`v=0`) は前回 (`b08e776d9`) の値と一致した。
- 既定経路の結果は `results/boot_summary_def0_default.json`。

KPI (起動に関わる PR): FLEngine 起動 units は **前 209 / 後 209** (diag_shim・監視版と同値)。既定経路は 895 のまま変わらず。最初のウィンドウ: **無し** (boot は `exit` / `unlifted` で止まる)。既定の build・lift 経路は変えていない (監視は `--objwatch` と診断出力だけ)。

## C. 観測範囲と結果 (diag_shim・obj = 0x12d7a090)

| 経路 | 監視の入り | 結果 |
|---|---|---|
| lifted の ST8〜STY (store) | `wo_chk_` (宛先一致) | `f_6bc010` の `0x6bc010` 1 件 (`v=0`・`obj=0x12d7a154`) のみ |
| lifted の `rep movs*` (memmove) | `wo_rep_` (宛先範囲 `[d, d+n*sz)` の一致) | 0 件 (本 PR で追加。前回の監視の穴) |
| lifted の `rep stos*` | ST64 のループ (既存の store 監視で拾う) | 0 件 |

- `rep stos` の根拠: 生成 C では `rep stosq` は `ST64(d0_ + k_ * 8, R[RAX])` のループに展開される (`fle_lifted_s*.c`・43 箇所を実測)。`wval_lift.py` の `REP_HOOK` は `memmove` の行にだけ当てるので、`rep stos` は `WO_ST64` の既存の store 監視が拾う。
| ホスト `imp_memset` (`fle_boot.c`) | `wobj_hw_` | 0 件 (本 PR で追加) |
| ホスト `ippsZero_8u` の memset | `wobj_hw_` | 0 件 (本 PR で追加) |
| 確保 (`fle_ov_getmem`) | `[wobj-getmem]` | `size=70` と `size=320` の両方で `obj+0xc4=0` |
| 解放 (`fle_ov_freemem`) | `[wobj-free]` | 解放時は常に 0 (5 回) |

- 確保の時点の値は、`size=70` (初回) で既に `obj+0xc4=0`、`size=320` (`freed_before=1`・解放済みの 0 の領域の再利用) でも 0。
- 観測の限界: ホストの `VirtualAlloc` (`imp_VirtualAlloc`) と FastMM 内部の `getmem` 本体は、lifted の store と memset 以外の書込みを観測しない。wasm のメモリは未書込み領域が 0 で初期化されるため、「0 の最初の書込み」が存在しない可能性がある (未確定)。

## D. 再現

```sh
FL_WIN64_DIR=<fl-win64 展開先> FLE_EXTRA_ROOTS= FLE_BOOT_WORK=<work> FLE_BOOT_TAG=wv0 FLE_BOOT_RUNS=diag_shim bash tools/flelift/boot/fle6_measure.sh
FL_WIN64_DIR=<fl-win64 展開先> FLE_BOOT_WORK=<work> WVAL_OBJWATCH=1 bash tools/flelift/boot/wval_measure.sh
```

- 既定経路の比較 (`FLE_IPP` 未指定) は `FLE_BOOT_RUNS=default` (units 895) と `WVAL_IPP= WVAL_NULLFILL=0` の組合せ。§G の units 209 とは条件が異なる。
- 素材: `oc_artifacts: fl-win64 toolchain-emsdk`。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0 の最初の書込み元 (観測範囲に無い・wasm の未書込み 0 か) | 受入 1 の確定 | #6220 (部分達成のため残す) |
| 既定経路 (units 895) で `f_6ba1f0` に入らない理由 | 受入 2 (同一性) | #6220 |
