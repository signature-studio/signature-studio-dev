# liftdiff LD-238 (#4423) — ret=i128 の segv 5 関数 (2 段 this 疑似オブジェクト) (付録)

> 親 #4378 (LD-211) の子。前段 [`REPORT_APPENDIX_LD211.md`](REPORT_APPENDIX_LD211.md) §3 の segv 5 関数が対象。
> 測定 commit: §3・§4 は `65d7e01e3` (コード変更は `ldlib/cases.py` の `vmt2` 追加と `tests/ld238_probe.py`)。§5 は `570611d4e` (`ensure_native()` 修正を含む)。プローブ: `tests/ld238_probe.py`。

## 1. 結論 (部分達成)

- **原因特定 (2 関数)**: `668390` と `6683d0` は小さなラッパー。`rax = [this+8]`・`rbx = [rax]`・`call [rbx+0x20]` の順に読むため、this の **2 段目のオブジェクト** (`[this+8]`) とその先頭の VMT が要る。LD-211 の `vmt` blob は `this+8` が 0 のため `[rax]` で segv していた。
- **`vmt2` blob で `this+8` は越えた**: `668390` / `6683d0` は `this+8` の読みを通過し、VMT の slot 4 (`0x50018080`) を間接呼出しする段階まで進んだ。その命令フェッチで segv する (§3)。
- **未達**: 5 関数の実行可能化は未達 (0/5)。仮 proc 番地の命令フェッチの segv の原因は未切り分け。`784520` / `8e7e10` / `a965c0` は `vmt2` を与えても LD-211 と同じく segv。
- **戻り経路の判定 (6 関数)**: 未着手。LD-211 §3 の結果 (rax・rdx が変化、xmm0 は判定不能) のまま。

## 2. 方法 (再現)

- 前提 build: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 liftdiff.py build targets/m11.json` (`work/m11/`、`sig_mismatch 0`・`undefined 0`・10.3 秒)。
- 実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tests/ld238_probe.py --out work/ld238_probe.json` (native のみ・約 6 秒)。
- 既存の回帰: `tests/ld211_fvm_probe.py --out work/ld238_regress.json` を同じ commit で再実行 (§4)。

## 3. 実測 (`ld238_probe.py`・blob=vmt2)

| 関数 | 実行 ok | segv (fault) |
|---|---|---|
| 668390 | 0/1 (arg0 のみ) | rip=0x50018080 (VMT slot 4 の仮 proc 番地。命令フェッチ) |
| 6683d0 | 0/1 | rip=0x50018080 |
| 784520 | 0/2 | arg0: fault 記録なし / arg1: addr 0x3 @ 0x50f625 (整数を ptr 扱い) |
| 8e7e10 | 0/2 | addr 0x0 @ 0x8e7fbd (RIP 相対のグローバル VA 0x1599430 が null) |
| a965c0 | 0/3 | fault 記録なし |

- 668390 の native の詳細: `rbx=0x22473000` (`arena+0x3000` の内部オブジェクト)、`rax=0x22474000`。`this+8` の読みは通っている。
- 仮 proc の番地 `0x50018080` は `LD_FAKEPROC_BASE + (LD_VMT_IDX0+4)*LD_FAKEPROC_SZ` と一致 (`cases.py` と `rt/ld_core.h` で確認)。native の stderr に mmap 失敗は出ていない。

## 4. 回帰 (同 commit・既存プローブ)

`tests/ld211_fvm_probe.py` (LD-211 の既存 blob `vmt`) は LD-211 §3 と一致:

| 関数 | 実行 ok |
|---|---|
| 45e1a0 45e280 45e2e0 45eb00 45ecc0 45ed20 | 3/3 ずつ |
| 668390 6683d0 784520 8e7e10 a965c0 | 0 (LD-211 §3 と同じ) |

## 5. 追補 (LD-238 再 run・古い実行器バイナリの修正)

- **前回の 668390 / 6683d0 の segv の原因**: 素材 `work-liftdiff` 同梱の `work/ld_native` が古く、仮 proc の thunk を敷けなかった (`rip=0x50018080` の命令フェッチ)。`ldlib/build_wasm.py` の `ensure_native()` は mtime で再ビルドするが、`Session(build=False)` の probe は呼ばないため古いバイナリを使い続けていた (#3088 と同じ症状)。
- **修正**: `tests/ld238_probe.py` が実行前に `build_wasm.ensure_native()` を呼ぶようにした (mtime が古いバイナリを検出すると `rt/` の現版から作り直す)。
- **測定 commit**: `570611d4e` (修正を含む。`eb943cdde` は修正前のため、ここでは §5 の数値は再現しない)。コード差分は `tests/ld238_probe.py` の 2 行のみ。
- **実測 (blob=vmt2・native・古い mtime のバイナリで再ビルド後)**:

| 関数 | 実行 ok | segv |
|---|---|---|
| 668390 | **1/1 ok** | — (前回は segv) |
| 6683d0 | **1/1 ok** | — (前回は segv) |
| 784520 | 0/2 | arg1: addr 0x3 @ 0x50f625 (整数を ptr 扱い) |
| 8e7e10 | 0/2 | addr 0x0 @ 0x8e7fbd (RIP 相対グローバル VA 0x1599430 が null) |
| a965c0 | 0/3 | fault 記録なし (逆アセンブル済み・下記) |

- **a965c0 の逆アセンブル (26 命令)**: `rax = [rip+0xb4bc69]` (VA 0x15e2258) を `call [rax]` で間接呼出し。このグローバルが未初期化だと呼出し先が 0。続いて `call 0x40c650` (直接)。戻りは `xmm0` (単精度, `cvtsd2ss` 経由) で、`ret=i128` とは整合しない。
- **784520**: `rcx`・`rdx` (ポインタ) と `xmm2` を取り、`call 0x50f600` で間接呼出し。第 2 引数 (整数) が `[r8]` で読まれるため、引数割り当てが誤り。
- **戻り経路の判定 (6 関数)**: 未着手。呼出し元の追跡が要るため、1 run では判定しない。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 784520 の引数割り当て (arg1 が vtable 扱い) | 実行不能のまま | [LD-238] #4423 (継続) |
| 8e7e10 のグローバル 0x1599430 の初期化 | 実行不能のまま | [LD-238] #4423 (継続) |
| a965c0 のグローバル 0x15e2258 (間接呼出し先) の初期化 | 実行不能のまま | [LD-238] #4423 (継続) |
| 6 関数の戻り経路 (rax・rdx・xmm0) の動的判定 | `ret_override` 未付与 | [LD-238] #4423 (継続) |

## 7. 追補 (784520 の引数割当の修正)

- **原因 (probe 側の誤り)**: `ld238_probe.py` は整数引数 1 つだけを this 以外の値にし、arg0 (rcx = this) に整数 `3` を渡していた。`784520` は `0x50f600` 経由で `rcx` を `[rax]` (VMT 読み) するため、`addr 0x3 @ 0x50f625` は this が整数だったことによる。
- **784520 の実引数 (逆アセンブル)**: `rcx` = this、`rdx` = arg1 (ポインタ、`r8` 経由で `0x50f600` に渡る)、`xmm2` = 単精度 float (arg2)。戻りは `xmm0` の float。IR 由来の署名 `(i64, i64) -> i128` は float 引数を落としていた。
- **修正**: `tests/ld238_probe.py` に `SIG_OVERRIDE` (784520 のみ・`(i64, i64, float) -> float`) を追加し、`vmt2_line` で arg0 を常に vmt2 の this にする。
- **実測 (blob=vmt2・native・修正後)**:

| 関数 | 実行 ok | segv |
|---|---|---|
| 668390 | 1/1 | — |
| 6683d0 | 1/1 | — |
| 784520 | 0/2 | rip 不明 (fault 記録なし) |
| 8e7e10 | 0/2 | addr 0x0 @ 0x8e7fbd (変化なし) |
| a965c0 | 0/3 | fault 記録なし (変化なし) |

- **784520 の残り**: 修正後の segv は `call [rax+0xb8]` (VMT slot 23) 周辺と推定。`vmt2` の VMT は 8 slot (`LD_VMT_SLOTS = 8`) しか作られない。slot 23 に仮 proc 番地を書く試行 (probe の外で blob を差し替え) は `rip=0x50110000` で segv し、thunk が敷かれていない番地を指した。**slot 23 の仮 proc を敷くには `rt/ld_core.h` の `LD_VMT_SLOTS` 拡張が要る** (rt の変更は本 run では行わない)。
- **未解決**: 784520 の VMT slot 23 (rt の仮 proc 域の拡張が要る) / 8e7e10 のグローバル 0x1599430 の初期化 / a965c0 のグローバル 0x15e2258 の初期化 / 6 関数の戻り経路の判定。起票先は [LD-238] #4423 (継続)。

## 8. 追補 (784520 の VMT slot 23 を rt の仮 proc 域に拡張)

- **測定 commit**: `d7ff728d8` (rt と cases の変更を含む最後の commit)。コード差分 (`git diff a34610a8b HEAD -- tools/liftdiff`) は `rt/ld_core.h` の `LD_VMT_SLOTS` 8→24 (と仮 proc 名配列) と `ldlib/cases.py` の `VMT_SLOTS` 8→24 の 2 箇所のみ。
- **前提**: `targets/m11.json` の `ir` は #5886 以降 `work/ld288/boot3_40c420_tr.ll` を指す。素材 `work-liftdiff` 同梱の IR には無いため、`tests/ld288_40c420_xmm0.py` で `tools/m11/work/boot_final3.ll` から生成した (2.5 秒)。`liftdiff.py build targets/m11.json` は `sig_mismatch 0`・`undefined 0`。
- **なぜ拡張が要るか**: 784520 は `call [rax+0xb8]` (VMT slot 23) を呼ぶ。`LD_VMT_SLOTS = 8` のままでは slot 23 の仮 proc thunk が敷けず、`rip=0x50110000` で segv していた (§7)。`LD_VMT_SLOTS = 24` で thunk が `LD_VMT_IDX0 + 23` まで敷かれる。VMT 域 (arena+0x2000〜+0x20C0) は vmt2 の内部オブジェクト (arena+0x3000) と重ならない。

### 実測 (native・probe 2 本・測定 commit `d7ff728d8`)

| 関数 | 実行 ok (前 §7) | 実行 ok (今回) | 失敗の内訳 |
|---|---|---|---|
| 668390 | 1/1 | 1/1 | — |
| 6683d0 | 1/1 | 1/1 | — |
| 784520 | 0/2 | **1/2** | `vmt2:0` (arg0 を ptr にし、arg1 は整数のまま): addr 0x1 @ 0x50f666 (arg1 の整数を ptr 扱い)。`vmt2:1` (arg1 を ptr にした case) は ok |
| 8e7e10 | 0/2 | 0/2 | addr 0x0 @ 0x8e7fbd (変化なし) |
| a965c0 | 0/3 | 0/3 | fault 記録なし (変化なし) |

回帰 `tests/ld211_fvm_probe.py` (`d7ff728d8` 時点): 45e1a0 系 6 件は 3/3 (変化なし)。784520 は 0/5 → 1/5。668390・6683d0 は 0/3 のまま (LD-211 §3 と同じ)。**注: 1/5 は vmt 入力が 24 slot だった `d7ff728d8` の値。§9 で入力を戻した現行 HEAD では 784520 は 0/5 (§11 の HEAD 実測)。現行 HEAD で再現しない。**

回帰テスト (native・wasm を含む build 後): `test_ld199_fvm_pin` / `test_ld200_struct_stub` / `test_ld203_slot_fill` / `test_ld253_point_arg_slot` / `test_ld259_patch_p` は全て PASS (rc=0)。

### 8e7e10 / a965c0 のグローバルの位置 (逆アセンブル訂正)

- §5 の「VA 0x1599430」は誤り。`objdump -d` で読むと、8e7e10 の fault 直前の命令 `mov rax,[rip+0xd11473]` は **VA 0x15f9430**。`.data` (0x13a5000〜) の外、`.bss` (0x15e6000〜) 相当の領域。
- a965c0 の間接呼出し先 `mov rax,[rip+0xb4bc69]` は VA 0x15e2258 (§5 と一致)。こちらも `.bss` 相当。
- 両方とも PE のセクションデータに値が無く、boot 後の値は `boot_state.json` の `img` に含まれるかを未確認。
- 切り分け (作業用・未コミット): `p=i:<RVA>:q=<仮 VMT>` で 0x15f9430 に仮 VMT を入れると、`[rax+0x40]` を読んで `addr 0x40000400ba89` の segv になる。仮 VMT の slot 8 は仮 proc ではなく、別の VMT 構造が要る。a965c0 は 0x15e2258 に仮 proc を入れると `rip=0x40000400ba49` で segv (仮 proc のマーク値を実行してしまう)。**どちらも仮値の置き方が誤りで、正しい値 (boot 後の実値) が要る。**

### 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 784520 の `vmt2:0` ケース (arg1 の整数を ptr 扱い) | 試験設計 (arg 割当) の見直しが要る | [LD-238] #4423 (継続) |
| 8e7e10 のグローバル VA 0x15f9430 (.bss) の実値 | 実行不能のまま | [LD-238] #4423 (継続) |
| a965c0 のグローバル VA 0x15e2258 (.bss) の実値 (間接呼出し先) | 実行不能のまま | [LD-238] #4423 (継続) |
| 6 関数の戻り経路 (rax・rdx・xmm0) の判定 | `ret_override` 未付与 | #4429 系 (LD-215・#5886 の別レーン) |
| `liftdiff.py run` の `unsupported_sig` (float 引数の 784520 は wasm 比較の対象外) | wasm 側の比較は未実施 | [LD-238] #4423 (継続) |

## 9. 追補 (review 差し戻し: 既存 blob の入力変化を解消)

- **指摘**: `VMT_SLOTS` 8→24 (§8 の `cases.py` 変更) は `make_blob_vmt` / `make_blob_vmt2` / `make_blob_vmtf` の全部に効き、既存 blob `vmt` / `vmt2` / `vmtf` の slot 8〜23 の入力が 0 埋めから仮 proc 番地に変わっていた。既存の fvm 42 件・691dd0 の vmo・ld211・ld259 の測定が古くなる。
- **修正**: `cases.VMT_SLOTS` を 8 に戻す。24 slot の blob `vmt24` (`make_blob_vmt2(nslots=VMT_SLOTS_WIDE)`) を `SPECIAL_BLOBS` に足し、`tests/ld238_probe.py` の 5 関数はすべて `vmt24` を使う。`rt/ld_core.h` の `LD_VMT_SLOTS` 24 は変えない (仮 proc 域は 24 のまま)。
- **入力の同一性 (実測・Python で blob バイトを比較)**:
  - 旧 `a34610a8b` (`ldlib/cases.py` 変更前) と HEAD で `vm` / `vmt` / `vmt2` / `u16` / `vmtf` は sha256 一致 (5 件とも `same`・`VMT_SLOTS` 8 と 8)。既存 blob の入力は元に戻った。
  - `vmt24` は `d7ff728d8` の `make_blob_vmt2` (24 slot) とバイト一致 (`True`)。旧 §8 の測定入力と同じ。
  - `vmt24` と `vmt2` の差は qword 16 件 (オフセット 0x2040〜0x20b8 = slot 8〜23)。slot 23 は `LD_FAKEPROC_BASE+(LD_VMT_IDX0+23)*LD_FAKEPROC_SZ` を指す。
- **回帰 (HEAD・実測)**: `tests/test_ld207_obj_pattern.py` PASS (rc=0)。
- **未実行 (正直に記録)**: 本 run の作業ツリーには `tools/liftdiff/work/` (m11 IR `work/ld288/boot3_40c420_tr.ll`・`work/m11/boot_state.json`) が無く、`ld_native` のビルドと `ld238_probe.py` が走らない。ld199・ld200・ld203・ld253・ld259・ld211・ld238 probe の HEAD 実測は未実施。§8 の数値は `d7ff728d8` (入力バイトは `vmt24` と同一) の測定で、HEAD 上の再測定ではない。
- **測定 commit**: §8 の実測は `d7ff728d8`。§9 は入力バイトの同一性 (上記) の確認で、HEAD 上の probe 再測定はしていない。`git diff d7ff728d8 HEAD -- tools/liftdiff/ldlib tools/liftdiff/tests` は `cases.py`・`ld238_probe.py` の 2 ファイルのみ。

## 10. 追補 (review round 3: HEAD 上の再測定の要求に対する状態)

- **判定**: HEAD (`4bab3a0d0`) 上の再測定は本 run では未実施。素材が無いため実行できない。
  - 本 run の `$ARTIFACTS_DIR` には `fl-win64.tar.zst` のみ。`work-m11`・`work-liftdiff`・`toolchain-emsdk` は無い (`ls` で確認)。
  - 作業ツリーに `tools/liftdiff/work/`・`tools/m11/work/` が無い。`tests/ld288_40c420_xmm0.py` の入力 (`boot_final3.ll`) も無いため、m11 IR (`work/ld288/boot3_40c420_tr.ll`) を生成できない。
- **測定 commit は据え置き**: 実測をしていないので、測定 commit を HEAD に進めない。§8 の実測は `d7ff728d8` のまま。
- **HEAD までのコード差分** (`git diff d7ff728d8 HEAD -- tools/liftdiff/ldlib tools/liftdiff/tests`): 下記 2 ファイル。REPORT 以外の差分はこれだけ。
  - `ldlib/cases.py`: `VMT_SLOTS` 8 (既存 blob 用)・`VMT_SLOTS_WIDE` 24 (`vmt24` 専用)・`make_blob_vmt24` の追加。`make_blob_vmt2` に `nslots` 引数。
  - `tests/ld238_probe.py`: `vmt2_line` の `blob` 引数化。5 関数は `vmt24` を使う。
- **既存 blob の入力**: §9 のとおり、`vm` / `vmt` / `vmt2` / `u16` / `vmtf` は `a34610a8b` と HEAD でバイト一致 (sha256)。`vmt24` は `d7ff728d8` の 24 slot `vmt2` と一致。したがって §8 の入力は `d7ff728d8` と同一。ただし、HEAD で走らせた結果ではない。
- **未実施 (次の run で必要)**: `tests/ld238_probe.py` (5 関数・`vmt24`)、`ld199`・`ld200`・`ld203`・`ld253`・`ld259`・`ld211` の HEAD 実測。`oc_artifacts: fl-win64 toolchain-emsdk work-m11 work-liftdiff` が要る。これが揃ったら、測定 commit を HEAD の最終 code commit に更新し、再測定の結果が §8 と違えばその数値を訂正する。
- **§10 は §11 で置き換えた** (素材が揃い、HEAD 実測を実施したため)。

## 11. 追補 (HEAD 実測・素材 work-m11 / work-liftdiff / toolchain-emsdk / fl-win64 を展開)

- **測定 commit**: `dcee6eed2` (`tools/liftdiff` の `rt`・`ldlib`・`tests`・fvm 関連スクリプトを変えた最後の commit)。`git diff dcee6eed2 HEAD -- tools/liftdiff ':!tools/liftdiff/REPORT*'` は 0 行 (HEAD = 測定 commit の code 状態)。
- **素材**: 実行 run の素材 (`fl-win64`・`work-m11`・`work-liftdiff`・`toolchain-emsdk`) を展開 (`work-m11` は `tools/m11/work/`、`work-liftdiff` は `tools/liftdiff/work/`、`fl-win64` は runner の一時展開先)。
- **IR・build**: `tests/ld288_40c420_xmm0.py` (2.6 秒) → `liftdiff.py build targets/m11.json`: `sig_mismatch 0`・`undefined 0`・OK。
- **単体・回帰 (HEAD・rc)**: `test_compare_ld11` / `test_ld52_machine_sig` / `test_ld200_struct_stub` / `test_ld181_i128_entry` / `test_ld248_i128_xmm_entry` / `test_ld179_tagpoint_tr` / `test_ld203_slot_fill` / `test_ld225_sample_vmo` / `test_ld259_patch_p` は全て rc=0。`test_ld207_obj_pattern` / `test_ld199_fvm_pin` / `test_ld253_point_arg_slot` も rc=0。
- **5 関数 probe (`tests/ld238_probe.py`・vmt24)**: 668390 1/1・6683d0 1/1・784520 1/2 (`vmt24:0` segv addr 0x1 @ 0x50f666、`:1` ok)・8e7e10 0/2 (addr 0x0 @ 0x8e7fbd)・a965c0 0/3。§8 の表と一致。
- **ld211 probe (HEAD)**: 45e1a0 系 6 件は 3/3。668390 0/3・6683d0 0/3・**784520 0/5**・8e7e10 0/5・a965c0 0/7。§8 の回帰行 (1/5) は HEAD で再現しない (上記 §8 の注)。
- **fvm 42 件 (HEAD 再測定・ld5406_fvm_fill.py・既定入力)**: 入力は HEAD で `liftdiff_e2e.sh` の [4/4] と同じ手順 (`liftdiff.py batch targets/m11.json --set sample:800 --shards 12 --nobuild --state auto`) で作り直した `work/m11/batch_sample_800.jsonl` (801 行・verdict match 360 / mismatch 236 / unexec 205・121 秒・rc=0)。fvm case 42 件を読めた (旧入力は `work/m11/batch_sample_800.jsonl` の 10/12 生成で fvm 0 件。旧版は `batch_sample_800_stale_1012.jsonl` として残置)。
  - 旧 (batch の fvm 内訳) both_fault 23 / native_fault 15 / diff 3 / hang 1 → 新 (vmtf) both_fault 24 / native_fault 9 / diff 8 / equal 1。`wasm_trap` 0 件。
  - 遷移: both_fault→both_fault 22・native_fault→native_fault 8・native_fault→diff 5・diff→diff 3・native_fault→both_fault 1・hang→both_fault 1・native_fault→equal 1 (`0x681380` fvm0)・both_fault→native_fault 1。
  - 分類 (`ld5406_fvm_classify.py`・HEAD batch): wasm_stub_unreach 14・native_null_field 10・wasm_oob 8・native_noaddr 4・diff 3・wasm_other 1・native_cand_arg 1・other:hang 1 (計 42)。
  - 入力 batch の fvm 内訳は前回測定 (`09dd25790`・both_fault 24 / native_fault 15 / diff 3) と 1 件ずつずれる (both_fault 23・hang 1)。`09dd25790` から HEAD までには `rt`・`ldlib` 等の code 差分 (11 files) がある (`git diff 09dd25790 HEAD --stat -- tools/liftdiff/rt tools/liftdiff/ldlib tools/liftdiff/tests`)。このため前回の数値は HEAD の入力では再現しない。HEAD の値は上の §11 の数値を正とする。ずれの原因の切り分けは未実施。
- **691dd0 (HEAD batch)**: verdict `mismatch` (`vmo` の `diff`・`z` は native_fault)。LD-225 の記録と一致。
- **ld259**: `test_ld259_patch_p` rc=0 (13 秒)。
