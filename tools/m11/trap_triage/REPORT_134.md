# #134 (M11-N5): unit 56 (VA 0x16fde0) の fail-fast 辺の入力と、probe が読んだ object (訂正版)

**既知類型との関係**: 該当なし (DEFECTS.md の D1a〜D23 への対応は未照合)。`function_410360` の vtable 呼出し脱落は間接 call 脱落の類型に近いが、icall §4 (D1〜D13) との突合は未実施 (別体系。下の未解決 #2)。

**訂正 (review round 1 対応)**: 初版の結論 (a)(b)(c) は撤回する。probe が読んだ 2 つの object (VA `0x566d68` / `0x566eb0`) は、fail-fast 辺の入力 (R と list) ではなかった。§3 の機械語照合で、この 2 object は `function_56fde0` が `function_8c5eb0` へ渡す `this` (Delphi の VMT) であり、guard の件数は `410320(this, 1)` の戻り値 R の経路から読まれると確認した。R と list の trap 時の値は未測定。

## 0. 結論 (現時点で言えること)

- **実測** (probe n=3 + NC): 2 つの VMT object の件数 (+0x14)・先頭 qword・`[vt-0x50]` は trap 時点で 3 回同一。全 942 unit の実行で、両 object の件数・先頭 qword は変わらなかった (`changed_after_unit: []`)。
- **静的** (PE 機械語): `56fde0` の 2 つの `8c5eb0` 呼出し (`570296`・`5702ae`) は、どちらも `dl=1` (bit 7 が立たない)。このとき `410320` は `[this-0x30]` を呼び、その戻り値 R を `8c5eb0` が使う。`[this-0x30]` は 2 つの VMT で同じ `0x40f960`。
- **guard の入力**: 件数は `[list + 0x14]`、list は `8c67a0(R)`。fail-fast 辺 (`8c608d`) の receiver は R (`410360(R)`)。
- **未測定 (B1)**: R・list・R の vtable (`[R-0x50]`)。件数 0 や vtable の無効値は、R について何も言えない。
- **撤回**: (a) 件数 0 は実行時の状態である、(b) 書込み元は skip unit か lift 脱落 store、(c) native は `[vt-0x50]` へ call する。いずれも guard の入力 R を測っていないため、結論にできない。
- **未実施の理由**: この run の `$ARTIFACTS_DIR` には `fl-win64` しか無く、`toolchain-retdec`・`toolchain-emsdk`・`work-m11` が無い。IR・`m11_boot.cjs`・`m11_image.bin` を生成できないため、probe を再実行できない。PR 本文に `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk work-m11` を入れ、次の run で素材を取得する (§5)。

## 1. 測定条件

| 項目 | 値 |
|---|---|
| 測定 commit (probe コード) | `a380b7c4` (`m11_survey.mjs` の env-gated probe と `probe_134.sh`。この commit が最後のコード変更。`46c92356..a380b7c4` は 1 commit) |
| 基準 survey 数値 | `46c92356` (a380b7c4 の直前。probe 無し) で測定。下 §2 |
| 検証 HEAD | 本 commit (訂正版)。コードの差分は `m11_survey.mjs` と `probe_134.sh` の**コメントのみ** (挙動不変)。文書の差分は REPORT_134.md と DOC_MAP の 1 行 |
| 差分の証跡 | `git diff a380b7c4 HEAD -- tools/m11/m11_survey.mjs tools/m11/trap_triage/probe_134.sh` は、コメント行の差分のみ。`git diff --stat a380b7c4 HEAD -- tools/m11` は REPORT_134.md のみ (実行結果は PR 本文の検証節) |
| PE | `fl-win64` の `extracted/block00031_PE.bin`、sha256 `b2c64da40921cf262c15c5b25c2b0422e4d1851e953c87e0bc38ed2c19f9496d` (本 run で `sha256sum` と一致を確認) |
| 素材 (前回 run) | `work-m11.tar.zst` を `tools/m11/work/` へ展開して測定した。本 run では再測定していない |
| `work/lift_pe.sha256` | 手で作成。内容は PE の sha256 hex 1 行 (パス無し)。`m11_e2e.sh` の 62 行 `echo "$PE_SHA" > work/lift_pe.sha256` と同じ書式。展開物に無く、全再生成は `m2/work/ghidra_dll` 欠落で `m11_bounds.py` が失敗するため手で作った |
| IR (前回 run) | `m11_gen_ir2.sh` で再生成。`ir_sha256` = `de46cada…8636`、ldfix/qstore = applied |

## 2. 基準の数値 (m4)

| 測定 | HEAD | survey ok / trap / miss / noproc | 備考 |
|---|---|---|---|
| 本 PR の基準 (前回 run) | `46c92356` (probe 無し) | **872 / 23** / 46 / 1 (clobber 0) | `m11_e2e.sh` n=1。stage 4/6、units_run 53 / 942 |
| issue 記載 | `750340fc` | 871 / 24 / 46 / 1 | issue 本文の値 |
| #134 の 2026-10-13 実測 | main `427eab37` | 870 / 25 (review 指摘の値) | 出所の REPORT は本 run で未照合。miss / noproc は未確認 |
| main の現在 (`b745bcbc`) | — | **未測定** | 本 run は素材不足で e2e 不可 |

- 872/23 と 870/25 の差は HEAD の差 (`750340fc`・`427eab37`・`46c92356`) による可能性があるが、切り分けは未実施。
- **既定 off の挙動**: probe は `M11_PROBE_134=1` のときだけ動く。a380b7c4 の既定 off の survey を本 run で再測定していない (素材不足)。コードの diff 精読で挙動不変を確認した (review の確認と同じ)。
- 基準 e2e の内訳: trap 内訳は unreachable 1、halt0→longjmp 7、OOB 15。停止は `unreachable` @ `function_8c5eb0` <- `function_56fde0`。

## 3. probe の実測 (`bash trap_triage/probe_134.sh`, n=3 + NC)

**注意: probe が読む対象は VMT (`this`) であり、guard の入力ではない。下の表の値は VMT の状態である (§4)。**

| object (linear / VA) | 件数 +0x14 (i32) | 先頭 qword (wasm / VA) | `[vt-0x50]` (wasm の値) |
|---|---|---|---|
| 1469800 / 0x566d68 | 0 (n=3: 0, 0, 0) | 0x168b50 / 0x568b50 | `0xffffd3a8e8000000` (n=3 同一) |
| 1470128 / 0x566eb0 | 0 | 0x16e0d0 / 0x56e0d0 | `0xccccccccccc35f5e` |

- n=3 の範囲: 件数・先頭 qword・`[vt-0x50]` は 3 回とも同一 (min = max)。trap 文字列は 3 回とも `unreachable`。
- 全 942 unit: 両 object の件数・先頭 qword は、どの unit の前後でも変わらなかった (`changed_after_unit: []`)。これは **VMT の不変性**の証拠であり、R と list の不変性の証拠ではない。
- **ネガティブコントロール** (NC): 読み取り先を 1 byte ずらした (`M11_PROBE_134_OBJS=1469801,1470129`) とき、件数は `536870912` (0x20000000)、先頭 qword は `0xf000000000001800` 系になり、VMT の値と一致しなかった。読み取り先が object に依存することの確認にはなる。
- NC は別アドレスの値であり、実 object の不変性の証拠にはならない (n=4 と数えない。実 object は n=3)。
- probe の `[vt-0x50]` は、`vt = [obj]` (先頭 qword) の `-0x50` 位置の値 (obj を instance と見たときの vtable 呼出し先)。guard の receiver (R) の vtable ではない。wasm の `410360` は IR で vtable を呼ばない (§4 の 410360 の行)。

## 4. 静的照合 (PE の機械語、capstone。PE sha256 `b2c64da4…9496d`)

| 位置 | 機械語 | 意味 |
|---|---|---|
| `8c5eb0`〜`8c5ed1` | `mov [rbp+0x88], dl`; `cmp byte [rbp+0x88], 0`; `je 8c5ef5` | dl == 0 なら R = this |
| `8c5eda`〜`8c5eee` | `rcx = [rbp+0x80]` (this); `rdx = dl`; `call 410320`; `mov [rbp+0x80], rax` | dl ≠ 0 なら R = `410320(this, dl)` |
| `410320` | `test dl, dl`; `jl 410331`; (bit 7 が立たない) `call [rax-0x30]` (rcx = this); `ret` | bit 7 が立つ → R = this。立たない → R = `[this-0x30](this)` の戻り値 |
| `8c5ef6`〜`8c5f0c` | `rcx = [rbp+0x80]` (R); `call 8c67a0`; `[rbp+0x58] = rax` (list); `ebx = [list+0x14]` | 件数 = `[list+0x14]`、list = `8c67a0(R)` |
| `8c608d` | fail-fast 辺: `410360([rbp+0x80])` | receiver は R |
| `410360` | `rbx = [rax]` (R の先頭 qword); `call [rbx-0x50]` | 機械語では R の vtable を呼ぶ。**IR では `ret i64 %arg1` で脱落** (下の未解決 #2) |
| `56fde0`〜`5702be` (1 関数。途中に ret 無し) | `570291`〜`570296`: `rcx = [0x566ca0]` (= 0x566d68); `dl = 1`; `xor r8, r8`; `call 8c5eb0`。`5702a2`〜`5702ae`: `rcx = [0x566de8]` (= 0x566eb0); `dl = 1`; `xor r8, r8`; `call 8c5eb0` | 2 呼出しとも `dl = 1` (bit 7 が立たない)。よって `410320` は `[this-0x30]` を呼ぶ |
| `[0x566d38]` = `[0x566e80]` | `0x40f960` | 2 つの VMT の `-0x30` スロットは同じ関数 |

- 以上から、`function_56fde0` が unit 56 で `8c5eb0` を呼ぶとき、guard が読む件数は `0x40f960(this)` の戻り値 R の list の +0x14 である。probe が読んだ `this` (VMT) の件数ではない。
- `dl = 1` のとき、R が this になるのは `410320` が bit 7 を見て this を返す場合だけ。`dl = 1` では bit 7 が立たないので、R = this にはならない。(dl = 0 のときも R = this になるが、この呼出しでは起きない)
- R の値は `0x40f960` の実行結果で、静的には決まらない。

## 5. 次の作業 (B1 の採取仕様・未実施)

採る対象 (trap 時点。n=3 + NC):

1. (i) arg2 の値 (`dl`・bit 7。期待値は `dl = 1`)
2. (ii) `410320` の戻り値 R
3. (iii) `8c67a0(R)` の戻り値 list
4. (iv) R と list それぞれの `+0x14` (i32)・先頭 qword・`[vt-0x50]` (先頭 qword の -0x50 位置)

手段 (どちらでもよい。採った対象を REPORT に明記する):

- `tools/m11/trap_triage/inspect_trap.mjs` (#1602、REPORT_1602 §16) で trap 時の wasm local を読む。`M11_INSPECT_FN` に `8c5eb0` の wasm 関数 index、`M11_INSPECT_FRAMES` と `M11_INSPECT_PEEK` で R・list を追う。`--wasm-enforce-bounds-checks` が要る。
- または `m11_ov.c` の C 転記で戻り値を大域に残す (再生成が要る)。

NC: R 系の読み取り先を 1 byte ずらす。繰返しは n=3。

素材: `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk work-m11` (PR 本文に記載)。

## 6. 判定 (訂正後)

| 判定 | 初版 | 訂正後 | 根拠 |
|---|---|---|---|
| (a) 件数 <= 0 は実行時の値か | 実行時の値 | **未判定** (R の件数は未測定) | guard は `[list+0x14]` を読む (§4) |
| (b) skip 3 が初期化するはずの object か | 未確定 | **未判定** (VMT の不変性のみ確認) | `changed_after_unit` は VMT の不変性で、R と list の不変性ではない |
| (c) vtable[-0x50] は有効な VA か | 無効 | **未判定** (probe の値は VMT の値) | `410360` の receiver は R (§4)。wasm では IR 脱落で vtable を呼ばない |

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| B1: R・list・R の vtable の trap 時実測 (§5) | (a)(c) の判定が未確定。unit 56 の原因の特定は未達 | 本 PR の次の round (`oc_artifacts` 行で素材を取得して実施) |
| `function_410360` の `call [rbx-0x50]` が IR で脱落 (`ret i64 %arg1`)。wasm の後段 (R の vtable 呼出し) が消えている疑い | 間接 call 脱落の別 miscompile の疑い。icall §4 (D1〜D13) との突合は未実施 | PM 判断 (子 issue 候補) |
| `410320` が `[this-0x30]` を呼ぶ先 `0x40f960` の wasm 側の lift 検証 | R の値が native と一致するかは未確認 | 上の B1 と同じ round |
| skip 3 の Init 0xfa9390 の出所 | skip 3 の unit の init が wasm で走らない疑い | PM 判断 |
| 基準 survey 数値の差 (872/23・871/24・870/25) | HEAD 差の影響は未切り分け | #718 への追記候補 (PM 判断) |

## 8. 再現

```sh
export FL_WIN64_DIR="$RUNNER_TEMP/fl-win64"
cd tools/m11
bash m11_e2e.sh                       # 基準 (stage 4/6, units_run 53, survey 872/23/46/1 — 46c92356 の値)
bash trap_triage/probe_134.sh         # VMT の probe n=3 + NC (出力は work/v134/)。guard の入力 R は採らない (§5 が未実施)
```

- 静的照合は PE だけで再現できる (§4)。`capstone` と `pefile` が要る。`block00031_PE.bin` の sha256 は §1。
