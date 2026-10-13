# #714 304/555: function_535bf2 の closure 外呼出し・923: OOB (部分調査, 2026-10-13)

**判定: 未達 (受入 1・2 は未達、受入 3 は回帰 0 のみ確認)。** 本 run は調査と、既定 OFF の C 転記 `M11_FIX_535BF2` の追加まで。

## 1. 受入条件の判定

| 受入条件 | 判定 | 根拠 |
|---|---|---|
| 535c2e が closure に入らない理由を実測し解消。304・555 が ok | **未達** | §2 で原因を特定 (535c2e は関数でなく 535bf0 系の `ret`)。転記で abort は消えたが、304・555 は OOB で trap のまま (§3) |
| 923 の OOB 原因を特定 | **未達** | §4。`410b10` 系の OOB の起点は未特定 |
| 回帰 0 (unit 単位、ネガコン付き) | **確認 (転記 OFF/ON 間で差分 0)** | §3。ただし転記 ON は既定にしていないので、現 HEAD の既定挙動は HEAD `1f83c5ee` と同じ |

## 2. 535c2e の正体 (実測)

- `0x535c2e` は関数の入口ではない。逆アセンブル (capstone, `block00031_PE.bin`):
  - `0x535bf0`: `jmp 0x535c11` (63B の関数)
  - `0x535bf2`: `add [rcx+0x10],1` … `cmp dword [rax+rdx*8],-1` … `jmp 0x535c2e`
  - `0x535c11`: 境界チェック後 `jl 0x535bf2`、否なら `xor eax,eax`
  - **`0x535c2e` = `ret`** (`0x535bf0` 関数の共通の戻り点)
- IR (`boot_final3.ll` 192008): `function_535bf2` の末尾が `call i64 @function_535c2e()` で、`declare` のみ (定義なし)。RetDec が分岐先の `ret` を独立関数として切り出した誤り。
- `m11_extra_seeds.txt` に `0x535c2e` が累積されていたが、`m11_tail.py` の `size(sv)` が 0 になり closure に入らない (`ret` の途中アドレスなので関数サイズが引けない)。**seed 追加では直らない**。
- 呼出し元: `function_535c11` (IR 192006 他)・`function_4fad10` 系 (IR 181122 他) が `535c11` / `535bf2` を呼ぶ。

## 3. 転記 (M11_FIX_535BF2) の実測

`m11_ov.c` に `function_535c11` / `function_535bf2` の C 転記を追加 (既定 0 で commit `8bea8f79`)。

| 構成 | build | survey ok/trap | 5 unit (304/555/923/291/296) | failfast |
|---|---|---|---|---|
| 転記 OFF (`M11_FIX_535BF2=0`) | rc=0 | 869 / 25 | trap, trap, trap, ok, ok | {} |
| 転記 ON (`M11_FIX_535BF2=1`) | rc=0 | 869 / 25 | trap, trap, trap, ok, ok | {} |

- 転記 ON/OFF で unit の判定は全 942 unit で同じ (ok 数・trap 数とも一致)。
- `M11_SURVEY_STACK=304,923` (転記 ON): unit 304 = `0x483140` / unit 923 = `0xf6c660`、いずれも `RuntimeError: memory access out of bounds`。
- 所要: build 25.9 秒 (IR 生成 43.8 秒を含まず)、survey 13.7 秒。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 304・555: `function_535bf2` の戻り/境界で OOB。closure 外参照は転記で消えたが、OOB の真因は未特定 | 2 unit が trap | #714 (継続) |
| 923: `410b10` 系 `[obj-0x80..]` の OOB 起点 | 1 unit が trap | #714 (継続) |
| `M11_SURVEY_STACK` は wasm フレームを出さない (メッセージのみ) | OOB の起点特定が手作業 | 要ツール化 (PM 判断) |

## 5. 再現

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64
cd tools/m11
bash m11_gen_ir2.sh                 # ldfix=applied (約 44 秒)
bash m11_build.sh                   # rc=0
mkdir -p work/probe714
M11_SURVEY_UNITS=work/probe714/units_714.json node m11_survey.mjs
python3 trap_triage/check_682.py work/probe714/units_714.json --units 304,555,923,291,296   # rc=1 (2/5)
```
