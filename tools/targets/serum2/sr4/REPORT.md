# SR-4 (#75) Serum 2 DSP 段階 lift 第 1 段 — 対象表 + pilot lift + 判定 gate

- 結論: **第 1 段 (WT osc → filter → voice) は未完**。vtable root 56 関数のうち実機機械語と bit 一致で lift できたのは **5 関数 (540 B / root 計 69,980 B = 0.77%)**。残りの不一致・未着手は原因別に分類済み (§4・§6)。issue 本文に受入条件が無いため `Closes` は付けず `Refs #75` とする (§7 に受入条件案)。
- 既知類型との関係: `docs/DEFECTS.md` **D1a** (ucomisd 後 jcc, osc_setscale) / **D3** (movlps store 脱落, §3.1 で修復) / **D4 の xmm 版** (movsd load の deref+disp 脱落, osc_get620 — 行案 §5) / **D5** (xmm1 引数, ladder_setp — §3.4 で修復) / **D9** (jump table, svf_process) に該当。`tools/icall/REPORT.md` §4 の D 番号は別体系。
- 検証起点 commit: `5415da7` (クリーン worktree で `sr4_run.sh --pilot` を 3 回再実行, §8)。入力 `Serum2_win64.vst3` sha256 `501e7bb3…5283` (SR-3 §11 と同一, 19,236,864 B)。
- 再現: `PY=<python+pefile,capstone,numpy> bash tools/targets/serum2/scripts/sr4_run.sh [--pilot]` (要 `toolchain-retdec` `toolchain-emsdk` `plugins-serum2`)。既定は strict (第 1 段が終わるまで **exit 1**)、`--pilot` は pilot ごとの期待との一致 (+ ネガコン) だけを判定。

## 1. 対象表 (survey) — `scripts/sr4_survey.py` → `out/sr4_summary.json` `out/sr4_funcs.tsv`

定義:
- **root** = (a) RTTI vtable (`WTOsc` `WTOscState` `XferFilterSVF` `XferFilterLadder` `Voice` 各 vtable) の `.text` を指す全スロット (`.pdata` 外の leaf = **gap 関数** を含む) + (b) Voice core 範囲 0x18007e700–0x1800861f3 に収まる `.pdata` 関数。重複 0。
- **closure** = root から**直接 call / 外向き jmp** だけを辿った推移閉包。vtable・fp 表・間接 call 経由の辺は張らない (= 下限。SR-3 §11 の動的トレース前提は変わらない)。
- 関数クラス (`out/sr4_funcs.tsv` の `class`、先に当たった順): `oss:<lib>` = SR-3 cut 表 / `iat` = IAT 呼び出しあり / `avx` = VEX 命令あり / `icall` = 間接 call あり / `closed` = 上のいずれも無い。**per-function の分類で、部分木が閉じている意味ではない** (部分木が閉じるかは `direct_callees` で別途見る)。
- gap 関数の末尾は『ret/jmp 直後が 0xCC/0x90』で推定 (pilot 9 本は RetDec 範囲と機械語目視で確認済み、それ以外は推定)。

| グループ | root 関数 (うち gap) | root バイト | closure 関数 (うち gap) | closure バイト | closure 内訳 (関数数) |
|---|---:|---:|---:|---:|---|
| wt_osc (WTOsc/WTOscState) | 21 (9) | 10,812 | 1,183 (176) | 520,838 | closed 989 / iat 91 / icall 60 / avx 30 / oss 13 |
| filter (SVF/Ladder) | 11 (5) | 27,282 | 109 (37) | 47,313 | closed 84 / avx 15 / iat 10 |
| voice (Voice vtable + core 範囲) | 24 (2) | 31,886 | 1,014 (191) | 411,135 | closed 830 / iat 92 / icall 62 / avx 24 / oss 6 |
| 3 グループ和集合 | 56 (16) | 69,980 | 1,451 (253) | 719,562 | closed 1,216 / icall 86 / iat 96 / avx 40 / oss 13 |

- Voice core 範囲 (0x18007e700–0x1800861f3) に収まる `.pdata` 関数 = **20 関数 / 31,113 B** (部分重複も 20 で同数)。
- **dsp_closure.py の vtable 抽出は `.pdata` 関数先頭でないスロットで打ち切る**ため `XferFilter*` が 1 method (dtor) しか見えていなかった (pdata 限定 method 数 SVF 1 / Ladder 1 に対し、.text を指すスロット実数は各 6)。実体の `setup`/`reset`/`process` は `.pdata` 外 leaf または別 pdata 関数。SR-3 §11.3 の cut 表・REPORT §4 の『filter root 34 methods』は同じ取りこぼしの影響を受ける可能性 (§6 未解決)。
- XferFilterSVF::process (0x1802f7510, 22,386 B, 4,765 命令, SSE スカラ FP 2,141) は**直接 callee 0・IAT 0・間接 call 0 の自己完結 leaf** (jump table 35 モードを除く)。= 第 1 段の『filter 1 種』の最有力候補。
- `avx` 40 関数 (closure 和集合) は CRT/libm 域と推定 (REPORT §4.1 の位置と整合。アドレスの突合は未実施)。

## 2. pilot lift — 実機機械語 (VA 敷設・ms_abi 直接実行) vs wasm の差分ハーネス

方式: RetDec (`--select-ranges`) → liftlib 修復 pass (base/F2/P1/F7/S1c) → SIMD helper 自動生成 → emcc → `liftlib/harness` の乱数 scenario で `this` 等**全バッファ + rax (+ xmm0 戻り指定時は xmm0)** を native と bit 比較。NaN 入力は除外。pilot 定義は `sr4/pilots.tsv`、target は `sr4/targets/`、入力分布は `sr4/specs/`。

| pilot | 関数 (VA, バイト) | 役割 | 期待 | 観測 | 一致/scenario | P1 UNSUPPORTED | FP ALU 被覆 |
|---|---|---|---|---|---:|---:|---:|
| sr4_svf_setup | 0x1802f7370 (380, gap) | SVF 係数設定 (exp 近似を inline, xmm1 f32 引数) | pass | **bit-exact** | 400/400 | 1 (警告) | 42/42 |
| sr4_svf_reset | 0x1802f74f0 (19, gap) | SVF 状態リセット | pass | **bit-exact** | 50/50 | 0 | 0/0 (対象命令なし) |
| sr4_ladder_reset | 0x1802f5c40 (19, gap) | Ladder 状態リセット | pass | **bit-exact** | 50/50 | 0 | 0/0 (対象命令なし) |
| sr4_osc_zero | 0x1803d08f0 (116, gap) | WTOsc 系 256B ゼロ化 (movups ×16) | pass | **bit-exact** | 50/50 | 0 | 0/0 (対象命令なし) |
| sr4_ladder_setp | 0x18008b2a0 (6, gap) | Ladder setter `movss [this+0xc], xmm1` (xmm1 f32 引数) | pass | **bit-exact** (§3.4 の修復後。修復前 0/200) | 200/200 | 0 | 0/0 (対象命令なし) |
| sr4_osc_setscale | 0x1803c87d0 (191, gap) | 周波数スケール設定 (ucomisd + jne/jp ×2) | fail | mismatch | 363/400 | 4 | 11/11 |
| sr4_svf_process | 0x1802f7510 (22,386) | SVF process (jump table 35 モード) | fail | mismatch | 32/200 | 0 | **21/2,531** |
| sr4_osc_get620 | 0x1803d0970 (9, gap) | `movsd xmm0, [this+0x620]` double getter | fail | mismatch | 0/100 | 0 | 0/0 (対象命令なし) |
| sr4_wt_const | 0x180087b10 (9, gap) | `movsd xmm0, [rip+const]` double 定数戻り | fail | mismatch | 0/20 | 0 | 0/0 (対象命令なし) |

- 計数: 一致/scenario は `steps` = scenario 数 (steps=1)。FP ALU 被覆 = 機械語の FP ALU 命令 (`cvt*`/`ucomis*`/`comis*` と mov 以外の `*ss/*sd/*ps/*pd`, 同一 reg の xorps は除外) のうち RetDec raw `.ll` の `!insn.addr` に現れる割合 (`scripts/sr4_cov.py`)。**bit 比較の入力が踏まない経路を被覆で補う**: svf_process は jump table の先を RetDec が辿れず raw IR が機械語の 0.83% にとどまる (その入力 32/200 は n=0 や範囲外 mode の自明経路)。
- **P1 UNSUPPORTED は警告扱い**: svf_setup の 1 件 (`seta` 消費, 0x1802f73fb) は偽陽性で、spec が p<43999 / p>43999 の両結果を踏むため 400/400 一致が証拠。osc_setscale の 4 件は実害あり (下記)。判定は差分の入力分布に依存する点が弱み (§6)。
- **osc_setscale の不一致 37/400 は全て『前回値と等しい (周波数・sample rate とも)』の早期 ret 経路**: native は更新せず ret、wasm は更新経路 (+0x200/+0x208/+0x210) を実行。P1 は `bind r8 @0x1803c8831` (r8d が 0/1 の 2 定義、eax が 0/-1 の 2 定義を合流) を扱えず IR 不変 (DEFECTS.md D1a の『ucomisd 後 jne+jp』イディオム)。(前回値 ≠ 新値) の 363 scenario は一致。

## 3. 本 PR で入れた liftlib の変更 (pilot を成立させるための最小)

### 3.1 S1c — `movlps/movlpd/movhps/movhpd` store 復元 (`liftlib/passes/base.py` `lower_asm_lane_store`)
RetDec は `movlps [m], xmm` を `call void @__asm_movlps(i64 <m の旧値 load>, i128 xmm)` にして書込みを落とす (DEFECTS.md D3 の i64 幅。S1a は i128 の movups/movaps/movdqa のみ)。旧値が直前の `load i64, ptr P` なら `store i64 (trunc/lshr xmm), ptr P` に復元。load 由来でない旧値は触らない。svf_setup で適用前は `wasm_trap=400/400` (helper 未対応の stub trap)、適用後 bit-exact。OTT/FA/KH の既存 IR に該当形が無ければ IR 不変 (合成 IR の単体試験 `tests/test_unit.py` T18、Serum2 PE 有りで `add_func` も試験)。
### 3.2 `Image.add_func` / cfg `extra_funcs` (`liftlib/pe.py` `pipeline.py`)
`.pdata` 外の leaf (unwind 情報なし) を合成エントリとして登録。無いと P1/F2 が `no_pdata` で機械語参照を諦め、xmm 引数 (`%xmm1_bits`) が足されない。`.pdata` 範囲と重なる登録は `ValueError`。
### 3.3 wasm ハーネスの xmm 引数対応 (`harness/wasm_runner.mjs`)
`%xmmK_bits` 仮引数は『登場順』ではなく **K 番目の float 引数**に対応 (native の `c.xmm[K]` と同じ)。xmm1 だけを読む関数で xmm1_bits が先頭の float 引数 (native では xmm0) を拾っていた。xmm0 から連続する既存 sig では結果不変 (推論。OTT/FA/KH の回帰は未実行 — §6)。

### 3.4 F2 の D5 型救済 (`liftlib/passes/f2.py` `find_sext_arg_for`)
RetDec は `movss [rcx+0xc], xmm1` で xmm1 を undef でなく `sext i64 %arg1 to i128` (= this ポインタ) に束ね、F2 は『xmm1 の undef 値が見つからない (引数のみ追加)』で結線できなかった (DEFECTS.md D5)。undef が見つからないときに限り、使用が全て xmm reader の機械語アドレス上にある `sext i64 %argN` を xmm 値の定義とみなして `zext %xmmK_bits` に差替える。ladder_setp: 修復前 0/200 → 修復後 **200/200 bit-exact**。undef が見つかる既存形は経路が変わらない (単体 T19 に reader 上/外の両ケース)。

## 4. 不一致・未達の原因分類

| pilot | 原因 (観測) | DEFECTS.md | 備考 |
|---|---|---|---|
| svf_process | RetDec が `jmp r9` (jump table, 35 モード) を辿れず raw IR が 206 `insn.addr` / 機械語 4,765 命令。`tools/liftlib` の `passes.icall` (jtchain) を試行: restored IR は 255 `insn.addr` に増えただけで switch 未展開、emcc も `icall_tbl_*` `icall_cfg_*` 未供給で link 失敗 (`sr4/targets` は icall 無しで固定) | D9 | #494 / PR #539 (icall 結線) の対象 |
| osc_get620 | `movsd xmm0, [rcx+0x620]` が `__asm_movsd__xq(i64 %arg1)` (**deref と disp が脱落**, this そのものを渡す) + `ret i128` (xmm0 戻りの形)。F7 は GPR 版のみ | D4 の xmm 版 + #250 L1 (FP 戻り値) | leafabi の `ret_xmm0` を指定しても `ret_threaded=0` |
| wt_const | RetDec は定数をそのまま渡す (`i64 4607182418800017408` = 1.0) が `ret i128`。leafabi (`ret_xmm0` 指定) が戻りを差し替えず xmm0 比較で不一致 | #250 L1 | 値自体は正しいと推定 (比較は xmm0 のみ不一致) |
| osc_setscale | §2 の通り P1 UNSUPPORTED (r8/eax 合流) | D1a | #250 の P1 拡張 (LIFTLIB-2 の phi 合成の延長) |

## 5. DEFECTS.md 行案 (PM 判断で反映。直接編集はしない)

| ID | 層 | 新旧 | 症状 (silent) | 根本原因 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|---|---|---|
| D17(案) | fe | D4 の xmm 版 (新規形) | `movsd xmm0, [rcx+disp]` の load が消え、アドレス (this) がそのまま xmm 値になる | `__asm_movsd__xq(i64 %argN)` に **load も disp 加算も無い**。F7 は GPR `mov r64,[b+d]` のみ対象 | Serum 2 WTOsc 系 getter (0x1803d0970): 100 scenario 全不一致 | `call i128 @__asm_movsd__xq(i64 %argN)` で引数が live-in そのもの / 機械語に mem operand | F7 を xmm load (`movss/movsd/movaps` mem 形) へ拡張し `load` + `add disp` を挿入 |
| D18(案) → §3.4 で修復済 | fe/opt | D5 の特殊形 | xmm1 のみ読む一命令 setter で、xmm 値が `sext i64 %arg1` (this ポインタ) になる | RetDec が引数スロット 1 を『rdx/xmm1』ではなく %arg1 に束ねる。F2 は undef を探すため結線不能 | Ladder setter (0x18008b2a0): 修復前 200 scenario 全不一致 → 修復後 200/200 | F2 ログ『xmm1 の undef 値が見つからない』 | F2: undef が無い場合は reader 上の `sext i64 %argN` を `%xmmK_bits` の zext で置換 (実装済) |

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| XferFilterSVF::process を jump table ごと lift (35 モード, 22,386 B) | 第 1 段の『filter 1 種』が未達 | **新規子チケット [SR-4a] 起票依頼** (親 #75, 関連 #494 #514 PR #539) |
| xmm load の deref+disp 脱落 (D17 案)・FP 戻り (L1)・P1 の r8/eax 合流 (osc_setscale) | root の 5/56 止まり。Voice の getter/条件分岐 setter 全般に及ぶと推定 (件数は未集計) | #250 にコメント (本 REPORT §4・§5 を根拠に) |
| 第 1 段残 root 51 関数 (うち Voice core 20 関数 31,113 B、WTOsc 3,682 B の process 0x1803d0980 を含む) | 第 1 段未完 | **新規子チケット [SR-4b] 起票依頼** (ポインタ連鎖 spec が必要。pilot 化の雛形は `sr4/specs/sr4_osc_setscale.json`) |
| Ladder process 0x1802f6000 (744 B) の callee 0x1809ebf20 / 0x1809e7910 (CRT libm と推定, 未確認) と 0x1802f62f0 | libm 差は dB 許容判定 (SR-5) 前提 | #73 (SR-5) へ共有 |
| liftlib 既存回帰 (OTT/FA/KH の T1 ほか `liftlib_e2e.sh`) 未実行 — 素材 `work-m6-ott` `work-liftlib` `work-liftlib-targets` が本 run に無い | §3 の変更が既存 target を壊さない保証は『IR 不変の論理』のみ | PR 本文の `oc_artifacts:` 行でレビュー run に実行依頼 |
| survey の closure は直接辺のみ (vtable/fp 表/間接経由を含まない) | closure 規模は下限。SR-3 §11 の cut 表・REPORT §4 の filter 34 methods も vtable 打ち切りの影響を受け得る | #71 (SR-3) にコメント |
| 認可状態の DSP 供給 (SR-2) と Voice の実行駆動 (SR-1 host) は未接続 | Voice core の状態入力 spec は手書きの乱数 | #72 / #69 は closed — 必要なら SR-4b で扱う |
| P1 UNSUPPORTED を警告に留めた (偽陽性あり) ため、差分の入力分布が分岐の両結果を踏まないと見逃す | 判定の弱点 (osc_setscale は『前回値と等しい』分布を入れたため検出) | #250 (P1 の UNSUPPORTED を機械的に分類する案) |

## 7. 受入条件 (issue 本文に無いため提案。PM が確定してください)
1. root 56 関数を全て: (a) bit-exact (または SR-5 の dB 許容) で native と一致、(b) P1 UNSUPPORTED が 0 または分岐両結果を踏む証拠付き、(c) FP ALU 被覆 1.0。`sr4_run.sh` の strict gate (現状 exit 1) がそのまま判定になる。
2. Voice の osc → filter → voice 結線 (render 1 ブロック) を native と比較。blockedBy SR-1 (#69 closed) / SR-3 (#71 open) の消化。

## 8. 検証記録 (実測)
- 全体 1 本 (survey + 9 pilot + ネガコン 6, 直列, 4 core): クリーン worktree (`git worktree add --detach … HEAD` = `5415da7`) で `sr4_run.sh --pilot` を 3 回: **80.5〜80.9 秒** (80.93 / 80.59 / 80.49, load average 1 分値 0.95 / 0.99 / 1.04)、3 回とも exit 0。毎回 `git status --porcelain -- tools/targets/serum2/out` が空 = コミット済み `out/` を byte 一致で再生成。既定 (strict) 実行は exit 1 (`SR4 STAGE1 NOT COMPLETE`, 実測は PR 本文)。
- 1 pilot の所要 (RetDec + 修復 + emcc + 差分): 7.9〜9.2 秒 (9 本の min–max, 初回 1 回分)。RetDec 単体は 22,386 B の svf_process でも 7.9 秒。
- ネガティブコントロール (`sr4_run.sh` §4):
  | NC | 操作 | 期待 | 実測 |
  |---|---|---|---|
  | survey | 存在しないクラスを必須化 | exit 2 | exit 2 |
  | a | svf_setup raw の −π/2 定数の仮数を 2^34 (相対 3.8e-6) 破壊 | pilot gate exit 1 / result=mismatch | exit 1・mismatch 216/400 (一致 184) |
  | b | raw から `__asm_movlps` 呼びを削除 (this+0x74 の書込み欠落) | exit 1 / mismatch | exit 1・mismatch 400/400 (一致 0) |
  | c | insn.addr メタデータ 10 件を削除 | fp_alu_cov < 1.0 | 0.9048 (38/42) |
  | d | 期待 fail の osc_setscale を bit-exact+被覆 1.0 に偽装 | pilot gate exit 1 | exit 1 |
  | e | strict gate | 5/56 で exit 1 | exit 1 |
  - 初版の NC-a は定数を +1 ulp (double) だけ変えたが**最終 float 変換で丸められ bit-exact のまま**で、NC 判定側が『mismatch でない』と報告した (= NC の検出力不足を NC 自身が検出)。2^34 に変更。また NC-a/b の初版は `sr4_pilots.py` の出力 dir 未作成で gate が入力不正 exit 2 を返し『FAIL を検出』と誤認した → 期待 rc を厳密化 (gate 不合格は 1・入力不正は 2)。
- `find tools/targets/serum2 tools/liftlib -type f -size +20M -not -path '*/work/*'` = 0 件。`tools/liftlib/tests/test_unit.py` は T1〜T17 が `work-m6-ott` 等を要するため未実行、T18・T19 (本 PR 追加) のみ単独実行 ok。
- 範囲外: 実 Serum 2 の host 駆動 (SR-1) での Voice 実行・音声出力・libm 差の dB 評価 (SR-5)・GUI・FX/mod/arp/spectral (§6.1 の残り 3〜5 人月分)・mac 版。
