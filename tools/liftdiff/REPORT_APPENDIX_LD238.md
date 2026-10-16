# liftdiff LD-238 (#4423) — ret=i128 の segv 5 関数 (2 段 this 疑似オブジェクト) (付録)

> 親 #4378 (LD-211) の子。前段 [`REPORT_APPENDIX_LD211.md`](REPORT_APPENDIX_LD211.md) §3 の segv 5 関数が対象。
> 測定 commit: `65d7e01e3` (コード変更は `ldlib/cases.py` の `vmt2` 追加と `tests/ld238_probe.py`)。プローブ: `tests/ld238_probe.py`。

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

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| VMT slot 4 の仮 proc 番地 (0x50018080) の命令フェッチ segv。thunk 敷設 (`ld_fake_ptr`) と boot state 経路 (`state_lines_for` → `SSNAP`) のどちらが原因か未切り分け | 668390 / 6683d0 の実行可能化が止まる | [LD-238] #4423 (本 issue を継続) |
| 784520 (整数引数を vtable として参照) / 8e7e10 (グローバル 0x1599430 の初期化) / a965c0 (逆アセンブル未実施) | 3 関数が判定不能のまま | [LD-238] #4423 (本 issue を継続) |
| 6 関数の戻りレジスタ (rax・rdx・xmm0) と戻り型 | `ret_override` 未付与 | [LD-238] #4423 (本 issue を継続) |

## 6. 追補 (LD-238 再 run・古い実行器バイナリの修正)

- **前回の 668390 / 6683d0 の segv の原因**: 素材 `work-liftdiff` 同梱の `work/ld_native` が古く、仮 proc の thunk を敷けなかった (`rip=0x50018080` の命令フェッチ)。`ldlib/build_wasm.py` の `ensure_native()` は mtime で再ビルドするが、`Session(build=False)` の probe は呼ばないため古いバイナリを使い続けていた (#3088 と同じ症状)。
- **修正**: `tests/ld238_probe.py` が実行前に `build_wasm.ensure_native()` を呼ぶようにした (mtime が古いバイナリを検出すると `rt/` の現版から作り直す)。
- **測定 commit**: `eb943cdde` (origin/main) からの作業ブランチ。コード差分は `tests/ld238_probe.py` の 2 行のみ。
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

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 784520 の引数割り当て (arg1 が vtable 扱い) | 実行不能のまま | [LD-238] #4423 (継続) |
| 8e7e10 のグローバル 0x1599430 の初期化 | 実行不能のまま | [LD-238] #4423 (継続) |
| a965c0 のグローバル 0x15e2258 (間接呼出し先) の初期化 | 実行不能のまま | [LD-238] #4423 (継続) |
| 6 関数の戻り経路 (rax・rdx・xmm0) の動的判定 | `ret_override` 未付与 | [LD-238] #4423 (継続) |
