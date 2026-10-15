# ildsp GeneralPitchShifter vtable 転送先 0x161fc0 の closure lift (T-SH-61 #3299)

既知類型との関係: 該当なし (本 run は lift の前段まで。意味変換と wasm 化は未実施のため、DEFECTS の類型判定は子 issue で行う)。

## 結論 (1 行)

転送先 0x161fc0 を選定した。closure の抽出・RetDec の範囲指定・ir_normalize まで通る (13 関数)。wasm 化の前段 `gen_helpers.py` は 49 種の SSE/AVX 命令で止まる。wasm 化と native 差分テストは子 issue に分けた (§5)。

測定 commit: `372bbe95` (`lift.sh` と `closure_select.py` を含む最後のコード commit)。

## 1. 選定 (3 候補の実測)

| 転送先 | body 命令数 (.pdata 範囲) | closure 関数数 | closure 命令数 | closure の直接 call 辺 (相異なる宛先) |
|---|---|---|---|---|
| 0x161fc0 | 324 | 13 | 1,119 | 12 |
| 0x162760 | 395 | 51 | 2,649 | 67 |
| 0x162f90 | 730 | 4 | 810 | 3 |

- body 命令数は issue 本文の値 (324 / 395 / 730) と一致する。
- issue の指定どおり、body 基準で最小の **0x161fc0** を選んだ。
- 注意: closure 基準 (lift する量) では **0x162f90 (810 命令)** が最小になる。どちらを選ぶかは PM 判断 (§4 の未解決)。
- closure = 転送先から `direct_call_sites` の直接 call / 直接 jmp の辺で到達する関数の集合。入力は `ildsp_vtable.py` の `closure_with_slots` (slot 先の closure は `ildsp_closure.py` の export closure には無い)。

## 2. closure 0x161fc0 (13 関数)

関数の先頭 (VA): `0x161fc0`・`0x1ac9b8`・`0x1b2f3c`・`0x1b7ffc`・`0x1b8ee4`・`0x1be120`・`0x1c383c`・`0x1c9280`・`0x1ca564`・`0x1ca7f0`・`0x1cab40`・`0x1cad30`・`0x1cadd0`。

- 間接 call / 間接 jmp: **この closure の内側に 0 件**。issue の受入条件 5 (間接 call 4 件: `0x1aedc0` ×3・`0x1b6f4c` ×1) の `in_func` は、いずれもこの closure の外にある。よって、この closure から 4 件は到達しない (`ildsp_vtable.json` の `indirect_calls` の `in_func` と closure 集合の照合)。

## 3. 再現

```sh
FL_WIN64_DIR=<fl-win64 展開先> RETDEC_BIN=<retdec-decompiler> ILDSP_WORK=<作業先> \
  bash tools/shared/lift/ildsp/lift.sh 0x161fc0
```

実測 (測定 commit `372bbe95`):

- `closure functions=13 insn=1119 direct_call_edges=12`・`body_insn=324` (closure_select.py)。
- `[ildsp] retdec: 13 functions lifted` (RetDec `--select-ranges`・絶対 VA `0x180161fc0-0x18016275c` ほか 12 範囲)。
- `[ildsp] unsupported helper ops (declare @__asm_*): 49 distinct` (`__asm_` の declare は 68 行)。
- `gen_helpers.py`: `unsupported helper: declare i32 @__asm_cvttss2si(i128)` で rc=1 (意図した未達。以降の wasm 化には進まない)。
- 所要: lift.sh 全体 1.98 秒 (実測・1 回。load は未測定)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `gen_helpers.py` は op 名では movss・movaps・mulss・addss・subss・xorps・ucomiss だけを扱い、その中でもシグネチャは限られる。closure の 49 種は大半が未実装 | wasm 化 (emcc) に進めない | 子 issue (§5 の A) |
| 差分テスト・ネガティブコントロール・gate が未実装 | 同一性の検証が無い | 子 issue (§5 の B) |
| 選定基準の不一致 (body 基準なら 0x161fc0、closure 基準なら 0x162f90) | 0x162f90 を選ぶと lift 量は 810 命令で済む | PM 判断 (#3299 のコメント) |

未対応の 49 種 (`declare @__asm_*` の op 名): addsd addss comiss cvtdq2pd cvtdq2ps cvtps2pd cvtsd2ss cvttpd2dq cvttsd2si cvttss2si divsd divss movapd movaps movd movdqa movdqu movhlps movlhps movq movsd movss mulpd mulsd mulss psllq psrldq psrlq stmxcsr subsd subss vaddsd vandpd vcvttpd2dq vfmadd132sd vfmadd213sd vfmadd231sd vfmsub213sd vfnmadd132sd vfnmadd231sd vmovapd vmovdqu vmovq vmovsd vmulsd vpsrldq vsubsd vxorpd xorpd

(一覧には movss・movaps・mulss・addss・subss も含まれる。gen_helpers.py はこれらの一部のシグネチャだけ扱うため、未対応の判定は op 単位ではなくシグネチャ単位で行う。)

## 5. 受入条件の扱い (issue の範囲を縮めた)

| 受入条件 (#3299 元の本文) | この PR | 行き先 |
|---|---|---|
| 3 転送先から最小の closure を選ぶ (根拠を REPORT に) | 達成 (§1) | — |
| RetDec → ir_normalize → gen_helpers → emcc で wasm 化 | 前段 (RetDec・ir_normalize) まで達成。gen_helpers 以降は未達 | 子 A |
| native (ms_abi) と wasm の全バイト比較・外部 import の扱い | 未達 | 子 B |
| ネガティブコントロールと、不一致・TRAP・カバレッジ不足で非 0 の gate | 未達 | 子 B |
| 間接 call 4 件 (0x1aedc0 / 0x1b6f4c) の扱い | 達成 (§2: この closure には 0 件) | — |

## 6. 検証範囲 / 範囲外

- 範囲内: closure の抽出 (`closure_select.py`)・RetDec の範囲指定と lift (13 関数)・ir_normalize・gen_helpers の失敗位置の確認。
- 範囲外: lift の意味変換の正しさ・wasm の生成・native との比較。どれも実施していない。
