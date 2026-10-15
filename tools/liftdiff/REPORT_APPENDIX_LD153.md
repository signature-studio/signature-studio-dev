# liftdiff LD-153 (#3349): hybrid の InitUnits native segv の原因と修正

親: #1464 (LD-50) / 前提: `REPORT_APPENDIX_LD42.md` §4・§6・§7、`REPORT_APPENDIX_LD25.md` §2。
測定 commit: `bb94bce77` (コードを変えた最後の commit)。

## 1. 原因 (実測・機械語で確定)

`System.@InitUnits` (image 0x4120c0) は InitTable の `(init, fini)` 組を先頭から全件走査し、
`init != 0 && *init != 0` のとき `call qword ptr [rbp+0x38]` (= `init` 自体へ call) する (逆アセンブル: capstone)。
hybrid の boot 状態では InitTable (`0x13768b0`・count 942) は正しく入っている (`precondition ok=True`)。

segv の時の native レジスタ (`check_initunits` の hybrid 行・`liftdiff.py run --fn 4120c0 --pattern z`):

| 項目 | 値 | 読み |
|---|---|---|
| fault | `addr=0x0`・`rip=0x500100c0` | rip は image 外 |
| rax | 0 | `add byte [rax], al` (`00 00`) が addr 0 に書く |
| `0x500100c0` | `LD_FAKEPROC_BASE (0x50010000) + 6 * 32` | GetProcAddress の仮 proc index 6 の thunk 番地 (`rt/ld_core.h`) |

仮 proc の thunk (`mov r10, imm; mov r11, stub; jmp r11`) は `ld_fake_ptr(i)` を呼んだ時にだけ敷かれる。
boot の entry 実行では GetProcAddress が index 6 を登録して thunk を敷いたが、boot state を **別プロセス** (check / batch の fresh native) へ移送すると、
状態中の値 `0x500100c0` は指すのに、その番地は 0 埋めのまま (`/proc/PID/mem` で確認: thunk 生成前は `0x500100c0` が全 0)。
SNAPSHOT で敷くのは VMT slot (index 256〜263) だけだったため、移送先では未生成のまま実行され segv した。

## 2. 修正

`rt/ld_core.h`: `ld_snapshot` で `ld_fakeproc_thunks_init()` を呼び、GetProcAddress 域 (`0..LD_VMT_IDX0-1`) の thunk を全部敷く。
移送先での名前は登録されず `?freeproc` になる (`ld_fakeproc_name`)。wasm 側は値だけで、呼ぶと ott_dispatch → ret-0 (既存の挙動) なので、native の `?freeproc` は ret-0 系と揃う。
`tests/check_initunits.py`: hybrid で `native_status != ok` が 1 件でもあれば FAIL (exit 1) を追加。出力行に `native_not_ok=N` を足した。

## 3. 受入条件の実測

| 受入条件 | 修正前 (旧 rt) | 修正後 (`bb94bce77`) |
|---|---|---|
| hybrid の InitUnits native 11/11 が ok | segv 11/11 (`native_fault` 11) | **ok 11/11** (`outcome diff` 11・wasm ok) |
| `check_initunits.py` hybrid の FAIL 条件 | (旧 rt の実行で) `native_not_ok=11`・`CHECK_INITUNITS FAIL`・exit 1 (ネガコン) | `native_not_ok=0`・`CHECK_INITUNITS PASS` |
| units 側の空振り | EMPTY 11/11 (従来どおり・FAIL 条件ではない) | 同じ (EMPTY 11/11) |
| e2e | PASS (hybrid の segv 11 件を見逃していた: 判定条件が無かった) | `LIFTDIFF_E2E PASS` (3m09s) |

boot の数字は修正前後で変わらない: hybrid `units_run=928/942`・`first_fail=830` (`10d50d0` segv)・entry_point は InitCount=246 で segv (`rip_rva=0x26833d`)。

### flag=1 経路 (TLS 取得 `0x41d110`) の wasm 側の戻り値

- `0x41d110` は `cmp byte [0x11ec2d8], 0` で分岐する。flag=0 は `gs:[0x58]` 直読み。flag=1 は import thunk `0x41cf60` (`jmp [IAT]`) で `TlsGetValue(index)` を呼ぶ。
- hybrid state で `liftdiff.py run --fn 41d110 --pattern z -v` を実行すると、native / wasm とも `TlsGetValue(0x1)` を 1 回呼び、`outcome equal` (diff 0)。
  - native `rax=0x10480000`、wasm `rax=0x10080000`。差 `0x400000` は `delta` (native heap = wasm heap + delta)。
  - 戻り値は同じ TLS block (heap 内) を指す。wasm 側も `ld_model_call` の共有モデル (`TlsGetValue` は heap の TLS 配列を読む) で値を返すため、hybrid で充足されている TLS slot 1 がそのまま見える。
- 本付録では units state の flag 値は測っていない (flag=0 の gs 経路の wasm 側の扱いは未確認。既定 batch は units のまま据え置く。判断は #1464)。

## 4. 既定 batch (sample:800) への影響

同じ `boot_state.json` で旧 rt と修正版の batch を比べた (`tests/ld42_transition.py`・関数単位・`batch --set sample:800 --state auto`):

| 実行 | rt | 一致 | 不一致 | 実行不能 |
|---|---|---|---|---|
| 単独 (`batch_sample_800_old.jsonl`) | 旧 (`cf296603`) | 360 | 233 | 207 |
| 単独 (`batch_sample_800_fix1.jsonl`) | 修正 (`bb94bce77` と同コード) | 360 | 234 | 206 |
| e2e [4/4] (`bb94bce77`・最終) | 修正 | 361 | 233 | 206 |

旧と修正 (単独) の関数単位の変化は **1 件**: `0x407320` `unexec → mismatch` (旧は全 pattern `native_fault` = 移送された仮 proc の segv。修正後は native ok で、タグ `icall_drop`・`import_call_seq`)。
単独と e2e の間の ±1 の揺れは LD-25 §3 と同じ (一致 360〜361)。判定基準 (units 既定) は変えていない。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| wasm 側の InitUnits は unit を 1 つも呼ばない (`icall_drop`: `call [rbp+0x38]` が lift で落ちる)。hybrid の InitUnits 比較は 11/11 `diff` で、`equal` にはならない | InitUnits の wasm 一致は lift 欠陥 (D1 系) の修正が要る | #1464 |
| hybrid の unit 単位フェーズの残り 3 unit が segv (最初 unit 830・`10d50d0`) | boot 928/942。InitUnits の native は ok だが、個別の 830 の原因は未同定 | #1464 |
| 既定 batch を hybrid にするか (遷移の根拠) | 基準値の更新を伴う | #1464 |

## 6. 検証

- 測定 commit `bb94bce77`・`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/liftdiff/liftdiff_e2e.sh --m11-only`: rc 0・**3m09s**・load 0.74→6.36・**LIFTDIFF_E2E PASS**。
  - [3b/4] `CHECK_INITUNITS PASS` (units: EMPTY 11・native_not_ok 0 / hybrid: EMPTY 0・native_not_ok 0・diff 11)。
  - [4/4] sample:800: 一致 361 / 不一致 233 / 実行不能 206。
- ネガコン: 旧 rt (`git show cf296603:tools/liftdiff/rt/ld_core.h` でビルド) で `tests/check_initunits.py` → `native_not_ok=11`・`CHECK_INITUNITS FAIL`・exit 1。
- 素材: `fl-win64 toolchain-retdec toolchain-emsdk work-m11 work-liftdiff` (`$HOME/artifacts`)。emsdk は `[EMSDK]` (`docs/REFERENCES.md`)。
- 測定 commit 以降のコード差分: `git diff bb94bce77 HEAD -- tools/liftdiff/rt tools/liftdiff/tests tools/liftdiff/ldlib tools/liftdiff/liftdiff_e2e.sh` の出力は 0 行 (測定 commit の後の commit は REPORT 付録と `docs/DOC_MAP.md` の登録だけ)。
