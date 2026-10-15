# liftdiff LD-158 (#3470) — ret=i128 39 関数の実戻りレジスタの実測と、xmm0 戻り 8 関数の署名修正

> 親 #976 (LD-24) の子 (前段 [`REPORT_LD38.md`](REPORT_LD38.md) §1 の『推定』を実測で置き換える)。
> 既知類型との関係: 該当なし (case 生成と署名型の問題)。副次観測の xmm 入力欠落は tag `xmm_arg_drop` (`docs/DEFECTS.md` 既存類型) と一致。
> 測定 commit: `f61e06d49` (コード差分の最終 commit。以後は本 REPORT のみ変更)。

## 1. 結論

- 39 関数のうち **8 関数** (`6957d0` `6957f0` `695930` `695960` `812df0` `812e70` `cc32f0` `cc3660`) は、
  11 pattern × xfill 2 水準 (計 22 実行) の全てで **rax が一度も書き換わらず**、xmm0 だけが書き換わった (動的実測)。
  実戻りは xmm0 (double) と判定し、署名 ret を `double` に直した (`targets/m11.json` の `ret_override`)。
  `cc32f0` は静的にも `mulsd xmm0, [rcx+0x1090]` の直後に `ret` (§3.3)。呼出し側の戻り値利用は未確認 (§6)。
- 修正後は 8 関数が実行可能になり (修正前は全件 `unsupported_sig`)、8/8 が `mismatch`。case 88 件 (8 × 11) の内訳は
  `diff` 53・`equal` 11・`native_fault` 24 (native の `segv`、`z` `s` `p1` の 3 pattern)。
- 残り **31 関数** は戻り経路を確定できなかった。11 関数は全 22 実行が native `segv` で判定不能。
  20 関数は rax か rdx の書換えを伴い、呼出し側なしでは戻りレジスタを区別できない (§3.1)。
  **rdx のみを書き換える関数は 0 件**。『rdx 戻り』を支持する実測は無い。
- sample:800 の判定は修正前後で同一 (一致 360 / 不一致 234 / 実行不能 206)。e2e (`--m11-only`) は両時点で PASS (§5)。

## 2. 方法 (再現)

- 動的プローブ `tests/ld158_ret_probe.py`: native 実行器 (`rt/ld_native.c`) の戻り後 `rax` `rdx` `x0` (xmm0 下位 64bit) を、
  11 pattern × `xfill` {1, 0} で取得する。`xfill=1` は引数に使われない整数・xmm レジスタに決定的な値を入れる (`rt/ld_native.c` の `ld_case.xfill` 節)。
  - `rax_w`: 戻り後 rax が入口値 `SENTINEL` (`0xCAFEBABE0BADF00D`) と異なる実行が 1 件以上。
  - `x0_w`: 戻り後 xmm0 が入口値 (xfill=1 は 1.25 = `0x3ff4000000000000`、xfill=0 は 0) のどちらとも異なる実行が 1 件以上。
  - `rdx_w`: arg1 が整数の pattern (`z` `s` `p0` `q0` `vm0` `u16`) で、戻り後 rdx が入口値 (`z` は xfill で 0 / `0x12`、他は `SMALL[1]`=5) と異なる実行が 1 件以上。
  - 書換えは『戻り値として使われた』を意味しない (関数内の clobber・呼んだ先の戻り値を含む)。本表は書き込みの実測。
- 静的 (参考・従来の heuristic): `tests/ld38_ret_convention.py` (窓 3 / 窓 8)。REPORT_LD38 §3 と同じ判定。
- 集計: `tests/ld158_summarize.py` → `work/ld158_table.tsv` (gitignore)。
  署名修正の集合 (`targets/m11.json` の `ret_override`) と『動的に xmm0 のみ』の集合の一致も確認する (`OVERRIDE_MATCH True 8`)。
- 再現 (`tools/liftdiff/` で実行。`FL_WIN64_DIR` 必須): `python3 tests/ld158_ret_probe.py && python3 tests/ld158_summarize.py`。

## 3. 件数表 (実測)

### 3.1 動的分類 (39 関数・実測 `work/ld158_probe.json`)

| 動的分類 (書換えのあったレジスタ) | 件数 | 関数 | 扱い |
|---|---|---|---|
| xmm0 のみ | **8** | 6957d0 6957f0 695930 695960 812df0 812e70 cc32f0 cc3660 | xmm0 (double) と判定し署名を修正 (§4) |
| rax + xmm0 | 3 | 6ed480 7ce2e0 ba05f0 | 対象外 (rax 書換えあり・区別不能) |
| rdx + xmm0 | 6 | 13114b0 1311f70 40c420 40c650 6a3a90 (1311ea0 は引数 `i128` の関数) | 対象外 (同上) |
| rax + rdx + xmm0 | 5 | 442670 442890 6a3ac0 40f210 677820 | 対象外 (同上) |
| rax + rdx | 6 | 12657b0 4421d0 45e3c0 45ee00 5b0970 8e6660 | 対象外 (xmm0 は書かれない。rax か rdx かを区別不能) |
| 判定不能 (全実行が segv) | 11 | 45e1a0 45e280 45e2e0 45eb00 45ecc0 45ed20 668390 6683d0 784520 8e7e10 a965c0 | 対象外 (§6) |
| rdx のみ | **0** | — | — |
| 合計 | 39 | | 8 + 3 + 6 + 5 + 6 + 11 = 39 |

- 注: 4421d0 は 10/22、45e3c0・45ee00 は 2/22 の実行だけが ok だった。`n_ok` は §3.4 の関数別表を参照。

### 3.2 静的 (参考・heuristic。決定には使わない)

| 判定 | 窓 3 (既定) | 窓 8 |
|---|---|---|
| xmm0 | 24 | 38 |
| other | 14 | 0 |
| no_ret | 1 | 1 |

- 窓 8 は別の呼出し後の xmm0 を拾うため、件数が増える (`REPORT_LD38.md` §3b の注意と同じ)。
- 判定器のネガティブコントロール (`python3 tests/ld38_ret_convention.py --control`): 3/3 OK (実測 `CONTROL ... OK` × 3)。

### 3.3 xmm0 のみの 8 関数の機械語 (実測・dsm)

| 関数 | 入力 | ret 直前 4 命令 (dsm 実測) |
|---|---|---|
| `6957d0` | `i64` | `movapd xmm0, xmm1` / `mulsd xmm0, [rcx+0x7c]` / `mulsd xmm0, [rip+7]` / `ret` |
| `6957f0` | `i64` | `movapd xmm0, xmm1` / `mulsd xmm0, [rip+0xc]` / `divsd xmm0, [rcx+0x7c]` / `ret` |
| `695930` | `i64` | `mulsd xmm0, [rcx+0x84]` / `mulsd xmm0, [rcx+0x18c]` / `mulsd xmm0, [rip+4]` / `ret` |
| `695960` | `i64` | `movsd xmm1, [rcx+0x84]` / `mulsd xmm1, [rcx+0x18c]` / `divsd xmm0, xmm1` / `ret` |
| `812df0` | `i64` | `movaps xmm0, xmm1` / `mulss xmm0, [rcx+0xc]` / `ret` (float 系の戻り) |
| `812e70` | `i64` | `movaps xmm0, xmm1` / `mulss xmm0, [rcx+0x10]` / `ret` |
| `cc32f0` | `i64` | `movapd xmm0, xmm1` / `mulsd xmm0, [rcx+0x1090]` / `ret` |
| `cc3660` | `i64` | `movapd xmm0, xmm1` / `mulsd xmm0, [rcx+0x10a8]` / `ret` |

- 8 件とも ret 直前は xmm0 への演算で、第 2 引数 (double) は xmm1 から読まれる (`cc32f0` 等)。IR 署名には xmm 引数が無い。
- `ld38` 窓 3 でも 8 件とも `xmm0` (§3.2)。dsm 抜粋は `python3` の直接読み (`ld38` と同じ dsm、`tools/m11/work/boot*.drc.dsm`)。

- 同じ 8 関数の IR は `define weak i128 @function_X(i64 %arg1)` で、本体は `__asm_movapd` と `__asm_mulsd` の i128 演算 (`tools/m11/work/boot_final3.ll`)。
  IR が xmm 値を i128 として持つことが、戻り型の誤りの原因と読める。

### 3.4 関数別表 (39 件・実測)

| 関数 | 入力 | ok / 実行 | 動的 | 静的 窓 3 |
|---|---|---|---|---|
| 12657b0 | i64 | 18/22 | rax+rdx | other |
| 13114b0 | - | 22/22 | rdx+xmm0 | xmm0 |
| 1311ea0 | i128 | 22/22 | rdx+xmm0 | xmm0 |
| 1311f70 | - | 22/22 | rdx+xmm0 | no_ret |
| 40c420 | - | 22/22 | rdx+xmm0 | xmm0 |
| 40c650 | - | 22/22 | rdx+xmm0 | xmm0 |
| 40f210 | i64,i64,i64 | 20/22 | rax+rdx+xmm0 | other |
| 4421d0 | i64,i64 | 10/22 | rax+rdx | other |
| 442670 | - | 22/22 | rax+rdx+xmm0 | xmm0 |
| 442890 | - | 22/22 | rax+rdx+xmm0 | xmm0 |
| 45e1a0 | i64 | 0/22 | unexec | xmm0 |
| 45e280 | i64 | 0/22 | unexec | other |
| 45e2e0 | i64 | 0/22 | unexec | xmm0 |
| 45e3c0 | i64,i64 | 2/22 | rax+rdx | other |
| 45eb00 | i64 | 0/22 | unexec | xmm0 |
| 45ecc0 | i64 | 0/22 | unexec | other |
| 45ed20 | i64 | 0/22 | unexec | xmm0 |
| 45ee00 | i64,i64 | 2/22 | rax+rdx | other |
| 5b0970 | i64,i64 | 16/22 | rax+rdx | other |
| 668390 | i64 | 0/22 | unexec | other |
| 6683d0 | i64 | 0/22 | unexec | other |
| 677820 | i64,i64 | 16/22 | rax+rdx+xmm0 | other |
| **6957d0** | i64 | 16/22 | **xmm0** | xmm0 |
| **6957f0** | i64 | 16/22 | **xmm0** | xmm0 |
| **695930** | i64 | 16/22 | **xmm0** | xmm0 |
| **695960** | i64 | 16/22 | **xmm0** | xmm0 |
| 6a3a90 | - | 22/22 | rdx+xmm0 | xmm0 |
| 6a3ac0 | - | 22/22 | rax+rdx+xmm0 | xmm0 |
| 6ed480 | i64 | 16/22 | rax+xmm0 | xmm0 |
| 784520 | i64,i64 | 0/22 | unexec | xmm0 |
| 7ce2e0 | i64 | 16/22 | rax+xmm0 | xmm0 |
| **812df0** | i64 | 16/22 | **xmm0** | xmm0 |
| **812e70** | i64 | 16/22 | **xmm0** | xmm0 |
| 8e6660 | i64 | 18/22 | rax+rdx | other |
| 8e7e10 | i64,i64 | 0/22 | unexec | other |
| a965c0 | ptr,i64,i64 | 0/22 | unexec | other |
| ba05f0 | i64 | 16/22 | rax+xmm0 | xmm0 |
| **cc32f0** | i64 | 16/22 | **xmm0** | xmm0 |
| **cc3660** | i64 | 16/22 | **xmm0** | xmm0 |

(太字 = 署名修正の対象 8 件。関数名は `function_` 接頭辞を省略。)

## 4. 署名修正 (xmm0 戻り 8 関数)

- 変更 (`tools/liftdiff/`):
  - `targets/m11.json`: `ret_override` に 8 関数を `double` で登録 (理由は `ret_override_note`)。
  - `ldlib/session.py`: 読み込んだ sigs に上書きを適用し、`tr=True` を付ける。
  - `ldlib/cases.py`: `sig['tr']` のとき case 行に `tr=1` を付ける。
  - `rt/ld_runner.mjs`: `tr=1` のとき `m11_tr_function_<VA>` (全 i64×8 引数・i64 返し = IR の `trunc i128` 下位 64bit) を呼び、8 引数になるよう 0 で埋め、戻りを `x0` のビット列として返す。
- 効果 (`liftdiff.py run targets/m11.json --fn <8 件> --nobuild --state auto`、測定 commit): 8/8 が `verdict=mismatch` で実行可能になった (修正前: `unsupported_sig`)。
  case 集計 `diff` 53・`equal` 11・`native_fault` 24 (8 × 11 = 88 件)。
- 陽性対照: 修正後の wasm 戻り `x0` が非零の case は 21 件 (raw 記録 53 件中)。`tr=1` 経路が値を返すことを示す。
- 注意: 8 関数の `diff` の多くは入力側の欠落と読める。8 件とも第 2 引数 (double) を xmm1 から読むが、IR 署名に xmm 引数が無いため case 生成は xmm1 を投入しない。native は xfill で xmm1 = 2.25 (`0x4002000000000000`) を入れる。
  tag `xmm_arg_drop` と一致する。戻り型の修正だけでは一致判定は通らない。これは本 issue の範囲外 (§6)。

## 5. 検証

| 項目 | 結果 |
|---|---|
| e2e 修正前 (`2399e38dd`・変更なし) `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/liftdiff/liftdiff_e2e.sh --m11-only` | **PASS** (02:04:26→02:07:08 = 162 秒。batch 95 秒・12 shard・終了時 load 4.43) |
| e2e 修正後 (`f61e06d49`) 同コマンド | **PASS** (02:17:18→02:20:00 = 162 秒。batch 95 秒・12 shard・終了時 load 5.30) |
| sample:800 修正前 | 一致 360 / 不一致 234 / 実行不能 206 (`unsupported_sig` 1) |
| sample:800 修正後 | 一致 360 / 不一致 234 / 実行不能 206 (`unsupported_sig` 1)・不一致類型の主因・該当数も全て同一 |
| 単体 (e2e [0/4]) | `test_compare_ld11` 23 件 OK |
| 静的判定器の対照 | `ld38_ret_convention.py --control` 3/3 OK |
| 動的分類器の対照 (i64 戻り 4 件) | `function_6614a0` `1234fd0`: rax_w=1 (整数戻り)、`101a5f0` `105f710`: rax_w=0 (rax 不書換え)。x0_w は 4 件とも 0。sample:800 で `match` の i64 戻り関数を使用。`work/ld158_control_i64.json` |
| 測定 commit から HEAD までのコード差分 | `git diff f61e06d49 HEAD -- tools/liftdiff tools/m11 docs/DOC_MAP.md` の出力: 本 REPORT・DOC_MAP・REPORT_LD38 の文書変更のみ (下記 §8 に出力を添える) |

- 検証範囲: 素材 `fl-win64` `work-m11` `work-liftdiff` `toolchain-emsdk` の展開済み状態。`toolchain-retdec` は未使用 (liftdiff の build は emsdk のみ)。
- 範囲外: OTT 旧 chain (`--m11-only` で省略)・closure 全数 (`--full`)・wasm 側の lift 本体の修正。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 戻り経路が決まらない 31 関数 (判定不能 11・rax/rdx 書換えの併存 20)。呼出し側の戻り値利用の確認を含む | 署名修正の対象外。件数表の『書込み実測』は戻り値の確定ではない | 子 issue [LD-162] (#3572) (本 PR で起票) |
| 修正 8 関数の `diff` の主因 (xmm1 などの入力欠落 = `xmm_arg_drop` 推定) | 8 関数の一致判定は通っていない | #976 の残件 (PM 判断) |
| 修正 8 関数の戻り型 `double` は、呼出し側で xmm0 が読まれることを未確認 | 呼出し側が戻り値を使わない場合、`double` 署名の意味が無い | [LD-162] (#3572) |

## 7. 次の作業 (提案)

- [LD-162] (#3572): 31 関数の戻り経路を、判定不能 11 件は this の疑似オブジェクトで実行可能化して、併存 20 件は呼出し側の読みで確定する。
- xmm 入力欠落 (`cc32f0` 型) は #976 の残件として PM 判断。

## 8. 測定 commit からの差分 (差分 0 の証跡)

- `git diff f61e06d49 HEAD -- tools/liftdiff tools/m11 docs/DOC_MAP.md` は、本 REPORT と DOC_MAP・REPORT_LD38 の文書だけを含む (コード差分 0)。
  コマンドの出力は PR 本文に転記する。
