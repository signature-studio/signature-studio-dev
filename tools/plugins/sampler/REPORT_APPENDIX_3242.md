# sampler REPORT 付録 (#3242 [PLG-F3-34]: 非 VEX comis/ucomis の flag を IR に反映)

> 正本の結論は `tools/plugins/sampler/REPORT.md` の未解決表 (VEX 行)。本書は #3242 の実測と方式。
> 既知類型との関係: `docs/DEFECTS.md` **D1a** に該当 (comis は flag (@cf/@zf/@pf) を更新せず、後続の jcc が無関係な flag を読む)。 修復式 (CF=lt∨uno・ZF=eq∨uno・PF=uno) は D1a の行案と同じ。

## 0. 要点・測定 commit

- 測定 commit: **`c45bf383a`** (lift 経路を最後に変えた commit = origin/main `7f70eb1d5` の取り込み merge)。 §2 の実測は全てこの commit。 検証起点: `a9733bbb` (origin/main)。 初版の実装 commit は `dfe82526` (`feat(plugins): reflect non-VEX comis/ucomis flags into IR`)。
- 差分確認 (測定 commit 以後): `git diff c45bf383a HEAD -- tools/plugins/lift tools/plugins/sampler/*.sh tools/plugins/sampler/*.py` の出力は空 (0 行)。 本 PR の pass・m11・engine の経路 `git diff dfe82526 HEAD -- tools/plugins/lift/passes/comis_flags.py tools/plugins/lift/passes/m11_simd2.py tools/plugins/sampler/engine_lift.sh` も 0 行。
- 取り込み分 (`git diff --stat dfe82526 c45bf383a -- tools/plugins/lift tools/plugins/sampler/engine_lift.sh` = 7 files・+351 −1): main 側の `passes/ir5_patch.py` +102 (`forward_vmovsd_store`・#2017 ほか)・`passes/vex_comis_flags.py` (新規)・`passes/test_vex_comis_flags.py`・`passes/test_forward_vmovsd.py` (新規)・`lift_ranges.sh` の VEX 呼出し。 本 PR の commit 分は `passes/test_comis_flags.py` (assert 追加) と `passes/SOURCES.txt` (2 行のうち 1 行)。
- 旧版の未再測定 (merge 前の `dfe82526` の数値だけを載せていた) は、この commit の再測定で解消した (§2)。
- 既定 1 の適用範囲: `engine_lift.sh` (19252・19048) と、`sampler_engines.sh` (`lift_from_ll.sh` 経由。 23664・23677) の経路。 他の lift 経路 (`PLUG_COMIS_FLAGS` 既定 0) の出力は変わらない。 23664・23677 の実測は §7。
- 方式: RetDec の reg2mem 形の関数では flag が `%cf.0.reg2mem`・`%zf.0.reg2mem`・`%pf.0.reg2mem` (alloca i1) に store/load で載る。 comis の直後に fcmp で flag を計算して slot へ store し、呼出しを消す。 slot の無い関数は flag が SSA 値 (`%15 = xor i1 0, 0` など) のまま流れるため、今回は反映せず unimpl に残す (範囲外・子 [PLG-F3-36] #3305)。
- 実装: `tools/plugins/lift/passes/comis_flags.py` (新規)・`tools/plugins/lift/passes/test_comis_flags.py` (新規)・`tools/plugins/lift/passes/m11_simd2.py` (`PLUG_COMIS_FLAGS=1` のとき comis を unimpl 化)・`tools/plugins/lift/lift_ranges.sh` (`PLUG_COMIS_FLAGS=1` で pass を m11_simd2 の前に実行)・`tools/plugins/sampler/engine_lift.sh` (既定 1)。

## 1. 件数 (`engine_lift.sh` 既定 = 反映あり。 dfe82526 で測定、c45bf383a でも `e.cflag.json` の hist が一致)

| engine | 非 VEX 呼出し | 反映 (呼出し削除) | 未反映 (unimpl に残す) | 内訳 (未反映) | VEX (範囲外・#3241) |
|---|---|---|---|---|---|
| 19252 | 56 | **9** (comisd 3・ucomisd 系 3・ucomiss 3) | **47** | slot 無し 40 ・cf か zf の一方だけ slot 7 | 11 |
| 19048 | 80 | **6** (comiss 1・ucomisd 系 2・ucomiss 3) | **74** | slot 無し 64 ・部分 slot 10 | 9 |

- 数え方: `comis_flags.py` が入力 (lift 後の `e.final.ll`) の `call void @__asm_(u)?comis[sd](__N)?(...)` を数え、関数ごとの slot の有無で反映・未反映を分けた (`e.cflag.json` の `hist`)。 `__N` 付きは base で合算 (`ucomisd 系` = `ucomisd` + `ucomisd__35`/`__38`)。 非 VEX = 反映 + 未反映。
- 反映後に残る呼出し (symbol 別, dfe82526 の値。 c45bf383a の `e.final.ll` でも宣言行を除いて一致): 19252 = comisd 16・comiss 25・comiss__17 5・ucomiss 1 (計 47)。 19048 = comisd 18・comiss 6・comiss__25 36・ucomisd__38 1・ucomiss 13 (計 74)。 VEX は 19252 が vcomisd 6・vucomisd 2・vucomiss 3、19048 が vcomisd 3・vcomisd__22 1・vucomisd 2・vucomiss 3 (本 issue の範囲外のまま unimpl)。
- 反映で宣言が消えた symbol: 19252 = `ucomisd`・`ucomisd__35` (`declare` を削除)、19048 = `ucomisd`。

## 2. 実測 (`summary.csv` の列: block,pdata_funcs,lift_rc,defines,f80_funcs,**unimpl_helpers**,emcc_c_rc,fixcmp_patched,emcc_c_rc_after_fixcmp,lift_s,missing_define,missing_bytes,missing_ref,extra_inside,function_defines,**emcc_c_rc_after_f80**)

| 測定 | block | unimpl (dfe82526・旧) | **unimpl (c45bf383a)** | emcc (argw) | emcc (fixcmp) | emcc (f80 後) | lift_s |
|---|---|---|---|---|---|---|---|
| baseline `PLUG_COMIS_FLAGS=0` | 19252 | 4 | **3** | 1 | 1 | **0** | 17 |
| 反映 (既定 1) | 19252 | 8 | **7** | 1 | 1 | **0** | 16 |
| baseline `PLUG_COMIS_FLAGS=0` | 19048 | 4 | **4** | 0 | 0 | **0** | 64 |
| 反映 (既定 1) | 19048 | 9 | **9** | 0 | 0 | **0** | 64 |

- 測定: `bash tools/plugins/sampler/engine_lift.sh <B>` (反映) と `PLUG_COMIS_FLAGS=0 bash tools/plugins/sampler/engine_lift.sh <B>` (baseline) を各 1 回、commit `c45bf383a` で実行。 PE は `fl-win64` の `extracted/block19252_PE.bin`・`block19048_PE.bin` (2 本だけ展開)。 emcc と RetDec は runner に既存の toolchain をそのまま使った (`toolchain-*.tar.zst` は展開していない。 `lift_ranges.sh`・`engine_lift.sh` が直接参照する)。
- 生の行 (`summary.csv`・c45bf383a): `19252,522,0,551,1,3,1,0,1,17,2,165,0,29,549,0` (baseline) / `19252,522,0,551,1,7,1,0,1,16,2,165,0,29,549,0` (反映) / `19048,1658,0,1712,0,4,0,0,0,64,2,97,0,54,1710,0` (baseline) / `19048,1658,0,1712,0,9,0,0,0,64,2,97,0,54,1710,0` (反映)。
- 19252 の `emcc (argw)` = 1 は baseline から変わらない (`do not know how to soften fp_extend`。f80 段で 0 になる既存の挙動)。 受入の `emcc -c` rc 0 は f80 後の列で判定した。
- 19252 の baseline unimpl が 4 → 3 に変わった理由: `dfe82526` の 4 件は `__asm_vcomisd`・`__asm_vmovsd(i64,i128)`・`__asm_vucomisd`・`__asm_vucomiss`、`c45bf383a` は vmovsd を除く 3 件。 原因は main 側の `ir5_patch.py` `forward_vmovsd_store` (#2017・`db8de2922`・dfe82526 より後)。 `__asm_vmovsd` を含む行は 39 → 35 (`e.final.ll`)。 baseline は `PLUG_COMIS_FLAGS=0` なので comis の反映とは無関係。
- 反映 (19252 = 7) の内訳: 非 VEX 4 (`comisd`・`comiss`・`comiss__17`・`ucomiss`) + VEX 3 (`vcomisd`・`vucomisd`・`vucomiss`)。 反映で増えた unimpl は非 VEX の 4 symbol (反映されずに残った comis が、従来の「実装済み扱いの空 stub」から unimpl に変わったため)。
- 19048 の反映 (9) の内訳: 非 VEX 5 (`comisd`・`comiss`・`comiss__25`・`ucomisd__38`・`ucomiss`) + VEX 4 (`vcomisd`・`vcomisd__22`・`vucomisd`・`vucomiss`)。 baseline 4 は VEX 4 件で dfe82526 と同じ。 反映で増えた非 VEX は 5 symbol。
- lift_s は 16–17 s (19252)・64 s (19048)。 wall は 19252 反映の 1 回のみ計測 (18.9 s)。 uptime の load は実行中 0.7–1.0 (4 vCPU)。

## 3. 述語の検算 (反映の向きと式)

`python3 tools/plugins/lift/passes/test_comis_flags.py` (6 件 OK)。

- 方法: ホスト x86-64 (gcc 13.3) で `comiss`・`ucomiss`・`comisd`・`ucomisd` を実行して CF/ZF/PF を採取する。 入力は 4 命令 × 11 × 11 = **484 件** (±0・±1・±2・±inf・qNaN・sNaN・最小 denormal・0.5 の組)。 pass が出す fcmp (CF=`ult`・ZF=`ueq`・PF=`uno`) の真偽と突き合わせる (独立な算法: C の inline asm 対 LLVM の述語の意味)。
- 結果: 正しい述語で不一致 **0 / 484**。
- ネガティブコントロール (述語を 1 つ壊す。 FAIL することの確認):
  - CF を `olt` (順序付き) にする → 不一致 **160 / 484** (NaN で CF が一致しない)
  - ZF を `oeq` にする → 不一致 **160 / 484**
  - PF を `ult` にする → 不一致 **140 / 484**
- IR 変換の単体テスト (合成 IR): cf/zf/pf の slot を持つ関数は呼出しが消えて fcmp (ult/ueq/uno) と store が入る / cf/zf のみの関数は fcmp uno も pf の store も入らない / slot の無い関数は呼出しと宣言が残る / VEX は範囲外で残る、を確認。
- 述語の回帰検出: `fcmp uno` を `fcmp ueq` に壊したコピーで、IR 変換テストの `fcmp uno` の assert が FAIL することを確認 (1 件 FAIL)。
- 未検証 (範囲外): IR の第 1 引数が x86 の第 1 オペランド (dst) であるという規約は、`m11_simd2.py` の `add`・`sub` 等 (第 1 引数 = dst) と同じ前提。 wasm 実行での flag の一致は確認していない (sampler engine の実行 harness が無い)。

## 4. 検証範囲 / 範囲外

- 範囲: sampler engine 19252・19048 の lift → `emcc -c` の到達性 (受入条件どおり)、反映の式 (§3)、未反映の unimpl 化 (§2・§1)。 sampler engine 23664・23677 (`sampler_engines.sh`・既定 on) の到達性と反映件数 (§7)。
- 範囲外: VEX comis (`vcomisd`・`vucomisd`・`vucomiss`・`vcomisd__22`) → [PLG-F3-33] #3241。 slot の無い関数と部分 slot の関数 → [PLG-F3-36] #3305。 engine 以外の lift 経路 (`batch_lift.sh` や他 plugin family) は `PLUG_COMIS_FLAGS` 既定 0 のまま (従来どおり silent の stub。既定化は PM 判断)。 wasm 実行の挙動一致。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| slot の無い関数の非 VEX comis 40 + 64 件、部分 slot の関数 7 + 10 件の flag が未反映 (unimpl に出る) | flag は未反映。 silent は解消 | [PLG-F3-36] #3305 (`親: #3242`) |
| VEX の comis (19252 11 件・19048 9 件) が unimpl のまま | 従来どおり。 flag 未反映 | [PLG-F3-33] #3241 |
| `PLUG_COMIS_FLAGS` の既定 0 の経路 (`batch_lift.sh`・他 plugin family) は silent の stub のまま。 既定化は PM agent の判断待ち (既定案: 0 のまま。 他経路の挙動は変えない。 既定が可逆) | 他 family の comis 欠落は未対応 | PM agent の判断待ち |
| comis の OF/SF/AF は未反映 (pass は CF/ZF/PF のみ書く。 SDM では comis が 0 にする)。 対象 2 engine (19252・19048) では読みが無い: `e.final.ll` (4 測定) に `%of`・`%sf`・`%af` の参照と reg2mem slot は 0 件 (slot は cf・zf のみ。 pf の slot も 0 件) (c45bf383a で確認) | 対象 2 engine では影響なし。 他 family に広げるときは読みの有無を再確認 | 未起票 (他 family に広げるときに再確認) |
| 反映した comis の wasm 上の実行 (19252 の 9・19048 の 6・23664 の 87・23677 の 17 = 119 件。 うち sampler engine 経路の既定 on 分は 104 件) | flag の一致は述語の検算 (§3) まで。 wasm 上の実行は未検証 | PM 判断 (sampler の実行 harness が無い) |
| 19252 の `emcc (argw)` rc 1 (`fp_extend` の f80 段) | 変化なし。 f80 段で rc 0 になる既存 | 既存 (本 REPORT §7b・変更なし) |

## 6. 再現

```sh
export FL_WIN64_DIR=<fl-win64 の展開先>             # tar --zstd -xf fl-win64.tar.zst
bash tools/plugins/sampler/engine_lift.sh 19252     # 反映あり (既定 PLUG_COMIS_FLAGS=1)
PLUG_COMIS_FLAGS=0 bash tools/plugins/sampler/engine_lift.sh 19252   # baseline
bash tools/plugins/sampler/engine_lift.sh 19048     # 同 19048
bash tools/plugins/sampler/sampler_engines.sh       # 23664・23677 (既定 on。 baseline は PLUG_COMIS_FLAGS=0 を付ける・§7)
python3 tools/plugins/lift/passes/test_comis_flags.py   # 単体 6 件 (IR 変換 4 + 述語の検算 2。 gcc が無ければ検算は skip)
```

- 出力: `tools/plugins/work/sampler/engine<B>/` (gitignore)。 反映件数は `e.cflag.json` の `hist`、unimpl は `e.simd.log`。

## 7. sampler engine 23664・23677 (`sampler_engines.sh`・既定 on) の実測

`sampler_engines.sh` は `lift_from_ll.sh` 経由で `engine_lift.sh` を呼ぶため、既定の `PLUG_COMIS_FLAGS=1` が 23664・23677 にも効く。 既定 on は維持する (issue #3242 の「sampler engine の経路で既定 on」どおり。 judge 判定は反映・baseline とも不変)。

- 測定: `bash tools/plugins/sampler/sampler_engines.sh` (反映・既定) と `PLUG_COMIS_FLAGS=0 bash tools/plugins/sampler/sampler_engines.sh` (baseline) を各 1 回、逐次。 検証 HEAD `a92d70769` (コード差分 `git diff c45bf383a HEAD -- tools/plugins/lift tools/plugins/sampler/*.sh tools/plugins/sampler/*.py` は 0 行。 測定のコードは c45bf383a と同じ)。 PE は `fl-win64` から `block23664_PE.bin`・`block23677_PE.bin` の 2 本だけ展開。 emcc は `[EMSDK]`、RetDec は `[RETDEC]` (runner の既存 toolchain。 `toolchain-*.tar.zst` は展開していない)。 `TMPDIR=$RUNNER_TEMP`。 4 vCPU・load 0.6〜1.3。

| engine | 測定 | 反映 (呼出し削除) | unimpl (`simd2`) | emcc -c (f80 後) | defines / function_defines | missing_ref | lift_s |
|---|---|---|---|---|---|---|---|
| 23664 | 反映 (既定 1) | **87** | 92 | 0 | 5993 / 5990 | 0 | 192 |
| 23664 | baseline (`PLUG_COMIS_FLAGS=0`) | 0 | 85 | 0 | 5993 / 5990 | 0 | 188 |
| 23677 | 反映 (既定 1) | **17** | 51 | 0 | 2525 / 2524 | 0 | 93 |
| 23677 | baseline (`PLUG_COMIS_FLAGS=0`) | 0 | 44 | 0 | 2525 / 2524 | 0 | 89 |

- 判定: 反映・baseline とも `judge engines: PASS 2/2` (lift_rc 0 / define>0 / 最終 IR の `emcc -c` rc 0 / missing_ref 0)。 `sampler_engines.sh` の exit は両方 0。 wall は反映 210 s・baseline 207 s (2 本並列)。
- 23677 の `emcc (argw)` rc 1 (`fp_extend` の f80 段) は両方で同じ。 f80 段を通すと rc 0 (既存の挙動。 §2 の 19252 と同じ)。
- 反映件数の内訳 (`e.cflag.json` の `hist`、呼出し箇所数):
  - 23664: 反映 comiss 71・ucomiss 8・comisd 6・ucomisd 2 (計 **87**)。 未反映 (`kept`): no_flag_slot 351・partial_slot 95・vex_out_of_scope 34。
  - 23677: 反映 comiss 3・comisd 8・ucomisd 3・ucomiss 3 (計 **17**)。 未反映 (`kept`): no_flag_slot 240・partial_slot 39・vex_out_of_scope 20。
- unimpl の増分 (baseline → 反映。 `e.simd.log` の `unimplemented:` 行の差分): 両 engine とも **+7 symbol**。 いずれも非 VEX で、slot の無い関数・部分 slot の関数に残った comis。 baseline では実装済み扱い (空 stub) だったため、反映後は unimpl に出る (§2 の 19252 と同じ扱い)。
  - 23664: `__asm_comisd(i128,i128)`・`__asm_comiss(i128,i128)`・`__asm_comiss__47(i128,i32)`・`__asm_ucomisd(i128,i64)`・`__asm_ucomisd__127(i128,i128)`・`__asm_ucomiss(i128,i128)`・`__asm_ucomiss__24(i128,i32)`
  - 23677: `__asm_comisd(i128,i128)`・`__asm_comiss(i128,i128)`・`__asm_comiss__83(i128,i32)`・`__asm_ucomisd(i128,i128)`・`__asm_ucomisd__91(i128,i64)`・`__asm_ucomiss(i128,i32)`・`__asm_ucomiss__6(i128,i128)`
  - VEX の unimpl は両 run で同じ (差分 0)。
- 未検証: 反映した 104 件 (23664 の 87 + 23677 の 17) の wasm 上の flag の一致は、§3 の述語の検算までで、実行はしていない (19252・19048 の 15 件と同じ扱い。 §5 の未解決)。
- 関係: `REPORT.md` §6 の `sampler_engines.sh` 行 (4c3ae00・318 s) は反映の前の値。 define・emcc・missing_ref は本節の baseline と一致する。 反映後の値は本節を正とする。 §6 の「define 2,524」は 23677 の `function_defines` 列 (`defines` 列は 2525)。
