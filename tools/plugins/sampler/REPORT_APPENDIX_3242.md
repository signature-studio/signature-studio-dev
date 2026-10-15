# sampler REPORT 付録 (#3242 [PLG-F3-34]: 非 VEX comis/ucomis の flag を IR に反映)

> 正本の結論は `tools/plugins/sampler/REPORT.md` の未解決表 (VEX 行)。本書は #3242 の実測と方式。
> 既知類型との関係: `docs/DEFECTS.md` **D1a** に該当 (comis は flag (@cf/@zf/@pf) を更新せず、後続の jcc が無関係な flag を読む)。 修復式 (CF=lt∨uno・ZF=eq∨uno・PF=uno) は D1a の行案と同じ。

## 0. 要点・測定 commit

- 測定 commit: **`dfe82526`** (コードを変えた最後の commit。 `feat(plugins): reflect non-VEX comis/ucomis flags into IR`)。 検証起点: `a9733bbb` (origin/main)。
- 差分確認: `git diff dfe82526 HEAD -- tools/plugins/lift tools/plugins/sampler/engine_lift.sh` (本 commit は付録と DOC_MAP のみで、この範囲の出力は空)。
- 方式: RetDec の reg2mem 形の関数では flag が `%cf.0.reg2mem`・`%zf.0.reg2mem`・`%pf.0.reg2mem` (alloca i1) に store/load で載る。 comis の直後に fcmp で flag を計算して slot へ store し、呼出しを消す。 slot の無い関数は flag が SSA 値 (`%15 = xor i1 0, 0` など) のまま流れるため、今回は反映せず unimpl に残す (範囲外・子 [PLG-F3-36] #3305)。
- 実装: `tools/plugins/lift/passes/comis_flags.py` (新規)・`tools/plugins/lift/passes/test_comis_flags.py` (新規)・`tools/plugins/lift/passes/m11_simd2.py` (`PLUG_COMIS_FLAGS=1` のとき comis を unimpl 化)・`tools/plugins/lift/lift_ranges.sh` (`PLUG_COMIS_FLAGS=1` で pass を m11_simd2 の前に実行)・`tools/plugins/sampler/engine_lift.sh` (既定 1)。

## 1. 件数 (測定 commit `dfe82526`・`engine_lift.sh` 既定 = 反映あり)

| engine | 非 VEX 呼出し | 反映 (呼出し削除) | 未反映 (unimpl に残す) | 内訳 (未反映) | VEX (範囲外・#3241) |
|---|---|---|---|---|---|
| 19252 | 56 | **9** (comisd 3・ucomisd 系 3・ucomiss 3) | **47** | slot 無し 40 ・cf か zf の一方だけ slot 7 | 11 |
| 19048 | 80 | **6** (comiss 1・ucomisd 系 2・ucomiss 3) | **74** | slot 無し 64 ・部分 slot 10 | 9 |

- 数え方: `comis_flags.py` が入力 (lift 後の `e.final.ll`) の `call void @__asm_(u)?comis[sd](__N)?(...)` を数え、関数ごとの slot の有無で反映・未反映を分けた (`e.cflag.json` の `hist`)。 `__N` 付きは base で合算 (`ucomisd 系` = `ucomisd` + `ucomisd__35`/`__38`)。 非 VEX = 反映 + 未反映。
- 反映後に残る呼出し (symbol 別, 測定 commit): 19252 = comisd 16・comiss 25・comiss__17 5・ucomiss 1 (計 47)。 19048 = comisd 18・comiss 6・comiss__25 36・ucomisd__38 1・ucomiss 13 (計 74)。 VEX は 19252 が vcomisd 6・vucomisd 2・vucomiss 3、19048 が vcomisd 3・vcomisd__22 1・vucomisd 2・vucomiss 3 (本 issue の範囲外のまま unimpl)。
- 反映で宣言が消えた symbol: 19252 = `ucomisd`・`ucomisd__35` (`declare` を削除)、19048 = `ucomisd`。

## 2. 実測 (`summary.csv` の列: block,pdata_funcs,lift_rc,defines,f80_funcs,**unimpl_helpers**,emcc_c_rc,fixcmp_patched,emcc_c_rc_after_fixcmp,lift_s,missing_define,missing_bytes,missing_ref,extra_inside,function_defines,**emcc_c_rc_after_f80**)

| 測定 | block | unimpl | emcc (argw) | emcc (fixcmp) | emcc (f80 後) | lift_s | wall |
|---|---|---|---|---|---|---|---|
| baseline `PLUG_COMIS_FLAGS=0` | 19252 | 4 | 1 | 1 | **0** | 16 | 18 s |
| 反映 (既定 1) | 19252 | 8 | 1 | 1 | **0** | 15 | 18 s |
| baseline `PLUG_COMIS_FLAGS=0` | 19048 | 4 | 0 | 0 | **0** | 62 | 66 s |
| 反映 (既定 1) | 19048 | 9 | 0 | 0 | **0** | 61 | 65 s |

- 生の行: `19252,522,0,551,1,4,1,0,1,16,2,165,0,29,549,0` → `19252,522,0,551,1,8,1,0,1,15,2,165,0,29,549,0`。 `19048,1658,0,1712,0,4,0,0,0,62,2,97,0,54,1710,0` → `19048,1658,0,1712,0,9,0,0,0,61,2,97,0,54,1710,0`。
- 19252 の `emcc (argw)` = 1 は baseline から変わらない (`do not know how to soften fp_extend`。f80 段で 0 になる既存の挙動)。 受入の `emcc -c` rc 0 は f80 後の列で判定した。
- 19048 の反映あり実行を 2 回行い (測定 commit で 2 回目)、summary は同一。 実行時間は 19252 が 18–19 s (baseline 2 回 / 反映 2 回)、19048 が 65–66 s。 負荷は `uptime` で load 0.11–1.43 (4 vCPU)。 n=2 の min–max。
- unimpl の増分は、反映されずに残った非 VEX の comis (19252 で 4 symbol・19048 で 5 symbol) が、従来の「実装済み扱いの空 stub」から unimpl に変わったため。 VEX の 4 件 (19252) は従来どおり。

## 3. 述語の検算 (反映の向きと式)

`python3 tools/plugins/lift/passes/test_comis_flags.py` (5 件 OK)。

- 方法: ホスト x86-64 (gcc 13.3) で `comiss`・`ucomiss`・`comisd`・`ucomisd` を実行して CF/ZF/PF を採取する。 入力は 4 命令 × 11 × 11 = **484 件** (±0・±1・±2・±inf・qNaN・sNaN・最小 denormal・0.5 の組)。 pass が出す fcmp (CF=`ult`・ZF=`ueq`・PF=`uno`) の真偽と突き合わせる (独立な算法: C の inline asm 対 LLVM の述語の意味)。
- 結果: 正しい述語で不一致 **0 / 484**。
- ネガティブコントロール (述語を 1 つ壊す。 FAIL することの確認):
  - CF を `olt` (順序付き) にする → 不一致 **160 / 484** (NaN で CF が一致しない)
  - ZF を `oeq` にする → 不一致 **160 / 484**
  - PF を `ult` にする → 不一致 **140 / 484**
- IR 変換の単体テスト (合成 IR): slot を持つ関数は呼出しが消えて fcmp と store が入る / slot の無い関数は呼出しと宣言が残る / VEX は範囲外で残る、を確認。
- 未検証 (範囲外): IR の第 1 引数が x86 の第 1 オペランド (dst) であるという規約は、`m11_simd2.py` の `add`・`sub` 等 (第 1 引数 = dst) と同じ前提。 wasm 実行での flag の一致は確認していない (sampler engine の実行 harness が無い)。

## 4. 検証範囲 / 範囲外

- 範囲: sampler engine 19252・19048 の lift → `emcc -c` の到達性 (受入条件どおり)、反映の式 (§3)、未反映の unimpl 化 (§2・§1)。
- 範囲外: VEX comis (`vcomisd`・`vucomisd`・`vucomiss`・`vcomisd__22`) → [PLG-F3-33] #3241。 slot の無い関数と部分 slot の関数 → [PLG-F3-36] #3305。 engine 以外の lift 経路 (`batch_lift.sh` や他 plugin family) は `PLUG_COMIS_FLAGS` 既定 0 のまま (従来どおり silent の stub。既定化は PM 判断)。 wasm 実行の挙動一致。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| slot の無い関数の非 VEX comis 40 + 64 件、部分 slot の関数 7 + 10 件の flag が未反映 (unimpl に出る) | flag は未反映。 silent は解消 | [PLG-F3-36] #3305 (`親: #3242`) |
| VEX の comis (19252 11 件・19048 9 件) が unimpl のまま | 従来どおり。 flag 未反映 | [PLG-F3-33] #3241 |
| `PLUG_COMIS_FLAGS` の既定 0 の経路 (`batch_lift.sh`・他 plugin family) は silent の stub のまま | 他 family の comis 欠落は未対応 | PM 判断 (#3242 の issue コメントで依頼) |
| 19252 の `emcc (argw)` rc 1 (`fp_extend` の f80 段) | 変化なし。 f80 段で rc 0 になる既存 | 既存 (本 REPORT §7b・変更なし) |

## 6. 再現

```sh
export FL_WIN64_DIR=<fl-win64 の展開先>             # tar --zstd -xf fl-win64.tar.zst
bash tools/plugins/sampler/engine_lift.sh 19252     # 反映あり (既定 PLUG_COMIS_FLAGS=1)
PLUG_COMIS_FLAGS=0 bash tools/plugins/sampler/engine_lift.sh 19252   # baseline
bash tools/plugins/sampler/engine_lift.sh 19048     # 同 19048
python3 tools/plugins/lift/passes/test_comis_flags.py   # 単体 5 件 + 述語の検算 (gcc が無ければ skip)
```

- 出力: `tools/plugins/work/sampler/engine<B>/` (gitignore)。 反映件数は `e.cflag.json` の `hist`、unimpl は `e.simd.log`。
