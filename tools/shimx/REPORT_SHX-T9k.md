# tools/shimx REPORT 付録 — SHX-T9k (#2593) unit 22 の GetLastError=126 の発生元と wasm PC の対応

> 本体: `tools/shimx/REPORT_SHX-T9j.md` §2.4・§4 (親 #2491 `[SHX-T9i]`)。前段: `REPORT_SHX-T9.md` §3.3.1〜§3.3.4。
> probe: `tools/m11/shimx_link/probe_sxlasterr_2593.mjs`。証跡: `tools/shimx/evidence_2593/`。
> 素材: `oc_artifacts: fl-win64 work-m11 work-liftdiff toolchain-emsdk`。

## 1. 結論

- 受入 1 (発生元の特定): unit 22 で shimx 版の GetLastError を 0 → 126 にするのは **GetProcAddress の 1 回目の呼出し** (sxt 呼出し #108)。直前の GetModuleHandleW("oleaut32.dll") (#107) は成功 (戻り値 `0x11443000`, GetLastError 0 のまま)。
- 受入 2 (IR 行番号と wasm バイトオフセット): 1 例以上を取った (§2.2)。呼出し元は IR `gen_fix/boot_trace.ll` の `function_457c70` (160539 行の GetModuleHandleW・160540 行の `function_457c40` 呼出し) と、`function_457c40` (160524 行の GetProcAddress)。wasm オフセットは V8 の wasm フレームと wasm-ld の map (関数範囲) と逆アセンブルの 3 つで突き合わせた。
- 126 の直接原因 (実測): GetProcAddress の `hModule` が **`0x56670`** で、GetModuleHandleW の戻り値 (`0x11443000`) ではない。shim の GetProcAddress は `mod_by_base_locked` で見つからないハンドルを `ERROR_MOD_NOT_FOUND` (`tools/shimx/src/module.c:330`) として扱う。
- hModule の出所 (IR 上の事実): `function_457c40` は引数 `arg1` の `+40` を読んでハンドルにする。`arg1` は `function_457c70` の alloca `%stack_var_-56` で、この関数内では `function_457c40` に渡される前に一度も store されない (未初期化読み)。その残存値が `0x56670`。残存値の出所は未特定 (§4)。
- baseline (`m11_win.c:90`) の GetProcAddress は常に 0 を返しエラーを立てない。よって 126 は「入力 (未初期化の hModule) は同じでも shimx の検査が NULL 系の失敗を 126 として見せる」差。baseline 側の hModule 値は未計装のため比較していない。

## 2. 測定

### 2.1 受入 1: unit 22 の shim 呼出し列 (測定 commit `6603d5f5`・clean rebuild・probe)

`probe_sxlasterr_2593.mjs` で unit 1〜21 を通常実行した後、unit 22 だけ trace (`sxt_set_print` と `sxt_set_stack` を 1)。`le` は呼出し直前の GetLastError。

| sxt # | 呼出し | le (呼出し前) | 戻り値 (実測) | 備考 |
|---|---|---|---|---|
| #107 | `GetModuleHandleW("oleaut32.dll")` | 0 | `0x11443000` | 成功 (SetLastError 0) |
| #108 | `GetProcAddress(0x56670, "VariantChangeTypeEx")` | 0 | `0` | **ここで 126 が立つ** |
| #109 | `GetProcAddress(0x56670, "VarNeg")` | 126 | `0` | 以後 21 回 (計 22 回) は全て失敗 |
| … | (`VarNot`…`VarBstrFromBool`) | 126 | `0` | hModule は同じ `0x56670` |

- 126 の発生元の根拠: #108 と #109 の間に他の wrapped 呼出しは無い。#108 の内部で `module.c:330` の `!m` 分岐 (`SetLastError(ERROR_MOD_NOT_FOUND)`) に入ったと読む。hModule 0x56670 はロード済みモジュールの base に一致しない (GetModuleHandleW の 0x11443000 とも一致しない)。
- 全体 (unit 22 の `sxt_ret`): GetModuleHandleW 1 回、GetProcAddress 22 回。GetProcAddress は全て 0 を返す。
- 証跡: `evidence_2593/probe_u22_shimx_head.txt` (`[sxt]` 行と `sxt_stk` 行・`ret` 行)。

### 2.2 受入 2: IR 行番号 ↔ wasm バイトオフセット (1 例以上)

IR は build 入力の `tools/m11/work/shimx_link/gen_fix/boot_trace.ll` (`--fix` 後・`__sxt_` 改名済み)。`boot_final3.ll` の同行も同じ命令 (`@GetProcAddress`・`@GetModuleHandleW`) で、行番号は同一だった (`evidence_2593/ir_boot_final3_lines.txt`)。wasm オフセットは V8 の wasm フレーム (`wasm-function[n]:0xOFF`)。

| 呼出し | IR 行 (boot_trace.ll) | 関数 (IR) | wasm オフセット | 関数範囲 (wasm-ld map) | 逆アセンブル |
|---|---|---|---|---|---|
| GetModuleHandleW("oleaut32.dll") | 160539 `%0 = call ptr @__sxt_GetModuleHandleW(…)` | `function_457c70` (160536〜) | `0x1beac0` (`call 16648` = `__sxt_GetModuleHandleW`) | `0x1bea99`+`0x325` | `evidence_2593/objdump_0x1beac0.txt` |
| GetProcAddress (126 を立てる 1 回目) | 160524 `%6 = call ptr @__sxt_GetProcAddress(ptr %5, ptr %arg2)` | `function_457c40` (160513〜) | `0x1bea6d` (`call 16650` = `__sxt_GetProcAddress`) | `0x1bea3f`+`0x5a` | `evidence_2593/objdump_0x1bea6d.txt` |
| 呼出し元 (function_457c70 → function_457c40, 1 回目) | 160540 `%1 = call i64 @function_457c40(…, i64 4551360)` | `function_457c70` | `0x1bead6` (`call 4611`) | 同上 | `evidence_2593/objdump_0x1bead6.txt` |

- V8 フレームの対応 (`probe_u22_shimx_head.txt` の `#0`・`#1`): GetModuleHandleW は `sxt_enter` → `[16648]` (wrapper) → `[4612]:0x1beac0` (= function_457c70)。GetProcAddress は `sxt_enter` → `[16650]` (wrapper) → `[4611]:0x1bea6d` (= function_457c40) → `[4612]:0x1bead6` (= function_457c70)。
- 同じ呼出し元 `function_457c70` は `function_457c40` を 22 回呼ぶ (IR 160540〜160582 行)。2 回目の戻り先は `0x1bea6b` (IR 160542 行)。
- 対応の検証: 逆アセンブルの命令境界 (`call` 命令の先頭) と V8 の offset が一致する。map の関数範囲に全て収まる。

### 2.3 再現性の注意: archive 由来の `work-m11` の IR では 126 は出ない

- (a50c3ea7 時点の測定。6603d5f5 では未再測定) 素材 `work-m11.tar.zst` 同梱の `boot_final3.ll` (2026-10-10) を使った shimx `--trace --soft --fix` は、unit 18 が `exc=memory access out of bounds lasterr=87`、unit 22 が `lasterr=0` だった (126 は出ない)。REPORT_SHX-T9j §2.3 の「旧 IR」行と同じ挙動。
- 126 を再現するには **IR を現行コードから再生成する** 必要がある: `FL_WIN64_DIR=… bash tools/m11/m11_gen_ir2.sh` (50 秒・`490735 行`) → `FL_WIN64_DIR=… bash tools/m11/m11_build.sh` (25 秒・`boot_final3.ll` 再生成)。その後で shimx を clean rebuild する。
- 再生成後の baseline (`m11_boot.cjs`) は unit 22 `ret=1 lasterr=0` (`evidence_2593/probe_u22_baseline_regen.txt`・6603d5f5 で再実行し証跡と同一)。

### 2.4 IR 上の確認 (hModule の出所)

- `function_457c40` (IR 160513〜160534): `%1 = arg1+40`・`%3 = load i64 [%1]` (`+40` の読みのみ・store 無し)。`%3 == 0` なら `arg3` を返し、非 0 なら `GetProcAddress(inttoptr %3, arg2)` を呼び、NULL なら `arg3` を返す。
- `function_457c70` (IR 160536〜): `%stack_var_-56 = alloca [7 x i64]` (160538)。以降 22 回の `function_457c40(%stack_var_-56, name, fallback)` 呼出し (160540〜160582) で、この alloca に対する store は無い。
- 結論 (IR 上): `+40` が未初期化の読み。実行時の値 `0x56670` は alloca の残存値。残存値の書き手は未特定 (§4)。

## 3. 再現性 (WORKFLOW §6)

- 測定 commit: `6603d5f5` (`a50c3ea7` に `origin/main` (`9b352bd7`) を merge した commit。競合は `build.sh` の EXPORTS 行のみで、main の `_sxt_ret_site,_sxt_site_name` と本計装の `_sxt_set_print,_sxt_set_stack` を両方残した)。計装 (`tools/m11/shimx_link/trace_rt.c`・`build.sh`・`probe_sxlasterr_2593.mjs`) の中身は `a50c3ea7` と同じ。main 取り込みで IR の `__sxt_GetProcAddress` に site 引数が増え、wasm の配置が変わった (§2.2 のオフセットは `a50c3ea7` 時点の `0x1bea33`・`0x1be9e2`・`0x1bea49` から変わっている)。§2.1 の値 (le・戻り値) は両 commit で同一。前段 `0cfb592c` → `a50c3ea7` は EXPORTS の 2 語を別行へ分けただけ。
- 再現手順 (clean rebuild → probe):
  1. 素材を展開: `tar --zstd -xf $ARTIFACTS_DIR/work-m11.tar.zst -C <worktree>`・`work-liftdiff` も同様。`fl-win64` は `extracted/block00031_PE.bin` だけ (`mkdir -p $RUNNER_TEMP/fl-win64 && tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64 extracted/block00031_PE.bin`)。
  2. IR 再生成: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/m11/m11_gen_ir2.sh` → `FL_WIN64_DIR=… bash tools/m11/m11_build.sh`。
  3. shimx clean rebuild: `rm -rf tools/m11/work/shimx_link/obj tools/m11/work/shimx_link/gen_fix && bash tools/m11/shimx_link/build.sh --trace --soft --fix` → `[sxlink] OK trace_soft_fix` (`evidence_2593/build_trace_soft_fix_head.log`・15 秒)。
  4. probe: `node tools/m11/shimx_link/probe_sxlasterr_2593.mjs $PWD/tools/m11/work/shimx_link/m11_sx_trace_soft_fix.cjs 21` (unit 22 を trace。0.5 秒)。
- 測定時の値: `m11_sx_trace_soft_fix.cjs` sha256 `bd963f6b…`・`.wasm` sha256 `349d53f3…` (先頭 16 桁)。emcc は 6.0.12 (`[EMSDK]`)。`uptime` load 0.78 (build 時・4 CPU)。
- 結果は HEAD (`6603d5f5`) の clean rebuild で再現した (§2.1 は HEAD の出力・`evidence_2593/probe_u22_shimx_head.txt`)。証跡内のワークツリー絶対パスは `<repo>/` に置換した (それ以外は出力のまま)。
- `git diff 6603d5f5 HEAD -- tools/m11 tools/shimx/src` の出力: 0 行 (測定後の変更は本 REPORT と evidence のみ)。参考: `git diff --stat a50c3ea7 6603d5f5 -- tools/m11 tools/shimx/src` は 19 files (+851 / −65) で、main 取り込み分。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `function_457c70` の alloca `%stack_var_-56` の `+40` 残存値 `0x56670` の書き手 (前の呼出しの残りか、lift で落ちた store か) は未特定。元 x86 との照合も未実施 | unit 22 の 126 と unit 23 の VarBstrFromBool slot の fallback (`0x457860`) の根本原因 | #1607 (`[SHX-T9e]`・open。PR #2550 の未解決表も同じ項目を #1607 に割り当て済み) |
| archive 由来の `boot_final3.ll` と現行 IR の差 (§2.3) | 旧 archive を使うと 126 が再現しない | #2489 (`[SHX-T9h]`・既存) |
| baseline (`m11_win.c:90`) の GetProcAddress に入る hModule 値は未計装 | 「同じ入力か」は未確認 (126 は shimx 側の検査の差として読む) | 記載のみ (追跡は子 issue の範囲) |
