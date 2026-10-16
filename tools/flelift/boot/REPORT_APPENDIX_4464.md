# tools/flelift/boot — #4464 (WIN-51) CFI 経路の入口値の再現と受け手の取得 (#4384 の受入 1・2・後続 #5337)

測定 commit: 下の「コミット」節の hash (コードを変えた最後の commit)。素材は `fl-win64` (`$RUNNER_TEMP/extracted/block00031_PE.bin`)・`toolchain-emsdk` (emsdk 6.0.12)。

## 1. 結論

- 受入 1 (入口の `rcx`・`rdx`・`dl` の再現): **達成**。`cfi_entry_probe.py` で生成 C の work コピーに probe を入れ、§13 の値を再現した (§2)。
- 受入 2 (間接 call の受け手 VA): **部分達成** (残りは #5337)。受け手 slot `0x5ac308` の正しい値は `0x40f960` (PE 静的値)。`fle_textwin_install`・`fle_init` の直後は `0x40f960` になる (§14、`FLE_WWATCH` 診断下で確認)。`f_410320` の `call [rax-0x30]` の受け手 slot は、unit 245 (ExitProcess) の後・unit 246 の直前の 16B 書込み (戻り番地 `0x2ec1d8d`) で 0 になる。seed 後の `[icall]` の target `0x0` (§4) は、この消失の後の値を見ている。
- 受入の判定: 受け手の正しい VA (`0x40f960`) は確定した。ただし、CFI 呼出しの時点まで値を保つ経路は未解決 (書込み元 `f_134cad0` は推定、消失を止める処理は未特定)。実機の loader が `0x5ac308` に入れる値も未確認。いずれも #5337 に残す。
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
| 実機で受け手 slot `0x5ac308` に入る値 (loader の充填)。harness では 0 のまま | 実機の受け手 VA は未特定。S13 以降に進めない | #5337 [WIN-60] (#4384 [WIN-49] は CLOSED) |
| `[icall]` の target `0x0` と、wasm stack の先頭 `f_410360` の対応 (stack 名の解釈) | trap 段の厳密な特定に使う。推定のまま | #5337 [WIN-60] |
| harness が `self` を渡さない (`fle_run(0x1375990)` の全引数 0) | 実機の `self` を harness で再現できない | #5337 [WIN-60] |

## 6. 統合 HEAD での再測定 (#4464・測定 commit `09eedbf0c`・mode 1 のみ)

- 理由: 先行 run のブランチを `origin/main` と統合した (`x64c.py` の `shard_approx[k]` を採用)。統合後の値を取り直した。
- 測定: `FLE_SHARDS=8 FLE_EXTRA_LDF="-g --profiling-funcs" FLE_BOOT_RUNS=tol FLE_EXTRA_ROOTS=0x6a7b70,0x1375990 bash tools/flelift/boot/fle6_measure.sh` → rc 0・所要 3 分 27 秒 (lift 80 s・clang plain 84 s・boot tol 25 s)。load 1.1〜1.9。
- 結果: dispatch 209・GetMem 2,314 / FreeMem 1,199・`cfi threw oob`・longjmp 0・exit 0。§11・§12-1 と一致。
- 入口の値 (probe 生成器 `cfi_entry_probe.py` を `work/` の lift 複製に適用・`FLE_CFI_SEED` 無し): §2 の表と一致 (`0x410320` は rcx=0・rdx=1・dl=1)。
- seed 有 (`FLE_CFI_SEED=1`): `[cfi-seed]` の書く前の live 値は `0x1104e30=0x0`・`0x5ac270=0x0`・`0x5ac308=0x0`。chain の rcx は `0x1105350` で `0x1104ef8`・`0x5af120` と `0x410320` で `0x5ac338`。`[icall] rax=0x5ac338 target=0x0`。
- 差分 (測定 commit から HEAD まで): 本節の追加のみ (`git diff 09eedbf0c HEAD -- tools/flelift` は REPORT のみ)。

## 7. 受け手 VA の実行時取得 (#5337・測定 commit `f045b48fc`・mode tol・寛容起動)

- 測定: `FLE_SHARDS=8 FLE_EXTRA_LDF="-g --profiling-funcs" FLE_BOOT_RUNS=tol FLE_EXTRA_ROOTS=0x6a7b70,0x1375990 bash tools/flelift/boot/fle6_measure.sh` → rc 0・所要 3 分 56 秒 (lift 〜48 s・clang plain 119 s・boot tol 25 s)。load 0.85 → 2.19。baseline の計数は dispatch 209・GetMem 2,314 / FreeMem 1,199・`cfi threw oob`・longjmp 0・exit 0 で §11 と一致 (測定 commit `6e1b4d6c8` = origin/main)。
- 受け手 VA: `f_410320` の `call [rax-0x30]` は `rax = rcx = self` で、受け手 slot は `self - 0x30`。`self = 0x5ac338` のとき slot は `0x5ac308`。PE 静的値は `0x40f960` (`.text` 内 raw off `0x1ab708`・`f_40f960` は lift 済み)。
- 実行時の値: `0x5ac308` は呼出し前 `0x0`。理由は `fle_data_install` がこの slot を含まないため。生成器の実出力は `[fle_data_gen] sections ..., windows 11079, total 4002981 bytes` (`fle_data_gen.py`・PR HEAD の `x64c.py` lift 出力に対して静的に実行。`tools/flelift` のコード差分は 0)。敷設は memcpy 11,083 件 (窓 11,079 + セクション 4) で、合計 4,002,981 B。`fle_data.c` を走査し、`0x5ac308` を覆う memcpy は 0 件。PE の値は harness に敷設されていない。
- `FLE_CFI_RECV=1` (新設): `0x5ac308` へ `0x40f960` を書く。`FLE_CFI_SELF=<VA>` (新設): `fle_run` の第 1 引数 (rcx) を渡す。
- seed 有 (`FLE_CFI_SEED=1`・RECV 無し): trap 段 `f_410360` ← `f_5af120` ← `f_1105350` ← `f_13752f0` ← `f_1375990`。§4 と一致。
- seed 有 + RECV (A): trap 段の先頭 `f_410320` ← `f_976b60` ← `f_976a90` ← `f_1264050` ← `f_12652c0` ← `f_1265390` ← `f_1265690` ← `f_1375990`。`threw=oob`・dispatch 209・GetMem 2,314・FreeMem 1,199 (計数は不変)。
- seed 有 + RECV + SELF=`0x5ac338` (B): A と同じ stack・同じ threw。`self` を渡しても、chain は `rcx` を global から再読込するため結果は変わらない。
- 所見 (静的・生成器の出力を走査): `0x976410` は窓 `w_4420` (`0x976400`・96 B) に入るため、敷設後は前版の PE 値 `0x9764d8` になる。`0x9764a8` (PE 値 `0x40f960`)・`0x5ac308` は敷設する memcpy に入らず、harness では 0 のまま。前版の「`f_976b60` の `rcx` は `0x976410` から来る」は、コードの静的な読みで実行時値は未計測。`f_410320` の `rax` が 0 となり `LD64(0xffffffffffffffd0)` で oob する、は推定 (`rcx`・`rax` の実行時値は未計測。推定)。
- 未解決 (起票先: #5337 に残す): (1) `0x976410` の敷設後の実行時値を probe で確定する (静的には `0x9764d8`)。(2) `fle_data_install` が覆わない `0x9764a8`・`0x5ac308` (いずれも `.text` 内) の敷設方法を決める。(3) 実機の loader が充填する値は未確認 (起票先: #5337。#4384 は CLOSED)。
- 訂正 (§14 で実測): 上の (2) の「敷設されない」は誤り。`fle_textwin_install` が `.text` 全域 (`0x401000`〜) を敷設するので、`0x5ac308`・`0x976410` は敷設直後に正しい値 (`0x40f960`・`0x9764d8`) になる。以後の問題は「敷設後に 0 になる」ことで、§14 で `0x5ac308`・`0x976410` は確認した。`0x9764a8` は未計測。

## 14. 受け手 slot の消失の所在 (#5337・測定 commit `9b8a0426c`・mode tol・寛容起動)

- 測定: `FLE_SHARDS=8 FLE_EXTRA_LDF="-g --profiling-funcs" FLE_EXTRA_CCF="-DFLE_WWATCH -DFLE_WWATCH_SLOTS=0x5ac308ull,0x976410ull" FLE_BOOT_RUNS=tol FLE_EXTRA_ROOTS=0x6a7b70,0x1375990 bash tools/flelift/boot/fle6_measure.sh` → rc 0・所要 3 分 39 秒 (lift 82 s・clang plain 101 s・boot tol 26 s)。load 0.96〜2.05。
- 計数 (診断 knob 下): dispatch 209・GetMem 2,314 / FreeMem 1,199・`cfi threw oob`・exit 0。§11・§12-1 と一致 (診断は計数を変えない)。
- 敷設直後・初期化直後の値 (probe): `0x5ac308=0x40f960`・`0x976410=0x9764d8` (`fle_textwin_install`・`fle_init` の後で、どちらも PE 静的値と一致)。
- 消失の時点: `fle_wwatch` の監視で、両 slot は **同じ 1 回の 16B 書込み** で 0 になる (`old=0x40f960 new=0` と `old=0x9764d8 new=0`)。書込みは unit 245 (ExitProcess) の後、unit 246 の直前。寛容ループの各 unit 前の検査で、最初に `0x5ac308=0` となるのが unit 246 (`[slot-zero]`)。前回 §3・§12 の clobber 695 件 (unit 246〜940) の開始点と一致する。
- 書込み元: 戻り番地 `0x2ec1d8d` (wasm 内の code 位置)。code section の関数本体の範囲で引くと code 位置 `11254` (範囲 `0x2ec1d5f`〜`0x2ec1dbd`) に入る。name section の index は import (36 件) を含むため、この code 位置の名前は `f_134cad0` と読めるが確定ではない (推定)。書込み命令は `STX` (16B の store・`fle_cpu.h:79`)。
- 既定経路 (root 無し・`FLE_EXTRA_LDF` 付き・`9b8a0426c^` と `9b8a0426c` で同一): dispatch 895 / GetMem 3,680 / FreeMem 1,499 / exit。この値は前回 REPORT の 209 (root 有・既定 root 無し) と条件が異なる。既定の数値は変えていない (`9b8a0426c^` で同じ値を再現)。
- 所見: 受け手 slot の消失は、既知の clobber (unit 246〜) と同じ時点・同じ経路。受け手の実行時 VA (`0x40f960` が正しい値) は、書込みを止めれば取れる見込み。ただし書込みを止める処理 (clobber の原因) はまだ特定していない。
- 未解決 (起票先: #5337 に残す): (1) 書込み元の関数 `f_134cad0` の実行時の名前と役割 (推定の段階)。(2) clobber を起こす unit 245 の後の処理 (#3060 の `f_6a7b70` 広域ゼロ埋めと同じ現象かは未確認)。(3) 実機の loader が充填する値 (#4384 は CLOSED)。

## 15. 段の特定: oob は `f_976b60` 経由の rcx=0 (#5337・測定 commit `dd047c232`・mode tol・寛容起動)

- probe: `tools/flelift/boot/probe_976.py` (生成 C の `work/` コピーだけを書き換える。`[p976a90]` 入口の global `0x976410`・`0x141d6b8`・`0x141d6c0`、`[p976b60]`・`[p410320]` の rcx・rdx)。
- 測定: `FLE_EXTRA_CCF="-DFLE_WWATCH -DFLE_WWATCH_SLOTS=0x5ac308ull,0x976410ull" FLE_SHARDS=8 FLE_EXTRA_LDF="-g --profiling-funcs" FLE_BOOT_RUNS=tol FLE_EXTRA_ROOTS=0x6a7b70,0x1375990 bash tools/flelift/boot/fle6_measure.sh` を lift 再生成で 1 回 (rc 0・所要 3 分 4 秒 (lift 62 s・clang plain 76 s・boot tol 20 s)・load 1.1〜1.8)。その後 probe を入れた work/ の lift で `FLE_CFI_SEED=1 FLE_CFI_RECV=1 FLE_IPP=1 FLE_TOLERANT=1` の boot を 1 回 (rc 0・dispatch 209・GetMem 2,314 / FreeMem 1,199・`cfi threw oob`)。計数は §11・§12-1 と一致。
- 時系列 (1 回の boot):
  1. `[cfi] f_1375990 rcx=0` → `f_13752f0` → `f_1105350 rcx=0x1104ef8` → `f_5af120 rcx=0x5ac338` → `f_410320 rcx=0x5ac338 rdx=1` → `[icall] rax=0x5ac338 target=0x40f960` (受け手 VA は実行時に `0x40f960`)。
  2. 同じ run で `[fle_wwatch] ret=0x2ec1f06 slot=0x5ac308 old=0x40f960 new=0` と `slot=0x976410 old=0x9764d8 new=0` が同じ 16B store で出る (unit 246 の直前・§14 と一致)。
  3. 後で `[p976a90] mem976410=0x0 mem141d6b8=0x0 mem141d6c0=0x0` → `[p976b60] rcx=0x0 rdx=0x1` → `[p410320] rcx=0x0 rdx=0x1` → `threw=oob`。
- 段の結論: oob を起こすのは直接経路 (`f_5af120` → `f_410320`) ではなく、**`f_976a90` が読む global `0x976410` が 0 になった後の `f_976b60` 経由の `f_410320` (rcx=0)**。`f_976b60` は引数 rcx を `f_410320` にそのまま渡すので、`f_410320` の `rax=0`・受け手 slot `LD64(0xffffffffffffffd0)` の oob は、この rcx=0 から来る (推定を含む。`rax` は未計測)。
- 出所: `0x976410` の書込みは `ret=0x2ec1f06` の 16B store (§14 の書込み元と同じ経路)。書込み元の関数名は未確定 (#5337 に残す)。
- 注意: lift 済み C に probe を重ねると clang の obj が古いまま残るため、`FLE_EXTRA_CCF` を変えるときは `obj/plain_*.o` を消してから build する (`cc()` は C のソースが新しいときだけ再コンパイルする)。
- 差分 0 の証跡: 測定 commit `dd047c232` から HEAD までのコード差分は本節のみ (`git diff dd047c232 HEAD -- tools/flelift` は REPORT のみ)。

## 16. 書込み元の特定を試みた結果 (#5337・診断 knob `FLE_WWATCH_STACK`・未確定)

- 追加: `fle_cpu.c` の `fle_wwatch` に `-DFLE_WWATCH_STACK` (既定無効) を足した。受け手 slot や `0x976410` が非 0 から 0 に変わるとき、`R[RSP]` から 32 語を走査して 4 MiB 以上 32 MiB 未満 (`0x400000`〜`0x2000000`) の guest VA 候補を出す。既定経路の挙動は変えない。
- 測定: `FLE_EXTRA_CCF="-DFLE_WWATCH -DFLE_WWATCH_STACK -DFLE_WWATCH_SLOTS=0x5ac308ull,0x976410ull" FLE_SHARDS=8 FLE_EXTRA_LDF="-g --profiling-funcs" FLE_BOOT_RUNS=tol FLE_EXTRA_ROOTS=0x6a7b70,0x1375990 bash tools/flelift/boot/fle6_measure.sh` → rc 0。dispatch 209・GetMem 2,314 / FreeMem 1,199・`cfi threw oob` と同じ計数。
- boot: `FLE_CFI_SEED=1 FLE_CFI_RECV=1 FLE_IPP=1 FLE_TOLERANT=1` を 2 回 (rc 0)。stack 付きの 2 回目で `[fle_wwatch] ret=0x2ec1dc7 slot=0x5ac308 old=0x40f960 new=0`・`slot=0x976410 old=0x9764d8 new=0`。1 回目の診断無し版では `ret=0x2ec1de6`。§14 の `ret=0x2ec1f06`・§15 の `ret=0x2ec1dc7` とは番地が違う (ビルドのたびに wasm の code 位置が変わる)。
- wasm の対応 (自作の code section 解析): `0x2ec1dc7`・`0x2ec1de6` はどちらも wasm 関数 `STX` (`fle_cpu.h:79` の 16B store ヘルパ) の範囲 `0x2ec1d98`〜`0x2ec1df6` に入る。ヘルパは呼出し元ではないため、guest 側の書込み元は `R[RSP]` の走査からしか引けない。
- 走査の結果: `[1]=0x6c7923`・`[3]=0x6cf116`・`[5]=0x15eac01`・`[15]=0x15eac80`・`[17]=0x815920`・`[23]=0x5af36a`・`[25]=0x4130b4`。lift の関数範囲で引くと `0x5af36a` は `f_5af330`、`0x4130b4` は `f_413060` の中。ただし走査は古いスタック語を含むため、実行中の呼出し連鎖とは断定できない。
- 所見: `fill6a7b70` の書込み範囲 (`dst`・`cnt`) は両 slot を覆わないので、0 書込みは fill 以外の guest 16B store。走査の候補 `f_5af330`・`f_413060` は呼出し連鎖の一部で、書込みを行うと断定できる根拠は無い。`f_409c80` は候補にしない (16B store を含むが、0 を書く経路は未確認)。書込み元の guest 関数は未確定。
- 未解決 (起票先: #5337 に残す): (1) 走査でなく実行中の呼出し連鎖を取る (`ott` の call 深さ追跡)。(2) `f_409c80` を呼ぶ 20 件の呼出し元のどれが unit 245 の後で動くかの確定。(3) 実機の loader が `0x5ac308` に充填する値 (#4384 は CLOSED)。
