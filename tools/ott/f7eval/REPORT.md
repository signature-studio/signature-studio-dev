# CAB-238 評価 REPORT — `ott --auto f7,p1` 既定化 + 新規 F7 サイト / 脱落分岐の再計上

最終更新: 2026-10-11 (CAB-238 再委任分 = 全数値を実測で再取得)。親 REPORT: `tools/ott/REPORT.md` §9。

**検収 (別セッション, 2026-10-11, commit 0800703 + f82f414 を検証):** 判定 = **受入 (PASS)**。
ただし §6 の無限ルーブ 2 combo は **本検証時点で未修** (params=0.9 / [0x248]=1) のため、
「CAB-138/CAB-238 検収通過 + 実運用 blocker として LIFTLIB-2 引継」が確定扱い。
詳細・独立再計算・ネガティブコントロールは `tools/ott/ACCEPTANCE_CAB238_CAB135.md` /
`tools/ott/f7eval/accept_recount.py`。

## 0. 結論 (先出し)

- **検収 4 項目すべて実測 PASS** (検証環境 = a137396 (CAB-239 適用後) + CAB-238 既定化, §1):
  ① 既定 (`python3 -m liftlib ott`, 引数無し = auto f7,p1) で **checks 7 / broken 0・band maxdev 0.0・nbad 0**、
  ② census[0x248]=0 junkHi **104 ≤ 104** (ゲート OK。旧既定 175 から **−71**)、③ **trap rc 0**、
  ④ **出力 SHA は m10 参照と分離** — 旧既定 `--auto none` は従来どおり **42/42 combo 一致** (f0 21/21) を継続ゲートとして維持し、
  auto 既定モードは修復 (F7 load 復元 7 site + P1 再構成 19) 由来の出力変化が正のため突合を分離:
  実測では **40 combo 中 34 が不一致** (一致 6 = param 0.0 の無音 combo のみ, §5)。
- **新規 F7 は 7 サイト** (チケット記載の 6 + 0x180120632)。F7 修復は `mov reg,[base+0]` 形の落ちた load を load 命令へ
  復元し operand 1 個書換 (0x1801c6b5b のみ 3 個) — site 明細は production の `auto_repair.log` から実測 (§3)。
- **census 寄与 (実測)**: junkHi 175→104 の改善は **P1 tail 6 site の再構成が全量** (`p1_tail` 単独で 104)。
  **F7 単独は census0 不変 (175)**。**F7@0x180120632 は例悪**: これ 1 個を外すだけで census0 104→**52** /
  census1 248→**0** (absmax 1.13e34→**2.2e-3**)。残る 6 site は個別の census 寄与 ≈0 (§3)。
- **bit 一致影響**: x64c bit-exact 参照 (native 実機械語と 50,236 cell 一致) との突合 (6 combo × 512 cell = 3072) は
  **P1 再構成の有無で 765/3072 ↔ 0/3072** に分かれる (F7 の有無は無関係)。
- **新規発見 (要対応, §6)**: auto f7,p1 の既定ビルドは **params=0.9 / [0x248]=1 / amp=0.0,1.0 の 2 combo で
  processReplacing が停止しない (無限ルーブ)**。原因は P1 再構成 site **0x18012024b と 0x1801204b9** (単体で再現,
  残留 30 とは別物)。旧既定・m10 参照・他の 17 site 単体はいずれも完走する (e2e gate が param 0.5 固定なので未検出)。
- 回帰: `liftlib_e2e.sh --full` **ALL PASS** (FA 400/400・KH 366/366・regress {fa,kh,ott,ott_auto_none} 4 PASS・
  inject 94/94・leafspec PASS)。`ott_e2e.sh` (tools/ott の x64c lifter, liftlib 非依存) も PASS。

## 1. 検証環境 (snapshot) と再現

| 項目 | 実測 |
|---|---|
| snapshot | `tools/liftlib/work/wt_cab238/tools/liftlib` (git 非管理のコピー)。`git archive a137396 tools/liftlib` との `diff -rq` で **passes 4 ファイル (f2.py/p1.py/pipeline.py/regbind.py) が完全一致**、差分は CAB-238 の 4 ファイル (cli.py / recipes/ott.py / liftlib_e2e.sh / README.md) のみ |
| メインツリー | tools/liftlib は **LIFTLIB-2 未コミット WIP** (p1.py +588/−69 ほか 4 ファイル) で OTT auto が emcc `Instruction does not dominate all uses!` / `instruction expected to be numbered` でビルド不能 (`work/cab238/cab238_default.log` 等) → 既定 gate は snapshot で実施。CAB-238 由来の破壊ではなく LIFTLIB-2 着地時に同一 gate が自動再検証される |
| 実行 | `cd <snapshot> && python3 -m liftlib ott` (既定) / `... ott --auto none` (旧既定) / `LIFTLIB_PKG=<snapshot> bash tools/ott/f7eval/run_eval.sh` (既定 34 tag) / `bash tools/ott/f7eval/outhash_gate.sh` (SHA gate) |

## 2. 検収実測

| ゲート | 実測 | 判定 |
|---|---|---|
| 既定 (auto f7,p1) = tag `production` | checks **7/0**, band maxdev 0.0, nbad 0, **trap rc 0**, census gate `junkHi 104 <= 104 -> OK`, RESULT **PASS** | PASS |
| └ census[0x248]=0 | zero 132 / normal 140 / **junkHi 104** / junkTiny 136 / nan 0 / absmax **1.67e18** (旧 175・1.67e20) | 104≤104 OK |
| └ census[0x248]=1 | zero 4 / normal 259 / junkHi 248 / junkTiny 1 / absmax 1.13e34 (旧 252・1.13e36) | (改善) |
| └ x64c bit-exact 参照 | 6 combo / 3072 cell 一致 **0** | (設計どおり, §5) |
| 旧既定 (--auto none) | checks 7/0, trap 0, census 132/69/**175**/136 (旧値どおり), IR 一致 O1〜O4 **全 true**, 出力 SHA **42/42 equal** (f0 21/21), RESULT **PASS** | PASS |
| `liftlib_e2e.sh --full` | unit PASS / FA Gain **400/400** / KH Gain **366/366** / regress `{"fa_gain":"PASS","kh_gain":"PASS","ott":"PASS","ott_auto_none":"PASS"}` (21.9 s) / inject 94 detected 94 FP 0 / leafspec PASS / **ALL PASS** | PASS |
| `ott_e2e.sh` (x64c, liftlib 非依存) | 89 scenario / 50,236 cell bit-exact, state 差 0 qword — PASS (x64c 依存のみで auto 既定の影響を受けない) | PASS |

## 3. 新規 F7 サイト別評価 (production と 1 site 外しを比較)

production の `auto_repair.log`: `F7 skip` **179** + **`F7 repaired` 7** = dropped_load **186**、unbound 58 / no_user 98 / no_pdata 8 は skip。
census は e2e 標準 (256 sample, param 0.5) の junkHi。`f7_ex_<va>` = その site だけ外した構成 (checks は全構成 7/0・trap 0)。

| site | 機械語 | IR 修復内容 (operand) | census0 junkHi (production 104) | census1 junkHi (248) | bit-eq/3072 |
|---|---|---|---|---|---|
| 0x18011ef10 | `mov rax,[rdi+0]` | load `%f7_18011ef10_v` 挿入, 1 個書換 (%rdx.0.ph.reload) | **104** | 248 | 0 |
| 0x18011f00e | `mov rax,[rdi+0]` | 同 (%rdx.3.reload) | **104** | 248 | 0 |
| 0x18011f9aa | `mov rax,[rdi+0]` | 同 (%rdx.4.reload) | **104** | 248 | 0 |
| **0x180120632** | `mov rax,[r12+0]` | 同 (%r8.3.reload) | **52** | **0** (absmax 2.2e-3) | 0 |
| 0x180120e6a | `mov rax,[rdi+0]` | 同 (%arg1) | **104** | 248 | 0 |
| 0x1801adda1 | `mov r15,[rbx+0]` | 同 (%arg2) | **104** | 248 | 0 |
| 0x1801c6b5b | `mov rbx,[rcx+0]` | 同, **3** 個書換 (%arg1) | **104** | 248 | 0 |

構成比較 (全 tag 実測, `work/cab238/summary.md`):

| 構成 | recon | census0 junkHi | census1 junkHi | bit-eq/3072 | p0.9_f1 無限ルーブ |
|---|---|---|---|---|---|
| production (F7 7 + P1 19) | 19 | **104** | 248 | **0** | **HANG** |
| f7_only (F7 のみ) | 0 | 175 | 252 | 765 | 完走 |
| p1_only (P1 のみ, F7 無し) | 19 | 104 | 248 | 0 | HANG |
| p1_tail (F7 + tail 6) | 6 | 104 | 248 | 0 | HANG |
| p1_env / p1_resume / p1_cvt / p1_tanpoly (F7 + 各 group) | 8/1/2/1 | 175 | 252 | 765 | 完走 |
| --auto none (m10 chain 再現) | 0 | 175 | 252 | — | 完走 |

読み取り: ① junkHi 175→104 は **P1 tail 6 site** の再構成が全量 (env/resume/cvt/tanpoly だけでは 175 のまま)。
② **F7@0x180120632 は例悪** — 修復した load (`[r12+0]`) が per-sample 経路で junk を増幅しており、外すだけで census1 が junk 0
(absmax 2.2e-3 = junk 実質消滅)。残 6 site は単独除外で census 不変 (出力は変化するが junk 分類の閾を跨がない)。
③ bit-eq 765→0 の境界は「P1 再構成の有無」で決まる (F7 の有無は無関係)。修復による出力変化が m10 参照 SHA・
x64c 参照 bit の両方と不一致になるのは設計どおり (§5)。

## 4. 脱落分岐 (P1) の再計上

production 実測 (auto_stats): sites **89** = state_branch 33 (rewired **30** + unresolved_orient 3) +
state_dropped 49 (**reconstructed 19** + unsupported **30**) + consumer **7** (派生値。定義 =
`sites − state_branch − state_dropped` = 89 − 33 − 49 で、auto_stats に consumer 単体のキーは無い。
旧記述の「consumer 4」は 33 + 49 + 4 = 86 ≠ 89 で収支が合わず誤り。4 は別キー `unsupported_consumer`
の値で consumer ではない)。チケット時点の「再構成 5 / 残 47」は CAB-239
(a137396) の語彙拡張で 19 / 30 に更新済みで、本評価で同じ数値を再現 (vocab: call 4 / call_arg_marker 4 / comis_frag 3 / int_jcc 2 / rot 2)。

**再構成 19 site** (関数帰属は `P1_FNMAP=1` の実測 mapping = `work/cab238/p1_site_functions.json`):

| group | site (survivor / region blocks) | 数 |
|---|---|---|
| env | 18011ed6f(T/2) 18011eda5(T/2) 18011eddc(T/2) 18011ee12(T/2) 18011ee49(T/2) 18011eeb9(T/2) 18011ef39(T/2) 18011ef6f(T/2) | 8 |
| **tail** | 18011ffdd(F/1) 180120049(T/6) 18012024b(F/1) 1801202b7(T/6) 1801204b9(F/1) 180120525(T/6) | 6 |
| resume | 1801209bb(F/2) | 1 |
| tan | 1801aa108(F/1) | 1 |
| exp | 1801b4277(T/2) | 1 |
| cvt | 1801bca83(T/4) 1801bd1d7(T/4) | 2 |

**残留 30 の理由分類** (site 数): region join **8** / bind xmm0 **6** / bind rcx **5** / reg2mem 値消失 **5** /
bind xmm1 **2** / bind xmm5 **2** / 間接 call **1** / region live-out **1** (計 30)。

関数帰属 (実測, 残留 30 / 再構成 19):

| 関数 | 残留 | 再構成 |
|---|---|---|
| processReplacing (0x18011ec20) | **14** | **14** |
| cvt (0x1801bc890) | 6 | 2 |
| 0x1801aa1a0 | 2 | 0 |
| 0x1801b4610 (reconstructed exp site を含む) | 2 | 1 |
| 0x1801b4e30 | 2 | 0 |
| tan (0x1801a9be0) | 2 | 1 |
| log (0x1801b4900) | 1 | 0 |
| resume (0x180120800) | 1 | 1 |

- **訂正 (前回 REPORT §4 の誤り)**: 「processReplacing 内の残留 = region join cluster + bind xmm1 2 + reg2mem 2 +
  間接 call 1 = 14 site」は実測と合わない。実測は processReplacing 内 = **region join 7 / reg2mem 4 / bind xmm1 2 /
  bind xmm0 1 = 14** (region join: 18011ff2f, 18011ffa2, 18012019a, 180120210, 180120408, 18012047e, 180120562)。
  間接 call **18012085b (`call qword ptr [rax+0xe0]`) は resume (0x180120800)** 内。census1 junkHi 248 の根の候補は
  processReplacing の上記 14 site (per-sample 帯)。

## 5. 出力 SHA の分離 (検収④)

- **旧既定 (`--auto none`)**: liftlib 生成 vs 元 m10 成果物 = **42 combo 全一致** (equal=true, f0 21/21)。
  各段 IR も O1〜O4 全て m6〜m10 中間成果物とテキスト一致 — m10 と bit 同一であることを継続ゲートとして維持。
- **auto 既定 (f7,p1)**: m10 参照との SHA 突合を **40 combo** で実施 (cmd: `f7eval/outhash_gate.sh`) →
  **一致 6 / 不一致 34** (f0 は 21 中 3 一致)。一致した 6 は **p0_f0_a0, p0_f0_a0.3, p0_f0_a1, p0_f1_a0, p0_f1_a0.3,
  p0_f1_a1** = param 0.0 (無音) の combo のみ。param 0.1〜1.0 の combo は **34 個全て不一致**。
  **除外 2 combo** (p0.9_f1_a0, p0.9_f1_a1) は §6 の無限ルーブ。**差分理由 = §3・§4 の修復そのもの**
  (census junkHi −71・absmax 1.67e20→1.67e18 と同じ根) で、**正当な変化**のため auto モードでは m10 SHA 突合を
  合格条件に含めない (`outhash=not auto`)。

## 6. 無限ルーブ (新規発見 / 未解決・下流要对処)

- 事象: 既定ビルド (`work/ott_auto_f7_p1/ott_gen.cjs`) で params=0.9・[0x248]=1・amp=0.0 および amp=1.0 の
  **2 回目の processReplacing 呼び出し**が終わらない (60 s timeout で HANG、CPU 100% で継続。1 回目は 3〜4 ms で完走)。
- 既存 gate では未検出: `e2e_check.mjs` / census は param 0.5 固定、trap10 は別シナリオ (すべて完走)。
- 原因 (実測 bisect, `p1_one_*` 19 tag): **P1 再構築 site 0x1801204b9 または 0x18012024b** の単体再現。
  両者は log 上 `survivor=F, region blocks=1` の再構成 (3 site 中の 2)。同条件の 0x18011ffdd (survivor=F/1) は完走。
  残る 17 site 単体はいずれも完走。
- 影響: param 0.9 + per-sample 経路 ([0x248]=1) を FL が踏むとオーディオスレッドが停止する。
  census/checks/trap の gate は通るため、既定化の検収条件 (①②③④) は満たすが **実運用上の blocker**。
  対応は下流チケット案 §8-1 (site 修正 or 白リスト)。

## 7. 再現手順

```sh
SNAP=/home/ubuntu/work/webstudio/tools/liftlib/work/wt_cab238/tools/liftlib   # a137396 + CAB-238 の snapshot
# site 別評価 (1 tag = 1 process で並列, 既定 34 tag / 実測 約 1 分) → tools/ott/work/cab238/<tag>/result.json
LIFTLIB_PKG=$SNAP P1_HANG_PROBE=1 P1_FNMAP=1 bash tools/ott/f7eval/run_eval.sh
LIFTLIB_PKG=$SNAP P1_HANG_PROBE=1 python3 tools/ott/f7eval/cab238_eval.py <tag> [--reuse]   # 単体
# 検収 gate (既定 + 旧既定)
(cd $SNAP && python3 -m liftlib ott)            # checks 7/0, junkHi 104, trap 0 -> PASS
(cd $SNAP && python3 -m liftlib ott --auto none)  # IR 一致 + SHA 42/42
bash tools/ott/f7eval/outhash_gate.sh            # 既定ビルド vs m10 参照 SHA (40 combo, 無限ルーブ 2 combo 除外)
# bit 一致 (対象 build vs x64c 参照): MOD_A=<build>.cjs MOD_B=tools/ott/work/lift/ottl.cjs
#   node tools/ott/f7eval/cab238_bitcmp.mjs
# 無限ルーブ probe: OTT_CJS=<build>.cjs V=0.9 F=1 A=0 timeout 30 node tools/ott/f7eval/cab238_probe.mjs
bash tools/ott/ott_e2e.sh                       # x64c 参照 (89 scenario / 50,236 cell bit-exact)
```

## 8. 次タスク提案 (下流チケット案)

1. **[高] P1 tail 2 site (0x18012024b / 0x1801204b9) の再構成修正** (LIFTLIB 側): params=0.9 + [0x248]=1 で
   processReplacing が停止する無限ルーブを解消。site 修正か白リスト (`.survivor=F, region blocks=1` 形の再構成は
   別条件で検証)。本 REPORT §6 の bisect と `f7eval/cab238_probe.mjs` が再現器。
2. **[中] F7@0x180120632 の再検討**: 自動修復から除外するだけで census1 junkHi 248→0・census0 104→52
   (absmax 2.2e-3)。白リスト vs deref 先の意味解析。実測は §3。
3. **[中] region join / 多定義 bind の phi 合成** (LIFTLIB 側): 残留 30 の過半 (join 8 + bind 系 15) と
   processReplacing 内の 14 site が対象。census1 junkHi 248 の更なる低減。
4. **[小] 0x18012085b 間接 call `call [rax+0xe0]`** (resume 内, VST host callback 系) — tools/ott の x64c lifter の
   dispatch switch 方式が参照実装 (`tools/ott/REPORT.md` §2 D1)。
5. **[小] e2e gate の combo 拡張**: `e2e_check.mjs` の param を 0.5 固定から 0.0/0.1/0.9/1.0 に広げれば §6 の無限ルーブを
   自動検出できる (timeout 付き)。
