# #3095 (KH-43) Delay の SIMD 疑似関数・swi の規則 (付録)

- **結論**: 現 main の Delay emcc 残件 576 件のうち、SIMD 疑似関数 25 件 (13 種) を shim に**実装**し、swi 21 件を **fail-fast** (abort) とした。emcc 残件は **506 件** (SIMD・swi の未宣言 0)。Gain/Haas/Gate は 1000/1000 bit-exact (回帰なし)。実装 13 種はホスト x86 intrinsics と 200,000 試行で一致 (ネガティブコントロールは FAIL)。
- **入力の訂正**: issue 本文の「SIMD 40 件・swi(3) 21 件」は測定 commit `7d1d0e2e` の値 (emcc 601 件) である。現 main では SIMD 25 件。差 15 件 (ABS 10・ZEXT416 2・maxps 2・vpsrldq_avx 1) は #3071 で shim に定義済み。swi 21 件の内訳は **swi(3) 17 件 + swi(0x29) 4 件** (issue の「swi(3) 21 件」は誤り)。

## 1. 測定の前提

- 素材: `plugins-kilohearts` (Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` 76,642,304 B、`work/` に手展開)、`toolchain-emsdk` (emcc 6.0.12)。
- Ghidra 12.1.4 ([GHIDRA]): 公式 release zip を run 内で取得し、sha256 `ddac49f9…d2db` の一致を確認。JDK 21 (temurin-21)。
- decompile: lift 集合 141 件。`snapins/snapins.json` の `delay.lift` を**挿入順**で渡す (昇順では emcc 577 件になり、601 は再現しない)。結果 **141/141 OK** (wall 28〜29 s, n=1)。Gain/Haas/Gate は 10 関数で **10/10 OK** (27 s)。
- load: 測定時 0.4〜0.6 (4 vCPU)。

## 2. 規則

| 疑似関数 | 件数 (現 main, 変更前) | 規則 | 定義の内容 |
|---|---|---|---|
| `SUB84(x, off)` | 3 | 実装 | lvalue から `off` の 4 byte を切り出す (`kh_sub84`) |
| `SUB168(x, off)` | 5 | 実装 | V128 値から `off` (0/8) の 8 byte を切り出す |
| `ZEXT816(v)` | 2 | 実装 | 下位 64bit に v、上位 64bit は 0 (movq) |
| `minps` | 1 | 実装 | lane 毎 `a < b ? a : b` (NaN は b)。`maxps` と対称 |
| `vcvtdq2pd_avx` | 3 | 実装 | 下位 2 個の int32 → 2 個の double |
| `vcvtpd2dq_avx` | 1 | 実装 | 2 個の double → int32 (既定丸め = 最近接偶数)。NaN・範囲外は 0x80000000、上位 64bit は 0 |
| `vshufps_avx` | 2 | 実装 | Intel の SHUFPS 選択 (imm の 2bit ずつ) |
| `vpmovsxdq_avx` | 2 | 実装 | 下位 2 個の int32 を符号拡張して int64 |
| `vpsubq_avx` / `vpsubd_avx` | 1 / 1 | 実装 | src1 − src2 (lane 毎・wrap) |
| `vpsrlq_avx` | 1 | 実装 | lane 毎の論理右シフト。imm ≥ 64 は 0 |
| `vpand_avx` / `vpor_avx` | 1 / 2 | 実装 | 128bit の論理積・論理和 |
| `swi(n)` (17 + 4) | 21 | **fail-fast** | `kh_swi_fail()` = `abort()`。引数は評価しない |
| `ABS` / `ZEXT416` / `maxps` / `vpsrldq_avx` | (現 main では 0) | 既存 | #3071 で定義済み (`fabs`・`ZEXT416`・`maxps`・`vpsrldq_avx`)。本 issue では変更なし |

- 実装 13 種の合計は 25 件 (= 3+5+2+1+3+1+2+2+1+1+1+1+2)。
- SUB168・SUB84 の未宣言エラーは消えるが、同じ行の V128 同士の `*` (`auVar6 * auVar3`) と `^` は型不一致として残る (#3096)。SIMD 行に残った 17 件はレーン参照 (#3094) と型不一致 (#3096)。
- **swi の根拠**: x86 の `int 3` は breakpoint、`int 0x29` は `__fastfail` で、どちらも戻らない trap。直後は `(*pcVar1)();` (間接呼出し) で、正常系の戻りは無い。未処理なら Windows では process が終わるため、abort による fail-fast が同じ観測結果になる。到達の有無は native 突合で確認する (#3073)。

## 3. emcc 残件の変化 (`ghidra_route/emcc_census.py`、排他分類)

| 分類 | 601 (`7d1d0e2e` 再現) | 576 (現 main, 変更前) | 506 (`12647936d`) |
|---|---|---|---|
| 未関数化 callee | 6 | 6 | 6 |
| レーン型 (`undefined1[N]`・メンバ参照) | 200 | 190 | 166 |
| 引数数不一致 | 108 | 108 | 108 |
| SIMD・AVX・swi 疑似関数 | 61 | 46 | **0** |
| code 型の間接呼出し | 21 | 21 | 21 |
| 未定義 identifier | 17 | 17 | 17 |
| 演算・代入の型不一致 | 186 | 186 | 186 |
| その他 | 2 | 2 | 2 |
| **合計** | **601** | **576** | **506** |

- 576 → 506 (−70): SIMD・swi −46 と、同じ行に付随していたレーン型 −24。変更前後で、疑似関数を含まない行のエラーは 489 件で不変 (行単位で照合)。
- 601 → 576 (−25): SIMD −15 (#3071 の定義による。`7d1d0e2e` の shim を `git archive` で取り出し、同じ out141 から 601 件を再現して確認)。レーン −10 は原因未特定。

## 4. 検証 (測定 commit `12647936d`・`git archive HEAD` の clean export で再実行)

- **単体突合** (`ghidra_route/simd_shim_check.c`): 実装 13 種を、ホストの x86 intrinsics (`_mm_sub_epi64`・`_mm_min_ps`・`_mm_cvtpd_epi32`・`_mm_shuffle_ps` 等) と各 200,000 試行で比較。入力は乱数の 128bit (vcvtpd2dq は任意ビット列の double で NaN・Inf・範囲外を含む、vshufps は代表 16 通りの即値)。**mismatches: 0** (rc 0)。
- **ネガティブコントロール**: `-DKH_NEG=1` で vpsubq の参照を `b − a` にすると **mismatches: 200000、rc 1**。検査が誤りを検出することを確認した。
- **回帰** (`build_cmp.sh <n> 1000 7 bitcast,intload,stackpair,assoc,concat`、clean HEAD):
  - Gain **1000/1000** bit-exact (calls 4999/4999, wasm 15,161 B)
  - Haas **1000/1000** (calls 5500/5500, wasm 16,878 B)
  - Gate **1000/1000** (calls 4999/4999, wasm 17,367 B)
  - 3 本とも wasm サイズは §10-7q ⑤ と一致。生成 C は変更前の converter の出力と `cmp` で一致 (3 本とも差分 0)。
- **未実施**: Delay の native 突合 (emcc が 506 件で通らないため)。#3073 の範囲。

## 5. 測定 commit の証跡

- 測定 commit = `12647936d` (コード変更は `ghidra_route/ghidra_shim.h`・`ghidra_route/ghidra_to_c.py`・新規 `ghidra_route/simd_shim_check.c`)。
- `git diff 12647936d HEAD -- tools/targets/kilohearts/ghidra_route tools/targets/kilohearts/snapins/scripts` の出力は 0 行 (この節を含む REPORT の commit は範囲外)。

## 6. 再現

```sh
cd tools/targets/kilohearts
# (1) decompile: DecompEach.java に lift 集合 141 件を挿入順の 10 進で渡す (snapins.json の delay.lift)
python3 ghidra_route/ghidra_to_c.py delay work/gr/x work/ghidra/out141 work/winpkg/HeartCore.core_64 --fix bitcast,intload,stackpair,assoc,concat
emcc -c -ferror-limit=0 -I ghidra_route work/gr/x/delay.c -o work/gr/x/delay.o 2> work/gr/x/emcc.log
python3 ghidra_route/emcc_census.py work/gr/x/emcc.log            # 合計 506
# (2) 単体突合 (emscripten.h のスタブを置く)
printf '#define EMSCRIPTEN_KEEPALIVE\n' > work/simd_check/emstub/emscripten.h
gcc -O1 -mavx2 -Wno-unused-function -I ghidra_route -I work/simd_check/emstub ghidra_route/simd_shim_check.c -o work/simd_check/pos -lm && work/simd_check/pos   # mismatches: 0
gcc -O1 -mavx2 -DKH_NEG=1 -Wno-unused-function -I ghidra_route -I work/simd_check/emstub ghidra_route/simd_shim_check.c -o work/simd_check/neg -lm && work/simd_check/neg   # mismatches: 200000, rc 1
# (3) 回帰
bash ghidra_route/build_cmp.sh gain 1000 7 bitcast,intload,stackpair,assoc,concat   # haas / gate も同じ
```

## 7. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| レーン参照 166 件 (`undefined1[N]` のメンバ参照。`auStack_x._8_4_`・`auVar._0_16_` 等) | Delay の emcc が通らない | #3094 [KH-42] |
| 引数過不足 108・型不一致 186 (V128 同士の `*`・`^` を含む)・code 間接呼出し 21・未定義 identifier 17・未関数化 6・その他 2 (計 340) | 同上 | #3096 [KH-44] |
| 実装 13 種のオペランド順 (Ghidra pcodeop の規約: 先頭が vvvv の src1) を機械語で個別確認していない。swi の到達は未確認 | 反転・到達の誤りは Delay の native 突合でしか検出できない | #3073 [KH-41] |
| レーン 200 → 190 の 10 件の原因 (`7d1d0e2e` 以降の変更のどれか) | 件数の説明のみ | 起票しない (件数の説明だけの未解決) |
