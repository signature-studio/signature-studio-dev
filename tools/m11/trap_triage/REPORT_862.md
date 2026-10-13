# halt0 unit 492 (`410630`) の再測定と前提の訂正 (#862)

**結論: 前提が現 main で成立しない。unit 492 は `410630` に到達せず、OOB (`4133f0`) で trap する。**
`410630` (GetCurrentThreadId 比較) は現 main の survey でどの unit のフレームにも現れない。
受入条件 1・2 (`410630` の呼出経路と `[obj+8]` の実測特定、原因分類) は対象が消えたため未達。受入条件 3・4 は下記の実測で判定する。

- 検証起点: `origin/main` = `986e7415` (本 PR は `tools/m11/` のコードを変更しない)
- 素材: `work-m11` (boot_final.ll・m11_image.bin)・`fl-win64` (block00031_PE.bin)・`toolchain-emsdk` (`/opt/emsdk`)
- IR 再生成: `bash tools/m11/m11_gen_ir2.sh` (`FL_WIN64_DIR`=素材展開先、`ldfix=applied`、rc 0、実測 40 s)。
  work-m11 同梱の `ir_conditions.json` は無いため、再生成が必要だった。
- build: `bash tools/m11/m11_build.sh` (rc 0、`wasm-ld signature mismatch: 0, undefined symbol: 0`)

## 1. 実測 (HEAD `986e7415` の m11_ov.c、3 回反復)

`node tools/m11/trap_triage/survey_units.mjs` (load average 0.55–0.66、直列 1 並列)

| 回 | 所要 | ok | oob | halt0 | miss | other | abort | noproc |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| 1 | 10.93 s | 869 | 16 | 8 | 47 | 1 | 0 | 1 |
| 2 | 11.61 s | 869 | 16 | 8 | 47 | 1 | 0 | 1 |
| 3 | 10.83 s | 869 | 16 | 8 | 47 | 1 | 0 | 1 |

3 回の unit 別 kind は全て一致 (差 0)。unit 492 は 3 回とも `oob`。

## 2. unit 492 の経路 (現 HEAD)

- survey: `kind=oob`、`msg=memory access out of bounds`
- frames: `4133f0 ← 4473f0 ← 446400 ← 446ad0 ← ad5700 ← m11_tr_ad5700 ← m11_icall ← m11_call_unit`
- 単体 trace (`SV_ONLY=492 SV_TRACE_AT=492`): `icall 0x6d5700` → `icall 0xf960` の後 `oob`。`410630` / `4109f0` への到達なし (trace 出力 5 行)
- `410630` の IR 呼出元は `function_4109f0` のみ (`work/boot_final.ll` の 1 箇所)。どの unit の frames にも `410630` は現れない

## 3. `410630` の機械語 (`disasm_fn.py 410630`)

```
410635: mov ebx, dword ptr [rcx + 8]   ; [obj+8] を読む
410638: call 0x406f90                  ; GetCurrentThreadId 相当
41063d: cmp ebx, eax
41063f: je 0x410648
410641: mov cl, 0x19
410643: call 0x409730                  ; Error(0x19)
```

## 4. 4133f0 (現 OOB 最上位)

`4133f0` (size 135) は参照カウント解放の経路 (`lock xadd dword ptr [rax+8]`、`mov qword ptr [rbx], rsi` で置換後、
旧値に対して `call 0x409440`)。`[r13-8]` の符号判定で `0x412c20` / `0x409c80` を呼ぶ。
OOB の原因 (引数・ヒープの値) は未特定。`4473f0` は配列長計算 (`0x92492493` の乗算) を含む。

## 5. 受入条件の判定

| # | 条件 | 判定 |
|---|---|---|
| 1 | `410630` の呼出経路と `[obj+8]` の値を実測で特定 | **未達 (対象消失)**。現 main で `410630` に到達する unit は 0 |
| 2 | IR 脱落か shim 戻り値不一致かを分類し DEFECTS 類型に対応づけ | **未達 (対象消失)** |
| 3 | 修復の結果 unit 492 の ok/oob を実測しネガコン | 修復なし。現状 **oob** を 3 回で実測。ネガコンは未実施 |
| 4 | ok→非 ok の回帰が無いこと (per-unit JSON) | コード変更なし。3 回反復で unit 別 kind 差 0 |

## 6. 未実施 (限界)

- ネガコン用の旧 `m11_ov.c` (`64e617f`) での build は wasm-ld のリンクで失敗した (rc 1)。原因は未調査。
  `m11_ov.c` は HEAD に復元済み (`cmp` で一致確認)。このため「旧版では 410630 に止まる」の再現は取れていない。
- 旧 REPORT §6-3 の数値 (ok 841 / halt0 8 / oob 45) とは基準が違う。現 HEAD は ok 869 / halt0 8 / oob 16。
  差の原因は未切り分け (`REPORT.md` §8.2 と同じく、IR の生成条件差の可能性がある)。

## 7. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 492 の OOB (`4133f0`) の原因特定 | halt0 ではなくなったが ok ではない | 子 issue (本 run で起票) |
| `410630` の REPORT §6-1 記述が現 main と不一致 | 文書の正確性 | 本 PR の REPORT_862 §5 で訂正 |

## 8. 再現

```sh
bash tools/m11/m11_gen_ir2.sh        # FL_WIN64_DIR=<fl-win64 展開先>、capstone・pefile 必要
bash tools/m11/m11_build.sh          # PE=<...>/extracted/block00031_PE.bin
node tools/m11/trap_triage/survey_units.mjs tools/m11/work/trap_triage/head.json
python3 tools/m11/trap_triage/halt0_classify.py tools/m11/work/trap_triage/head.json
```

## 9. 追補: origin/main `1ef8ccfb` での再測定 (#862 再 run)

§1〜§5 の結論 (`410630` が現 main で到達 0、unit 492 は OOB) が main の進行後も成り立つかを確認した。

- 検証起点: `origin/main` = `1ef8ccfb` (`986e7415` から m11 関連 commit 多数を含む)。`tools/m11/` のコードは変更していない。
- IR 再生成: `bash tools/m11/m11_gen_ir2.sh` rc 0 (実測 43.8 s、ldfix applied)。
- build: `bash tools/m11/m11_build.sh` rc 0 (`wasm-ld signature mismatch: 0, undefined symbol: 0`)。
- survey (`survey_units.mjs`、3 回反復、load average 1.09→0.77 付近):

| 回 | 所要 | ok | oob | halt0 | miss | other | noproc |
|---|--:|--:|--:|--:|--:|--:|--:|
| 1 | 13.19 s | 869 | 16 | 8 | 47 | 1 | 1 |
| 2 | 12.96 s | 869 | 16 | 8 | 47 | 1 | 1 |
| 3 | 12.95 s | 869 | 16 | 8 | 47 | 1 | 1 |

- 3 回の unit 別 kind の差は 0 (per-unit JSON で照合)。`986e7415` の結果とは件数 (ok 869 / oob 16 / halt0 8) のみ一致し、unit 単位の一致は未確認。
- unit 492: 3 回とも `oob`、frames `4133f0 ← 4473f0 ← 446400 ← 446ad0 ← ad5700`。
- `410630` を含む frame は全 unit で 0 件。`410630` の IR 呼出元は `function_4109f0` のみ (`boot_final.ll`、検証 HEAD `8311dcb2` で再確認)。
- halt0 は unit 114 / 245 / 279 / 314 / 368 / 509 / 647 / 895 の 8 件。
- 前回 (§1〜§5 時点) の halt0 残 8 件には unit 492 が含まれていたが、本再測定では 492 が oob に変わっている。変化の要因は未切り分け (IR 生成条件の差の可能性。§6 と同じ扱い)。
- 検証 HEAD `8311dcb2` でレビュー run が再実行した (素材は `oc_artifacts:` で `fl-win64`・`toolchain-retdec`・`toolchain-emsdk`・`work-m11`・`work-liftdiff` を取得)。`m11_gen_ir2.sh` rc 0 (ldfix applied、`boot_final.ll` 490,693 行)、`m11_build.sh` rc 0 (`wasm-ld signature mismatch: 0, undefined symbol: 0`)、survey 3 回 (13.21〜13.37 s) は ok 869 / oob 16 / halt0 8 / miss 47 / other 1 / noproc 1 で、3 回の per-unit JSON は `cmp` で完全一致。unit 492 は 3 回とも oob、frames `4133f0 ← 4473f0 ← 446400 ← 446ad0 ← ad5700`。halt0 は上記 8 件と一致し、`410630` を含む frame は 0 件、IR 呼出元は `function_4109f0` のみ。

受入条件 1・2 は対象 (`410630` の到達) が現 main に存在しないため引き続き未達。原因追跡は #1046 (unit 492 の OOB `4133f0`) に引き継ぐ。
