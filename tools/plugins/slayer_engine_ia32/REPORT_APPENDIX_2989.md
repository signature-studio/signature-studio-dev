# REPORT_APPENDIX_2989 — x87 を含む関数の native vs wasm 差分試験 (#2989 PLG-G2-25)

既知類型との関係: 該当なし (`docs/DEFECTS.md` の既存 ID には当たらない)。 f80→f64 の精度差は方式 (ADR D28) の帰結で、行案は `REPORT_APPENDIX_1099.md` §6 (D24 (案)) に既にある。 本付録はその関数レベルでの観測を足す (`DEFECTS.md` は編集しない)。

- 親 REPORT: `tools/plugins/slayer_engine_ia32/REPORT.md` §13。 方式は `docs/DECISIONS.md` D28 (f80→f64)。 本付録が測定値の正本。
- 測定 commit: `565111174` (`feat(ott): native vs wasm differential test for x87 functions (#2989)`。 試験のコードを含む最後の commit)。 本付録の commit は docs のみ。
- 起動・GUI に関わらない (製品 KPI は対象外)。 入力は fl-win64 の `block22434_PE.bin` (sha256 は REPORT_APPENDIX_1223 §1 と同じ素材) と乱数で生成した試行のみ。

## 1. 結論

- x87 を含む leaf 関数 2 本 (`0x10002ee0`・`0x10005400`) を、native (実 x87 命令) と wasm (ia32 x64c lift → `ott_x87.h` の double) で各 4,000 試行 (seed 2989) 実行し、eax・ST(0)・x87 深さ・OBJ 窓 (1,344 B) を突合した。 **構造 (eax・x87 深さ・行数) は全行一致。 float32 結果 (ST(0)・OBJ 窓) は全行一致。**
- ST(0) を double で読むと、**行の 2.75% (`0x10002ee0`: 110 / 4,000) と 14.88% (`0x10005400`: 595 / 4,000) で 1 ulp 以上の差が出る**。 f80→f64 の丸め差で、float32 結果には伝播しなかった (本試験の入力範囲では)。
- ネガコン 2 種とも検出: (a) bit 一致の行 1 件の ST(0) の最下位 bit を反転 → 7,295 → 7,294。 (b) lowering の 1 演算の取り違え (`f_10002ee0` の fsubp を SUB→SUBR) → float32 結果が一致しない行 4,000 / 4,000。

## 2. 対象と方法

- 対象 (`x87_fn_diff.py` の `TARGETS`): どちらも lift 出力で x87 を含み、import も未 lift の call も無い leaf 関数。
  - `0x10002ee0`: stdcall (float a0, 添字 a1) `ret 8`。 `[ecx+a1*4+0xb0..0x1f4]` を読み書きし、ST(0) を残して返る (lift 出力の x87 行 18 件)。
  - `0x10005400`: stdcall (float a0..a4) `ret 0xc`。 `fcomp`・`fnstsw`・`fdivr` と `[ecx+0x4fc..0x518]` の更新を含む (x87 行 71 件)。
- native (`x87_fn_native.c`): freestanding i386 ELF。 image を VA `0x10000000` に敷設し、呼出し前に `fninit`、呼出し後に `fnstsw` で TOP から深さ `d = (8 - TOP) & 7` を求め、`fsts` (float32)・`fstl` (float64) で ST(0) を読む。
- wasm (`x87_fn_glue.c`・`x87_fn_entry_wasm.mjs`): `ott_lifted.c` を同じ翻訳単位に取り込む (`ott_x87.h` の state は static のため)。 呼出し前に x87 を初期化し、呼出し後に `d = (8 - ott_ftop) & 7`、ST(0) を `(float)` と `(double)` で取る。
- 入力: seed 2989。 OBJ 窓の初期値は一様な有限の float32 (±1000)。 float 引数は `fn_10002ee0` が ±1000、`fn_10005400` が ±100。 添字は 0..15。
- 判定: 構造 (行数・eax・x87 深さ不一致 0、OBJ 窓が変わった行 = 非自明性) を exit の条件にする。 float 語の差分は落とさず分布として出す (ADR D28 の f80→f64 の差を gate しないため)。

## 3. 実測 (測定 commit `565111174`、`ws-2989` で再現)

| 関数 | n | 行の全項目が一致 | float32 結果のみ一致 | ST(0) float64 の一致 / 1ulp / 2ulp / ≥3ulp | eax・x87 深さ不一致 | OBJ 窓が変わった行 |
|---|---:|---:|---:|---|---:|---:|
| `0x10002ee0` | 4,000 | 3,890 (97.25%) | 4,000 / 4,000 | 3,890 / 64 / 22 / 24 | 0 / 0 | 4,000 |
| `0x10005400` | 4,000 | 3,405 (85.12%) | 4,000 / 4,000 | 3,405 / 595 / 0 / 0 | 0 / 0 | 4,000 |

- OBJ 窓の float32 語: 1,344 B = 336 語 × 4,000 行 × 2 関数 = 2,688,000 語、全語一致。
- 所要 (1 driver 実行): native build 0.03–0.05 s、emcc 3.36–3.64 s、native 実行 0.104–0.106 s、wasm (node) 0.145–0.152 s。 load1 は 0.16–0.49 (cpu 4)。 driver 全体は約 5 s。
- 再現: 同じ seed で 2 回実行し、上の数値は同一 (`main` checkout と `ws-2989` の双方で確認)。

## 4. ネガコン

- (a) 判定器: wasm 側の bit 一致行 (行 0) の ST(0) float32 の最下位 bit を反転 → bit 一致 `7295 → 7294` (`python3 x87_fn_diff.py --nega`、exit 0 = 検出)。
- (b) 意味の誤り: `lift` の `f_10002ee0` の最初の `x87_arith(2, 1, …)` (X87_SUB) を `(3, 1, …)` (X87_SUBR) に差し替えて wasm を作り直す → `fn_10002ee0` の float32 結果が一致しない行 `4,000 / 4,000` (`python3 x87_fn_diff.py --nega-lower`、exit 0 = 検出)。 この取り違えで float32 結果がずれることを確認したので、float32 の全行一致は空振りではない。

## 5. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 EMSDK=$RUNNER_TEMP/emsdk    # fl-win64 は extracted/block22434_PE.bin のみで足りる
source $EMSDK/emsdk_env.sh                                            # emsdk 6.0.12 (toolchain-emsdk)
python3 tools/plugins/slayer_engine_ia32/lift_text.py                 # work/lift_text/ott_lifted.c を作る (前提)
python3 tools/plugins/slayer_engine_ia32/x87_fn_diff.py               # 突合 (exit 0)
python3 tools/plugins/slayer_engine_ia32/x87_fn_diff.py --nega        # ネガコン (a) (exit 0)
python3 tools/plugins/slayer_engine_ia32/x87_fn_diff.py --nega-lower  # ネガコン (b) (exit 0)
```

- 鮮度の証跡 (WORKFLOW §6): 測定 commit `565111174` の後に変えたのは本付録と REPORT / DOC_MAP の文書のみ。 `git diff 565111174 HEAD -- tools/plugins/slayer_engine_ia32/x87_fn_diff.py tools/plugins/slayer_engine_ia32/x87_fn_native.c tools/plugins/slayer_engine_ia32/x87_fn_glue.c tools/plugins/slayer_engine_ia32/x87_fn_entry_wasm.mjs tools/plugins/slayer_engine_ia32/lift_text.py tools/ott/lift tools/ott/rt` の出力は 0 行。 検証 HEAD は PR 本文の『検証 HEAD』欄が正 (付録の commit 自身では hash を書けないため)。

## 6. 範囲と未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 残りの leaf x87 関数 36 本 (lift 済み・import と call が無い) の差分試験 | 対象の 2 本以外の x87 の命令組合せは未確認。 本付録の 2 本で受入は満たす | 未起票 (本表で追跡。 同じ scen 生成で足せる) |
| 超越関数・`frndint`・`fscale`・`fprem` 等を含む関数 (lift が `ott_unsup` のまま) | 対象外 | #2966 (PLG-G2-23) |
| `fld`/`fstp` m80 の差分試験 | 80bit メモリ経路は未試験 | #2967 (PLG-G2-24) |
| 入力は一様な有限 float32 のみ (NaN・inf・非正規・0 除算は未試験)。 引数は 6 本まで | 例外的な値での一致は未確認 | 未起票 (本表で追跡) |
| export `main`・import を通る関数・実行時の間接 call・`sahf` の AF・`fs:` (TEB) | 関数単位の残り (x87 以外も含む) | #3127 / #3128 |
| f80→f64 の丸め差 (ST(0) の double で 1 ulp 以上、行の 2.75% / 14.88%) | float32 結果には伝播しなかった。 方式の帰結 | ADR D28 (方式)。 行案 D24 (案) は `REPORT_APPENDIX_1099.md` §6 |
