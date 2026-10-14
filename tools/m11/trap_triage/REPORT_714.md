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
- **集計差 (ok 869 / trap 25、§9 の ok 870 / trap 24 との差) は未特定**。§7 の測定 commit は本文に明記されていない。差の候補は §9 「検証」を参照。

**OOB の実測 (ON, `M11_SURVEY_STACK=304,555,923`)**: 前回 §6 の「304 の先頭 = `function_535bf2`」は再現しなかった。

| unit | 先頭 wasm フレーム (関数) | OOB 命令 | 直上の呼出し鎖 |
|---|---|---|---|
| 304 | 14871 `function_4133f0` (`_UStrAsg`) | `i32.load offset=0` (`[src-8]` の refcount 読出し) | 3147 `function_535ab0` ← 3156 `function_4fad10` ← 1759 `function_4fb910` ← 5235 `function_883140` |
| 555 | 14871 `function_4133f0` | 同上 | 同鎖の一部 (`function_4fad10` 経由 6211 ほか) |
| 923 | 14900 `function_410b10` (OOB 直前 `i64.const 128; i64.sub` = `obj-0x80`) | `i32.load` | 1759 `function_4fb910` (呼出し鎖の上位は未確認) |

- `function_4133f0` の C 転記 (`m11_ov.c`) は `src != nil` のとき `[src-8]` を読む。src がアドレス空間外の値になっているのが起点。
- **未解決 (次の一手)**: `function_535ab0` が `4133f0` に渡す `src` の出どころ (呼出し元 `function_4fad10` の引数組立て) を、OOB 直前の値で確認する。`function_883140` 側の `i64.const 2074840` (0x1faa18) 付近の定数が、ポインタとして使われていないかも見る。

## 8. 結論 (本 run)

- 受入 1 (304・555 が ok): **未達**。OOB の起点は `_UStrAsg` の src 読出し (§7) で、§6 の `535bf2` 走査仮説は ON/OFF 両方で棄却 (トップフレームに出ない)。
- 受入 2 (923 の原因): **未達**。鎖は §7 の表。
- 受入 3 (回帰 0): OFF 既定の survey は HEAD と同じ ok 869 / trap 25。ON も同一。

## 9. OOB 呼出し鎖の再測定と呼出し元 (2026-10-13, 追補 run 3、n=1)

**注意: 本節の数値は、WORKFLOW §4.6 / AGENTS §4.6 に違反した手順で取った値である** (共有 main ツリーで測定。本 PR の HEAD では再現していない)。以下は違反した手順による記録として扱い、検証 commit 限定の数値とする。

測定 (`M11_FIX_535BF2` 既定 0 = OFF、測定 commit `92cfb784`、共有 main 作業ツリーで実施、n=1。コード変更は本 PR に無い): gen_ir2 rc=0 / build rc=0 / survey rc=0 / check_682 2/5 (304=trap 555=trap 923=trap 291=ok 296=ok) rc=1。
survey の集計は ok 870 / trap 24 / noproc 1 / miss 47 で、§7 (ok 869 / trap 25) と一致しない。**原因は未特定** (下記「検証」)。check_682 の判定は同じ。
**本検証 (fix run) で再現不能**: 上記の数値は `92cfb784` の共有 main ツリーでの測定値として残すが、検証 commit 限定の数値として扱う。下記「検証」を参照。

**先頭 wasm フレーム (OFF, `M11_SURVEY_STACK=304,923`、`trap_triage/oob_insn.py` で逆引き)**

| unit | 先頭フレーム | OOB 命令 | 直上の呼出し鎖 (wasm index) |
|---|---|---|---|
| 304 | 3372 `function_535bf2` (0x1a336f) | `i32.load` = `tbl + cnt*24` の sentinel 比較 (`tbl`=`*(*(obj+8)+8)`、`cnt`=`[obj+0x10]`+1) | 3147 `function_535ab0` ← 3157 `function_4fad10` ← 1759 `function_4fb910` ← 5237 ← 12403 ← 14849 ← 14865 |
| 923 | 14900 `function_410b10` (0x354f17) | `i32.load` = `*(*(obj)-0x80)` | 2017 ← 1759 `function_4fb910` ← 1758 ← 8528 ← 14849 ← 14865 |

- §6 (OFF) の「304 の先頭 = `function_535bf2`」と一致する。§7 (ON) では先頭が `function_4133f0` に変わる。先頭フレームは `M11_FIX_535BF2` の値で変わるため、§7 の「535bf2 仮説は棄却」は OFF 側では成立しない。ON 側の結論と OFF 側の結論を分けて扱う。

**IR 上の呼出し元 (`work/boot_final.ll`)**

- `function_535bf2` (189324): `obj+0x10` を +1 して `tbl + cnt*24` を読み、`-1` なら `function_535c11(@m11num_1)` を呼ぶ。`function_535c11` (189355) は `[obj+8]+8` と `[items-8]` で境界を見る。
- `function_535c11` の呼出し元: `function_4fa3d0` (178270 から始まる関数内 178436 / 178462 / 178501 / 178527)、`function_4fad10` (178917 から始まる関数内 179009 / 179035)。両方とも引数は `function_535240(obj_field, flag)` の戻り値で、`function_535240` は `function_535b30(const 1003752, flag, obj)` を呼ぶ。
- `function_4fad10` は `function_535ab0` を 179017 で呼ぶ (`stack_var_-80` を渡す)。`function_535ab0` は `function_4133f0(arg, src)` を先に呼ぶ。
- `function_4fb910` (179735) は `function_4fad10(load [18818720], arg1, arg2)` を呼ぶ。`function_4fb910` の呼出し元のうち 102123 (`function_136c660`) は `arg2 = 2074840` (0x1faa18) で呼ぶ。0x1faa18 は survey の image 範囲 (0x400000〜0x1ec0000) の外にある定数で、ポインタとして使われているかは未確認。
- `function_4fb910` の 206344 / 206345 / 211067〜211069 でも同じ定数 (2074840) を arg2 にして呼ばれている。

**次の一手 (未着手, 優先順)**

1. `function_4fad10` の 179017 付近で `tbl` と `cnt` を作る `obj` (`function_535240` の第 1 引数) の由来を確認する。OOB 直前の `obj+8` / `obj+0x10` の値を JS 側で読むのが最短。
2. `function_4fb910` の arg2 = 0x1faa18 が `function_4fad10` 内でどう使われるか (アドレスとして読まれるか) を確認する。
3. 923: `function_410b10` の `obj` を渡す `function_4fb910` 側 (1759) の arg1 (= 16169216 系の定数) から辿る。

### 検証 (差し戻し対応 run, 2026-10-13)

- **再測定は不能**。素材 `fl-win64` は `$HOME/artifacts` から `$RUNNER_TEMP/fl-win64` へ展開でき (`extracted/block00031_PE.bin` 実在)、`bash m11_gen_ir2.sh` を実行したが rc=1 (`m11_merge.py` が `work/boot0.lift.ll` を開けない)。lift 成果物は RetDec (`[RETDEC]`) で作るが、本 run の素材指定は `fl-win64` のみで `toolchain-retdec` が無く、`work-m11` / `work-liftdiff` も `$ARTIFACTS_DIR` に無い。`tools/m11/work/` の前回生成物も無い。このため gen_ir2 / build / survey / check_682 は本 run で再実行しておらず、§9 の数値は測定 commit `92cfb784` の記録として残す (検証 commit 限定)。
- **main 共有ツリーの状態**: 本 run で確認した `git status --porcelain` は ` M package.json` / ` M pnpm-lock.yaml` の 2 件 (本 run は触っていない)。`92cfb784` 測定時の clean 状態は記録が無く、未確認。
- **鮮度 (92cfb784 → 08fd858a)**: `git diff 92cfb784 08fd858a -- tools/m11 ':!*.md'` の出力は次の 2 ファイルのみ。
  - `tools/m11/m11_zeropad_liftdiff.py` (新規 82 行)
  - `tools/m11/results/sigfix_zeropad_liftdiff.tsv` (新規 1,050 行)
  - 経路外の根拠: `grep -rn` で両ファイルを参照するのは `REPORT_N55.md` と `docs/DOC_MAP.md` のみ。`m11_gen_ir2.sh`・`m11_build.sh`・`m11_survey.mjs`・`trap_triage/check_682.py` はいずれも liftdiff を参照しない。両ファイルは 0 詰め site の集計 TSV 出力だけで、IR・image・survey の入力にならない。
- **集計差 (870 / 869) は未特定**。§7 には測定 commit が書かれていないため、比較基準は仮定 (§6 の計測 HEAD `1d7b619e`) として扱う。`1d7b619e..92cfb784` の間に、survey・build・IR 生成に効く m11 ファイルが 47 件変わっている (`m11_ov.c`・`m11_build.sh`・`m11_passes.py`・`m11_post.py`・`m11_survey.mjs` を含む)。候補は `9af7827f` (#1043、`function_980ed0` の 10 進 inttoptr を LVA に remap、IR を変える) と `b57371e9` (#1004、survey に guest ポインタ検査を追加) など。ただし unit 別の結果 (JSON) が §7 と §9 のどちらにも残っておらず、どの unit が trap→ok に移ったかは確認できない。判定 (check_682 の 2/5) には影響しない。

## 10. 再現の実測と OOB 実値の採取計画 (2026-10-13, 追補 run 4、n=1)

測定 commit `a67af27b` (本 PR の作業ベース。コード変更なし)。`git diff a67af27b HEAD -- tools/m11` は本 PR 追記の REPORT_714.md のみ。素材は `$RUNNER_TEMP` と worktree の `tools/m11/work/` に展開 (fl-win64・toolchain-retdec・toolchain-emsdk・work-m11・work-liftdiff)。`FL_WIN64_DIR`・`RETDEC_ROOT` で参照。`M11_FIX_535BF2` 既定 0 (OFF)。

| 工程 | 結果 | 所要 |
|---|---|---|
| `m11_gen_ir2.sh` | rc=0 (`boot_final.ll` 490693 行) | 35.6 秒 |
| `m11_build.sh` | rc=0 (`m11_boot.cjs(+.wasm)`) | 22.8 秒 |
| `m11_survey.mjs` | rc=0 / ok 870 / trap 24 / noproc 1 / miss 47 / units 942 | 13.3 秒 |
| `check_682.py` | 2/5 (304=trap 555=trap 923=trap 291=ok 296=ok) rc=1 | - |

load average は工程中 1.3〜2.4。§9 の ok 870 / trap 24 と一致した (§7 の 869 / 25 との差は今回の HEAD でも残る)。

**先頭フレームの逆引き** (`M11_SURVEY_STACK=304,555,923`、`trap_triage/oob_insn.py`):

- 304・555: `function_535bf2` (wasm 3372, 0x1a336f)。`i32.load offset=0` (`tbl + cnt*24` の sentinel 比較)。§9 と同一。
- 923: `function_410b10` (wasm 14900, 0x354f17)。`i32.load offset=0` (`*(*(obj)-0x80)`)。§9 と同一。
- IR の呼出し鎖 (`work/boot_final.ll`): `function_535240` → `function_535b30` (`obj` は `function_535240` の第 1 引数)。`function_4fad10` は `function_535ab0` を呼び、その先頭で `function_4133f0(%0, %14)` を呼ぶ。

**判定**: 受入 1・2 は**未達のまま**。今回の実測は §9 の追認で、OOB 時の `tbl`・`cnt`・`obj` の**実値**は未採取。

### 次の一手 (実値の採取)

wasm の外から、OOB 直前の値を読む計測が必要。

1. 304・555: `function_535bf2` の入口で `obj`・`*(obj+8)`・`*(obj+8)+8`・`obj+0x10` を JS 側で読み、`tbl`/`cnt` が線形メモリ内か確認する。
2. 923: `function_410b10` の入口で `obj` を読み、`obj-0x80` が範囲外か確認する。
3. 両者の `obj` を作る関数 (`function_4fad10` / `function_4fb910` の arg1・arg2) まで遡る。

子 issue を起票する (`[M11-N91]`、`親: #714`)。既存 `[M11-N62]` (halt0 unit 492 の 4133f0 系 OOB) と対象 unit が別なので重複にはしない。

### 11. 実値採取の試行と計測器の影響 (2026-10-13, 追補 run 5、n=1)

測定 commit `3ed5a18c` (origin/main, 本 PR の作業ベース。コード変更なし)。素材は `$RUNNER_TEMP` と worktree の `tools/m11/work/` に展開。

| 工程 | 結果 | 所要 |
|---|---|---|
| `m11_gen_ir2.sh` | rc=0 | 34.8 秒 |
| `m11_build.sh` (probe 無し・`boot.o` 再生成) | rc=0 | 18.3 秒 |
| `m11_survey.mjs` | rc=0 / ok 870 / trap 24 / noproc 1 / miss 47 | 13.3 秒 |
| `check_682.py` | 2/5 (304=trap 555=trap 923=trap 291=ok 296=ok) rc=1 | - |

**probe 入口 dump の試行は不採用**: `probe_entry.sh` (`m11_pe`) で 304・923 を入れた build は、`[pe]` が 1 件も出ず、304 が ok・923 が oob になった。probe の挿入が OOB の挙動を変える。`probe_entry.sh` の手順は `boot.o` を作り直すが、直後の `m11_build.sh` は `boot_final3.ll` が新しいと再コンパイルしないため、後片付けの順序にも注意が要る。probe 版で得た ok 判定は計測器の影響として扱い、本 REPORT の判定には使わない。

**stale `boot.o` の注意**: probe 版の `boot.o` を消さずに通常 build を回すと、通常 build の判定 (ok 4/5) が probe 版のものになった。`boot.o` を消して再ビルドし、2/5 (trap 3 件) に戻ったことを確認した。

**先頭フレーム (probe 無し・clean build、`M11_SURVEY_STACK=304,555,923`)**: 304・555 は wasm 3372 `function_535bf2` (`0x1a336f`)、呼出し鎖 3147 `function_535ab0` ← 3157 `function_4fad10` ← 1759 `function_4fb910` ← 5237 ← 12403 ← 14849 ← 14865。§9 と一致。

**未解決 (変更なし、起票先 #714 / 子 `[M11-N91]` #1426)**: OOB 時の `tbl`・`cnt`・`obj` の実値は未採取。wasm の関数引数 (local) を読む手段が現行ツールに無い (`oob_insn.py` は命令の逆引きのみ)。実値採取には、probe を使わず wasm local を読む計測の追加が要る。これは `[M11-N91]` の範囲。

判定: 受入 1・2 は未達のまま (本 run は再現と計測器の影響の確認まで)。

## 12. 実値採取の再試行 (#1426, 2026-10-14, n=1)

測定 commit `cb3a89a6` (origin/main, 本 PR の作業ベース。コード変更なし)。素材は `$RUNNER_TEMP/fl-win64`・`tools/m11/work/` (work-m11)・`$RUNNER_TEMP/retdec`・`$RUNNER_TEMP/emsdk` に展開 ([EMSDK]・[RETDEC] は既存)。`FL_WIN64_DIR` 指定。`M11_FIX_535BF2` 既定 0 (OFF)。load average は開始時 0.66。

| 工程 | 結果 | 所要 |
|---|---|---|
| `m11_gen_ir2.sh` | rc=0 (`boot_final.ll` 490693 行、§10 と一致) | 39.0 秒 |
| `m11_build.sh` | rc=0 (`m11_boot.cjs(+.wasm)`) | 23.4 秒 |
| `m11_survey.mjs` (通常 build) | rc=0 / ok 870 / trap 24 / noproc 1 / miss 47 | 14.4 秒 |
| `check_682.py` | 2/5 (304=trap 555=trap 923=trap 291=ok 296=ok) rc=1 | - |

**probe 版で実値を採る試行は失敗**。`probe_entry.sh` で入口 dump を入れると、対象 unit が `trap` でなく `halt0` (DllMain 完了後の longjmp) で止まり、`[pe]` 行は 0 件だった。

| 試行 | survey 結果 (`SURVEY_UNITS`) | `[pe]` 行 | 所要 |
|---|---|---|---|
| `probe_entry.sh p535 535bf2,410b10 304,923` | `halt0: 2` (304・923 とも起動直後に停止) | 0 | 40.0 秒 |
| `probe_entry.sh p923 410b10 923` | `halt0: 1` | 0 | 未計測 (所要は記録せず) |
| probe 後の復元 → 通常 build survey | ok 870 / trap 24 / noproc 1 / miss 47、check_682 2/5 (§10 と一致) | - | 14.4 秒 |

- 復元 (`probe_entry.sh` の trap restore) で通常 build の判定は元に戻った。probe 版の結果は本判定に使わない。
- 含意: 入口 dump の `call` を挿入すると、304・923 の OOB は trap でなく別経路 (halt0) に変わる。§10 下位節 11 の「probe の挿入が OOB の挙動を変える」は、この unit では trap 自体が消えることを意味する。OOB 直前の値を入口 dump で採る方式は、この 2 unit では使えない。
- `m11_survey.mjs` は wasm の関数 local を出さないため、trap 時点の `tbl`・`cnt`・`obj` の値はこの手段では読めない (§10 下位節 11 と同じ結論)。

**鮮度の注記 (差し戻し対応 run, 2026-10-14)**: 本 PR の HEAD は main 取り込み後 (`af3b1d7e`)。`git diff cb3a89a6 HEAD -- tools/m11` には本節の追記と他 area の REPORT (md) 追加も含まれ、実行されるコードの差分は main 側の `tools/m11/ldfix/bin_table_pre_boot.mjs` (新規 29 行、#942 の診断用。`m11_gen_ir2.sh`・`m11_build.sh`・`m11_survey.mjs`・`check_682.py` のいずれも参照しない) の 1 件だけ。上の表は測定 commit `cb3a89a6` の数値として残す。差分はパイプライン外だが、`toolchain-retdec`・`work-m11` が `$ARTIFACTS_DIR` に無いため HEAD での再測定はできていない。

### 判定 (本 run)

- 受入 1 (304・555 の OOB 直前の `obj`・`*(obj+8)`・`*(obj+8)+8`・`obj+0x10` の実測): **未達**。実値は未採取。
- 受入 2 (923 の `function_410b10` 入口の `obj` 実測): **未達**。
- 受入 3 (回帰 0): **確認**。通常 build の survey は ok 870 / trap 24 (§10 と一致)、check_682 は 2/5 のまま。

## 13. C 版内 stderr 計測 (#1602, 2026-10-14, n=1)

結論: C 版内の stderr 計測 (`M11_INSTR_1602=1`) の ON では survey が ok 872 / trap 22 になったが、OFF・空関数対照では 870 / 24 に戻る。ON 時の差の由来は未特定 (計測内容では説明できない。揺らぎの可能性がある (n=1 のため未確認))。計測は本体に入れず patch に退避。受入 1・2 は未達、受入 3 (回帰 0) は計測 OFF で確認。詳細・測定表・計測 patch の適用範囲 (FIX=0 では読取りがコンパイルされない) は [REPORT_APPENDIX_1602.md](REPORT_APPENDIX_1602.md) §13。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 計測 ON で 872/22 になる由来が未特定 (揺らぎか、ビルド差か)。n≥3 の反復が要る | 受入 1・2 が未達 | #1426 (継続) |
| 読取りを実際にコンパイルする計測での 304・555・923 の実値採取 | 受入 1・2 が未達 | #1426 (継続) |
