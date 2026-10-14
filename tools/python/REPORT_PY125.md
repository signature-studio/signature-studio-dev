# tools/python REPORT: PY-125 general.clearLog・dumpScoreLog の dispatch 0xd843d0 と下位関数の意味確定と C provider 実装 (#3001, 親 #2979, 前段 #2830 の子)

> 正本: `tools/python/REPORT_PY87.md` (general の状態読出し 4 件)・`REPORT_PY61.md` (status → 例外文言の写像 `0xd82c20`)・`REPORT_PY43.md`/`REPORT_PY39.md` (dispatch `0xd843d0` の初期解析)。本付録は PY-125 の実測のみ。
> 前段 `tools/python/REPORT_PY121.md` は repo に存在しない (親 #2979 も open)。本 REPORT は PE を直接読んで確定した。

## 結論

- **dispatch `0xd843d0` の out の写し方を確定**: 呼出し側が読むのは `out[0]` (= コールバックが job+0x60 に書いた status)。述語 gate 偽・未実行なら `out[0] = -2` のまま。
- **clearLog (fn `0xd6a1f0`)・dumpScoreLog (fn `0xd6a060`) の戻り値を確定**: 成功経路の戻り値は None。mock と C に実装し、`tests/general_diff.mjs` の差分は 0。
- **`0x11eb5f0` の効果を確定** (flag で分岐)。**`0x124c020` の効果は一部のみ確定** (silent で出力抑止する分岐まで)。`0x12df090` (クリア本体) は未読。
- **-2 の Python 側の挙動は未確定**: `0xd82c20(-2)` は報告ゲート R (`[[[0x861b1f]+8]+0x88]`) の実行時値で None か RuntimeError (`Operation unsafe at current time`) に分かれる。R の値は静的に決まらない。mock/C は述語 P 真・gate 真を仮置きし、-2 の経路に到達させない。

## 手段

- 逆アセンブル: `FL_WIN64_DIR=<[WIN64] 展開先> python3 analysis/flapi/pe_disasm.py <VA> <命令数>` (先頭から線形。RIP 相対の絶対アドレスは次命令 + disp で手計算)。入力は `extracted/block00031_PE.bin` (`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst --wildcards '*block00031_PE.bin'`、展開 3 秒)。
- entry: `FL_WIN64_DIR=... python3 analysis/flapi/pe_handler_probe.py clearLog dumpScoreLog`。clearLog は entry 0x151ac80・fn 0xd6a1f0・flags 4 (NOARGS)、dumpScoreLog は entry 0x151ac60・fn 0xd6a060・flags 3 (VARARGS|KEYWORDS、kwsig `i|i`)。
- 署名: `analysis/flapi/flapi_table.json`。clearLog `()→None`、dumpScoreLog `(time:int, silent:bool=False)→None`。

## 確定事項 (PE VA)

### 1. dispatch `0xd843d0` の out の写し方

引数: rcx=obj・rdx=out・r8=callback・r9=ctx・スタック arg5〜arg10 (`[rbp+0x80..0xa8]`)・arg11 (`[rbp+0xb0]`) = flag。

| 段 | VA | 動作 |
|---|---|---|
| 初期値 | 0xd843e9 | `*out = -2` (sentinel) |
| gate | 0xd843f0〜0xd84403 | `[obj+0x50]` が非 0 かつ `0xd84f30` が偽 → `0xd84500` で out を返す (コールバック非実行、out=-2) |
| job 生成 | 0xd84409〜0xd8446b | `0xd841e0` で job を確保。`job+0x18..0x40` ← arg5〜arg10、`job+0x58` ← callback、`0x4133f0(job+0x48, ctx)` |
| 同期実行 | 0xd844a8〜0xd844bd | thunk `0xd84290` (`call [job+0x58]`、rcx=job) を `0x526190` で実行 |
| 写し | 0xd844c2〜0xd844db | `out+0x08 = job+0x10`・`out+0x10 ← 0x4133f0(job+0x50)`・**`out[0] = job+0x60`** (status) |
| 後始末 | 0xd844f8〜0xd84500 | `0x40faa0(job)` で解放。rax = out |

### 2. 2 関数の呼出し鎖と述語

- clearLog `0xd6a1f0`: `dispatch(obj, &out, cb=0xd6a1a0, ctx=0, arg5..10=0, flag=1)` → `0xd82c20(out[0])` を返す (0xd6a268〜0xd6a278)。
- dumpScoreLog `0xd6a060`: PyArg `i|i` (time `[rbp+0x9c]`・silent `[rbp+0x98]`、既定 0)。解析失敗 (eax≤0) は `0xd82c20(eax)` へ直行 (0xd6a0df)。成功は `dispatch(obj, &out, cb=0xd69ff0, arg5=time, arg6=silent, flag=1)` → `0xd82c20(out[0])`。
- 2 つのコールバックの共通の述語 P: `G=[0x15e4790]`・`X=[G]`・`Y=[X+8]`・`P = call [[Y]+0x98]`。P 偽 → `job+0x60 = -2` のまま返る (効果なし)。P 真 → `job+0x60 = 0` にして効果を行う。
  - `0xd6a1a0` (clearLog): P 真で `0x11eb5f0(dl=1)` (0xd6a1d6〜0xd6a1e2)。
  - `0xd69ff0` (dumpScoreLog): P 真で `0x124c020(rcx=[[0x15e0ff8]], edx=job+0x18 (time), r8b=(job+0x20 == 1) (silent))` (0xd6a026〜0xd6a03c)。
  - P の `[+0x98]` 形は REPORT_PY87 の safeToEdit (0xd6a2c0) と同じだが、同一の述語かは未照合。

### 3. 下位関数

- `0x11eb5f0(dl=flag)` (0x11eb5f0〜0x11eb69f): flag≠0 は `0x12df090(*[0x15e3158])` を呼ぶ (0x11eb68f)。flag=0 は文言を組んで `0x9636a0` (edx=0x20036) を呼び、戻り値 0x100 のときだけ `0x12df090` を呼ぶ。`0x9636a0` の中身は未読。rcx (obj) は `0x11eb5f0` 内で使われない。
- `0x124c020(obj, time, silent)` (0x124c020〜): 先頭で flags 定数と比較 (0x124c0b2)。一致かつ silent=0 は文言を組んで `0x9635b0` (edx=0x30) を呼ぶ。silent≠0 は出力せず終わる (0x124c0c6 → 0x124c4c4)。不一致経路 (0x124c136〜) は `0x10601e0` を呼ぶが未読。time の使われ方 (0x124c172 の `time*1000`) は未確定。

### 4. -2 の Python 側

- `0xd82c20(-2)` (`REPORT_PY61` §4-2 の既存読み): status<0 は 0xd82c6a〜0xd82c7e で報告ゲート `R = call [[[0x861b1f]+8]+0x88]` を読む。R=0 は 0xd82dd0 → `0xc38bc0` (0xd82dd0〜0xd82dd9。REPORT_PY40 の読みで、グローバル値を返すだけ。None に相当)。R≠0 は文言 "Operation unsafe at current time" の例外 (FL_E_UNSAFE = code 3・RuntimeError)。
- **R の実行時値は未確定**: `0x861b1f` の初期値と `[+0x88]` の実装は未読。
- -2 になる経路は 2 つ: (a) dispatch gate (`0xd84f30` 偽)、(b) 述語 P 偽。両方とも実行時値に依存し、静的には決まらない。

## 実装

- `host/fl_mock.mjs`: `general.clearLog` (arity 0) と `general.dumpScoreLog` (arity 1〜2、int 検査) を None で返す。
- `provider/fl_engine.c`: 同じ。`NARGS(0,0)` / `NARGS(1,2)` と `A_INT`。
- 効果 (0x12df090・0x124c020) は API から観測できないため状態を持たない。P と gate は真の定数とし、-2 の経路は到達させない (仮置き)。
- `tests/general_diff.mjs`: 呼出し 3 件と引数違い・型違い 4 件を追加 (計 16 件。既存 9 件)。
- `tests/provider_check.mjs`: `pe125` (2 関数) を追加。実装 84→86、未実装 351→349 (PY-125 の PR 作成時の base 上)。main 取り込み後は main 側の `pe100` (2 関数)・`pe119` (6 関数) を含むため、期待値は 実装 92→94、未実装 343→341 (main `875eba29` まで)。main `8fd940bb` の取り込み後は main 側の `pe121` (5 関数) を含むため、97→99、未実装 338→336 (merge commit `6a9fe2df`)。

## 検証

測定 commit: `6a9fe2df` (コードを変えた最後の commit。main `8fd940bb` を取り込んだ merge)。main は `875eba29` の取り込み後にも進んだため、再 merge した。競合は `host/fl_mock.mjs` と `tests/provider_check.mjs` の 2 件で、両側の追加 (PY-121 の screen 5 関数と PY-125 の 2 関数) を残した。以後の commit は REPORT_PY125.md のみ。
環境: runner 4 core。測定中の load average は 0.11〜0.18 (`uptime` 21:55:18〜21:55:46。直前のビルドの後)。素材: `fl-win64` ([WIN64]) を展開し、`extracted/block00031_PE.bin`・`block25159/24429/24430/24618_DATA.bin` を使う (`FL_WIN64_DIR` = [WIN64] の展開先)。emsdk は [EMSDK] の 6.0.12。この run は launch 時に `toolchain-emsdk` が展開されていなかったため、上流から導入した (`git clone` emsdk → `./emsdk install 6.0.12` → `./emsdk activate 6.0.12`、約 2 分)。PR 本文に `oc_artifacts: fl-win64 toolchain-emsdk` を書いた。

前提の生成物 (gitignore): `bash fetch_inputs.sh` (rc 0)・`bash build_cpython_wasm.sh` (rc 0、3 分 50.6 秒。`e3154671` の tree で作成。以後 `tools/python/src`・`analysis`・CPython ビルドスクリプトは変わっていない (`git diff --stat e3154671 6a9fe2df -- tools/python/src tools/python/analysis tools/python/build_*.sh` は空))・`FLPY_SKIP_TABLE=1 bash build_flpy.sh` (rc 0、4.6 秒。`6a9fe2df` で再ビルド)・`bash provider/build.sh` (rc 0、0.7 秒。`gen_provider.py --check-handlers` でハンドラ 99)。

| コマンド | 結果 | wall |
|---|---|---|
| `node tests/general_diff.mjs` | calls 16、diffs 0、PASS (rc 0) | 0.037 秒 |
| `node tests/provider_check.mjs` | PASS (435 / 実装 99 / 未実装 336 / MCP 静的 60) (rc 0) | 0.278 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback 往復 true (rc 0) | 1.269 秒 |
| `node tests/all_tools.mjs` (既定 JS mock) | 48/48 ok、host_calls 37,425、callback 往復 true (rc 0) | 1.286 秒 |
| `node tests/mixer_diff.mjs` (main 側の追加分。既定色 0xff636c71 を mock と wasm で検査) | calls 59、diffs 0、PASS (rc 0) | 0.039 秒 |
| `node tests/screen_diff.mjs` (main 側 #2985 の追加分) | calls 32、diffs 0、PASS (rc 0) | 0.044 秒 |

ネガティブコントロール (`docs/WORKFLOW.md` §5): `host/fl_mock.mjs` の `clearLog` の戻り値を `undefined` から `0` にすると、`node tests/general_diff.mjs` は `AssertionError [ERR_ASSERTION]: general 差分 1 件` で rc 1。元に戻すと calls 16・diffs 0・PASS (rc 0)。

コード差分 (前回の測定 commit `e8604912` から `6a9fe2df` まで。`tools/python` の .md 以外。main 側の PY-118 既定色・PY-121 screen 状態・両者の merge 解消と、本 PR のコメント修正):

```
$ git diff --stat e8604912 6a9fe2df -- tools/python ':!*.md'
 tools/python/host/fl_mock.mjs         | 13 +++++--
 tools/python/provider/fl_engine.c     | 14 ++++++--
 tools/python/tests/mixer_diff.mjs     |  6 ++++
 tools/python/tests/provider_check.mjs |  8 +++--
 tools/python/tests/screen_diff.mjs    | 67 +++++++++++++++++++++++++++++++++++
 5 files changed, 100 insertions(+), 8 deletions(-)
```

測定 commit から本 REPORT の commit までの差分 (`git diff 6a9fe2df HEAD -- tools/python ':!*.md'`) は空 (本 commit は REPORT_PY125.md だけを変える)。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x12df090` (クリア本体) と `0x124c020` (ダンプ本体) の効果 | mock/C は効果を持たない。観測できる戻り値は None のみ | 子 #3045 (PY-145) |
| -2 の Python 側: 報告ゲート R の実行時値、述語 P、dispatch gate `0xd84f30` の条件 | -2 の経路 (None か RuntimeError) を確定できない。mock/C は到達させない | 子 #3045 (PY-145) |
| `0x4133f0`・`0x526190`・`0x425210` の中身 | `out+0x08`・`out+0x10` の意味。両関数は読まないので実装には影響しない | 本表のみ |
</content>
