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
    - 走査式: `mov rdx,[rcx+0x10]` → `lea rdx,[rdx+rdx*2]` (`rdx = cnt*3`) で、`[rax+rdx*8]` = `tbl + cnt*24` (24B stride)。§6 と整合。
    - 命令列は `block00031_PE.bin` 内で同一並びを確認 (`83 41 10 01 / 48 8b 51 10 / 48 8d 14 52 / 83 3c d0 ff`)。VA と file offset の対応は未確認
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

## 6. OOB 命令の特定 (2026-10-13, 追補 run、n=1)

再現 (計測コード HEAD `1d7b619e`。後続 commit `09b46640`・`37c5fcaa` は本ファイルの追記・表記修正のみでコード変更なし): gen_ir2 36 秒 rc=0 / build 23.6 秒 rc=0 / survey 11.7 秒 rc=0 (ok 869 / trap 25、§3 と一致) / check_682 2/5 (304=trap 555=trap 923=trap)。

`M11_SURVEY_STACK=304,923,555` の wasm スタックを `trap_triage/oob_insn.py` で逆引きした結果:

| unit | 先頭フレーム (wasm fn / offset) | OOB 命令 | 読んでいる式 |
|---|---|---|---|
| 304 | `function_535bf2` (3370 / 0x1a3318) | `i32.load offset=0` | `tbl + cnt*24` の dword (sentinel `-1` 比較)。`tbl` = `*(*(obj+8)+8)`、`cnt` = `[obj+0x10]` を +1 した値 |
| 555 | `function_535bf2` (3370 / 0x1a3318) | 同上 | 同上 (304 と同一命令・同一 offset) |
| 923 | `function_410b10` (14898 / 0x354e6f) | `i32.load offset=0` | `*(*(obj) - 0x80)` の読み (`obj` = 第 1 引数。`[obj-0x80..]` 系、§4 と一致) |

- 304・555 は同じ OOB 命令 (`535bf2` のテーブル走査) を通る。`535bf2` は `cnt` を加算してから sentinel を探す走査で、sentinel が見つからないか `tbl` が壊れていると線形メモリ外へ出る。
- 原本では走査の前に `0x535c11` の境界チェック (`jl 0x535bf2`) がある。転記 `M11_FIX_535BF2` の C 版でこの境界条件がどう扱われているかは未確認。
- 次の一手 (未着手): OOB 直前に `tbl` と `cnt` の値 (`obj` の 0x08 / 0x10) を JS 側で読み、(a) `tbl` が指す表の sentinel の有無、(b) `obj` の初期化元 (この走査を持つ構造体を作る関数) を特定する。923 は `410b10` の `obj-0x80` の `obj` 生成元を追う。

本追補の run は上記の逆引きまでで止める (真因は未特定)。

## 7. フラグ配線の修正と再測定 (2026-10-13, 追補 run、n=1)

**§3 の訂正**: `M11_FIX_535BF2` は `m11_ov.c` の既定 0 だけで、`m11_build.sh` の `CF` と stamp に渡っていなかった。そのため §3 の「転記 ON」は実際には ON になっておらず、ON/OFF の差分 0 は転記の無効性を示すものではなかった。`m11_build.sh` に `M11_FIX_535BF2` を `CF` と `ov_535bf2.stamp` で配線した (既定 0 のまま)。

| 構成 | build | survey ok/trap | check_682 (304/555/923/291/296) |
|---|---|---|---|
| OFF (既定) | rc=0 / 28.9 秒 | ok 869 / trap 25 | trap, trap, trap, ok, ok (2/5, rc=1) |
| ON (`M11_FIX_535BF2=1`、`ov.o` に転記が入ることを確認) | rc=0 | ok 869 / trap 25 | trap, trap, trap, ok, ok (2/5, rc=1) |

- gen_ir2 48.8 秒 rc=0 / survey OFF 16.0 秒 rc=0。
- ON でも 304・555・923 は trap。転記は OOB の起点ではなかった。

**OOB の実測 (ON, `M11_SURVEY_STACK=304,555,923`)**: 前回 §6 の「304 の先頭 = `function_535bf2`」は再現しなかった。

| unit | 先頭 wasm フレーム (関数) | OOB 命令 | 直上の呼出し鎖 |
|---|---|---|---|
| 304 | 14871 `function_4133f0` (`_UStrAsg`) | `i32.load offset=0` (`[src-8]` の refcount 読出し) | 3147 `function_535ab0` ← 3156 `function_4fad10` ← 1759 `function_4fb910` ← 5235 `function_883140` |
| 555 | 14871 `function_4133f0` | 同上 | 同鎖の一部 (`function_4fad10` 経由 6211 ほか) |
| 923 | 14900 (`function_410b10` 系) | `i32.load` | 1759 `function_4fb910` ← 1758 ← 8526 |

- `function_4133f0` の C 転記 (`m11_ov.c`) は `src != nil` のとき `[src-8]` を読む。src がアドレス空間外の値になっているのが起点。
- **未解決 (次の一手)**: `function_535ab0` が `4133f0` に渡す `src` の出どころ (呼出し元 `function_4fad10` の引数組立て) を、OOB 直前の値で確認する。`function_883140` 側の `i64.const 2074840` (0x1faa18) 付近の定数が、ポインタとして使われていないかも見る。

## 8. 結論 (本 run)

- 受入 1 (304・555 が ok): **未達**。OOB の起点は `_UStrAsg` の src 読出し (§7) で、§6 の `535bf2` 走査仮説は ON/OFF 両方で棄却 (トップフレームに出ない)。
- 受入 2 (923 の原因): **未達**。鎖は §7 の表。
- 受入 3 (回帰 0): OFF 既定の survey は HEAD と同じ ok 869 / trap 25。ON も同一。
