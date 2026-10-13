# liftlib REPORT — 共通 lift 修復基盤の統合 (CAB-49 / CAB-54 / CAB-55 / CAB-220 / CAB-239 / LIFTLIB-2)

> 正本: `tools/liftlib/REPORT.md` (§0〜§9 + 要約)。
> **付録 (分割移動・内容は削除していない)**: [`REPORT_APPENDIX_A.md`](REPORT_APPENDIX_A.md) (§10〜§12)・
> [`REPORT_APPENDIX_B.md`](REPORT_APPENDIX_B.md) (§13〜§16)・[`REPORT_APPENDIX.md`](REPORT_APPENDIX.md) (§17)。
> 節番号は全ファイルで通し番号 (本体の §N 参照は付録の同番号節を指す)。

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
| §16 | 環境パス置換 (#386): `tools/liftlib/liftlib` の `/home/ubuntu` を `tools/shared` へ | DLL パスを `tools/shared/paths.py` 経由に置換 (既定値同一)。`tools/liftlib/` 直下 5 ファイルの残りは §16.3 の未解決表 | [`REPORT_APPENDIX_B.md`](REPORT_APPENDIX_B.md) §16 |

## 17. HB-H3 (#93): 整数引数脱落 (D3) の機械検出・復元 pass `iargs` — 付録へ移動

全文は **[`REPORT_APPENDIX.md`](REPORT_APPENDIX.md) §17** (本体の 250 行上限対応で分割移動。内容は削除していない)。
- 結論: `passes.iargs` (既定 off) が RetDec の整数引数 (rdx/r8/r9) 脱落を機械語基準で検出・復元する。OTT ctor の native 突合は iargs ON 200/200・ネガコン (OFF) 0/200 (§17.2)。
- 検出 `iargs.scan()` は define 15 / 引数不足 site 15 / 入口素通し位置の誤値 site 17 (`sites_entry`, #427 で実装) を返す (§17.7)。
- 未達: getParameter の xmm0 戻り (RetDec route; jump table 欠落が先, §17.3)。未解決は §17.5。

## 18. LIFTLIB #241 — ymm(i256) helper ABI + pcmpistri + F2 xmm 戻り搬送

- 既知類型との関係: **該当なし** (`docs/DEFECTS.md` D1a〜D16 / `icall §4` とも未登録。新類型行案は §18.7)
- 検証起点 commit: `main` = `400d546` (着手時)。数値はコミット済み HEAD `8476a82` の clean worktree (`git worktree add --detach`) で再現して取得 (§18.6)。
- 環境: GitHub Actions runner (nproc=4, emcc 6.0.12, gcc `-mavx2 -mfma`)。**`tools/m6/work` / `targets/*/work` は未展開**のため
  FA/KH/OTT の回帰 (`liftlib_e2e.sh` の (a)(b)(c)(f)) は**この run では未実施** (§18.6)。

### 18.1 結論

| 項目 | 着手前 | 本 run (実測) |
|---|---|---|
| `simd report` 未被覆 (効果/共通基盤/合算/host 込) | 1/1/2/2 (`pcmpistri` / `vinsertf128`) | **0/0/0/0** |
| `simd test` mismatch | 0 (192 mnemonic / 281 form / 95,400 vec) | **0** (223 mnemonic / 347 form / 182,400 vec: exact 181,895 / approx_ok 505) |
| ymm(i256) 形の helper | 未対応 (stub = trap) | **生成 + 実機突合** (64 mnemonic・179 命令インスタンス) |
| `pcmpistri` | 未対応 | **imm8 全 128 値 × 2 形 (void / i32) = 256 命令インスタンスを実機突合 mismatch 0** |
| F2 xmm 戻り搬送 (OTT 実 DLL leaf 3 callee) | 検出器なし | 検出 3 callee / 11 ret → 搬送 9 → 残 2。注入 **9/9 検出** (偽陽性 0) |

### 18.2 ymm(i256) の ABI (wasm32 の実測に基づく)

C は `i256` を表現できないが、LLVM IR の i256 は wasm32 で **引数 = i64 ×4 に分割 / 戻り値 = sret (先頭 i32 引数)** に lower される
(`clang --target=wasm32-unknown-emscripten -S` の `.functype` で実測: `f (i32, i64×8) -> ()` ← `i256 f(i256, i256)`,
`h (i32, i64×6)` ← `i128 h(i128, i256)` は sret を持たず `i128` 戻りは別規約に注意)。
- `gen.py`: i256 引数は `u64 pN_0..pN_3` に平坦化し prologue で `Y` (= `struct{u64 q[4]}`) に束ねる。戻り値は C の `Y` 返し (wasm32 の C ABI は
  struct 戻りを sret にするので IR の i256 戻りと一致)。`liftlib_simd.h` に `Y`/`YLO`/`YHI`/`MKY`。
- 128bit レーン独立の packed 命令 (`YMM_LANEWISE` 62 mnemonic) は xmm 版 kernel を下位/上位に適用 (`Spec.lanes`)。レーン横断は個別実装:
  `vinsertf128` / `vextractf128` / `vperm2f128` / `vshufpd` (ymm 版は上位レーンが imm bit[3:2] を使う — 実機突合で判明し個別化)。
- **突合方法**: C は i256 を書けないので `simdtest.wasm_ir()` が **LLVM IR wrapper** (`load i256` → `call i256 @helper` → `store i256`) を生成し、
  emcc で C と一緒にリンクする。native 側は gcc inline asm (`v256` / `-mavx2`) の実 ymm 命令。ABI 不一致は mismatch として現れる (§18.4 NC2)。

### 18.3 pcmpistri

`liftlib_simd.h: ll_pcmpistr()` に SSE4.2 implicit-length 文字列比較の全 imm8 (要素幅 ub/uw/sb/sw × 集約 4 種 × 極性 4 種 × 出力 LSB/MSB) を実装。
RetDec は `void(i128,i128,i8)` と lift し ECX/EFLAGS を捨てる → **void 形は shadow global (`ll_pcmpistr_ecx` / `ll_pcmpistr_fl`)** に結果を残す
(フラグ消費は P1 系 pass が担う方針は不変。ECX/フラグを後続が読む配線は未実装 — §18.7)。`d` 形 (ECX を返す) も同一実装。
実機突合は ECX + EFLAGS[CF,ZF,SF,OF] (pushfq) を比較、imm8 0..127 全値。

### 18.4 ネガティブコントロール (1 件を壊して FAIL を確認)

| 検査 | 壊し方 | 結果 (`simd test --n 200`) |
|---|---|---|
| NC1 | `vinsertf128` の imm 解釈を反転 | **BAD 1 form** (mismatch 検出) |
| NC2 | i256 戻りの hi/lo 反転 (`MKY`) | mismatch **29,752** / bad_forms 56 (ABI・レーン順の破壊を検出) |
| NC3 | `pcmpistri` の極性 (negative) 処理を無効化 | mismatch **12,800** / bad_forms 2 |

### 18.5 F2 xmm 戻り搬送 (`f2.xmm_ret_scan` / `run_xmm_ret`)

- 検出: 機械語の**到達可能な全 ret で xmm0 が関数内定義** (`MFunc.ret_in_xmm0`、LIFTLIB-3) なのに、IR の `ret i64/i32` が leafabi の差した
  `%lf_<va>_t*` (xmm0 由来) でない callee。修復は `leafabi.run` (ret → xmm0 bits / call 直後の最初の xmm0 読み → call 戻り) を該当 callee に適用。
- 入力 (再現): OTT インストーラ (`plugins-ott` 素材) から `OTT_x64.dll` を 7z 展開し、`retdec-decompiler -m bin --select-ranges
  0x1801b4220-0x1801b4615,0x1801a9be0-0x1801aa193,0x1801aa1a0-0x1801aa378 -o leaf OTT_x64.dll` (実測 54 s) → `leaf.ll` (5 define)。
  `LL_XRET_LL=leaf.ll LL_XRET_DLL=OTT_x64.dll` を設定すると `inject-eval` と unit T17b が走る (未設定なら skip)。
- 実測 (定義: 1 件 = 1 ret 命令 / 1 callee = 1 define): 検出 **3 callee (exp 1801b4220 8 ret / tan kernel 1801aa1a0 2 ret / 1801b4610 1 ret) = 11 ret**
  → 搬送 **9 ret** (exp 7 + tan kernel 2) → 修復後も未搬送 **2 ret**。
- 注入評価 (`inject.eval_f2_xret`): 搬送済み 9 ret を `ret i64 0` に 1 件ずつ戻し scan が検出するか → **9/9 検出**。`inject-eval` 全体 RESULT
  `injected=9 detected=9 false_positive_on_clean=0` (この run は FA/KH/OTT 入力が無く xret のみ)。
- 残 2 ret (実測: `ret_unbound 2`, 機械語 VA で特定): (1) `function_1801b4220` の `ret` @`1801b4474` — 複数経路 (@1801b43db/43fb/4430 ほか) が
  `jmp 0x1801b4470` で合流する共有 ret で、xmm0 の到達定義が複数 (多定義 phi) のため leafabi の bind が値を 1 つに決められない
  (IR 側は `ret i64 %rax.0.reload`)。(2) `function_1801b4610` の `ret` @`1801b4614` — RetDec が関数全体を `ret i64 (xor 0,0)` 1 本に
  退化させており (機械語は `vpxor xmm0` + 合流先)、xmm0 の元値が IR に無い。どちらも「合流先 ret の多定義 xmm0」で LIFTLIB-4 の領域 phi 合成と同系 (**未解決表へ**)。
- `tan` 本体 `1801a9be0` は `ret_in_xmm0()` が False (entry/call の phi が ret に混ざる、LIFTLIB-4 §14.7 と同件) のため対象外。

### 18.6 検証 (実測秒・load average・並列数)

| 検証 | 結果 | real | load average (nproc=4) |
|---|---|---|---|
| `python3 -m liftlib simd test --n 200` (clean HEAD `8476a82`) | 223 mnemonic / 347 form / 182,400 vec: exact 181,895 / approx_ok 505 / **mismatch 0** | 5.8 秒 | 0.33 / 0.37 / 0.24 |
| `python3 -m liftlib simd report` | 未被覆 0/0/0/0 | — | — |
| `python3 -m liftlib inject-eval` (`LL_XRET_*` 設定) | injected 9 / detected 9 / false_positive 0 | — | — |
| unit T5 / T17a / T17b | 全 ok | — | — |
| 着手前ベースライン `simd test` (400d546) | 192 mnemonic / 281 form / 95,400 vec / mismatch 0 | 2.8 秒 | — |

**範囲外 (未実施・主張しない)**: `liftlib_e2e.sh` 全体 (FA 400/400・KH 366/366・OTT・leafspec) と unit T1〜T4/T6〜T15 — いずれも
`tools/m6/work`・`tools/targets/{freshair,kilohearts}/work`・`/home/ubuntu/work/...` の参照データが runner に無く実行できない (必要素材:
`work-m11` 等では代替不可、`liftlib` 用の work スナップショットが R2 allowlist に無い → §18.7)。`gen.py` の変更は i256/pcmpistri を含む宣言だけに
効く分岐で、既存形の生成コードは不変 (`simd test` の既存 477 命令インスタンスが全て mismatch 0 で維持) だが、FA/KH/OTT の実 IR での
回帰は**未確認**。
liftdiff の 4 スナップショット (`ir_instr.ll`) の declare で C 生成 → emcc コンパイルを試行: `ott_old` は 156/156 生成・emcc OK、`m11*` 4 本は
**未知型 (`?` 型: cpuid / rep_movsq 等) の stub が `void` 変数宣言で emcc 失敗** (既存 stub 経路の欠陥、本 #241 の範囲外・§18.7)。

### 18.7 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| FA/KH/OTT 回帰 (`liftlib_e2e.sh`) を本変更で再実行できていない | gen.py/kernels.py の変更が既存実 IR に無影響である確証が無い | **新規子チケット (親 #50): liftlib 用 work スナップショットを R2 allowlist (`prepare-event-context.sh`, #293) に追加 → 回帰を再実行** |
| `pcmpistri` の ECX/フラグを後続命令へ配線 (void 形は shadow global に残すのみ) | KH/OTT の実 IR で pcmpistri 結果を消費する経路は未接続 | 新規子チケット (P1 系 pass の flags 配線) |
| F2 xmm 戻り 残 2 ret (合流先 ret の多定義 xmm0 phi: 1801b4474 / 1801b4614) | 該当経路で xmm0 を返さない | 既存 #272 系 (領域 phi 合成) へコメント |
| F2 xmm 戻りのスタック引数・GPR 引数個数不一致 | issue 記載の F2 未対応面のうち本 run は xmm 戻りのみ | 新規子チケット |
| `gen.py` stub が未知型 (`?`) で `void` 変数宣言になり emcc 失敗 (m11 snapshot 4 本で実測) | 未知型を含む IR の helper 生成 | 新規子チケット |
| ymm 幅変更/レーン横断の命令 (vcvtdq2pd ymm・vpmovmskb ymm・vperm*d・vbroadcast*) は未実装 | Convolver / Filter Table の実 closure で必要になる可能性 | 親 #50 に提案 |

### 18.8 新類型行案 (DEFECTS.md 形式)

| 症状 (silent) | 根本原因 | 観測 (証拠) | 検出信号 | 修復 |
|---|---|---|---|---|
| xmm0 で結果を返す関数が `ret i64 <rax 側ゴミ>` に lift され caller に garbage が流れる | RetDec は戻りレジスタを rax/xmm0 で区別せず `ret i64` に一律化 | OTT exp 1801b4220: 8 ret 中 8 が未搬送 / tan kernel 2/2 | 機械語の全 ret で xmm0 が関数内定義かつ IR の ret が xmm0 由来でない | `f2.run_xmm_ret` → `leafabi.run` |
| ymm 引数を C helper の `u128` 2 個と誤宣言すると wasm ABI がずれ上位レーンが落ちる | wasm32 は i256 を i64×4 に分割し戻りは sret | 本 run NC2 (レーン順反転で mismatch 29,752) | helper 署名と IR declare の i256 数の不一致 | `gen._params` (u64×4 平坦化 + Y 戻り) |
