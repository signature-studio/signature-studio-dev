# #1046: unit 492 の OOB (`4133f0` 参照カウント解放経路) の原因特定 (途中経過)

親: #862 (受入 3・4 の持ち越し先)。検証起点: `origin/main` = `9aad4595`。本 PR は `tools/m11/` のコードを変更しない (REPORT のみ)。

**結論 (途中): 受入 1・2 は未達。入力値の実測は未完。最有力は D11 (10 進 `inttoptr` の絶対 VA 残り) だが未確定。**

## 1. 素材と再現

- 素材: `fl-win64` (`[WIN64]`、`$FL_WIN64_DIR/extracted/`)、`toolchain-emsdk` (`[EMSDK]` 6.0.12)・`toolchain-retdec` (`[RETDEC]` v5.0)、`work-m11`・`work-liftdiff` (`tools/m11/work/`・`tools/liftdiff/work/` へ展開)。
- `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` を指定する (`docs/WORKFLOW.md` §11)。PE は `$FL_WIN64_DIR/extracted/block00031_PE.bin` (`[WIN64]`)。
- IR: `bash tools/m11/m11_gen_ir2.sh` rc 0 (実測 44.0 s、`ldfix=applied`、`boot_final.ll` 490,693 行、`ir_sha256` `2c68ceae…`)。
- build: `bash tools/m11/m11_build.sh` rc 0 (`wasm-ld signature mismatch: 0, undefined symbol: 0`)。
- survey: `node tools/m11/trap_triage/survey_units.mjs` 3 回 (13.27 s・全て rc 0)。per-unit JSON は `cmp` で完全一致。

## 2. survey の実測 (HEAD `9aad4595`、3 回反復)

| 回 | ok | oob | halt0 | miss | other | noproc |
|---|--:|--:|--:|--:|--:|--:|
| 1 | 870 | 16 | 7 | 47 | 1 | 1 |
| 2 | 870 | 16 | 7 | 47 | 1 | 1 |
| 3 | 870 | 16 | 7 | 47 | 1 | 1 |

- unit 492: 3 回とも `oob` (`memory access out of bounds`)。`410630` を含む frame は 0 件。
- halt0 は 114 / 245 / 279 / 314 / 509 / 647 / 895 の 7 件。REPORT_862 §9 の 8 件から unit 368 が抜けている。これは #1043 (`pass_m2q_fn980ed0` による修復、ok 869→870) の既知の変化で、本件の変化ではない。
- oob は 16 件 (144, 149, 275, 280, 304, 477, 484, 492, 513, 520, 555, 659, 745, 830, 880, 923)。

## 3. unit 492 の経路 (全 unit 実行での最上位 frame)

- frames: `function_4133f0 ← function_4473f0 ← function_446400 ← function_446ad0 ← function_ad5700`
- 最上位 frame の wasm offset: `wasm-function[14873]` (= `function_4133f0`) の `0x352bb9` (`top_off` は `oob_top.mjs` による全 unit 実行の値)。
- 命令 (`oob_insn.py m11_boot.cjs.wasm 14873 0x352bb9`): `i32.load offset=0` の直前が `i64.load offset=32` → `i64.const 8` → `i64.add` → `i32.wrap_i64`。つまり `4133f0` の `cmp dword ptr [r13 - 8], 0` に対応する `*(arg - 8)` の読みで OOB。
- 注意: `SV_ONLY=492` の単独実行では最上位 frame が `function_407a50` になり、全 unit 実行と異なる。unit 492 の挙動は先行 unit の状態に依存する。単独実行の frame は採用しない。

## 4. 機械語と IR の対応 (実測)

- `4133f0` (size 135): `rdx` (引数 `r13`) が NULL でなければ `[r13-8]` (refcnt) を読む。解放経路は `lock xadd [rax+8]` → `call 409440`。
- `4473f0` (size 249): `[rbp+0x40]`・`[rbp+0x48]` のスロットを `447df0` で埋めてから `4133f0` を呼ぶ。`447df0` は `cmp qword [rbx],0` が 0 のときだけ `[arg5 + arg4*8]` を読んで `41c820` へ渡す。戻り値は常に `rbx` のアドレス。
- IR (`boot_final.ll` `@function_4473f0`): `447df0` の第 5 引数が `inttoptr i64 16433440` (`0xfac120`)・`16433496` (`0xfac158`) の定数。機械語の `lea rax,[rip+disp]` (`0x447467`・`0x44749e` の直前) はこの表を指すはず。

## 5. 未解決 (本 run で切り分けられなかった点)

1. **入力値 (`4133f0` の `rdx`) の実測は未完**。`447df0` が読む表の要素が何か (rdata の表か、機械語の誤読か) を確定していない。
2. IR 定数 `16433440` (`0xfac120`) と `16433496` (`0xfac158`) は、RVA (= LVA、`M11_LB_BASE=0`) として PE を読むと **6 要素のポインタ配列** になる (`0x4260f0, 0x426100, …` / `0x426160, 0x426170, …`、16B 間隔の rdata 表として妥当)。`0xfac120` を VA として (ImageBase を引いて) 読むのは誤り。よって IR 定数は RVA として正しく、D11 (絶対 VA の残り) の疑いは **否定**。
3. DEFECTS 類型への対応: 未確定。表の内容 (`0x4260f0…` 系のポインタ) が何の vtable / 文字列表か、要素 `[arg4*8]` のどれが `41c820` に渡って `4133f0` の OOB 入力になるかは未実測。`lea` の実効位置の照合も未完。

## 6. 受入条件の判定

| # | 条件 | 判定 |
|---|---|---|
| 1 | `4133f0` の OOB の入力値 (ポインタ・長さ) を実測で特定 | **未達**。命令 (`*(arg-8)`) と入力の供給元 (`447df0` の表読み) までは特定。値は未実測 |
| 2 | `4473f0` の配列長計算 (`0x92492493`) の戻り値が原因か実測 | **未達**。`4473f0` の IR と機械語の対応まで確認。戻り値の実測なし |
| 3 | DEFECTS 類型への対応づけ | **未達**。D11 が最有力候補 (未確定) |
| 4 | unit 492 の kind 実測と per-unit JSON で回帰が無いこと | **達成 (測定のみ)**。3 回とも `oob`、per-unit JSON `cmp` 一致。コード変更なし (回帰 0) |

## 7. 再現

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64   # PE: $FL_WIN64_DIR/extracted/block00031_PE.bin
bash tools/m11/m11_gen_ir2.sh
bash tools/m11/m11_build.sh
node tools/m11/trap_triage/survey_units.mjs tools/m11/work/trap_triage/run1.json
node tools/m11/trap_triage/oob_top.mjs tools/m11/work/trap_triage/topall.json   # 最上位 frame と top_off
python3 tools/m11/trap_triage/oob_insn.py tools/m11/work/m11_boot.cjs.wasm 14873 0x352bb9 40
LD_M11_PE=$FL_WIN64_DIR/extracted/block00031_PE.bin python3 tools/m11/trap_triage/disasm_fn.py 4133f0 4473f0 447df0
```

注: `disasm_fn.py` は `LD_M11_PE` で PE を指定する (`$FL_WIN64_DIR/extracted/block00031_PE.bin` と同一。`[WIN64]`)。

## 8. 測定 commit からの差分 (差分 0 の証跡)

- 測定 commit: `9aad4595` (§1・§2 の測定)。検証 HEAD: `b55c9f7c` (main `d7d91d26` を取り込み)。
- `git diff --stat 9aad4595 b55c9f7c -- tools/m11/m11_gen_ir2.sh tools/m11/m11_build.sh tools/m11/trap_triage/ tools/shim tools/m11/*.py tools/m11/*.sh`: 出力は `tools/m11/trap_triage/REPORT_1046.md` (+67) と `REPORT_714.md` (+42) のみ。コード差分 0。
- 同範囲外の差分 (`tools/shared/lift/libkio/*`・`tools/m11/ldfix/ldfix_509_e2e.sh`) は m11 の IR 生成・build・survey から参照されない (`grep` で 0 件)。

## 9. 再着手 run の追加測定 (HEAD `a647ceba`、コード変更なし)

- 再現: `m11_gen_ir2.sh` rc 0 (36.6 s、490,693 行) → `m11_build.sh` rc 0 (wasm-ld signature mismatch 0・undefined 0) → `survey_units.mjs` rc 0 (9.9 s)。結果 `ok 870 / oob 16 / halt0 7 / miss 47 / other 1 / noproc 1` で §2 と一致。
- `.data` の表 (RVA `0xfac120` / `0xfac158`) の中身は絶対 VA (`0x4260f0`, `0x426100`, … / `0x426160`, `0x426170`, …、ImageBase `0x400000` 付き)。RVA の `.text` では読めず `.data` 配置で読んだ。§5-2 の「6 要素のポインタ配列」は同じ値で、表が VA を格納している点を追記する。
- `SV_ONLY=492 SV_TRACE_AT=492` の単独実行: `oob` 1 件のみ (trace 行 4 件)。全 unit 実行の `SV_TRACE_AT=492` では trace 行 `[m11][UStrAsg]` が 146 件 (dest/src の 0 が 24 件、`src=0x10e1ac` が 9 件)。ただし unit 境界の行が出ないため、unit 492 の OOB 直前の `UStrAsg` を切り出せなかった。
- 結論: 受入 1 (OOB 入力値 `src`) は未達のまま。入力値を取るには `function_4133f0` の入口で unit 番号つきの値を記録するビルドが要る (`m11_ov.c` の `M11_TRACE` は unit 番号を出さない)。受入 2・3 も未達。未解決は #1288 (`[M11-N79]`) に残す。
