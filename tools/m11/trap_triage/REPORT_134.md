# #134 (M11-N5): unit 56 (VA 0x16fde0) の fail-fast 辺の guard 入力 (trap 時の実測)

**既知類型との関係**: 該当なし (DEFECTS.md の D1a〜D23 への対応は未照合)。`function_410360` の vtable 呼出しの IR 脱落は、間接 call 脱落の類型に近いが、icall §4 (D1〜D13) との突合は未実施 (未解決 #3)。

## 0. 結論 (本 run の実測で言えること)

- **guard の入力を trap 時点で実測した** (§3。n=3 + NC、3 回とも同一)。8c5eb0 の入口 arg2 は `dl = 0x01` (bit 7 なし)。guard の R (410320 の戻り) の先頭 qword は `0x566d68` = this。list (8c67a0(R) の戻り) の件数 `[list+0x14]` は **0**。
- **件数 0 は wasm 実行の trap 時点の値**。ただし native の値は未測定のため、「wasm で 0」までが言える。
- **R と list の `[vt-0x50]` は両方 VA `0x410070`**。PE の静的値 (`[0x566d18]`・`[0x8bd308]`) と一致し、その番地は `ret` 1 命令の stub (no-op)。よって fail-fast 辺の vtable 呼出し先は有効な no-op で、「vtable が無効」が trap の原因ではない。
- **旧 §3 の VMT (this) の値は本 run で再現** (n=3 同一)。VMT は補助 (§3 の表 B)。
- **未判定**: (b) skip 3 の書込み元 (本測定の範囲外)。native 側の件数 (比較の手段が無い)。

## 1. 測定条件

| 項目 | 値 |
|---|---|
| 測定 commit (コードを変えた最後の commit) | `df420360` (IR probe `probe134_ir.py`・`m11_rt.c` の記録関数・`m11_survey.mjs` の読取り・`m11_build.sh` の `M11_PROBE_134` 分岐) |
| 検証 HEAD | この PR の head (最後の push)。PR 本文の「検証 HEAD」と一致させる |
| 差分の証跡 | `git diff df420360 HEAD -- tools/m11/m11_rt.c tools/m11/m11_build.sh tools/m11/m11_survey.mjs tools/m11/trap_triage/probe134_ir.py tools/m11/trap_triage/probe_134.sh` の出力は空 (本ファイルの変更のみ) |
| 素材 (本 run で展開・実在を確認) | `fl-win64` (`extracted/block00031_PE.bin` のみ展開)・`work-m11` (→ `tools/m11/work/`)・`toolchain-emsdk` (`/opt/emsdk`)・`toolchain-retdec` (`/opt/retdec`) |
| PE | `extracted/block00031_PE.bin`、sha256 `b2c64da40921cf262c15c5b25c2b0422e4d1851e953c87e0bc38ed2c19f9496d` |
| IR | `bash m11_gen_ir2.sh` を本 run で再生成 (33 秒)。`ir_sha256` = `f199b896…be22` (build 後の値。qstore・ldfix・ld108 = applied)。旧 REPORT の `de46cada…8636` とは一致しない |
| build | 採取: `M11_PROBE_134=1 bash m11_build.sh` (IR probe 入り)。既定: `bash m11_build.sh` |
| 実行日時・出力 | 採取 2026-10-14 18:11〜18:12 UTC。出力は `tools/m11/work/v134/` (gitignore。`n1`〜`n3`・`nc_shift1`・`build.log`) |

`work/lift_pe.sha256` は本 run で作っていない (`m11_gen_ir2.sh` と `m11_build.sh` だけを使った。`m11_e2e.sh` の全再生成経路は通していない)。

## 2. 基準の数値 (m4)

| 測定 | commit | 環境 (IR) | ok / trap / miss / noproc (clobber) |
|---|---|---|---|
| 本 run・既定 off (本 PR の head) | `df420360` の既定 build | 本 run の再生成 IR | **870 / 24 / 47 / 1 (0)** |
| 本 run・基準 (control) | `46c92356` (本 PR の基点) | 本 run の再生成 IR | **870 / 24 / 47 / 1 (0)** |
| 旧 REPORT の値 | `46c92356` | 前回 run (IR `de46cada…`) | 872 / 23 / 46 / 1 (0)。本 run では再現せず |
| issue 本文 | `750340fc` | — | 871 / 24 / 46 / 1 |
| review 指摘 | `427eab37` | — | 870 / 25 (出所の REPORT は未照合) |

- 本 PR の head と基点 `46c92356` は、同じ環境・同じ IR 生成で同一の値。本 PR のコードは既定 off の survey を変えない (測定値)。
- `872/23` は本 run で再現しない。差の原因は IR の再生成の環境差 (ir_sha が一致しない) と推定するが、切り分けは未実施 (未解決 #4)。
- main の現在の基準は未測定。`m11_judge` (stage) と `m11_run` は本 run で未実行。

## 3. 採取の実測 (B1: trap 時の guard 入力。n=3 + NC)

probe の方式は §5。単位は trap 時点 (unit 56 の catch)。linear 0x… は wasm 線形メモリの番地 (VA = linear + 0x400000)。

**表 A: guard の入力 (IR probe で 8c5eb0 の call 戻り値を採取)**

| 項目 | 採取値 (n=1・n=2・n=3 同一) | NC (1 byte ずらした読取り) |
|---|---|---|
| (i) arg2 | `dl = 0x01`、bit 7 = false (期待値 `dl = 1` どおり) | — |
| (ii) R = `410320` の戻り | `0x10b698c0` | — |
| R `+0x14` (i32) | **0** | `+0x15` = 0 (真の値と同じ 0 のため NC として弱い) |
| R 先頭 qword | `0x166d68` (= VA `0x566d68` = this) | `+1` 読みは `0x166d` (別値) |
| R `[vt-0x50]` | `0x10070` (VA `0x410070`) | — |
| (iii) list = `8c67a0(R)` の戻り | `0x10bc4e40` (R とは別の番地) | — |
| list `+0x14` (i32) | **0** (件数 0) | `+0x15` = 0 (同上) |
| list 先頭 qword | `0x4bd358` (VA `0x8bd358`) | `+1` 読みは `0x4bd3` (別値) |
| list `[vt-0x50]` | `0x10070` (VA `0x410070`) | — |

- 記録 mask = 7 (arg2・R・list が揃っている)。trap は list を求めた後で起きた (fail-fast 辺)。
- 記録件数 n = 1: unit 56 の trap 時点まで 8c5eb0 の入口は 1 回だけ。trap は 1 回目の呼出し (this = `0x566d68`) で起き、2 回目 (this = `0x566eb0`) には到達しない。
- R が「採った対象」であること: R の先頭 qword = this は、`dl` の bit 7 が立たない経路で `[this-0x30]` (= `0x40f960`) が生成したインスタンスの性質 (`[inst] = self`) と一致する。list は R と別の番地。両方とも IR の call 戻り値 (`%5` = 410320、`%6` = 8c67a0) を記録したもので、メモリの読取りではない。

**表 B: 補助 (this = VMT の状態。guard の入力ではない。旧 §3 の値の再測定)**

| object (linear / VA) | `+0x14` (i32) | 先頭 qword | `[vt-0x50]` |
|---|---|---|---|
| 1469800 / `0x566d68` | 0 | `0x168b50` (VA `0x568b50`) | `0xffffd3a8e8000000` |
| 1470128 / `0x566eb0` | 0 | `0x16e0d0` (VA `0x56e0d0`) | `0xccccccccccc35f5e` |

- n=3 同一。全 942 unit の実行で不変 (`changed_after_unit: []`)。これは VMT の不変性であり、R と list の不変性ではない。
- NC (読取り先を 1 byte ずらす `1469801,1470129`): 件数 `536870912`、先頭 qword `0xf000000000001800` 系で、VMT の値と一致しない (`nc_shift1`)。

## 4. 静的照合 (PE の機械語・データ。capstone / pefile)

| 位置 | 内容 | 意味 |
|---|---|---|
| `56fde0` の 2 呼出し (`570296`・`5702ae`) | 直前に `dl = 1`、`rcx = [0x566ca0]`・`[0x566de8]` (= 0x566d68・0x566eb0) | `410320` は bit 7 が立たず `[this-0x30]` を呼ぶ |
| `410320` | `test dl,dl; jl`。bit 7 なし → `call [rax-0x30]` | R = `[this-0x30](this)` の戻り |
| `[0x566d38]` = `[0x566e80]` | `0x40f960` | 2 つの VMT の `-0x30` は同じ NewInstance |
| `[0x566d18]` | `0x410070` | R の `[vt-0x50]` (wasm 実測と一致) |
| `[0x8bd308]` | `0x410070` | list の `[vt-0x50]` (wasm 実測と一致) |
| `0x410070` | `c3` (`ret`)。`0x410060`・`0x410080` も `ret` の stub | 有効な no-op。int3 padding ではない |
| `410360` | `rbx = [R]`; `call [rbx-0x50]` | fail-fast 辺の vtable 呼出し。IR では `ret i64 %arg1` で脱落 (未解決 #2) |

## 5. 採取の方法 (本 run で実施)

- `trap_triage/probe134_ir.py` が `function_8c5eb0` の本体に 3 点の観測呼出しを入れる: 入口の `arg2` (f=0)、`410320` の戻り `%5` (f=1)、`8c67a0` の戻り `%6` (f=2)。`m11_rt.c` の `m11_p134_put`/`m11_p134_get` が 64 件の環状配列に記録する。
- 挿入は `M11_PROBE_134=1` のときだけ (`m11_build.sh` の stamp `work/instr_134.stamp` で post 出力を作り直す)。既定 build は IR に観測呼出しが無く、`_m11_p134_*` も export されない。`m11_rt.c` の記録関数は既定 build にも含まれるが、呼出し元が無い。
- survey は unit 56 の catch で `p134ir()` を読む (R・list の `+0x14`・先頭 qword・`[vt-0x50]`、NC は 1 byte ずらす)。読取りは trap 直後で、state を変えない。
- `inspect_trap.mjs` (REPORT_APPENDIX_1602.md §16) は使わなかった。

## 6. 判定

| 判定 | 結果 | 根拠 |
|---|---|---|
| (a) 件数 0 は実行時の値か | **wasm では trap 時点の list の件数は 0** (native は未測定) | §3 表 A |
| (b) skip 3 の object の初期化 | 未判定 (本測定の範囲外) | — |
| (c) `[vt-0x50]` は有効か | **有効**。R・list とも VA `0x410070` = `ret` の stub (no-op) | §3 表 A・§4 |
| fail-fast 辺の `410360` の IR 脱落 | 対象の vtable 呼出し先は no-op のため、この脱落が trap の原因とは言えない。脱落の影響そのものは未確認 | §4 |

撤回: 初版 (a)(b)(c) の結論は、訂正版の時点で撤回済み。本判定は R と list を直接採った値による。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| native 側の list 件数 (0 か) | 件数 0 が native でも起きるかは不明。native 比較の手段が無い | PM 判断 |
| `function_410360` の `call [rbx-0x50]` の IR 脱落 (`ret i64 %arg1`) | 対象の呼出し先は no-op。他の間接 call 脱落との突合 (icall §4 D1〜D13) は未実施 | PM 判断 (子 issue 候補) |
| skip 3 の Init `0xfa9390` の出所 | (b) の判定。unit 56 の原因特定は未達 | PM 判断 |
| 基準 survey の差 (872/23 と 870/24) | 本 run で基点も 870/24。IR 再生成の環境差の切り分けは未実施 | #718 への追記候補 (PM 判断) |

## 8. 再現

```sh
export FL_WIN64_DIR="$RUNNER_TEMP/fl-win64"   # extracted/block00031_PE.bin を展開しておく
cd tools/m11
bash m11_gen_ir2.sh                  # IR を再生成 (約 33 秒。ir_conditions.json)
bash trap_triage/probe_134.sh        # M11_PROBE_134=1 で build し、n=3 + NC (約 50 秒)。出力は work/v134/
M11_PROBE_134=0 bash m11_build.sh && node m11_survey.mjs   # 既定 off の基準 (870/24/47/1 相当)
```
