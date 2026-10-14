# tools/flelift/boot — REPORT 付録 (PERF-P14 #970: boot closure の variant 別 build と実行時間)

> 正本: この付録 (測定値)。`REPORT.md` §0 の 1 行から参照する。親 #672 の PERF-P14 (元 #168 PERF-P9 の残件 ④ の boot 連鎖側)。

## A. 結論

- boot closure (FLE-6 shim 経路・lift closure 2・root `0x6a7b70`) を **-O0 / -O2 / -O2 -flto** の 3 変種で build し、wasm bytes・build 所要時間・node 実行時間 (n=10) を実測した。
- **3 変種とも boot の出力署名は一致** (`dff527aaafbcb7ac`)。units_run 209・GetMem 2,314 / FreeMem 1,199・va_bytes 15,470,544 も一致。
- 実行時間は **-O0 p50 24.65 s → -O2 p50 3.6 s** (約 1/7)。-O2 -flto は -O2 と同じ 3.6 s で、LTO による差は見えない (n=10 の範囲で差 0.1 s 以内)。
- 署名は boot の状態 (`boot` と `ipp` の JSON 正規化 sha256 の先頭 16 桁) で、出力メモリ全体の比較ではない。最初のウィンドウは未達 (unit 209 の後の `MessageBoxA` → `exit(0)`、#3060) のため、描画の同一性は未確認。

## B. 測定条件

- 同一 lift 産物を全変種で共有: `fle6_measure.sh` の lift (closure 2・root `0x6a7b70`・cap 13800MB) = 29,908 関数 / 1,557,903 insn / peak 610MB / 76 s。
- 8 shard (`FLE_SHARDS=8`) の C を変種ごとに `build.sh` で `emcc -c` → link。link の変種は `FLE_CC_OPT` で与えた最適化と同じ。
- -O0 は `fle6_measure.sh` の既定 (`FLE_CC_JOBS=3`・shard cap 5000MB)。-O2 / -O2 -flto は `FLE_CC_JOBS=2` (ピーク RSS を抑える)・shard cap 6000MB。
- -O2 -flto の build 全体は `rss_cap.py` で cap 12000MB (木全体) を監視。
- 実行: `FLE_IPP=1 node fle_boot.mjs <cjs> <json> --boot-only` を n=10。壁時計は node 起動・wasm (60〜127MB) のコンパイル・boot を含む (boot 本体だけの時間ではない)。p90 は線形補間。

## C. 実測値

### C-1. build (wasm bytes・所要時間・ピーク RSS)

| 変種 | wasm (B) | build 壁時計 (s) | ピーク RSS | 備考 |
|---|--:|--:|--:|---|
| -O0 (`plain`) | 127,079,338 | 72 | shard 8 本: 2,198〜2,668 MB | `fle6_measure.sh` の `clang-plain` 工程 (shard + 他 TU + link) |
| -O2 | 64,682,372 | 270 | shard 8 本: 1,298〜1,690 MB | |
| -O2 -flto | 62,604,179 | 652 | 木全体 8,200 MB (LTO link 段) | shard は bitcode (`-flto`) |

link の検査: 3 変種とも `mismatch 0 / undefined 0 / duplicate 0`。

### C-2. 実行時間と署名 (node・`--boot-only`・n=10)

| 変種 | p50 (s) | p90 (s) | min–max (s) | units_run | 署名 | `FLEBOOT_IPP_CHECK` |
|---|--:|--:|--:|--:|---|---|
| -O0 | 24.65 | 25.55 | 23.9–26.0 | 209 | `dff527aaafbcb7ac` | NG (rc 3・既知。REPORT §10) |
| -O2 | 3.6 | 3.6 | 3.5–3.6 | 209 | `dff527aaafbcb7ac` | 同左 |
| -O2 -flto | 3.6 | 3.7 | 3.5–3.7 | 209 | `dff527aaafbcb7ac` | 同左 |

署名は 3 変種・各 10 回すべて同一。停止点は 3 変種とも unit 209 の後の `MessageBoxA` → `exit(0)` (`0x412a12`)。

## D. 起動指標 (前後)

- units_run: 前 209 (§10 既定経路 / shim 経路) → 後 209 (3 変種とも)。**変化なし**。
- 最初のウィンドウ: 未達のまま (`MessageBoxA` の text 源は未特定、#3060)。
- GetMem / FreeMem: 2,314 / 1,199 (3 変種とも同一)。

## E. 再現

```sh
FL_WIN64_DIR=<fl-win64 展開先> FLE_BOOT_RUNS=shim bash tools/flelift/boot/fle6_measure.sh   # gen → lift → -O0 (plain) → boot
FLE_CC_OPT="-O2" FLE_LABEL=o2 FLE_SHARDS=8 FLE_CC_JOBS=2 FLE_CC_RSS_CAP_MB=6000 bash tools/flelift/boot/build.sh plain
FLE_CC_OPT="-O2 -flto" FLE_LABEL=o2lto FLE_SHARDS=8 FLE_CC_JOBS=2 FLE_CC_RSS_CAP_MB=6000 bash tools/flelift/boot/build.sh plain
FLE_BOOT_N=10 bash tools/flelift/boot/variant_boot.sh plain o2 o2lto   # 集計: work/boot/variant/summary.tsv
```

素材: `oc_artifacts: fl-win64 toolchain-emsdk` (emsdk は既存の `/opt/emsdk` を使用)。生成物は `work/boot/` (gitignore)。

## F. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 描画 (最初のウィンドウ) の変種間同一性。unit 209 の後 `MessageBoxA` で止まるため未確認 | 署名は boot 状態までで、出力の描画一致は未確認 | #3060 [FLE-11] |
| 署名は boot 状態の正規化ハッシュのみ。出力メモリ全体の hash 比較は未実施 | 同上 | #3060 (FLE-11 の検証で扱う) |
| 測定は commit `6fbb6bcc` の内容を commit 前のワークツリーで実施。HEAD からの再 build は時間の都合で未実施 | コード差分は測定後 0 (下記 §G の差分確認)。再現は §E | 本 PR 本文 (再測定の子は起票しない) |
| 既定経路 (root 無し) の変種別測定 | 本付録は shim 経路のみ | #672 (親)・#3060 |

## G. 差分確認

- 測定 commit: `6fbb6bcc` (コードを変えた最後の commit: `tools/flelift/boot/build.sh`・`tools/flelift/boot/variant_boot.sh`)。
- `git diff 6fbb6bcc HEAD -- tools/flelift/x64c.py tools/flelift/boot/build.sh tools/flelift/boot/fle6_measure.sh tools/flelift/boot/rss_cap.py tools/flelift/boot/variant_boot.sh` は空 (差分 0)。本付録と REPORT の更新は docs のみ。
