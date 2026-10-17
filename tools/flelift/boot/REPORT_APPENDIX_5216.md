# tools/flelift/boot — #5216 (PY-379 の gate フラグ `0x16baff0`・`0x16baff1` の実行時値を boot で測る)

- **既知類型との関係: 該当なし** (DEFECTS.md D1a〜D23 を照合。計測のみで lift・IR は変えていない)。
- 親: #4527 / #3538 (closed)。前提の静的同定: `tools/python/REPORT_PY379.md` (vt[+0x88] = `!A && !B && !vt[+0x48]()`・A/B = `0x16baff0`・`0x16baff1`)。

## 1. 結論

- フラグ 2 つ (`0x16baff0` = byte 0・`0x16baff1` = byte 1) は、shim boot の **unit 0 から unit 209 で停止するまで値が変わらず 0**。監視 slot の変化点は初期値の 1 件のみ (`site 0`・`old 0x0`・`new 0x0`)。
- したがって、boot の 209 unit の範囲では `vt[+0x88]` の述語は `A=0, B=0` で、`!vt[+0x48]()` (= `[0x13e7628]` の値) が真偽を決める。
- **`[0x13e7628]` (`vt[+0x48]` の読み先) は unit 0 で 0x2c0000 の初期値 (byte 0 = 0) になり、unit 209 の GetMem 解放 (site 8・proc 0x74) で 0 になる。 byte 0 は unit 0 から unit 209 まで 0**。
- 述語 `vt[+0x88]` (`0x1262a90`) の呼出しは、`FLE_TRAP_VA=0x1262a90` (trap 1 件入り) の boot でも到達せず (`boot_threw=exit`・units 209 のまま)。boot の 209 unit の範囲では述語は評価されていない。

## 2. 測定

- 変更: `tools/flelift/boot/fle_boot.c` の `g_py_watch` に `0x13e7628` を 1 slot 追加 (`PY_WATCH_N` 13 → 14)。計測のみ (監視の読出し・挙動は変えない)。
- 測定 commit: **`4fc1472ff`** (`feat(flelift): watch [0x13e7628] in py_snap (#5216)`)。ベース `fe48dca85` (origin/main)。`git diff 4fc1472ff HEAD -- tools/flelift/boot/fle_boot.c tools/flelift/boot/fle_boot.mjs tools/flelift/boot/build.sh tools/flelift/boot/fle6_measure.sh` の出力は **空 (差分 0)**。
- 手順: `FL_WIN64_DIR=$RUNNER_TEMP/py5216/x` (`fl-win64` を展開) / emsdk 6.0.12 ([EMSDK]) / `FLE_BOOT_TAG=py5216c FLE_BOOT_RUNS=shim bash tools/flelift/boot/fle6_measure.sh`。
- 実測 (監視): real 3m19.9s・rc=3 (shim の既知 `ok:false`・#5168 までと同じ)・load 1.63 → 1.95 (clang 中) → 1.75。lift 81 s・clang-plain 87 s・boot 25 s。
- 述語の到達確認: `FLE_TRAP_VA=0x1262a90 FLE_BOOT_TAG=py5216t bash tools/flelift/boot/fle6_measure.sh`。real 3m36.7s・rc=3・`traps 1` (lift 時に trap stub 1 件)・`boot_threw=exit`・units 209。

## 3. 結果 (unit 209 までの監視 slot の変化)

| 監視 slot | 変化点 | 判定 |
|---|---|---|
| `0x16baff0` (フラグ A・B) | unit 0 site 0 の `new 0x0` の 1 件のみ | unit 209 まで 0 |
| `0x13e7628` (`[0x13e7628]`・vt[+0x48] の読み先) | unit 0 site 0 `new 0x2c0000` → unit 209 site 8 (proc 0x74) `new 0x0` | byte 0 は unit 0 から 209 まで 0 |
| `0x15e1c78`・`0x15e4790`・`0x15e1140`・`0x13a5c90`・`0x15f34a0` | 従来どおり | 不変 |

- `boot.py_events`: n 27 件 (over 0)。`boot.py_snap.last`: unit 209・pos 0・count 0・`safe_obj` 0 (前回と同じ)。

## 4. 静的解析の補足 (#5216・PE 上)

- `0x13e7628` を即値・rip 相対で直接参照する命令は 0 件。参照は `[0x15e1890]` (`.data` の値 = `0x13e7628`) 経由のみ (58 箇所の読出し)。
- `[0x15e1890]` を経由して 1 を書く関数は 3 件 (`0xa8de8e`・`0x11c7615`・`0x1262970`)。`0x1262970` は VMT `0x125b1c0` の slot `+0x60` (`vt[+0x60]`) で、`vt[+0x48]` (`0x1262950`) の読み先を 1 に立てる setter。
- `vt[+0x60]` の呼出し元は、`+0x60` を読む間接呼出し 519 件 (多数のクラスの VMT で共用) のため、静的には特定できない。実行時に setter `0x1262970` が呼ばれたかは、本測定では直接確認していない (監視は値の変化だけを見る)。`[0x13e7628]` の byte 0 は unit 0 で 0x2c0000 になり、unit 209 の site 8 (GetMem 呼出し直前) で 0 に変わる。この値変化の書込み元は未特定。

## 5. 製品 KPI (起動・boot の前後)

- FLEngine boot の units_run: **209 → 209 (不変)**。停止 `MessageBoxA` → `exit`。
- 最初のウィンドウ: **未達** (前後とも)。本 PR は計測のみで、起動の挙動は変えていない。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 209 より後のフラグ値 (boot は 209 で止まる) | 209 以降の `vt[+0x88]` の真偽は未確定 | #4527 (親) |
| `0x1262970` (`vt[+0x60]`・`[0x13e7628]` の setter) の実際の呼出し元 | setter が boot の範囲で呼ばれるかは未確定 | #4527 (親) |
