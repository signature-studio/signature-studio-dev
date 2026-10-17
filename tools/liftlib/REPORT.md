# liftlib REPORT — 共通 lift 修復基盤の統合 (CAB-49 / CAB-54 / CAB-55 / CAB-220 / CAB-239 / LIFTLIB-2)

> 正本: `tools/liftlib/REPORT.md` (§0〜§9 + 要約)。
> **付録 (分割移動・内容は削除していない)**: [`REPORT_APPENDIX_A.md`](REPORT_APPENDIX_A.md) (§10〜§12)・
> [`REPORT_APPENDIX_B.md`](REPORT_APPENDIX_B.md) (§13〜§16)・[`REPORT_APPENDIX.md`](REPORT_APPENDIX.md) (§17・§18)・[`REPORT_APPENDIX_C.md`](REPORT_APPENDIX_C.md) (§19)・[`REPORT_APPENDIX_D.md`](REPORT_APPENDIX_D.md) (§22)。 節番号は全ファイルで通し番号 (本体の §N 参照は付録の同番号節を指す)。
> #2128 (ott_getparam leaf への icall runtime 配線・測定 commit `f8bd2ea0`・部分達成): [`REPORT_APPENDIX_2128.md`](REPORT_APPENDIX_2128.md)。
> #2181 (ott_getparam F=281 の SSA dominance 修復・部分達成・測定 commit `e05270d33` (leafspec 200/200・probe 表の両方)): [`REPORT_APPENDIX_2181.md`](REPORT_APPENDIX_2181.md)。 #2861 (iargs unbound の rip `lea` 合成・部分達成): [`REPORT_APPENDIX_2861.md`](REPORT_APPENDIX_2861.md)。
> #3067 (`legacy_p1` の repmap を挿入前の行へ適用): [`REPORT_APPENDIX_3067.md`](REPORT_APPENDIX_3067.md)。 #294 (dir64 gate の `FL_WIN64_DIR` を env.sh 経由に置換・実測。gate `[1]` は既存 FAIL): [`REPORT_APPENDIX_294.md`](REPORT_APPENDIX_294.md)。

- 日付: 2026-10-11 / 担当 dir: `tools/liftlib/` (他 dir は読取のみ) / 再現: `bash tools/liftlib/liftlib_e2e.sh` (キャッシュ時 約 25 秒 + leaf spec 約 4 分, `--fresh` で FA/KH を RetDec lift から約 1 分)
- 数値はすべて本 dir で実測。推定は「推定」と明記。

## 0. 結論 (先出し)

| 項目 | 結果 (実測) |
|---|---|
| (a) OTT | liftlib 側のみで再現: **各段 IR がテキスト完全一致** (base=ott_lift.ll / P1→shift→gdata=ir7e_p1..p3 / memfix0 / memfix1 / 最終 ott_m10.ll の 7 段すべて true) → emcc → **checks 7 / broken 0, band 係数 maxdev=0.0 (nbad 0)**, E7 OOB 不発, census([0x248]=0) は `tools/ott/REPORT.md` §2.3 の旧 chain 行 = M10 と同値。helper は **自動生成 153 本**で署名不一致 0 / undefined 46 (M10 と同数)。processReplacing 出力 42 組合せ (param×[0x248]×入力振幅) の SHA が **元 m10 成果物と 42/42 一致** |
| (b) Fresh Air Gain | **400/400 シナリオ bit-exact** (全バッファ+guard 比較, 手書きパッチ無し。P1 は機械語から自動再構成)。対照: P1 無効 85 不一致 / F7 無効 376 不一致+trap 2 / F2 無効 400 不一致 |
| (c) Kilohearts Gain | **61 シーケンス×6 ブロック = 366/366 ステップ bit-exact** (元 6 ブロック列を含む)。対照: P1 無効 305 不一致 / F7 無効 全シナリオ hang→trap / F2 は KH では不要 (callee 0) |
| SIMD helper (CAB-54) | 宣言駆動で自動生成。KH census 205 mnemonic の **未被覆 83(効果)/31(共通基盤)/90(合算)/92(host 込) → 1/1/2/2** (残: `pcmpistri`, `vinsertf128`)。**実機 inline asm vs wasm を 192 mnemonic・281 form・95,400 ベクタで突合: 不一致 0** (近似命令 4 種は相対誤差 <1.6·2⁻¹² を許容して 489 件合格) |
| 検出器 (CAB-55) | パターン注入 **94 件 (F7 57 / P1 畳込み 35 / F2 2) を 94/94 検出**, 修復済み IR への偽陽性 0。OTT 生 IR で既知 [F7] 1 件 + **新規 6 件の F7 型脱落**, comis 89 サイトの分類 (§5) |

コミット列: c8027d3 (基盤: base/P1/F7/F2/simd/harness) → 56679d5 (OTT recipe・CLI・e2e・注入評価) → 09b3918 (docs/unit test; feature 完了点) → cf096a6 (lowbase 取り込み CAB-220) → CAB-239 → 本チケット (LIFTLIB-2 / CAB-256)。

**CAB-239 追加 (§11, 付録 A)**: mini-lifter 語彙 9 系統拡張 — OTT 落下分岐の再構成 **5 → 19**, 理由付き残留 **47 → 30**。
auto f7,p1 で junk census junkHi **175 → 104** (checks 7/0・band maxdev 0・trap 0 維持)。
OTT leaf native spec 新設 (`leafspec`) — **exp leaf 40/40 bit-exact**, log 32/40 (残は native CRT 経路 crash による除外)。
liftlib 本体の欠陥 3 件修正 (base A7 メタデータのカンマ落ち / gdata 表サイズ / f2 の v128 引数 wasm ABI)。

## 1. 既存資産の棚卸し (pass ごとの 検出条件 / 修復内容 / 入力依存)

| # | 元 | pass | 検出条件 | 修復内容 | 入力依存 | liftlib での扱い |
|---|---|---|---|---|---|---|
| 1 | m2 ir_normalize | A0 | typed ptr / 名前付き定数 / xor identity | opaque ptr 化, datalayout wasm32 | なし | `passes/base.py` に統合 |
| 2 | m3/m5 ir5_patch | A1–A8 | datalayout・constexpr 畳込み・ptrtoint 幅・メタデータ | 正規化 | なし | base.py (A7 は `!insn.addr` を保持するよう変更) |
| 3 | m5 | A9L / A9L2 | 残存 constexpr (ptrtoint/inttoptr/icmp/算術) | 命令化 (OTT 5 残, mm closure 677 関数で 187→2) | なし | base.py (A9=命令化 lift) |
| 4 | m5 | B1 | 未 store alloca の load | `xor 0,0` (決定論化) | なし | base.py |
| 5 | m5 | S1a/S1b | `__asm_movups(load値,値)` 形の store 化け / movss.3 | store 復元 / zext | helper 名 | base.py (S1a 正規表現を addr 付に拡張) |
| 6 | m5 | C1/C9/C11/C12/C13 | select closure・redirect・戻り値・未解決 stub・external global | 選択/置換/stub/0 初期化 | seed 関数名 (CLI 引数) | base.py に保持 (cfg から) |
| 7 | m6 ir6_pass [P1] | comis 直後 13 行内の `br i1 %cf/zf.N` / `or cf,zf` | flag を fcmp 由来に差替 (**no_branch 66/94 は未対応**) | SSA 名パターン | `p1_legacy.py` (IR 完全一致) + `p1.py` (機械語正本) |
| 8 | targets/kilohearts ir_kh_p1 | [P1] miswire | 同上 (8 行内) | 同上 | SSA 名 | `p1.py` rewire |
| 9 | targets/freshair fa_fix_gain | P1' dropped | 手書き: `%37,%38,%42,%34,%35` | 脱落 jbe/jae を select で再構成 | **関数固有 SSA 名** | `p1.py` reconstruct (mini-lifter) |
| 10 | m6 ir6_shift | VA remap | `i64 0x18…` / `@global_var_18…` | −0x150000000 平行移動 | BASE/MAXV 定数 | `passes/remap.shift_va` (一致) |
| 11 | m6 ir6_gdata + m6_data_gen | データ実体化 | 全 `@global_var_*` | DLL 実バイトで定義 / .rdata+.data を線形メモリ敷設 C 生成 | DLL パス, 0x30000000 | `remap.gdata(_legacy)` + `passes/dataimage.py` (m6_data.c と本体一致) |
| 12 | m6 m6_memfix | CRT 置換 | `function_1801a2a20/1801a30d0` define | C 実装へ外出し | **OTT 固定名** | `recipes/ott` (vendored) |
| 13 | m6 m6_full_extract | splice | closure で declare のみの 3 関数 | full lift から抽出+helper 改名 | **HELPER_RENAME=RetDec 接尾番号** | vendored。名前依存部は §4 の正規名化で不要化可 |
| 14 | m7/m8 ir7_argpass(_fixed) | F2(setParameter) | f32 引数落ち + jump table 退化 | 3 引数化 + dsm から本体再生 | dsm・関数名 | vendored (本体再生は固有) / 引数接続は `f2.py` |
| 15 | m8 ir8_valueflow | F1/F2(SVF) | accessor 誤訳 / xmm1 落ち 16 callsite | 再生成 / 2 引数化 | insn.addr+dsm | vendored / F2 は `f2.py` が同型を検出 (OTT で 22 callee) |
| 16 | m9 ir9_bootstraps | F3–F6 | resume/gate box/exp,log,tan の破れ | C port 置換 | 関数名・定数 | vendored |
| 17 | m9 ir9_outcopy / KH ir_kh_f7 / FA F7' | **F7** | `mov r64,[b]` の load 脱落 (`add …, %r8.3.reload` 等) | load 復元 | **SSA 名・VA 固定** | `f7.py` に統合 (3 件を同一ロジックで修復) |
| 18 | m9 m9_tablebind / m9_boot / m10_boot | F8/F9 | band filter 係数 / 低 VA thunk 領域 | C port・表敷設 | 固定 VA | runtime C を入力利用 (固有) |
| 19 | m6 gen_msimd6 + m6_simd_check | helper 生成 | declare 型 | msimd6.c 生成 (153 種) | **接尾番号 (`mulss__18` 等)・OTT 専用 core.h** | `simd/gen.py`+`kernels.py` で署名駆動に置換 |

**統一できたもの**: 1–11, 17, 19 (汎用) / **固有のまま vendored**: 12–16, 18 (OTT の関数・dsm・定数に結合)。

## 2. 統一パッケージ (`tools/liftlib/`, Python3 約 6.5k 行 + C)
`liftlib/{ir,pe,mc,regbind}.py` 基盤 / `passes/{base,p1,f7,f2,remap,dataimage,p1_legacy}.py` / `simd/{kernels,gen,simdtest}.py+liftlib_simd.h` /
`harness/{spec,diff,specgen}.py+native_runner.c+ms_call.S+wasm_runner.mjs` / `recipes/ott*` / CLI `python3 -m liftlib`。使い方は README.md。

## 3. 回帰結果の詳細
### (a) OTT (`python3 -m liftlib ott`)
- 入力 (読取のみ): `tools/m6/work/{ott.drc.ll, full_t1.drc.{ll,dsm}, m6_stubs*.c}` (既存 RetDec 成果物; 全 decode の再実行は未実施), runtime C (`m6_rt/m8_rt/m9_rt/m10_boot.c`, shim heap), `m6_build.sh` の export 一覧。**m*/ のスクリプトは一切実行しない** (同等 pass は liftlib 実装 or `recipes/ott/` の無改変コピー)。
- IR 一致 (非空行完全一致): base / P1(18 insert) / shift(38) / gdata(400) / memfix0 / memfix1 / 最終 `ott_m10.ll` / `m6_data.c` 本体。
- ビルド: emcc 1.4 s, signature mismatch 0, undefined 46 (=M10), `undefined __asm_*` 0。
- e2e: checks 7/0, maxdev 0.0, trap rc 0。census([0x248]=1) 4/254/252/2 も M10 と同値。
- **auto モード** (`ott --auto f7[,p1]`): 汎用 F7 が `ir9_outcopy` を包含 (outcopy 省略) して checks 7/0 維持。census([0x248]=1) は normal 254→255 / junkTiny 2→1
  (新規 F7 6 サイトが [0x248]=1 経路に効く証拠)。p1 を足しても 7/0 維持 (census 不変)。
### (b)(c) FA / KH (`python3 -m liftlib lift targets/{fa,kh}_gain.json`)
- 手順は pass 鎖 1 本 (base→P1→F7→F2→gdata→正規名化 helper→emcc)。FA 修復: P1 再構成 1 (region 3 ブロック) / F7 1 / F2 callee 2+call site 2。KH: P1 rewire 1 / F7 1。
- 比較: 全バッファ (this/P/Q/buf/ctx/L/R, guard 64B) の bit 一致 + ポインタ欄は `buf+off` トークン一致。native crash 0, wasm trap 0。
- FA の旧ハーネスは L/R+状態の一部のみ比較だったのに対し, 本ハーネスは P(40KB) 全域も比較しており strictly 強い。

## 4. SIMD helper 自動生成 (CAB-54)
- 規約 (3 バイナリの declare で確認): 引数 = 命令の **read operand を順に** (RMW dst は dst_old を含む / write-only dst は含まない / VEX 3-op は src1,src2), 戻り = dst 値。ストアは src 低位値。
- 生成は `(base, 戻り型, 引数型)` のみ依存。`__asm_<base>__<ret><args>` に正規名化 (例 `mulss__xxd`): FA の `mulss(i128,i32)` と OTT の `mulss(i128,i128)` を衝突させない。
  単体テスト T3: 全 declare の接尾番号を付け替えても生成 C が同一 (156 helper)。
- 実機突合 (`simd test`): 205 mnemonic のうち asm で検証できる 192 を 281 form × 各 200 ベクタ (imm 違い含め 477 命令インスタンス, 計 95,400): exact 94,911 / approx_ok 489 / **mismatch 0**。
  検証不能: comis 系 (フラグは P1 pass が担う no-op), ストア形の RetDec 規約 (低位値返し)。
- 被覆 before→after: 効果 42 本 83→1, 共通基盤 31→1, 効果+共通 90→2, host 込 92→2。残 `pcmpistri` (SSE4.2 文字列比較+フラグ), `vinsertf128` (ymm)。
  **ymm(i256) 形は C の ABI で表現不能のため未対応** (KH closure 内 VEX-256 は 6 関数 / OTT は memfix で消滅する 3 helper)。
- 近似命令 `rcpps/rsqrtps/rcpss/rsqrtss` は 12bit 近似テーブルの bit 再現はせず誤差許容 (denormal→inf, 負→QNaN の特例は実機と一致)。

## 5. silent miscompile 検出・修復 (CAB-49/55)
### 5.1 検出器の検出力 (パターン注入, `inject-eval`)
| 対象 | F7 (load 削除) | P1 畳込み (br i1→br label) | F2 (xmm 引数除去) | 偽陽性 (修復済 IR) |
|---|---|---|---|---|
| FA gain | 5/5 検出・5 修復 | 1/1 | 2/2 | 0 |
| KH gain | 9/9 検出・9 修復 | 1/1 | 0 (対象無) | 0 |
| OTT 生 IR | 43/43 検出・42 修復 | 33/33 | — | — |
### 5.2 OTT 生 IR に対する自動検出の所見 (旧チェーンが未対応/未検出だった部分)
- **comis 89 サイト** (旧 ir6 の「94」は declare 等を含む数): 分岐あり 33 (→30 を fcmp 再配線, 3 は向き解決不能) / **分岐脱落 52** / cmov 消費 4。
  脱落 52 のうち mini-lifter が再構成できたのは **5** (未検証: OTT には native 突合用 spec が無い)。残 47 は理由付きで報告 (断片内に rsp 基準メモリ・call・整数フラグ分岐が在る,
  r15/rbx/xmm0 の到達定義が call を跨いで bind 不能, など)。→ M10 REPORT の「18011efb0 per-sample 分岐」系の根の可能性 (推定)。
- **F7 型脱落**: 緩い候補 186 → 厳密修復 7。既知 m9 [F7] (0x180120632) に加え **0x18011ef10 / 0x18011f00e / 0x18011f9aa / 0x180120e6a / 0x1801adda1 / 0x1801c6b5b** (M10 §5 が「[F7] 型の 0x18011e* 適用」と挙げていた入力 deref 欠落に一致)。
- **F2 型**: 入口 live-in xmm を持つのに xmm 引数が無い callee が 22 (SVF 0x180126040 など)。OTT の固有 recipe 側で個別対処済みの分と未対処の分の仕分けは未実施。
### 5.3 mini-lifter の範囲
脱落断片が木構造で, 語彙が {xmm/gpr 間 mov, ゼロ化, comis+jcc, GPR mov/imm, メモリ load/store (rsp 基準除く), SSE 算術 (kernels にある形)} に収まる場合のみ再構成。
FA の P1' (comisd×2+jbe/jae+xorps/movaps+jmp, 合流先は reg2mem alloca) が代表例。それ以外は `UNSUPPORTED <理由>` を出して IR を変更しない。

## 6. 検証の限界 (正直な評価)
- bit-exact を実機突合で示せたのは FA Gain / KH Gain の 2 関数のみ (P1 再構成の native 検証は FA の 1 事例)。OTT の自動修復 (F7 7 / P1 30+5) は e2e 7/0 維持までで **bit 突合は未実施**。
- harness は IAT 呼出を含む関数は native 実行不能 (crash はシナリオ除外として計上)。wasm 側の xmm0 戻り値は未搬送 (rax のみ)。NaN 入力は除外。
- spec は FA/KH とも手書き (`specgen` は雛形のみ: 配列サイズ・ループ回数・フラグ分布は人手)。
- F2 は xmm *戻り値* (OTT [F1] accessor) とスタック引数・GPR 引数個数不一致を扱わない。
- OTT の RetDec 全 decode (`full_t1`, 約 15GB) は再実行していない (既存成果物を入力)。RetDec 再 lift の非決定性は base の fixup (`add i64 0, i64 %X`, 重複 declare) で吸収。

## 7. 未解決・ブロッカー
1. OTT 脱落分岐 47/52 の自動再構成 (rsp 基準メモリ・call を含む断片, call 跨ぎの reaching-def bind) — 設計済みだが未実装。
2. ymm(i256) helper の ABI (Convolver / Filter Table 用) と `pcmpistri`。
3. OTT 固有 recipe (#12–16, 18) の汎用化 (insn.addr 駆動の jump table 本体再生など)。
4. 自動修復の bit 突合を OTT 関数へ広げる spec (SVF / exp / tan 等 leaf) と xmm0 戻り搬送。

## 8. ユーザ依頼事項
- 特になし (素材は既存 work を利用)。判断依頼: `tools/m5〜m10` の pass を liftlib へ一本化 (旧 dir は参照専用へ) してよいか。

## 9. 次タスク提案
1. **KH Tier-S 一括 lift**: `specgen`+`lift` で Channel Mixer/Haas/Clipper/Gate/3-Band EQ/Stereo (CAB-48 系)。
2. **FA Compressor/Filter** を同パイプラインで (FA-2)。
3. **OTT M11**: `ott --auto f7,p1` を既定化し, 新規 F7 6 サイトと脱落分岐の影響を junk census/bit 突合で評価。
4. mini-lifter 語彙拡張 (rsp 基準・call・整数フラグ) と OTT leaf への native spec。
5. ymm/i256 helper ABI, `pcmpistri`, F2 の xmm 戻り値対応。

## 10〜16. 追補セクション (付録へ分割移動)

§10〜§16 の全文は 250 行上限 (`docs/DOC_MAP.md` §1) のため付録に**そのまま分割移動**した (節番号・本文は不変, 内容は削除していない)。
本体には結論 1〜2 行とリンクのみ残す。測定値は付録側が正本 (本体に再掲しない)。

| 節 | 内容 | 結論 (要約) | 全文 |
|---|---|---|---|
| §10 | lowbase 取り込み (CAB-220) | OTT を liftlib pipeline 内で最初から低位 base 生成可能にし, 複数 base と旧既定の出力 SHA 全件一致を確認。`lowbase_e2e.sh` ALL PASS | [`REPORT_APPENDIX_A.md`](REPORT_APPENDIX_A.md) §10 |
| §11 | mini-lifter 語彙拡張 + OTT leaf native spec (CAB-239) | 語彙 9 系統で落下分岐の再構成が増え, leaf native spec (`leafspec`) を新設。liftlib 本体の欠陥 3 件を修正 | [`REPORT_APPENDIX_A.md`](REPORT_APPENDIX_A.md) §11 |
| §12 | LIFTLIB-2 (CAB-256): 領域 DAG の phi 合成 + 無限ループ修復 | OTT 既定ビルドの無限ループ (CAB-238) を修復し, 多定義 bind / region join の残留を削減。e2e gate に param sweep + hard timeout を追加 | [`REPORT_APPENDIX_A.md`](REPORT_APPENDIX_A.md) §12 |
| §13 | LIFTLIB-3 (CAB-264): 汎用 xmm0-ret bind + tan 入口誤解析修正 | leafabi/regbind/mc/f2 に xmm0-ret bind を実装し残留 dropped と tan を改善。census junkHi は不変 (記録のみ) | [`REPORT_APPENDIX_B.md`](REPORT_APPENDIX_B.md) §13 |
| §14 | LIFTLIB-4 (CAB-272): leaf region の phi 合成 | OTT 既定 p1 の残留 UNSUPPORTED をさらに削減, tan 改善。回帰 ALL PASS | [`REPORT_APPENDIX_B.md`](REPORT_APPENDIX_B.md) §14 |
| §15 | LIFTLIB-1 (#224): 旧 dir 参照専用化の検収 | 対応表を `README.md` に追記, 旧 dir REPORT に参照専用注記。`liftlib_e2e.sh` 通常・`--fresh` とも ALL PASS | [`REPORT_APPENDIX_B.md`](REPORT_APPENDIX_B.md) §15 |
| §16 | 環境パス置換 (#386): `tools/liftlib/liftlib` の `<HOME>/work` 固定を `tools/shared` へ | DLL パスを `tools/shared/paths.py` 経由に置換 (既定値同一)。`tools/liftlib/` 直下 5 ファイルの残りは §16.3 の未解決表 | [`REPORT_APPENDIX_B.md`](REPORT_APPENDIX_B.md) §16 |

## 17. HB-H3 (#93): 整数引数脱落 (D3) の機械検出・復元 pass `iargs` — 付録へ移動

全文は **[`REPORT_APPENDIX.md`](REPORT_APPENDIX.md) §17** (本体の 250 行上限対応で分割移動。内容は削除していない)。
- 結論: `passes.iargs` (既定 off) が RetDec の整数引数 (rdx/r8/r9) 脱落を機械語基準で検出・復元する。OTT ctor の native 突合は iargs ON 200/200・ネガコン (OFF) 0/200 (§17.2)。
- 検出 `iargs.scan()` は define 15 / 引数不足 site 15 / 入口素通し位置の誤値 site 17 (`sites_entry`, #427 で実装) を返す (§17.7)。
- 未達: getParameter の xmm0 戻り (RetDec route; jump table 欠落が先, §17.3)。未解決は §17.5。

## 18. LIFTLIB #241 — ymm(i256) helper ABI + pcmpistri + F2 xmm 戻り搬送 — 付録へ移動

全文は **[`REPORT_APPENDIX.md`](REPORT_APPENDIX.md) §18** (本体の 250 行上限対応で分割移動。内容は削除していない)。
- 結論: ymm(i256) helper の ABI と `pcmpistri` を実装して SIMD helper 自動生成の未被覆を解消し、F2 に xmm 戻り搬送 (`xmm_ret_scan` / `run_xmm_ret`) を追加した。実測値・未解決は付録 §18.1・§18.6・§18.7。

## 19. PERF-P1 (#155): lift ビルド標準設定 + 出力署名ガード — 付録へ配置

全文は **[`REPORT_APPENDIX_C.md`](REPORT_APPENDIX_C.md) §19**。
- 結論: `python3 -m liftlib build <cfg>` が標準設定 (`-O3 -flto` + gc-sections + 最小 export、正本 `data/std_build.json`) で全変種 (ref/o2/o3/std) をビルドし、署名不一致なら exit 1・成果物なし。`bash tools/liftlib/stdbuild_e2e.sh` (合成入力) で 3/3 PASS・ネガコン FAIL を確認。
- 未達: 実 OTT / FA / KH を標準設定で通す検証 (素材不足)。未解決は §19 の表。

## 20. lowbase_e2e.sh の DLL パス環境変数化 (#440, 親 #294 / 発見 #427)

既知類型との関係 (DEFECTS.md): 該当なし (lift 欠陥ではなくスクリプトのパス固定の解消)。

- 変更: `tools/liftlib/lowbase_e2e.sh` の DLL 行 (`[ANALYSIS-PLUGINS]` 配下の `OTT_vst2_win64.dll` を絶対パスで直書き) を
  `source tools/shared/env.sh` + `DLL="${OTT_DLL:-$PLUGINS_DIR/ott/binaries/OTT_vst2_win64.dll}"` に置換。
  `PLUGINS_DIR` 未設定時の既定は `[ANALYSIS-PLUGINS]` (= `$ANALYSIS_DIR/plugins`) で従来と同一パス。DLL が無い場合は exit 2。
- 是正 (review 5499056345 / Copilot 指摘, b0bedb6): `tools/liftlib/liftlib/env.py` の `OTT_DLL` が環境変数 `OTT_DLL` を見ず
  `PLUGINS_DIR` からのみ導出していたため、[2] (`python3 -m liftlib ott`) は `OTT_DLL` と別の DLL を使い得た。
  `OTT_DLL = os.environ.get("OTT_DLL") or os.path.join(PLUGINS_DIR, ...)` に変更 (未設定・空文字は従来と同じ導出)。
- 初回検証 (コミット済み HEAD 100b550、Actions runner 4 vCPU、`ANALYSIS_DIR=$HOME/analysis`、直列 n=1):

| 項目 | 実測 |
|---|---|
| 変更後 `bash tools/liftlib/lowbase_e2e.sh` | ALL PASS / rc=0 / 1:19.00 / load average 1.39 (1 分値) |
| 変更前 (origin/main 版の DLL 行のみ runner の実在パスに差替) | ALL PASS / rc=0 / 1:19.78 |
| SUMMARY 節 (liftlib ott ×2・x64c 3 構成・合計 150,708 cell) の diff | 差 0 (`SUMMARY_IDENTICAL`) |
| ネガコン `PLUGINS_DIR=/nonexistent` | `/nonexistent/ott/binaries/OTT_vst2_win64.dll 無し` exit 2 |
| ネガコン `OTT_DLL=/nonexistent/x.dll` | `/nonexistent/x.dll 無し` exit 2 |
| 環境変数なし (既定値) | `[ANALYSIS-PLUGINS]/ott/binaries/OTT_vst2_win64.dll` を指す (この runner には無く exit 2) |

- 是正後の検証 (コミット済み HEAD b0bedb6、同 runner・直列 n=1、`ANALYSIS_DIR=$HOME/analysis`、`capstone 5.0.7` / `pefile 2024.8.26` は
  runner 側 venv で用意):

| 項目 | 実測 |
|---|---|
| `bash tools/liftlib/lowbase_e2e.sh` (環境変数なし) | ALL PASS / rc=0 / 81.5 秒 / load average 0.96 (終了直後の 1 分値)。SUMMARY は ott 2 構成 PASS・x64c 3 構成 計 150,708 cell・`max_ulp 0`・`state_diff_qwords 0` |
| 旧 `env.py` (35d78c9) で `OTT_DLL=<別パスの DLL>` を与えた `env.OTT_DLL` | `PLUGINS_DIR` 由来の既定 DLL を返す (指摘の再現) |
| 新 `env.py` (b0bedb6) で同条件の `env.OTT_DLL` | 与えた別パスの DLL を返す |
| `OTT_DLL=<既定 DLL と同一 sha256 のコピー>` + `PLUGINS_DIR=/nonexistent` | [1] PASS・[2] 2 構成 PASS (`PLUGINS_DIR` に依存しない)。[3] は 3 構成とも build FAIL (`build_x64c.sh` が `PLUGINS_DIR` 側の DLL を開き FileNotFoundError)、全体 rc=1 / 146.8 秒 |
| ネガコン `OTT_DLL=<実在の別 DLL (OTT_vst2_win32.dll, PE32)>` `--quick` | [1] の集計が既定 DLL と異なる (reloc DIR64 0 / IAT 368 slot。既定は 13000 / 375)、[2] は 2 構成とも `checks 8 / broken 3` で FAIL、rc=1 / 39.4 秒。[3] は既定 DLL を使うため PASS |
| ネガコン `PLUGINS_DIR=/nonexistent`・`OTT_DLL=/nonexistent/x.dll` | いずれも exit 2 (上の初回検証と同一メッセージ) |

- `OTT_DLL` が効く範囲 (上の実測): 存在確認・[1]・[2] (`liftlib/env.py` 経由)。[3] (`hostbridge/lowbase/x64c/build_x64c.sh` は
  `LB_DLL` か `PLUGINS_DIR` を参照) と `--full` (`hostbridge/lowbase/lowbase_e2e.sh` は `PLUGINS_DIR` のみ参照) には伝わらない。
- 検証範囲外: `--full` (hostbridge の RetDec chain + Chrome)。`tests/test_unit.py` (FreshAir 素材が要る。plugins-freshair 未取得)。
- 検証メモ: `work-liftlib` 素材内の `work/ott_*/work/full_t1.drc.{ll,dsm}` は作業 VM の旧 checkout 内ファイルへの絶対 symlink で、
  runner では dangling となり `recipes/ott.py` が `FileExistsError` で落ちる (初回 run で観測)。gitignore 対象の `work/` 内のため
  runner 上で検証用 worktree 内の同名ファイルへ張り直して検証した (commit 対象外。是正後の検証 worktree でも 98 本を同様に張り直した)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `work-liftlib` / `work-m6-ott` 素材の絶対 symlink (作業 VM の旧 checkout 内ファイルを指す) が runner で dangling。lowbase_e2e [2] が素材展開直後は FAIL | Actions 上で lowbase_e2e を再実行する度に手動張り直しが要る | #448 `[CI-8]` (OPEN) が追跡 (素材の相対 symlink 化 or `recipes/ott.py` の `os.path.lexists` 判定) |
| (初版の記述: `tools/ott/avx/build_avx.sh`・`tools/ott/crtinit/lift_crt.sh`・`tools/ott/accept/acc_crt_table.py`・`tools/ott/avx/unsup_scan.py`・`tools/m9/m9_tablebind.py`・`tools/shimx/scripts/import_scan.py`・`tools/liftlib/tests/test_unit.py`・`tools/liftlib/xmm0_ret_census.py` にも同一の固定パスが残る。同種の移植性欠陥 (本 issue の範囲外)。新規子チケット案 (CI-4 系列)) | **解消済み**: a4f8a08 (#450 / PR #460) と 2db928d (#427 / PR #438) で main に merge 済み。この HEAD で 8 ファイルとも旧ユーザ名付き絶対パスの出現数 0 を実測。#450 `[CI-4-ott-liftlib]` は CLOSED | 起票不要 |
| `OTT_DLL` が [3] (`build_x64c.sh`) と `--full` に伝わらない。[3] は `libottnative.so` (既定 DLL 由来) と比較するため、別 DLL を指定しても [3] だけ既定 DLL を検証する | 別 DLL を `OTT_DLL` で指定した検証が [1][2] と [3] で別対象になる | 未起票 (新規子チケット案、CI-4 系列・親 #294。PM に起票依頼) |
| `capstone` / `pefile` の依存がどこにも宣言されていない。素材展開だけでは [1] の最初の python 呼び出しで落ちる | Actions 上で e2e を再実行する度に手動インストールが要る | 未起票 (新規子チケット案、CI 系列。PM に起票依頼) |

## 21. DIR64 補正境界 (section 末尾 8B slot) の複製の全数列挙と修正 (#593 / M11-N22, 親 #572)

既知類型との関係: 該当なし (DEFECTS.md の D1a〜D16 にも icall §4 にも無い。データ敷設 C 生成器の境界 off-by-one で、m11 #572 と同根)。検証起点 commit: `1a94ac2` (修正コード)。

- 結論: 旧境界 `r < lo + len - 8` は 3 箇所 (`tools/m6/m6_data_gen.py:42` / `tools/liftlib/liftlib/passes/dataimage.py:35` / `tools/liftlib/tests/test_unit.py:116`) に複製されており、全て `<=` に修正。**FL 本体 PE (`block00031_PE.bin`) では `.data` 末尾 slot (RVA `0x11e5000`) が旧条件で補正漏れ、修正後は 0**。OTT 実機 DLL (`OTT_vst2_win64.dll`) は補正漏れ 0 (末尾 slot 自体が存在せず旧条件でも漏れない = 潜在バグは OTT 生成物には顕在化していなかった。下記「OTT 実機の実測」)。
- 再現: `bash tools/liftlib/dir64_boundary_gate.sh` (1 コマンド。PE 省略時 `$FL_WIN64_DIR/extracted/block00031_PE.bin`)。不合格は非 0 で終了する。

| 検査 | 算法 | 結果 |
|---|---|---|
| [1] 全数列挙 (`dir64_boundary_enum.py`) | (A) 行 regex と (B) python `ast` の Compare 走査を突合 (`tools/` 配下の `.py/.mjs/.js/.ts/.sh/.c/.h`、`work/` 除外、`reloc`/`DIR64` を含むファイルのみ) | 和集合 8 件 (grep 8 / ast 8, `.py` の不一致 0)。旧境界 0 件。意図的に旧式を残す `m11/m11_reloc_audit.py:83` (旧条件との選択差を測る式 OLD) だけ許可リスト |
| [2] 実バイト (`dir64_boundary_check.py`) | pefile の `DIRECTORY_ENTRY_BASERELOC` で DIR64 を列挙 (生成器は `.reloc` を手パース = 別算法) し、生成 C の `dlld_*[]` の slot を `v - IMG + VA_BASE` と比較 | m6 / liftlib とも 補正対象の末尾 slot 1 件 / 補正 1 / 補正漏れ 0 / 不正値 0 |
| [3] ネガコン | 3 箇所の条件を旧 `<` に戻した複製 | 列挙は OLD=3 で FAIL (rc 非 0)。実バイトは m6 / liftlib とも `MISS .data RVA 0x11e5000` 補正漏れ 1 (期待 1 で PASS)。現行コードに期待 1 を与えると FAIL |

- 影響なし (境界が正しい) と判定した箇所: `ott/lift/data_gen.py:28`・`hostbridge/lowbase/x64c/lb_data_gen.py:30` (`< lo + len - 7`、slot が収まる = `<= lo + len - 8` と同値)、`hostbridge/lowbase/audit_va.py` (`range(va, va+vs-7, 8)`)、`m11/m11_image_gen.py`・`plugins/lift/passes/m11_image_gen.py` (`r + 8 <= top`)、`m11/lb_check.py` (`r + 8 <= va + vs`)、`m11/m11_data_gen.py:50` (#572 で修正済)、`flelift/fle_data_gen.py` (生バイトコピーで補正なし)。
- 実測 (runner 4 vCPU、コミット済み HEAD を `git worktree add --detach` で展開): gate 3 回 全て ALL PASS・37.05 / 37.06 / 37.14 秒 (load average 0.31→0.65→0.81、直列)。
- 範囲外: 実行時の差 (LoadStringW 実装後の回帰確認) は #132 に依頼済み。

### OTT 実機の実測 (`analysis-ott-binaries` の `OTT_vst2_win64.dll`、検証起点 commit `f9adacd` = #636 merge 済み main)

| 検査 | 結果 |
|---|---|
| `dir64_boundary_check.py OTT_vst2_win64.dll --gen m6 / --gen liftlib` (`--expect-missed 0`、pefile 独立算法) | 両方 PASS: DIR64 total=13000 / 補正対象=13000 / 補正漏れ=0 / 不正値=0 / 末尾 slot 対象=0 |
| 旧条件 `<` に戻した複製 (m6 / liftlib) | 同じく補正漏れ=0 (OTT では旧条件でも落ちない) |
| `tests/test_unit.py` T7 (`t7()` 単独、3 回) | 3 回とも `T7 ok`: 補正 12329 件 (.rdata) = base 非依存、うち nt<0x400000 12329 件。0.611 / 0.596 / 0.600 秒 (load average 0.73→0.75→0.75、直列) |
| `dir64_boundary_gate.sh` (FL 本体 PE、同 HEAD) | ALL PASS・36.173 秒 (load average 0.69→0.83)。ネガコン (列挙 OLD=3 / 補正漏れ 1 / 期待逆転) 全て期待通り |

- 末尾 slot が無い理由: 補正対象 section は `.rdata` (VS=511510, 最終 DIR64 RVA 0x225618、末尾まで 235518 B) と `.data` (VS=56268, 最終 DIR64 RVA 0x268e70、末尾まで 15708 B) の 2 つで、どちらも最終 reloc から section 末尾まで 8B より十分離れている。他 section (`.text` / `.pdata` / `_RDATA` / `.rsrc` / `.reloc`) に DIR64 は 0 件。よって旧境界 `r < lo + len - 8` は OTT では結果を変えない。
- 測定条件: runner 4 vCPU、`$HOME/analysis/plugins/ott/binaries/OTT_vst2_win64.dll` (3146752 B)、`FL_WIN64_DIR` は `fl-win64` を展開した dir、`pefile` / `capstone` は uv venv に導入。
- T7 以外の `test_unit.py` 全体 (`python3 tests/test_unit.py`) は T6 で停止: Fresh Air 素材 (`targets/freshair/work/win/...SlateCore.core_64` = `work-liftlib-targets`) が今回の `oc_artifacts` に無いため。T1〜T5 は PASS (T6 以降未実行)。T7 は上記の通り単独実行で PASS。本 issue の受入条件は T7 のみ。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実行時の差の顕在化 (LoadStringW 実装後の回帰確認) | m11 同様、潜在バグで顕在化条件は未確認 | #132 にコメントで回帰確認項目を依頼 |

## 22. LIFTLIB-9 (#668): RetDec raw lift 出力の非決定性 — 付録 D へ分割 (要約)

- **結論**: 同一 PE・同一 ranges の RetDec raw `*.drc.ll` は実行ごとに変わり得る (ASLR 有効の実行群で distinct 1〜6 種)。差分は `uselistorder` 指示の行 (行の有無と並び)。`.drc.c` は 8/8 同一。既存の A7 段 (`run_base` / `ir5_patch`) がこの行を除去するため、liftlib base 段は 6/6、m6 chain は 3/3 が同一 (OTT 入力)。
- **対策**: raw は sha256 比較しない・A7 後の成果物で判定する。回帰 gate `lift_determinism_e2e.sh` は PASS し、1 行追加の検出と A7 外し (FAIL・rc=1) を確認。`setarch -R` は決定性の手段として採らない (ASLR 無効でも raw が一致しない事例があり、契機は未分離)。
- **未解決**: k80 (block18983_PE.bin) の alloca 並び差は OTT で再現せず、A7 後に残るかは未検証 (fl-win64 が必要) → `[LIFTLIB-10]` #695 に起票。PR は `Refs #668`。
- 詳細・全実測・受入条件の達成状況は [`REPORT_APPENDIX_D.md`](REPORT_APPENDIX_D.md) (§22.1〜§22.12)。再現: `bash tools/liftlib/lift_determinism_e2e.sh` (N=2、HEAD `116cbb3` で総 17 秒) / `bash tools/liftlib/lift_determinism_probe.sh 4` (同 33 秒)。レビュー指摘 (PR #696) の対応は §22.12。

## 23. LIFTLIB-5 (#342) — tan / tanf bit-exact・SVF 20/40 (未達)

- **結論**: tan 40/40・tanf 40/40 で gate 化。SVF 20/40 (未達・gate 無し)、cvt 26/40。本文は [`REPORT_APPENDIX_E.md`](REPORT_APPENDIX_E.md) (§23.1〜§23.7・DEFECTS 行案)。

## 24. CI-8 (#448): work-* 絶対 symlink の張り直しと lowbase_e2e [3] の素材 .so 不整合

- **結論**: 受入 1・2 は達成済み。受入 3 は素材の古い `libottnative.so` で [3] が FAIL したため、[3] で `tools/ott/native/build.sh` から再ビルドする修正 (2f1b76fc) で ALL PASS (詳細は [`REPORT_APPENDIX_448.md`](REPORT_APPENDIX_448.md))。
