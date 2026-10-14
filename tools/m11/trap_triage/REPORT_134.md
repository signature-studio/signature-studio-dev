# #134 (M11-N5): unit 56 (VA 0x16fde0) の trap 時点の object 状態と skip 3 の切り分け

**既知類型との関係**: 該当なし (DEFECTS.md の D1a〜D23 への対応は本 run で未照合)。ただし `function_410360` の `call qword [rbx-0x50]` が IR から脱落している点は間接 call 脱落の類型に近く、icall §4 の D1〜D13 との突合は未実施 (下表 #2)。

**結論 (切り分け)**
- (a) 件数 <= 0 は実行時の状態である。trap 時点で件数 (+0x14) は 0 で、静的 PE の 0 と一致した (n=3 全件)。
- (b) skip 3 (unit 30/39/40, 0 始まり index 29/38/39) は Init 値 0xfa9390 を持ち、icall miss で skip される。survey の全 942 unit 実行 (n=4) で、実行された unit が両 object を書き換えた例は 0 件。よって wasm 上の object 状態は静的データのまま固定で、書込み元は「skip された unit」か「lift で脱落した store」のどちらかである。**未特定**。
- (c) vtable[-0x50] は**有効な VA ではない** (obj1: `0xffffd3a8e8000000`, obj2: `0xccccccccccc35f5e`)。機械語 (`8c608d`→`410360`) に従うと、件数 <= 0 かつ arg2 下位 byte != 0 のとき native はこの値へ call する。native が正常に完走するなら、native の object は wasm と違う状態 (件数 > 0 か vtable 違い) のはずで、(b) 側 (書込み元の欠落) が有力。これは推定で、native 側の値は未測定。

## 0. 測定条件

| 項目 | 値 |
|---|---|
| HEAD | `46c92356` (origin/main, worktree `ws-134`, branch `134-m11-unit56-state`)。issue 記載の `750340fc` は祖先。`tools/m11` は 308 file 差分あり |
| PE | `$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin` (sha256 `b2c64da4…9496d`) |
| 素材 | `work-m11.tar.zst` を `tools/m11/work/` へ展開。`work/lift_pe.sha256` は**手で書いた** (展開物に無く、`m11_e2e.sh` が全再生成に入るのを避けるため。`m2/work/ghidra_dll` が無く `m11_bounds.py` が失敗するため全再生成は不可) |
| IR | `m11_gen_ir2.sh` 再生成, `ir_sha256` = `de46cada…8636`, ldfix/qstore=applied, guard699 既定 on |
| 計測コード | `tools/m11/m11_survey.mjs` の env-gated probe (`M11_PROBE_134=1`, 既定 off)。既定 off の survey 出力は変更前と同一 (ok 872 / trap 23 / miss 46 / noproc 1 / clobber 0) |
| 所要 | survey 1 本 約 17 秒 (n=3 + NC で約 70 秒) |

## 1. 基準の再現 (`bash tools/m11/m11_e2e.sh`, n=1)

| 項目 | 本 run (46c92356) | issue 記載 (750340fc) |
|---|---|---|
| 到達 stage | 4/6 | 4/6 |
| units_run / total | 53 / 942 | 53 / 942 |
| 停止 | `unreachable` @ `function_8c5eb0` <- `function_56fde0` | 同じ |
| survey ok / trap / miss / noproc | **872 / 23** / 46 / 1 (clobber 0) | 871 / 24 / 46 / 1 |
| trap 内訳 | unreachable 1, halt0→longjmp 7, OOB 15 | — |

survey の ok/trap が 1 ずれる。HEAD 差 (`750340fc` と `46c92356`) による可能性があるが、本 run では切り分けていない。以降の数値は本 run (46c92356) の値。

## 2. trap 時点の object 状態 (`bash trap_triage/probe_134.sh`, n=3)

probe は unit 56 の `try/catch` 直後 (clobber 復元より前) に読む。linear アドレスは IR 定数と同じ (`VA - 0x400000`)。wasm が保持する pointer 値は LVA 形式 (例: 0x168b50 = VA 0x568b50)。

| object (linear / VA) | 件数 +0x14 (i32) | 先頭 qword (wasm / VA) | vtable[-0x50] (wasm の値) | 静的 PE (img) |
|---|---|---|---|---|
| 1469800 / 0x566d68 | **0** (n=3: 0, 0, 0) | 0x168b50 / 0x568b50 | **0xffffd3a8e8000000** (n=3 同一) | 件数 0, 先頭 0x168b50, vt[-0x50] 同値 |
| 1470128 / 0x566eb0 | **0** | 0x16e0d0 / 0x56e0d0 | **0xccccccccccc35f5e** | 件数 0, 先頭 0x16e0d0, vt[-0x50] 同値 |

- n=3 の範囲: 件数・先頭 qword・vt[-0x50] はいずれも 3 回で同一 (min = max)。trap 文字列は 3 回とも `unreachable`。
- **trap 後の書換え**: trap 直後の値と survey 終了時の値は同一。さらに全 942 unit の前後で両 object の件数・先頭 qword が変わった unit は 0 件 (`changed_after_unit: []`, 本物の object の n=3 全件)。
- vtable[-0x50] 側は `0xccccccccccc35f5e` (0xcc は int3 の詰め物と同型) と `0xffff…` の 2 種で、どちらも image 範囲 (0x400000〜) の有効な code pointer ではない。

### ネガティブコントロール

probe の読み取り先を 1 byte ずらした (`M11_PROBE_134_OBJS=1469801,1470129`) 結果、件数は `536870912` (0x20000000)、先頭 qword は `0xf000000000001800` 系となり、本物の object の値 (件数 0, 0x168b50) と一致しなかった。読み取り先が object に依存していることを確認した。

### 補足: 本 IR の `function_410360` に vtable 呼出しが無い

`410360` の機械語は `mov rbx,[rax]; call qword [rbx-0x50]` を行い、`[rbp+0x60]` を返す (`trap_triage/disasm_fn.py 410360`)。一方、本 run の `boot_final.ll` の `function_410360` は `ret i64 %arg1` のみで、`call [rbx-0x50]` が脱落している。よって wasm では件数 > 0 の経路の vtable 呼出しも消えている。これは #134 の trap とは別の silent miscompile の候補。

## 3. skip 3 の出所 (`units_skipped`)

- `m11_ov.c` `function_4120c0` (InitUnits): 各 unit で `ICALL_AT(0x412126, proc, ...)` を呼び、icall miss が出た unit は `units_skipped++` で `units_run` に入らない。
- survey の `M11_SURVEY_DETAIL` (本 run) で、skip 対象は 0 始まり index **29・38・39** (= issue の 1 始まり unit 30・39・40)。3 unit とも Init = **0xfa9390** で `kind: miss, ret: 2` (closure 外)。
- 3 unit が同じ Init を持つこと、0xfa9390 が関数先頭でないことは前回記録 (REPORT.md §14) と一致する。本 run では PE 上の出所を特定していない。
- index 56 (1 始まり 57, VA 0x16fde0) が停止 unit で、Halt0 までに 53 + 3 = 56 unit が終わる (REPORT.md §14 と一致)。

**skip 3 が object を初期化するか**: 未確定。wasm では skip 3 は一度も実行されない (miss)。`changed_after_unit` が空なので、実行された 939 unit は両 object の件数・先頭 qword を書かない (他フィールドは未監視)。静的 PE からの直接参照 (imm/disp/RIP 相対) の全数走査は、本 run では完了できなかった (スクリプトは収録せず打ち切り)。

## 4. 判定と解釈

| 判定 | 結果 | 根拠 |
|---|---|---|
| (a) 件数 <= 0 は実行時の値か | **はい** (実行時 0、静的 0 と一致) | probe n=3, NC で読み取り先依存を確認 |
| (b) skip 3 が初期化するはずの object か | **未確定** (書込み元は skip unit か lift 脱落 store) | 実行 unit は書かない (n=4, 942 unit 全件)。skip unit は未実行 |
| (c) vtable[-0x50] は有効 VA か | **いいえ** (0xffff… / 0xcc…) | probe n=3 |

**推論**: 機械語どおりなら、件数 <= 0 かつ arg2 下位 byte != 0 のとき native は `[vt-0x50]` を call する (`arg2 = x | 1` なので下位 byte は非 0)。この値は有効な target ではないため、native が実際にこの状態に入れば落ちるはずである。native が完走する以上、native の object は wasm と違う状態 (件数 > 0、または先頭 qword が違う) にあると推定する。wasm には書込み元が見つからなかったので、書込み元 (skip 3 の unit か、lift で脱落した store) が原因として有力。ただしこれは推定で、native の値は未測定。

## 5. 再現

```sh
export FL_WIN64_DIR="$RUNNER_TEMP/fl-win64"
cd tools/m11
bash m11_e2e.sh                       # 基準 (stage 4/6, units_run 53, survey 872/23/46/1)
bash trap_triage/probe_134.sh         # probe n=3 + NC (出力は work/v134/)
```

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| object (VA 0x566d68 / 0x566eb0) の native 書込み元 (skip 3 の unit か、lift で脱落した store) の特定。件数 > 0 になる経路 | stage 5/6 未達 (unit 56 の trap)。(c) の推論が正しければ、この書込みを戻すまで unit 56 は native と一致しない | #134 へのコメント、または子 issue (本 PR では起票しない) |
| `function_410360` の `call qword [rbx-0x50]` が IR から脱落 (`ret i64 %arg1`) | 間接 call 脱落の別 miscompile の疑い。icall §4 (D1〜D13) との突合が未実施 | 子 issue 候補 (PM 判断) |
| skip 3 の Init 0xfa9390 の出所 (3 unit が同値、関数先頭でない) | skip 3 の unit の init が wasm で走らない | 上の子 issue と同じ |
| survey 数値の差 (872/23 vs issue の 871/24) | HEAD 差 (750340fc vs 46c92356) の影響は未切り分け | #718 への追記 |
