# tools/flelift/boot — #5216 (PY-379 の gate フラグ `0x16baff0`・`0x16baff1` の実行時値を boot で測る)

- **既知類型との関係: 該当なし** (DEFECTS.md D1a〜D23 を照合。計測のみで lift・IR は変えていない)。
- 親: #4527 / #3538 (closed)。前提の静的同定: `tools/python/REPORT_PY379.md` (vt[+0x88] = `!A && !B && !vt[+0x48]()`・A/B = `0x16baff0`・`0x16baff1`)。

## 1. 結論

- フラグ 2 つ (`0x16baff0` = byte 0・`0x16baff1` = byte 1) は、shim boot の **unit 0 から unit 209 で停止するまで値が変わらず 0**。監視 slot の変化点は初期値の 1 件のみ (`site 0`・`old 0x0`・`new 0x0`)。
- したがって、boot の 209 unit の範囲では `vt[+0x88]` の述語は `A=0, B=0` で、`!vt[+0x48]()` (= `[0x13e7628]` の値) が真偽を決める。`[0x13e7628]` の実行時値は本測定では未読。
- 残る未確定: unit 209 より後の値 (boot は unit 209 で `exit` して止まる)・`[0x13e7628]` の実行時値・`0x1262a90` の実際の呼出し回数。

## 2. 測定

- 変更: `tools/flelift/boot/fle_boot.c` の `g_py_watch` に `0x16baff0` を 1 slot 追加 (`PY_WATCH_N` 8 → 9)。計測のみ (監視の読出し・挙動は変えない)。`0x16baff0` の 8 byte には、フラグ 2 つ (byte 0・1) が含まれる。
- 測定 commit: **`c7361691a`** (`feat(flelift): watch gate flags 0x16baff0 in py_snap (#5216)`)。ベース `219e4d0ff` (origin/main)。`git diff c7361691a HEAD -- tools/flelift/boot/fle_boot.c tools/flelift/boot/fle_boot.mjs tools/flelift/boot/build.sh tools/flelift/boot/fle6_measure.sh` の出力は **空 (差分 0)**。
- 手順: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` (`fl-win64` を展開) / emsdk 6.0.12 (`/opt/emsdk`) / `FLE_BOOT_WORK=$RUNNER_TEMP/flelift-boot-work` / `FLE_BOOT_TAG=py5216 FLE_BOOT_RUNS=shim bash tools/flelift/boot/fle6_measure.sh`。
- 実測: real 2m41s・rc=3 (shim の既知 `ok:false`・#5168 までと同じ)。load 1.43 → 1.89 (clang 中) → 1.84。lift 61 s・clang-plain 75 s・boot 20 s。

## 3. 結果 (unit 209 までの監視 slot の変化)

| 監視 slot | 変化点 | 判定 |
|---|---|---|
| `0x16baff0` (フラグ A・B) | unit 0 site 0 の `new 0x0` の 1 件のみ | unit 209 まで 0 |
| `0x15e1c78`・`0x15e4790`・`0x15e1140`・`0x13a5c90`・`0x15f34a0` | 従来どおり (unit 209 の GetMem 直前で 0 化) | 不変 |

- `boot.py_events`: n 15 件 (site 0 の初期値 9 件 + unit 132 の `0x15f34a0` + unit 209 の 5 件)。over 0。
- `boot.py_snap.last`: unit 209・pos 0・count 0・`safe_obj` 0 (前回 #5168 までと同じ)。

## 4. 製品 KPI (起動・boot の前後)

- FLEngine boot の units_run: **209 → 209 (不変)**。停止 `MessageBoxA` → `exit`。
- 最初のウィンドウ: **未達** (前後とも)。本 PR は計測のみで、起動の挙動は変えていない。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 209 より後のフラグ値 (boot は 209 で止まる) | 209 以降の `vt[+0x88]` の真偽は未確定 | #4527 (親) |
| `[0x13e7628]` (`vt[+0x48]` の値) の実行時値 | `vt[+0x88]` の真偽を決める残りの項 | #3746 (PY-244) |
| `0x1262a90` の実際の呼出し回数・呼出し元 | 述語が boot 中に評価されるかが未確認 | #4527 (親) |
