# tools/flelift/boot — #4464 (WIN-51) CFI 経路の入口値の再現と受け手の取得 (#4384 の受入 1・2)

測定 commit: 下の「コミット」節の hash (コードを変えた最後の commit)。素材は `fl-win64` (`$RUNNER_TEMP/extracted/block00031_PE.bin`)・`toolchain-emsdk` (emsdk 6.0.12)。

## 1. 結論

- 受入 1 (入口の `rcx`・`rdx`・`dl` の再現): **達成**。`cfi_entry_probe.py` で生成 C の work コピーに probe を入れ、§13 の値を再現した (§2)。
- 受入 2 (間接 call の受け手 VA): **実行時の値を取得 (受け手は 0x0)**。`f_410320` の `call [rax-0x30]` の target は、seed 後の実行で `rax=0x5ac338`・`target=0x0` (`[icall]` ログ)。受け手の slot `0x5ac308` は、呼出し前の live memory が `0x0` (`[cfi-seed]` ログ)。PE ファイル上の `0x40f960` は、loader の充填が無い harness では現れない。
- 受入の判定: 受け手の VA は実行時に `0x0` と取れた。ただし実機で `0x5ac308` に入る値は未確認 (実機の loader 側の充填は本 harness の対象外)。したがって「実機の受け手」は未特定のまま。
- 原因の要点: `CreateFruityInstance` (`0x1375990`) は DLL の export で、実機の `self` は host が渡す。`f_13752f0`・`f_1105350` は `rcx` を固定の global slot (`0x1104e30`・`0x5ac270`) から再読込するため、harness の `rcx=0` は chain の `self` にならない。

## 2. 入口の記録 (受入 1)

probe: `tools/flelift/boot/cfi_entry_probe.py` (生成 C の `work/` コピーだけを書き換える。repo の lift 出力は変えない)。`tol` mode・FLE_CFI_SEED 無し・寛容起動 (`FLE_TOLERANT=1`)。

| 入口 VA | rcx | rdx | dl | 備考 |
|---|---|---|---|---|
| `0x1375990` | 0x0 | 0x0 | 0x0 | harness の `fle_run(0x1375990)` (全引数 0) |
| `0x13752f0` | 0x0 | 0x0 | 0x0 | |
| `0x1105350` | 0x0 | 0x0 | 0x0 | |
| `0x5af120` | 0x0 | 0x1 | 0x1 | |
| `0x410320` | 0x0 | 0x1 | 0x1 | `call [rax-0x30]` の oob 地点 |

- 再現: 結果 JSON の `cfi`: `threw=oob`・`longjmp=0`・`exit=0`・`last_dispatch=[0x6a7b70,0x6a7b70,0x6a7b70,0x1375990]`。§13 と一致。
- 計数 (dispatch 209・GetMem 2,314 / FreeMem 1,199・停止 unit 245 `exit`) も §11・§12-1 と一致。

## 3. 受け手の値の所在 (PE 静的値)

`f_1375990` は export `CreateFruityInstance` (`pefile` の export 表で確認)。呼出し chain の `self` の出所:

- `f_13752f0` (`0x13752f0`): `rcx = LD64(0x1104e30)` → PE 静的値 `0x1104ef8` を指す。
- `f_1105350` (`0x1105350`): `rcx = LD64(0x5ac270)` → PE 静的値 `0x5ac338` を指す。
- `f_410320` の `rax = rcx = 0x5ac338`。受け手 slot は `0x5ac338 - 0x30 = 0x5ac308`。PE ファイルの静的値は `0x40f960` だが、呼出し前の live memory は `0x0` (§4)。

## 4. seed 実験 (FLE_CFI_SEED=1)

`fle_boot.mjs` に `FLE_CFI_SEED=1` を追加 (既定は従来どおり)。CFI 呼出し前に `0x1104e30`・`0x5ac270` を PE 静的値へ書く。`[cfi-seed]` ログで書く前の live 値を出す。

| 実験 | 入口 `rcx` の chain | 受け手 slot `0x5ac308` (live) | 間接 call の target | threw |
|---|---|---|---|---|
| 既定 (seed 無し) | 0x0 / 0x0 / 0x0 / 0x0 / 0x0 | 未測定 | 未測定 | oob |
| seed 有 | 0x0 / 0x0 / 0x1104ef8 / 0x5ac338 / 0x5ac338 | 0x0 (呼出し前) | 0x0 (`[icall]`) | oob |

- seed で `f_5af120`・`f_410320` が `rcx=0x5ac338` で入ることを確認した (`[cfi]` 行)。
- seed 後の trap の wasm stack は `f_410360` を先頭に出す。`f_410320` の直接 call 先ではなく、`[icall]` の target `0x0` の段で oob が起きる。`0x0` の間接 call を経由する点は `[icall]` ログで確認した。
- 寛容起動の計数は seed の有無で変わらない (dispatch 209・exit・unit 245)。seed は CFI 呼出しだけに効く。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実機で受け手 slot `0x5ac308` に入る値 (loader の充填)。harness では 0 のまま | 実機の受け手 VA は未特定。S13 以降に進めない | #4384 [WIN-49] |
| `[icall]` の target `0x0` と、wasm stack の先頭 `f_410360` の対応 (stack 名の解釈) | trap 段の厳密な特定に使う。推定のまま | #4384 [WIN-49] |
| harness が `self` を渡さない (`fle_run(0x1375990)` の全引数 0) | 実機の `self` を harness で再現できない | #4384 [WIN-49] |
