# 検収 REPORT — CAB-238 (`ott --auto f7,p1` 既定化) + CAB-135 (AVX/VEX lift / FMA bit-exact)

検証手順: `docs/WORKFLOW.md` §6 (旧 `preflight RULES_SHA` 証跡は廃止・`docs/DECISIONS.md` D6)
   手持ちの 46 規則で検収を実施。差分の規則 47 (検収 agent: 合格 → Done + 検収コメント / 条件付き → **In Review 維持**)
   は本検収の選択 (無限ルーブ未修のため In Review 維持・所見コメント) と整合するため再実行は不要と判断。

## 0. 結論 (先出し)

- **CAB-238 = PASS (受入)**。検収 4 項目すべて**独立再現**: ① checks **7/0** ② census junkHi **104 ≤ 104**
  ([0x248]=0) ③ **trap rc 0** ④ 出力 SHA は m10 参照と**分離** (auto 既定 40 combo 中 **34 不一致** / 一致 6 は
  param 0.0 のみ / 旧既定 `--auto none` は **42/42 一致**を維持)。
- **CAB-135 = PASS (受入)**。残 unsup **0 種 / 0 箇所**、強制切替 **103 scenario 全 bit 一致**、
  FMA **300,012 case**、fpctl **10/10**、VEXCOV hit ⊆ native 実行 **OK** (node OOM 解消)、
  pcfuzz2 実機 **150,000 case 0 不一致**、回帰 crt_e2e/ott_e2e/entry_e2e **全 PASS**。
- **未修 (本検証時点) = CAB-238 の無限ルーブ 2 combo** (params=0.9 / [0x248]=1 / amp=0.0,1.0)。
  原因は P1 再構成 site **0x18012024b / 0x1801204b9** で、**本検収でも単体再現を確認した** (未修正)。
  検収条件 ①②③④ は満たすため受入とするが、**実運用 blocker として LIFTLIB-2 に引継** (Linear に明記)。
- Clean HEAD 再現: HEAD = **b8e762d**、検証対象 = `tools/ott` の 3 commit (0800703 / f82f414 / d4f0c9d)。
  再現は `git archive HEAD -- tools/ott` の snapshot (`work/verify_b8e762d/`) で実施 (規則 45①)。

## 1. 数え方の定義 (規則 36)

| 数値 | 定義 (単位・分母・除外) | 集計コマンド |
|---|---|---|
| scenario / cell | entry runner schema の 1 scenario = VST 入口〜processReplacing の 1 シナリオ。cell = 出力 f32 の 1 要素。bit 一致 = native 実機械語と 32 bit 完全一致 | `bash ott_e2e.sh` / `crt_e2e.sh` / `entry_e2e.sh` の `cmp_entries` / `matrix.py` |
| checks / broken | liftlib `e2e_check.mjs` の 7 検査 (E1..E7) とその失敗数 | `python3 -m liftlib ott` |
| junkHi | **native 実機械語と bit が異なる cell** のうち絶対値 ≥ 4 のもの。harness = 256 sample / param 0.5 / [0x248] 別。正規出力で \|v\| が 472 まで上がるため絶対値だけでは判定しない (tools/ott/REPORT.md §6.1) | `e2e_check.mjs` census |
| unsup 種/箇所 | 種 = 未対応 mnemonic のユニーク数、箇所 = その出現命令数。override 対象 8 関数は lift しないため数えない | `x64c.py` 出力の `unsup {}` / `unsup_scan.py` |
| 強制切替 scenario | `AVX_FORCE=fma,isa` (両側 .data に `__use_fma3=1` / `__isa_available=3`) で native/wasm 突合した scenario 数 | `avx/avx_e2e.sh` Gate B |
| FMA case | `fma_fuzz.c` 生成した (a,b,c) 組。native `vfmadd213sd` (実機) vs wasm musl `fma()` の出力 bit 比較 | `avx/avx_e2e.sh` [5/6] |
| fpctl case | `fpctl_scen.py` の 0x1801bc890 直叩き (x, y) 組 | `avx/fpctl_scen.py` |
| VEX hit | wasm 側 probe build (`-DOTT_VEXCOV`) が記録した VEX 命令実行アドレス集合 | `avx_e2e.sh` [4/6] |
| pcfuzz case | `pcfuzz2.c` の (needle, haystack) 組 | `avx/pcfuzz2.c` |
| SHA combo | (param, [0x248], amp) の直積。既定 6 param × 2 × 3 amp = 36 + f1 の 6 = 42 (m10 参照) | `f7eval/outhash_gate.sh` |

## 2. 検証環境とクリーン HEAD 再現 (規則 45)

| 項目 | 実測 |
|---|---|
| HEAD | `b8e762d`。対象 3 commit = 0800703 (CAB-238) / d4f0c9d + f82f414 (CAB-135)。全 commit が **tools/ott のみ** (他 dir 0 行)・最大 blob **80,427 B ≤ 20 MiB** |
| snapshot | `git archive HEAD -- tools/ott \| tar -x -C tools/ott/work/verify_b8e762d` (688 KB)。4 e2e は snapshot 内で実行。`../m6 ../m8 ../m9 ../m10 ../shim` は読取専用 symlink (m6..m11 改変 0 行) |
| CAB-238 liftlib 側 | `tools/liftlib/work/wt_cab238` (= a137396 + CAB-238 既定化 4 file)。`git archive a137396` との `diff -rq` で **passes 4 ファイル完全一致**・差分は CAB-238 由来 4 ファイルのみ。**実装本体は未 commit (LIFTLIB-2 WIP)** ゆえ既定 gate は snapshot でのみ再現可能 |
| 負荷 | 16 コア共有。各所要に開始/終了 load average を併記 (規則 38) |

## 3. CAB-238 検収 (4 項目 + 独立検証)

### 3.1 検収 4 項目 (メイン確定・本検収の実測)

| 項目 | 実測 (この検証) | 実装報告 | 判定 |
|---|---|---|---|
| ① checks | 既定 (`python3 -m liftlib ott` = auto f7,p1) で **checks 7 / broken 0** / band maxdev 0.0 / nbad 0 | 7/0 | **PASS** |
| ② census junkHi | census[0x248]=0 junkHi **104 ≤ 104** (zero 132 / normal 140 / junkTiny 136 / absmax 1.67e18)。旧既定 `--auto none` は junkHi **175** / absmax 1.67e20 → **−71** | 104≤104 | **PASS** |
| ③ trap | `trap_rc` = **0** (e2e_trap10) | rc 0 | **PASS** |
| ④ SHA 分離 | auto 既定: **40 combo 中 6 一致 / 34 不一致** (一致 = p0_f0_a0, p0_f0_a0.3, p0_f1_a0, p0_f1_a0.3, p0_f1_a1 = param 0.0 のみ。f0 は 21 中 3 一致)。旧既定: **42/42 一致** (f0 21/21) かつ IR O1〜O4 **全 true** | 40 中 34 不一致 | **PASS** |

- 差分のうち **2 combo (p0.9_f1_a0 / p0.9_f1_a1) は無限ルーブで計測不能**のため `DROP` 指定で除外
  (outhash_gate.sh と同じ手順)。40 combo は 42 − 2 の意図的な除外。定義は §1。
- 不一致 34 の理由 = F7 load 復元 7 site + P1 再構成 19 site による**修復由来の正当な変化**。
  根拠: 同一ビルドで census junkHi が 175 → 104 に減り absmax が 1.67e20 → 1.67e18 に落ちている
  (§3.2 の F7/P1 単独タグで確認)。**m10 参照 SHA 突合は auto 既定モードの合格条件に含めない**。

### 3.2 F7 7 サイト・P1 tail 6・F7@0x180120632 の独立検証

`f7eval/cab238_eval.py <tag>` を本検収で再実行 (production + 14 variant の計 42 tag を実測)。
census は §1 の定義 (256 sample / param 0.5)。

| 構成 | recon | census0 junkHi | census1 junkHi | absmax | bit-eq vs x64c (/3072) | p0.9_f1 無限ルーブ |
|---|---|---|---|---|---|---|
| production (F7 7 + P1 19) | 19 | **104** | 248 | 1.13e34 | **0** | **HANG** |
| f7_only (F7 のみ, P1 無し) | 0 | **175** | 252 | 1.13e36 | **765** | 完走 |
| p1_tail (F7 + tail 6) | 6 | **104** | 248 | 1.13e34 | 0 | HANG |
| p1_only (P1 のみ) | 19 | 104 | 248 | 1.13e34 | 0 | HANG |
| p1_env / p1_resume / p1_cvt / p1_tanpoly | 8/1/2/1 | 175 | 252 | 1.13e36 | 765 | 完走 |
| --auto none (m10 chain 再現) | 0 | 175 | 252 | 1.13e36 | — | 完走 |
| **f7_ex_180120632** (F7 6 site) | 19 | **52** | **0** | **2.25e-3** | 0 | HANG |

**独立検証の結論 (実装報告と一致):**
- **junkHi 175→104 の改善は P1 tail 6 site の再構成が全量** (`p1_tail` 単独で 104、`p1_env` 等の 4 group は 175 のまま)。
- **F7 単独は census0 不変 (175)** — F7 修復だけでは junk 分類は改善しない。
- **F7@0x180120632 は例悪**: この 1 site を外すだけで census0 104→**52** / census1 248→**0**
  (absmax 1.13e34→**2.25e-3**)。残る 6 site は単独除外で census 不変 (104/248)。
- bit 一致の境界は **P1 再構成の有無** (765 ↔ 0)。F7 の有無は無関係。

### 3.3 脱落分岐 (P1) 再計上の独立検算

`f7eval/accept_recount.py` (本検収で新規作成, 別アルゴリズム = テキストパース) の実測:

| 検査 | 実測 | 判定 |
|---|---|---|
| sites 収支 | sites 89 = state_branch 33 (rewired 30 + unresolved_orient 3) + state_dropped 49 (reconstructed 19 + unsupported 30) + consumer **7** | 収支一致 OK |
| dropped_load | `F7 repaired` 7 + `F7 skip` 179 = **186** = auto_stats.dropped_load | OK |
| F7 repaired site 集合 | {18011ef10, 18011f00e, 18011f9aa, 180120632, 180120e6a, 1801adda1, 1801c6b5b} = 7 site | OK |
| reconstructed | auto_repair.log の `reconstructed jcc@` 行 = **19** = auto_stats | OK |
| unsupported | 同 `UNSUPPORTED dropped@` 行 = **30** = auto_stats | OK |

**誤記を 1 件修正** (`fix(ott): acceptance report corrections`): `f7eval/REPORT.md` §4 の
「+ consumer **4**」は 33 + 49 + 4 = 86 ≠ 89 で収支が合わない。正は **7** (派生定義 =
`sites − state_branch − state_dropped`)。`4` は別キー `unsupported_consumer` の値で consumer ではない。

## 4. CAB-135 検収

### 4.1 受入条件と実測

| 受入条件 | 実測 (Clean HEAD snapshot) | 判定 |
|---|---|---|
| unsup 0 種 / 0 箇所 (crt 260 関数 / 16,378 命令) | crt build: **functions 260, insns 16378, unsup {}** (unlifted callees 13)。snapshot 再生成 coverage では **258 / 16,374 / unsup {}** も確認 | **PASS** |
| unsup 0 種 / 0 箇所 (closure 368 関数 / 23,360 命令) | override 無し closure 3 = **functions 368, insns 23360, unsup {}** (数値を完全再現) | **PASS** |
| 強制切替 103 scenario 全 bit 一致 | Gate B (`AVX_FORCE=fma,isa`): avx **9/9** + crt **9/9** + entry **85/85** = **103/103 PASS** | **PASS** |
| FMA 300,012 case | `fma_fuzz` native `vfmadd213sd` (実機) vs wasm musl `fma()`: **300,012 case bit 一致** (0 差分) | **PASS** |
| fpctl 10/10 | flags=0: **10/10 PASS** / FMA 強制: **10/10 PASS** (mxcsr dance / rcr site 両側 hit) | **PASS** |
| VEXCOV (buffer 0x35c00000, node OOM 解消) | native 実行 insn **5,436** / wasm VEX hit **182 種** / **hit ⊆ native 実行 OK**。mavx_cov も **9/9 PASS** (旧 run2.log の `memory access out of bounds` 4 FAIL は **解消**) | **PASS** |
| pcfuzz2 pcmpistri 0x40 実機 150,000 case | `pcfuzz2 150000 12345`: **model == hw (150,000 cases)** = 0 不一致 (実測 0.077 s) | **PASS** |
| 回帰 (crt_e2e / ott_e2e 89/50,236 / entry) | `crt_e2e.sh` **PASS** (crt 9/9 + entry 85/85 + 陰性対照 both OK + ott_e2e PASS + entry_e2e PASS)。`ott_e2e.sh`: **89 scenario / 50,236 cell / max_ulp 0 / state 差 0 qword**。`entry_e2e.sh --quick`: **10/10 PASS** (dsp_verified 30 / entry_new_verified 14) | **PASS** |

- Gate A (flags=0): crt 9/9 + entry 85/85 = **94/94 PASS**。
- `__isa_available` は DLL 静的値 (SSE2) 固定維持で決定 (実装 REPORT §3 と同旨)。強制切替でも
  bit-exact が実測されるため将来の切替も安全。

### 4.2 Gate 4 VEXCOV (OOM 解消) の確認

初版 probe build は buffer 配置 0x35e00000 が ott_boot MSCR / alog と重複し node OOM
(`e2e_run.log`: 4 scenario FAIL + `hit⊆native実行: NG`)。f82f414 が buffer を **0x35c00000** へ
移動し JS 読取アドレスを修正。**本検収の再実行では 4 FAIL 0 / hit⊆native OK** で解消を確認。

`avx/e2e_run2.log` の扱い: f82f414 では**未変更** (`git diff d4f0c9d f82f414 -- e2e_run2.log` = 空)。
d4f0c9d 時点で `[4/6]` まで書いて中断された記録で、f82f414 の `e2e_run3.log` (全 gate PASS) と
`final_regression.log` (crt_e2e 全工程 PASS) が正。**削除せず履歴として残す** (内容は中断地点の
部分ログであることを本 REPORT に明記)。

## 5. ネガティブコントロール (規則 41)

| # | 対象 | 壊し方 | 結果 |
|---|---|---|---|
| N1 | CAB-238 census gate (`junkHi ≤ 104`) | `OTT_AUTO_JUNKHI_MAX` を 103 に落とす (実値 104 のまま) | `junkHi 104 <= 103 -> NG` / **RESULT FAIL** |
| N2 | AVX/VEX lift (`i_rcr`) | `x64c.py` の `i_rcr` を無効化 (Unsup 化) | `unsup {'rcr': 6}`。Gate A (crt 9) = **PASS 0 / FAIL 9** (wasm `RuntimeError: memory access out of bounds`) |
| N3 | CAB-238 SHA 分離 | auto 既定を m10 参照と突合 (分離しない) | 40 combo 中 **34 不一致** → 合格条件に含めると FAIL (分離が正当) |

`crt_e2e.sh` [5/6] の `OTT_CRTINIT=0` (native SIGSEGV / wasm ott_unlifted 同一 garbage VA) は
e2e 内蔵の陰性対照で両側 OK を確認。

## 6. 実測所要 (規則 38: 実測秒 + load average)

| コマンド | 実測 (real) | 開始 load | 終了 load |
|---|---|---|---|
| `ott_e2e.sh` | 13.099 s | 1.35 | 1.81 |
| `crtinit/crt_e2e.sh` | 1 m 38.083 s | 2.74 | 2.42 |
| `entry/entry_e2e.sh --quick` | 16.758 s | 2.52 | 3.11 |
| `avx/avx_e2e.sh` (全 gate) | 2 m 44.847 s | 2.42 | 3.09 |
| `cab238_eval.py production` | 2 m 8.578 s | 1.38 | 2.08 |
| tag 単体 (f7_only 等) | 40〜130 s / tag (並列 6 時) | — | — |
| `pcfuzz2 150000` | 0.077 s | — | — |

所要は**単発測定**。共有 16 コアで負荷 1.20 〜 13.48 に振れたため参考値 (規則 38 の n≥3 レンジは未取得)。

## 7. 検証範囲 / 範囲外 (規則 40)

**検証した範囲**: Clean HEAD snapshot (`git archive` 展開・他 dir 書込 0) での 4 e2e 再実行、
CAB-238 の 42 tag 再測定、独立再計算 (accept_recount.py = 別アルゴリズム)、ネガティブコントロール 3 件、
commit 範囲 (tools/ott のみ / 最大 blob 80,427 B / 他 dir 0 行)。

**範囲外 (未実施・未検証)**:
1. **`ott --auto f7,p1` 実装本体 (tools/liftlib) は未 commit (LIFTLIB-2 WIP)**。既定 gate は
   snapshot (`wt_cab238`) でのみ再現でき、HEAD の tools/liftlib を直接叩いたものではない。
2. 旧 RetDec chain の before census は ott_e2e [6/6] の INFO 節として別途再現 (snapshot に `../m6`
   symlink): census[0x248]=0 junkHi **175** / absmax 1.67e20、[0x248]=1 junkHi **252** / 1.13e36。
3. FMA 経路の**全入力域保証はしない** (fpctl の denormal は 1 case のみ)。
4. VEX.128「dest 上位 = src1 上位」は「src1 ≠ dest かつ後続で上位を読む」コードが現 coverage に無く
   厳密には実行実績の範囲。
5. **無限ルーブ 2 combo は未修** (本検収で単体再現・未修正)。LIFTLIB-2 引継。
6. CAB-137/138/239 の受入条件そのものは再検証対象外 (CAB-135 の回帰として実行)。
7. `liftlib_e2e.sh --full` (ALL PASS) は tools/liftlib 未 commit WIP を含むため未実行
   (実装報告の数値を参照)。

## 8. 未解決 / 限界と起票先 (規則 42)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| **既定ビルドが params=0.9 / [0x248]=1 / amp=0.0,1.0 の 2 combo で processReplacing が停止しない (無限ルーブ)**。原因 = P1 再構成 site **0x18012024b / 0x1801204b9** (`survivor=F, region blocks=1` 形)。本検収でも単体再現確認・未修正 | FL が param 0.9 + per-sample 経路を踏むとオーディオスレッド停止。検収 ①②③④ は満たすが実運用 blocker | **(a) 既存 LIFTLIB-2 にコメント済** (本検収コメントで引継を明記。CAB-238 検収は通過) |
| **F7@0x180120632 は例悪** (修復した load が per-sample 経路で junk を増幅。除外だけで census1 junkHi 248→0 / absmax 2.25e-3) | census1 junkHi 248 の更なる低減チャンス。既定には未反映 | **(a) CAB-238 に検収コメント済** (次タスクとして記載) |
| **`f7eval/REPORT.md` §4 の「consumer 4」が誤り** (33+49+4=86≠89。正は 7) | 報告の数値整合性のみ (ロジックに影響なし) | 本コミット (`fix(ott): acceptance report corrections`) で修正済 |
| 旧既定 `--auto none` は `ott_auto_none` 回帰も維持 (42/42 SHA) するが、既定切替えに伴う **m10 参照 SHA との分離は運用ゲートに必ず書く**必要がある | 将来の snapshot 差分調査で誤って FAIL と誤認しうる | (a) CAB-238 検収コメントに明記済 |
| (参考) coverage 差分: snapshot 再生成 coverage は **258 関数 / 16,374 命令** (main tree 260/16,378 と差 2 関数/4 命令) | unsup 0 という結論は同じ | 起票不要 (coverage 差。notes に記録) |

## 9. 再現

```sh
SNAP=tools/ott/work/verify_b8e762d/tools/ott
cd $SNAP && bash ott_e2e.sh && bash crtinit/crt_e2e.sh   # 13.1 s / 1m38s
cd $SNAP && ENTRY_SKIP_COV=1 ENTRY_SKIP_LIFT=1 bash entry/entry_e2e.sh --quick   # 10/10
cd $SNAP && bash avx/avx_e2e.sh               # Gate A/B + VEXCOV + fma_fuzz 300,012
python3 tools/ott/f7eval/accept_recount.py    # 独立再計算 (42 tag の自動整合検査)
LIFTLIB_PKG=tools/liftlib/work/wt_cab238/tools/liftlib P1_HANG_PROBE=1 P1_FNMAP=1 \
  python3 tools/ott/f7eval/cab238_eval.py production ; bash tools/ott/f7eval/outhash_gate.sh
OTT_CJS=work/cab238/p1_one_1801204b9/ott_gen.cjs V=0.9 F=1 A=0 timeout 30 \
  node tools/ott/f7eval/cab238_probe.mjs     # 無限ルーブ単体再現 (HANG)
```

## 10. 環境前提 (規則 43)

- 環境: `bash tools/ott/env.sh` (PATH: node 26.10 / emsdk、所在は `docs/REFERENCES.md` `[EMSDK]`)
  と TMPDIR を修復。`avx/avx_e2e.sh` は node を `/opt/emsdk/node/24.19.0_64bit/bin/node` に固定し
  相対パス `work/avx/...` を参照するため **cwd = tools/ott で実行**すること。
- 必要: python3 (capstone, pefile), gcc/clang, emsdk 6.0.12, node ≥ 22, setarch。
  DLL は `docs/REFERENCES.md` `[ANALYSIS-PLUGINS]` の `plugins/ott/binaries/OTT_vst2_win64.dll`。
- snapshot の `../m6 ../m8 ../m9 ../m10 ../shim` は symlink (読取専用・改変 0 行)。
