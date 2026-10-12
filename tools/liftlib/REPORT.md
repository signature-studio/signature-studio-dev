# liftlib REPORT — 共通 lift 修復基盤の統合 (CAB-49 / CAB-54 / CAB-55 / CAB-220 / CAB-239 / LIFTLIB-2)

> 正本: `tools/liftlib/REPORT.md`。
> **行数目安**: 本ファイルは 250 行を超過 (`docs/DOC_MAP.md` §1 の上限ルール参照)。
> 超過分は Git 履歴に残る形での分割移動を推奨 (**内容は削除しない**)。

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

**CAB-239 追加 (§11)**: mini-lifter 語彙 9 系統拡張 — OTT 落下分岐の再構成 **5 → 19**, 理由付き残留 **47 → 30**。
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

## 10. lowbase 取り込み (CAB-220, 2026-10-10)

**結論**: `bash tools/liftlib/lowbase_e2e.sh` = **ALL PASS**。OTT を liftlib pipeline 内で「最初から」低位 base 生成でき,
2 base (0x10000 / 0x1230000) とも元 m10 成果物 (864MiB / 0x30000000) と **出力 SHA 42/42 bit 一致** (census 同値, [0x248]=0/1 両方)。
既定 (0x30000000) の回帰は IR 7 段テキスト一致 + outhash 42/42 を維持。x64c の native bit 一致 3 構成 150,708 cell も再現
(`tools/hostbridge/lowbase/lowbase_e2e.sh` も ALL PASS で CAB-90 成果物水準を再確認)。

| 項目 | 結果 (実測) |
|---|---|
| dataimage.py フィルタ修正 | `0x400000 <= nt` (補正後の妥当域) → **`img.base <= v < img.base + SizeOfImage`** (元値側の image 範囲, lowbase `lb_data_gen.py` 同規約)。旧条件は LB_BASE=0x10000 で **.rdata DIR64 12,329 件全件** (nt=0x10000+RVA は常に <0x400000) を黙って落としていた (T7 で実測) |
| LB_BASE 引数統一 | `ott --lb-base N` 1 値で駆動: `remap.shift_va(newbase)` / `gdata_legacy(datab)` / `m6_full_extract --newbase` / `ir7_argpass_fixed --shift` (既存 CLI) / `ir9_bootstraps --newbase` / `dataimage va_base`。shift の maxv は lowbase 時 `img.base+SizeOfImage` から導出 |
| lb_layout 共有化 | `liftlib/lb_layout.py` 新設 (lowbase 正本の取り込み。T8 が両者の同一性を検査)。legacy (0x30000000) レイアウトも LB_* 変数で表現し emcc フラグ生成を 1 本化 (`resolve_layout`) |
| C ランタイム | `runtime_lb.py` が m6_rt.c (`M6base` + **d2750 memcpy 範囲ガード** 追加) / m8_rt.c (`M8BASE` + 上限) / m6_stubs_hand.c (直値 4 箇所) / m10_boot.c (`MSCR` 静的配列化) を `#ifndef LB_IMG_BASE / LB_MAX_MEM` 付きで work へマクロ化コピー (T9, 置換数 assert 付き) |
| emcc | legacy: 旧フラグ完全維持 (`-Wl,--initial-memory=0x36000000`) / lowbase: `-sGLOBAL_BASE/-sINITIAL_MEMORY/-sMAXIMUM_MEMORY` + `-DLB_IMG_BASE/-DLB_MAX_MEM` (`-Wl,--initial-memory` は emscripten initial-heap 16MiB 加算で "too small")。init_mib は GLOBAL_BASE+stack 8MB から自動算出 (0x1230000 で wasm-ld required 実測 31,089,728B) |
| ott --lb-base 0x10000 | checks 7/0, band 係数 maxdev 0.0/nbad 0, trap rc 0, **outhash 42/42 equal**, census[0x248]=0 は `tools/ott/REPORT.md` §2.3 の旧 chain 行 = m10 同値。layout: base 0x10000 / arena 0x320000 / GLOBAL_BASE 0x420000 / initial 24MiB / max 64MiB |
| ott --lb-base 0x1230000 | 同じく checks 7/0 + outhash 42/42 (base 依存バグ無しの証拠)。initial 39MiB |
| audit_va.py 0x10000 | DIR64 13,000 全て image 内 (image 外 0) / IAT 375 slot の VA 保持 0 / base 64KiB 境界 → exit 0 |
| x64c 3 構成再現 | 0x10000/16MiB, 0x1230000/40MiB, 0x10000/8MiB の各 89 scenario 全 cell — **3 構成とも bit 一致 (max_ulp 0 / state_diff 0)**。cell 総数の正本は `tools/ott/REPORT.md` §2 |
| lowbase_e2e (hostbridge) | ALL PASS: 検収 65/65 (evidence 21+stub 3+marshal 13+PoC 28), 同居 512/512×2, Chrome Worker, prefix 差 0, E3 切り分け差 0 |

### 発見と修正 (lowbase 化で顕在化したもの)
1. **m6_rt.c d2750 (memcpy dispatch) に dst/src の上限が無い**: c38c8 family 系 junk 経路 (実測 dst=0xffffffff / src=-1 / n≈4.9MB) が
   864MiB では先行する fail-fast abort (missing function_1801baef8) のおかげで到達せず, 小 memory では OOB trap した。
   `dst/src + n <= LB_MAX_MEM` ガードを追加 (範囲外は no-op — m10 検収 trap10 の要求は「OOB 不発」のみ)。legacy では全 valid
   pointer が範囲内ゆえ挙動不変 (回帰 outhash 42/42 で確認)。既存 lowbase RetDec 成果物 (build_m10_lb.sh 産) の同系経路も
   OOB を確認 — trap probe を低 memory で走らせたのは liftlib 側が初めてのため顕在化した。
2. **e2e ハーネスの detached ArrayBuffer**: ALLOW_MEMORY_GROWTH の memory.grow 後に HEAPU8/DataView が detach
   (legacy は 864MiB で grow しないため未発覚)。全エクスポート呼出後にビューを張り直すよう修正 (e2e_check/outhash/coefdump)。

### icall (integration.md §B) について
`tools/icall/integration/liftlib_icall.patch` は **未適用のまま** (適用は CAB-228)。関数名は元 VA のままなので
icall_rewrite の名前解決は低 base 化の影響を受けない。関数ポインタ値 (newbase+RVA) を引く逆変換テーブルは適用時に対応。

### 再現
```sh
bash tools/liftlib/lowbase_e2e.sh            # 本チケットの 1 コマンド検証 (--full で CAB-90 e2e 全体も追加)
python3 -m liftlib ott --lb-base 0x10000     # 単体 (cwd=tools/liftlib)
python3 -m liftlib ott                       # 既定 (0x30000000) の回帰 = IR 7 段一致 + outhash 42/42
```

### 未解決
- lowbase RetDec chain の junk 経路は stack/heap 絶対位置依存が残る (lowbase REPORT §4.3 と同質)。本検証の範囲
  ([0x248]=0/1 × 2 rep × 256f) では差分 0 だったが、500blk 級の長時間 run では junk-tiny 差が出る可能性 (低 base REPORT 実測 2/128,000 cell)。
- liftlib lowbase の OOB ガードは c38c8 family の broken-lift を修復するものでなく no-op 化 (恒久修復は §7-1/§9-4 の mini-lifter 拡張)。

## 11. mini-lifter 語彙拡張 + OTT leaf native spec (CAB-239)

**結論**: 語彙 9 系統を拡張し OTT 落下分岐の再構成 **5 → 19**・理由付き残留 **47 → 30** (auto f7,p1 で
checks 7/0・band maxdev 0・trap 0 維持, junk census junkHi **175 → 104**)。leaf native spec (`leafspec`
コマンド) を新設し **exp leaf 40/40 bit-exact**, log 32/40 (残 8 は native 側 CRT 経路 crash = 除外計上)。
tan / SVF / f32変換は不一致 — 原因を断片レベルで特定。過程で liftlib 本体の欠陥 3 件 (base A7 メタデータ
のカンマ落ち / gdata 表サイズ / f2 v128 引数の wasm ABI) を発見・修正。

### 11.1 新語彙と実測 (stats 実測: sites 89 = branch 33 [rewired 30 + orient 未解決 3] + dropped 49 [reconstructed 19 + unsupported 30] + consumer 4)
| 語彙 | 内容 | 実測 |
|---|---|---|
| bind 定数 def 合成 | xor/sub 自己ゼロ化・mov/movabs 即値 def を IR 無しで合成 (call 跨ぎ callee-saved) | r15 ×10 + rbx ×1 解消 |
| rsp slot | `movsd [rsp+off], xmm` を head block の alloca 経由で受渡 (RetDec store/load-form 規約と整合) | addr base rsp ×6 解消 |
| 断片内 call | declare 駆動。第5引数以降 = [rsp+0x20+8i] (callee 側スタック引数)。post-call xmm0 = 戻り bits。F6 thread 用に直前 movsd(i64)→i128 marker | 断片 11 site のうち 6 解消 (vocab_call 4) |
| 整数フラグ | cmp/test+jcc (u/s) + setcc + cmovcc を flag 状態追跡で IR 化。rcr は CF 出力 = 旧 bit0 (ZF 保存) を伝搬 | tan poly の ja/seta/inc/rcr 連鎖 (int_jcc 2, rot 2) |
| GPR load/ALU/movabs/shift | mov r,[m], or/and/xor/add/sub/inc/dec, shr/sar/shl | mov r8d,[rip]・or eax・movabs 解消 |
| extract/lea/cvtsi, 断片内 ret, region br 重複回避 | movd/movq 抽出・lea・cvttsd2si / ret (rax 仮置き) / 再構成済み br の再取り上げ禁止 | lea 2 ほか・exp return 経路・支配破壊防止 |

残留 30 の内訳: region join (木でない断片) 8 / 多定義 bind (phi 合成要) 9 / reg2mem carry 4 / 入口 xmm
未引数化 5 / 間接 call 1 / 他 3。unit test T10 が再構成数と語彙発動を固定。

### 11.2 auto f7,p1 の census 影響 (junk 減少) と SHA
census[0x248]=0: zero 132 / normal 69→**140** / junkHi **175→104** / junkTiny 136, absmax 1.67e20→1.67e18。
census[0x248]=1: 4/254/252/2 → 4/259/248/1。checks 7/0・maxdev 0.0・trap rc 0 は維持。
**[0x248]=0 出力 SHA は m10 と不一致になる** (改善由来の変化)。SHA 突合は auto 無し (m10 再現) モードで継続。

### 11.3 OTT leaf native spec (`leafspec`, 新設)
`targets/ott_leaf.json` (roots {SVF reset, exp, log, tan, sqrt 系, f32変換} の call closure 71 関数) → base →
f2 (closure 限定) → P1 (新語彙) → **leafabi** → gdata(all+表 pad) → emcc → 実機機械語 (native_runner:
ImageBase に VA 敷設・MS x64 ABI 直接実行) と乱数 scenario で bit 突合。**xmm0 戻り**: leafabi が各 `ret`
の xmm0 到達定義を bind し `ret i64 (trunc i128 …)` に差替 (40 ret)。加えて RX: ret_xmm0 callee の call
直後の最初の xmm0 読みを call 戻りへ差替 (29 site — RetDec が call 後も呼出前 SSA を流用する欠落の修復)。
native R 行 xmm0 列 ↔ wasm 戻りを `ret_from_xmm0` spec で突合。ハーネス制約: ① IAT/CRT 経路は native
crash → シナリオ除外 (実測 log 8/40・cvt 23/40 — bits 系入力が CRT 報告経路 d2750 `jmp *rax` に入る)。
② wasm xmm0 戻りは未差替 ret では rax のまま。③ NaN/Inf は spec で除外。④ 入口 callee-saved/xmm4-15 は 0 初期化を仮定 (runner が gp/xmm 独立カウントで zero)。
| leaf | 40 scenario | 判定 |
|---|---|---|
| exp 1801b4220 | **40/40 bit-exact** | ✅ |
| log 1801b4900 | 32/40 + crash 8 | 一致行は完全一致 |
| tan poly 1801a9be0 | 1/40 | region join @1801a9dfa 未修復 + 入口 3 引数 (実体 xmm0 1 引数) の誤解析 |
| SVF reset 180126040 | 2/40 + crash 8 | tan 依存の係数に波及 |
| f32変換 1801bc890 | 4/40 + crash 23 + trap 13 | cmov 連鎖の多定義 phi 合成未実装 (bind rcx ×4) |

e2e の gate は spec の `expect_match_min` (crash を除く一致率) のみ適用 (exp 1.0 / log 0.9。tan/SVF/変換は測定対象)。

**発見と修正 (leaf spec 構築中に顕在化)**
1. **base A7**: メタデータ除去が区切りカンマを食み `) !insn.addr` 形を残し clang パースエラー
   (`x, !range !N, !insn.addr !M` → `x !insn.addr !M`)。値参照を ` +![\w.\-]+` で止めて修正
   (!range を含む OTT 系 IR で発生。FA/KH は !range 無しで未発覚)。
2. **gdata 表サイズ**: RetDec は表アクセスを `ptrtoint(@global)+idx*scale` で lift するが gdata は宣言型
   (i64=8B) でしか埋めず, 索引が宣言外の隣接データ (表の続き) を踏む。`gdata_pad=True` (leaf cfg のみ)
   で表 base を次 global VA まで実データ拡張 → **exp 0/40 → 40/40**。既定 False (FA/KH/OTT legacy 不変)。
3. **f2 v128 引数**: 入口 xmm live-in の v128 判定が i128 引数になり wasm ABI (2 個 lower) と不一致。
   movq/movd/movmsk 抽出を f64/f32 bits に分類し v128 も下位 64bit で受ける。call site 側も型別 cast。

### 11.4 CAB-238 / CAB-240 との境界と次タスク
- **CAB-238 (auto 既定化)**: auto 時は census 改善 (junkHi −71) の一方で m10 参照 SHA と不一致になる
  (改善由来)。検収は checks 7/0 + maxdev 0 + trap 0 + census 改善で行い, SHA 突合は auto 無しモードを継続。
- **CAB-240 (ymm ABI)**: 本チケットでは i256/ymm 未触 (`__asm_vmovdqu__yy` 3 種のまま)。断片語彙も
  VEX-256 未対応 (vfmadd 系巨大断片は次チケット候補)。
- 限界: 多定義 phi 合成未実装 (×9)。setcc/flag の上書き幅 zext 仮定。RX は同 block 読みに限定。
  leaf native は CRT 経路で crash (tools/ott/native の IAT thunk 方式で吸収可 — 読取のみのため未統合)。
- 次タスク: ① phi 合成 (tan/cvt が通る見込み) ② leafabi 方式の SVF 経路適用 (m9 C port からの置換)
  ③ leafspec の crash scenario 自動除外 ④ CAB-238 検収条件の策定。

## 12. LIFTLIB-2 (CAB-256) — 領域 DAG の phi 合成 + CAB-238 無限ルーブ修復

**結論**: ① OTT 既定ビルドの **無限ルーブを修復** (CAB-238 §6 の 2 combo が `rc=124` → `rc=0`)。
② 領域リフトを DAG 化する phi 合成で **多定義 bind の残留 9 → 4 / region join 8 → 0**,
**脱落分岐の再構成 19 → 25・理由付き残留 30 → 21** (LIFTLIB-2 着地で既定ビルドが初めて build 通過も達成)。
③ e2e gate を **param 0.0/0.1/0.9/1.0 の sweep + ハード timeout** に拡張 (CAB-238 提案④)。
④ 回帰すべて緑 (`liftlib_e2e.sh` ALL PASS / `ott_e2e.sh` 89 scenario 全 cell bit-exact・正本 `tools/ott/REPORT.md`)。

### 12.1 無限ルーブの原因と修復 (CAB-238 §6)

| 項目 | 実測 |
|---|---|
| 現象 | 既定 (`python3 -m liftlib ott` = auto f7,p1) で params=0.9 / [0x248]=1 / amp=0.0,1.0 の 2 combo が `processReplacing` で停止 (60 s timeout で HANG, CPU 100%) |
| bisect | `work/hang_bisect.py` を 25 再構成 site 単体で実行 → **HANG は `p1_one_18012024b` のみ** (他 24 site は完走)。`1801204b9` (CAB-238 snapshot 側) は本ツリーでは別 site に吸収され未再構成 |
| 機械語 | `0x18012024b jbe 0x180120336` — 脱落側入口 **D = 0x180120336** が *head block 自身の IR ラベル* (`dec_label_pc_180120336`: RetDec が 0x1801200f3..0x18012034d を 1 ブロックにマージし末尾 VA をラベルにしたもの)。collect() が D を出口と見なして `br label %dec_label_pc_180120336` (= head 自身) を張ったため **自己辺** になり永久ループ |

**修復 (3 点)**:
1. **join split**: D の IR ラベルが head 自身のとき, tail を「D の機械語コードの始点」で割り
   〔生存側尾部 (FALSE) / 合流点 (join)〕の 2 block にする。脱落側 relay の行き先を **合流点 block** に
   変更 (head 自身ではない) → 自己辺が消える。実測 2 site (`18011ffdd` / `18012024b`) が対象。
2. **join merge (phi)**: 合流点が「生存側尾部で定義した値」を読む場合 (ここでは `movaps xmm0, xmm14` =
   jcc の FALSE 側のみの def), 脱落側経路では実行されないので reg2mem 合成
   (入口 alloca + 各 pred 終端 store + 合流点 load) でマージ。脱落側の値は **分岐点 J** (D でなく) で
   bind する (D で bind すると生存側尾部の def を拾ってしまう)。実測 merge 1 件/site。
3. **安全網**: `dlabel` が head 自身のラベルになったら `Unsupported` (IR 無改変)。
   同じ形が別条件で現れても無限ループを出さない。

同じ scope で入れた IR 健全性対策 (clang `does not dominate all uses` 防止):
- **値の支配検証** (`Region._checked` / `_value_ok`): 領域 block が参照する値は (a) head 分割点より前,
  (b) head を支配する block, (c) 自領域内で定義 block が使用 block を支配する — のいずれかに限る。
  非支配/他 site 領域の値 (`%p1r_<va>_<salt>_…`) は候補から外し次の fallback に回す。
- **alloca load の再発行** (`_reissue_load`): 非支配だった reg2mem load は「使用点で load し直す」。
- **多定義 bind のフィルタ** (`_resolve_multi`): IR 値を持つ def が非支配/他領域なら採用せず,
  cmov select 合成 / def 命令のローカル lift にフォールバック。
- **`_bind_call_ret`**: RetDec が `call i64 @function_1801b4220()` (exp) 等と lift する CRT 数学関数の
  i64 戻りを xmm0 ビット列として補う (F6 の C port 規約と同じ) — `bind xmm0` 失敗の主因。

### 12.2 phi 合成 (領域 DAG 化) の実測

| 指標 | CAB-239 (a137396) | LIFTLIB-2 本ブランチ | 差分 |
|---|---|---|---|
| P1 sites 内訳 | 89 = branch 33 (rewired 30) + dropped 49 (再構成 19 + unsupported 30) + consumer 4 | 89 = branch 33 (rewired 30) + dropped 52 (**再構成 25** + unsupported 21) + consumer 4 | 再構成 **+6** / 残留 **−9** |
| region join (残留理由) | 8 | **0** | DAG 化で解消 |
| 多定義 bind (phi 要) | 9 (rcx 5 / xmm5 2 / xmm1 2) | **4** (rcx 1 / xmm5 1 / xmm0 1 / xmm1 1) | phi 合成 + フォールバックで半減 |
| vocab (初発動含む) | — | `phi_join` 2, `bind_call_ret` 2, `join_merge_store` 2, `load_reissue` 1 | — |
| processReplacing 再構成 | 14 | 14 (region blocks 最大 19) | DAG で大断片も扱う |

残留 21 の理由分類 (実測, `work/tmp/dbg_reason.py`): bind xmm0 6 / bind xmm1 5 /
merge xmm2 (非支配・他領域) 4 / reg2mem 値消失 (`no value`) 2 / 間接 call 1 / region live-out 1 /
bind rcx 1 / bind xmm5 1。

### 12.3 OTT 既定ビルドの検収 (CAB-238 検収条件を m10 SHA 分離のまま確認)

| ゲート | 実測 | 判定 |
|---|---|---|
| checks / broken | **8 / 0** (E7 param sweep 追加で 7→8) | PASS |
| band 係数 maxdev / nbad | 0.0 / 0 | PASS |
| trap rc | 0 | PASS |
| census[0x248]=0 | 132 / 140 / **junkHi 104** / 136 / nan 0 / absmax 1.67e18 | 104 ≤ 104 OK |
| census[0x248]=1 | 4 / 259 / junkHi 248 / 1 / absmax 1.13e34 | (CAB-238 と同値) |
| **E7 param sweep** | 0.0/0.1/0.9/1.0 × [0x248]=0/1 の **8 combo すべて完走** (timeout 60 s) | PASS (無限ループ解消) |
| 旧既定 `--auto none` | checks 7/0, census は `tools/ott/REPORT.md` §2.3 の旧 chain 行, SHA 42/42, IR 一致 | PASS (継続) |
| link | signature mismatch 0 / undefined 46 / `undefined __asm_*` 0 | PASS |
| simd helper | 自動生成 159 本 (CAB-239 時 153) | — |

### 12.4 tan / SVF / f32変換 leaf の bit-exact 進捗 (LIFTLIB-2 本来 scope)

`leafspec` 実測 (各 40 scenario, native 実機械語オラクル):
| leaf | CAB-239 | LIFTLIB-2 | 差分 |
|---|---|---|---|
| exp 1801b4220 | 40/40 | **40/40** (mismatch 0 / crash 0) | 不変 |
| log 1801b4900 | 32/40 + crash 8 | **32/40** + crash 8 (一致行は完全一致) | 不変 |
| tan 1801a9be0 | 1/40 | 1/40 | 不変 (残因は下記) |
| SVF reset 180126040 | 2/40 + crash 8 | 2/40 + crash 8 | 不変 (tan 依存の波及) |
| f32変換 1801bc890 | 4/40 + crash 23 + trap 13 | **11/40** + crash 23 + trap 6 | match **+7**, trap **−7** |

読み取り: ① f32変換は phi 合成 (`bind_multi_eq` / `phi_join`) と load 再発行で **wasm trap 13 → 6**、
match +7 (region live-out に塞がれていた経路が通るようになった)。② 残 6 trap は CRT 経路 crash と同根
(`tools/ott/native` の IAT thunk 方式で吸収可 — 読取のみのため未統合)。
③ tan は **region join @1801a9dfa の再構成は DAG 化で解消したが**, 入口 3 引数 (実体 xmm0 1 引数) の
誤解析が別に残り match は不変 (CAB-256 ticket 記載の「tan 1/40」と一致)。
④ SVF は tan の係数への波及で不変 (CAB-239 から引き継ぎ)。phi 合成の直接効果は
**残留理由の region join 8 → 0** と f32変換の trap 減に現れている。

### 12.5 e2e gate 拡張 (CAB-238 提案④)

`liftlib/recipes/ott/e2e_check.mjs` に **E7 param sweep** を追加:
- param **0.5 固定を廃止**し, 0.0 / 0.1 / 0.9 / 1.0 × [0x248]=0/1 の 8 combo で
  `processReplacing` (2 rep) が完走することを確認。checks は 7 → **8**。
- 無限ループは `processReplacing` 内で停止するため JS 側 watchdog では中断できない。
  各 combo を **子プロセス (`spawnSync`, 既定 timeout 60 s, `OTT_SWEEP_TIMEOUT` で調整)** として
  実行し, timeout/非 0 exit を HANG として FAIL にする (`--sweep-child` モード)。
- 本 gate があれば CAB-238 §6 の無限ループは CI で自動検出される (修復前なら 2 combo が timeout)。

### 12.6 再現

```sh
# 無限ループの再発/解消確認 (読取のみの再現器, timeout 必須)
OTT_CJS=tools/liftlib/work/ott_auto_f7_p1/ott_gen.cjs V=0.9 F=1 A=0.0 timeout 60 \
  node tools/ott/f7eval/cab238_probe.mjs        # rc 0 / "DONE v=0.9 f=1 amp=0"
# 既定 (auto f7,p1): checks 8/0 + census 改善 + E7 sweep
python3 -m liftlib ott
# 旧既定 (m10 chain 再現): IR 一致 + SHA 42/42
python3 -m liftlib ott --auto none
# 1 コマンド回帰 (unit T1..T11 + FA 400/400 + KH 366/366 + OTT + SIMD 95,400 + 注入 94/94 + leafspec)
bash tools/liftlib/liftlib_e2e.sh
# x64c 参照 (liftlib 非依存): 89 scenario / 全 cell bit-exact (正本: tools/ott/REPORT.md)
bash tools/ott/ott_e2e.sh
# site 単体 bisect (LIFTLIB-2 追加): V=0.9/F=1 無限ループの切り分け
python3 tools/liftlib/work/hang_bisect.py p1_one_18012024b
```

### 12.7 限界と次タスク
- 残留 21 の主因は **`bind xmm0` (CRT 数学関数の xmm0 戻り)** 6 件 — `_bind_call_ret` は exp/log/tan 系の
  明示的 C port 名 (`function_1801b4220/4900/ba860`) のみ対象で, 汎用の「i64 戻り = xmm0 ビット列」推論は
  未実装 (誤代入の危険があるため)。次はここを落とすのが最も効果が大きい。
- leaf native の CRT 経路 crash (log 8 / SVF 8 / cvt 23) はオラクル側の IAT thunk 未整備が原因
  (tools/ott は読取のみのため統合していない)。cvt の残 6 trap も同根。
- CAB-240 (ymm/i256 ABI) は未触 (`__asm_vmovdqu__yy` 3 種)。VEX-256 断片語彙も未対応。
- 次タスク: ① 汎用 xmm0-ret bind (CRT/移植関数全体) ② leafabi 方式の SVF 経路適用
  ③ `tools/ott/native` の IAT thunk を liftlib 側 spec に取り込み CRT crash を解消 ④ CAB-240 (ymm ABI)。

## 13. LIFTLIB-3 (CAB-264) — 汎用 xmm0-ret bind + tan 入口誤解析修正

- 既知類型との関係: **該当なし** (`docs/DEFECTS.md` の D1a〜D16 は ucomis 誤配線/load 脱落/xmm 引数落ち/store 欠落等で, 本チケットで扱う「callee の戻り値レジスタ推定」と「entry 純 move の live-in 誤判定」は未登録 → REPORT 末に新類型行案を記載)
- 検証起点 commit: `ae18b1e` (clean HEAD から `git worktree` 展開で再現・下記の検証を全て再実行して確認)

### 13.1 結論

**汎用 xmm0-ret bind を leafabi/regbind/mc/f2 に実装し, 残留 dropped を 21 → 15 に, tan を 1/40 → 8/40 に改善した。回帰はすべて緑。** census[0x248]=1 の junkHi は **248 で不変** (低減せず、記録のみ)。

| 項目 | LIFTLIB-2 (61f1e4e) | LIFTLIB-3 (ae18b1e) | 差分 |
|---|---|---|---|
| OTT 既定 (`--auto f2,f7,p1`) p1 残留 UNSUPPORTED | 21 | **15** | −6 |
| その内 `bind xmm0` | 6 | **1** | −5 |
| leaf spec `tan` (0x1801a9be0) | 1/40 | **8/40** | +7 |
| leaf spec `exp` / `log` | 40/40 / 32/40+crash 8 | **40/40 / 32/40+crash 8** | 不変 |
| leaf spec `svf` / `cvt` | 2/40+crash 8 / 11/40+crash 23 | 2/40+crash 8 / 11/40+crash 23 | 不変 |
| census[0x248]=0 junkHi | 104 | **104** | 不変 |
| census[0x248]=1 junkHi | 248 | **248** | **不変 (低減せず)** |
| checks / trap / HANG | 8/0 / 0 / 0 | **8/0 / 0 / 0** | 不変 |

### 13.2 残留 21 の実原因 (LIFTLIB-2 の記載と実測が違った点)

LIFTLIB-2 §12.7 は「`_bind_call_ret` は明示的 C port 名のみ bind でき」と書いていたが, **実測では 6 件の `bind xmm0` は call 戻りではない**:

| site | 所在関数 | root_def | 実原因 |
|---|---|---|---|
| 0x1801aa157 / 0x1801aa1c9 | tan / 0x1801aa1a0 | **entry** | 入口 xmm0 の IR 値が無い (f2 未適用) |
| 0x1801b4e7b / 0x1801b5163 | 0x1801b4e30 | **entry** | 同上 |
| 0x1801b4bf3 | 0x1801b4e30 | **到達不能ブロック** | pdata 無し関数の範囲誤読 (孤立ブロック列) |
| 0x18011ff6f | 0x18011ec20 | multi (addsd/mulsd) | SSE 多定義 = 別要因 |

`_bind_call_ret` (p1) が関係するのは call 戻り site だけなので, これでは残留は減らない。**主因は「CRT leaf が入口 xmm を読むのに IR 側に `%xmmK_bits` 引数が無い」こと**。

### 13.3 実装した汎用規則

1. **`mc.MFunc._writes_at_all_ret(reg)` / `ret_in_xmm0()`**: 全 ret で xmm0 が関数内定義かを判定。**到達不能ブロックは除外**する (孤立ブロック列を「対象外」と誤判定しないため)。rax は見ない — `defs_before` は call を volatile として rax の def にするため, call 経路ではほぼ常に「rax = 関数内定義」になり誤認の元 (実測: log/tanf は実は xmm0 戻りなのに `ret_reg_raw()=="both"`).
2. **`regbind.Binder.callee_returns_xmm0(target)` / `xmm0_ret_of_call(va)`**: 上記を callee 側に適用。**命名規則 (関数名・C port 名) に依存しない**。
3. **`regbind.value_defined_at`**: call site の i64/i32 戻りを xmm0 bits として拾えるように (従来は明示名のみ)。
4. **`regbind._bind_multi`**: xmm0 が multi-def で, def のうち xmm0-ret callee への call が **1 個だけ** のとき、その call の i64 戻りを採用 (`function_1801aa1a0` を呼ぶ tan で発動)。
5. **`leafabi.run` の自動 callee_set 拡張**: cfg の `ret_xmm0` 明示リストに **加えて** `ret_in_xmm0()` を満たす define を自動追加。従来はリスト漏れ (tan の kernel `function_1801aa1a0`) が tan の戻り 0 を招いていた。
6. **`leafabi._ret_thread`**: 非支配値の弾き方 (`dominates_use`) を追加 (clang "does not dominate all uses") + 同一 ret VA を p1 が複製した block での一時名衝突を `fresh()` で回避 + i64/i32 bind (xmm0 bits の下位 64bit) を `zext` して受理。
7. **`p1._call_ret_bits`**: callee 選定を `callee_returns_xmm0()` に変更 (旧: `function_1801b{4220,4900,ba860}` の name match)。`m9_d*` の OTT C port 名も併用。
8. **`f2.classify_kind`**: **dest のみを書く move (`movsd xmm1, xmm0`) は dest の旧値を消費しない**ので entry-live-in から除外。capstone の `regs_access` は dest も read と報告するため, 従来は tan が xmm1 も仮引数と誤判定していた (実体は xmm0 1 引数)。`movq xmm0, xmm0` (dest == src = 上位 zero 化の恒等) は旧値を使うので除外しない。
9. **`f2.find_undef_for`**: 同一 alloca の load が複数 undef になっていると「どれがその reg の値か」が曖昧 (tan は xmm0 も xmm1 も同じ undef に解決)。**機械語順で最も早い reader アドレスで使われている undef** を選ぶように変更。
10. **`recipes/ott.py` + `cli.py`**: `--auto` 既定を `f7,p1` → **`f2,f7,p1`** に。f2 は **callee 相のみ** (引数付与) を p1 の前に流す。callsite 相は recipe 側の名前依存 wiring (m9_d* C port) と衝突するため既定では入れない (`--auto f2` 指定時は両相)。
11. **`harness/wasm_runner.mjs`**: spec args の wasm 引数マッピングを **位置対応から ABI 分割対応** に (native_runner と同じ規約)。f32/f64 の A 行は xmm 仮引数 (`%xmmK_bits`), それ以外は gpr 仮引数 (`%argN`)。従来は位置対応だったため tan の f64 が余分な `%arg1` に入り `%xmm0_bits` が 0 になっていた (**tan 1/40 の直接原因**)。

### 13.4 数え方の定義・再計算 (規則 36・37)

`python3 tools/liftlib/xmm0_ret_census.py` (1 コマンド再現) を同梱:
- 分母 = RetDec raw `.ll` の module に define がある `function_<hex>` で image 内に範囲があるもの = **169**
- 検出 = そのうち「到達可能な全 ret で xmm0 が関数内定義」= **103**
- **別アルゴリズム**「ENTRY→ret の xmm0 未書経路が存在しない」で検算 = **103 (一致)**。実装は向きが逆 (不在判定 vs 存在判定) で完全に別コード。

残留内訳の再計算は `work/tmp/dbg_reason.py` (p1 単体) と同スクリプトに f2 callee 相を足した T13 (unit test) で固定。

### 13.5 ネガティブコントロール (規則 41)

| 検査 | 対象 | 結果 |
|---|---|---|
| `LL_NO_XMM0_RET_AUTO=1` (leafabi 自動 callee_set 拡張を停止) | leafspec tan | **8/40 → 1/40** (FAIL) 。exp は 40/40 のまま = 拡張のみが効いている証拠 |

### 13.6 検証 (実測秒・load average・並列数)

| 検証 | 内容 | 所要 (real) | 終了時 load average (nproc=16) |
|---|---|---|---|
| `bash liftlib_e2e.sh` (clean HEAD: `ae18b1e`) | unit T1..T14 + FA 400/400 + KH 366/366 + OTT 既定/旧既定 + SIMD 95,400 + 注入 94/94 + leafspec | **115 秒** (10:28:19 → 10:30:14) | 10.25 / 5.22 / 4.75 |
| `python3 tests/test_unit.py` (clean HEAD) | T1..T14 (T13 = f2→p1 残留, T14 = xmm0-ret 検出と別アルゴリズム一致) | 同 e2e 内 | 同上 |
| `python3 xmm0_ret_census.py` (clean HEAD) | 103/169 + 別アルゴリズム一致 | 同 e2e 内 | 同上 |
| `bash tools/ott/ott_e2e.sh` | 89 scenario / 全 cell bit-exact / E7 8 combo / OTT 既定 checks 8/0 | 前掲 (読取のみ・正本 `tools/ott/REPORT.md`) | — |
| `python3 -m liftlib ott` (develop 側) | checks 8/0・junkHi 104/248・trap 0・RESULT PASS | 10 秒 | — |

### 13.7 未解決 (起票先付き・規則 42)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 残留 15 の内訳: `bind xmm1` 5 / `merge xmm2` (非支配・他領域) 4 / `no value` 2 / 間接 call 1 / `bind xmm0` 1 / `bind xmm5` 1 | OTT 既定ビルドの未修復 dropped 分岐 | (b) 新規子チケット (CAB-49 下) を起票 — 次タスク |
| leaf native CRT 経路 crash (log 8/40 / SVF 8/40 / cvt 23/40) | leafspec の crash 除外 (tools/ott 読取制約) | (a) CAB-256 にコメント済 (LIFTLIB-2 §12.7 から継続) |
| tan の残 32/40 (region 内 phi 合成・cvt 依存) | tan の bit-exact は 8/40 止まり | 上記新規子チケット |
| IAT thunk spec (tools/ott/native 方式) の liftlib 統合 | CRT crash を解消できる | (c) 親チケット CAB-49 に提案コメント |
| CAB-240 ymm(i256) ABI | `__asm_vmovdqu__yy` 3 種 | (a) CAB-240 は既存 (Backlog)。本チケットでは未触のため重複起票はしない |

### 13.8 新類型行案 (DEFECTS.md 形式・規則 44)

| 症状 (silent) | 根本原因 | 観測 (証拠) | 検出信号 | 修復 |
|---|---|---|---|---|
| callee の i64 戻りが xmm0 (double bits) なのに整数と解釈して bind 失敗 | capstone2llvmir は結果レジスタの区別 (rax/xmm0) を落とし `call i64 @f()` に一律化。LIFTLIB-2 は OTT 固有名 (`function_1801b4220/4900/ba860`) で回避 | OTT 既定 p1 の `bind xmm0` 6 件 (うち 5 件は実は entry xmm0 で原因は別) / leafspec tan 1/40 | 機械語の全 ret で xmm0 が関数内定義か | `MFunc._writes_at_all_ret` + `Binder.callee_returns_xmm0` (命名非依存) |
| entry live-in の誤判定: `movsd xmm1, xmm0` の dest (xmm1) を read と数えてスカラー引数を余分に仮引数化 | capstone `regs_access` は dest のみ書く move について dest も read と報告 (MS ABI では上部 lane 保存のため実機では正しいが xmm1 の旧値は消費されない) | tan 定義が `(arg1,arg2,arg3,xmm0_bits,xmm1_bits)` の 5 引数 (実体 xmm0 1 引数) → wasm は `%xmm0_bits=0` で自明解を返す | entry-live-in 読取のうち dest のみ書く move の件数 | `f2.classify_kind` の純 move 除外 (dest == src は除外しない) + `find_undef_for` の最早 reader 選択 |
| 同一未初期化 alloca の load が複数 undef になり, xmm 仮引数の undef 対応が恒等的でない | RetDec reg2mem の全 load が同一 alloca を指し, f2 は「どれがその reg の値か」を無視して先頭を拾う | tan: xmm0 と xmm1 が同一 undef `%5` に解決 (実読取は xmm0 = `%6`) | 同一 undef を 2 レジスタが参照 | 機械語順で最も早い reader アドレスの undef を選ぶ |

## 14. LIFTLIB-4 (CAB-272) — leaf region の phi 合成 (残 15 → 6)

- 既知類型との関係: **該当なし** (`DEFECTS.md` D1a〜D16 と `icall §4` の別体系とも未登録。新類型行案を末に記載)
- 検証起点 commit: `fcaaf5f`。clean HEAD を `git archive` で展開し T1..T15 + e2e を再実行して確認 (下記 §14.6)

### 14.1 結論

**OTT 既定 p1 の残留 UNSUPPORTED 15 → 6** (再構成 31 → 34)。**tan 8/40 → 11/40**。exp 40/40・log 32/40 維持。census junkHi 104/248・checks 8/0・trap 0・HANG 0・ott_e2e 全 cell bit-exact すべて不変。回帰 ALL PASS。

| 項目 | LIFTLIB-3 (5bad530) | LIFTLIB-4 (fcaaf5f) | 差分 |
|---|---|---|---|
| p1 残留 UNSUPPORTED | 15 | **6** | −9 |
| うち `bind xmm1` | 5 | **1** | −4 |
| うち `merge xmm2` (非支配・他領域) | 4 | **0** | −4 |
| うち `bind xmm0` | 1 | **0** | −1 |
| `no value` | 2 | 2 | 不変 |
| 間接 call / `and rax [rip]` / `bind xmm5` | 1/0/1 | 1/1/1 | — |
| leafspec **tan** | 8/40 | **11/40** | +3 |
| leafspec exp / log | 40/40 / 32/40+crash 8 | 40/40 / 32/40+crash 8 | 不変 |
| census[0x248]=0 / =1 junkHi | 104 / 248 | **104 / 248** | 不変 |
| checks / trap / HANG | 8/0 / 0 / 0 | 8/0 / 0 / 0 | 不変 |

残 6 の内訳: `no value for %storemerge*.in.reg2mem` 2 / 間接 call (`call qword ptr [rax+0xe0]`) 1 / `bind xmm1 @1801a9da0` (tan) 1 / `and rax, qword ptr [rip+0x6443f]` (log) 1 / `bind xmm5 @1801bd172` (cvt) 1。

### 14.2 数え方の定義・再計算 (規則 36・37)

`python3 tools/liftlib/p1_residual_census.py` (コミット済み・1 コマンド):
- 母集合 = `tools/m6/work/ott.drc.ll` を base 正規化した module の `function_<hex>` define で `img.func_at` が解決できるもの
- 適用順 = **既定 `--auto` と同じ** (f2 callee 相 → f7 → p1)。f2 は callee 相のみ
- 1 件 = `p1.run_function` の 1 回の `UNSUPPORTED`。理由は `@<addr>` → `@X`・SSA 名 → `%V` に潰して集計
- `--json` で機械可読 (T15 の再計算に使用)

T15 (unit test) がこの数値とネガティブコントロールを自動固定する。

### 14.3 実装 — 残 15 の原因は 3 つ (全て LIFTLIB-2/3 の実装バグ)

1. **`regbind.value_defined_at` が同一アドレルの IR 命令の「末尾」を拾っていた** (`bind xmm1` 5 のうち 3)。p1 は領域を再構成すると**同一機械語アドレスに IR 命令が 2 本**できる (原本 block の `%N` と領域 block の `%p1r_…`)。従来は末尾 = 領域側を拾うため, 別経路の経路固有 SSA を参照して非支配 (clang "does not dominate all uses")。→ **原本 (非領域) を優先** するようにした。領域 block の判別は **ラベルではなく dst の SSA 名** (`%p1r_` / `%p1tail_` / `%p1relay_` / `%p1srelay_`) で行う (領域 block のラベルは `dec_label_pc_<va>` で原本と区別できない)。
2. **`Region._value_ok` が領域値の名前に埋めた VA を「値の機械語 VA」と誤認していた** (`merge xmm2` 4 と `bind xmm0/xmm1` の残り)。`%p1r_<va>_<salt>_<tag><n>` の `<va>` は **タグ** であって def の VA ではない (relay 値は他所の VA をタグに使う)。`self.mf.block_of(dva)` はので実際には別ブロックになり、正当な自領域値を「非支配」と誤判定していた。→ `self.vdb` (`nm()` で定義 block を記録) で判定するようにした。同時に `merge_in` が合成値を `nm()` する時点で `cur_va` が未設定 (前ブロックのまま) だったので `run()` で先にセットするよう修正。
3. **他領域値を一律拒否していた**。`P1R_NAME` の salt が違うと即False にしていたが、`_dom_func` (関数全体の機械語ブロック支配) でその領域の入口が use を支配するなら合法だった。→ IR レベル (`ix.dominates(dbi, head_bi)`) + 機械語レベル (`_dom_func`) の両方で判定する `_dom_func` を新設 (cache 付き)。

副次修正:
- **`_reissue_load` の値が兄弟 relay block で非支配になる不具合**を修正 (LIFTLIB-3 から潜んでいた)。`emit_merge_stores` は 1 終点ごとに新規 relay block を作るが、或る pred の終端前に挿入した load を別の relay から store すると非支配 → `self.vdbld` に (alloca, ty) を覚えておき `_for_block` で **その relay 自身でもう一度 load** する。
- **`leafabi._ret_thread` が別領域コピーを拾って ret threading を落としていた** (tan 8/40 の一因)。`candidates_at()` (同アドレスの全候補) を追加し、**その ret block を支配する候補**を選ぶようにした → tan 8 → 11。
- `Region.nm()` が `vdb` を記録するようにした (LIFTLIB-2/3 の補助)。

### 14.4 ネガティブコントロール (規則 41)

| 検査 | 対象 | 結果 |
|---|---|---|
| `LL_NO_ORIG_PREF=1` (原本優先 bind を停止) | 残留 | **6 → 9** (`bind xmm1` 1 → 4) |
| `LL_NO_VDB_DOM=1` (vdb 支配判定を停止、旧タグ誤認に戻す) | 残留 | **6 → 14** (`merge xmm2` 0 → 6, `bind xmm0` 0 → 1, `bind xmm1` 1 → 2) |
| 両方 OFF | 残留 | **15** (= LIFTLIB-4 着手前) |

どちらの switch も効いており、個別効果が測定できている。

### 14.5 検証 (実測秒・load average・並列数)

| 検証 | 内容 | real | 終了時 load average (nproc=16) |
|---|---|---|---|
| `python3 tests/test_unit.py` (clean HEAD `fcaaf5f`) | T1..T15 | e2e 内 | 4.48, 4.20, 3.96 |
| `python3 p1_residual_census.py` (clean HEAD) | 残留 6 内訳の再計算 | 数秒 | — |
| `bash liftlib_e2e.sh` (clean HEAD `git archive` 展開) | unit T1..T15 + FA 400/400 + KH 366/366 + OTT 既定/旧既定 + SIMD 95,400 + 注入 94/94 + leafspec | **138 秒** (12:01:29 → 12:03:47) | 4.48, 4.20, 3.96 |
| `bash tools/ott/ott_e2e.sh` | 89 scenario / 全 cell bit-exact / E7 8 combo | 前掲 (正本 `tools/ott/REPORT.md`) | — |
| `python3 -m liftlib ott` | checks 8/0・junkHi 104/248・trap 0・RESULT PASS | 10 秒 | — |

### 14.6 検証範囲・範囲外 (規則 40)
- clean HEAD 検証は `git archive HEAD -- tools/liftlib` を `<dir>/work/verify_L4` に展開し、参照データ (`tools/m6/work`, `tools/targets/{freshair,kilohearts}`, `tools/shim`) を symlink して実行した (これらは gitignore 対象なので archive に含まれない)。
- **native 実機との bit 比較は leafspec の 5 leaf (exp/log/tan/svf/cvt) のみ**。OTT 既定 (`auto f7,p1`) の p1 修復は census/checks/trap/outhash で評価しており bit 突合はしていない。
- junkHi 248 の低減効果は**測れなかった** (不変 = 記録のみ)。残 6 のうち 2 件 (`no value` は領域が書く reg を store で運べない型) と 1 件 (間接 call) は icall (CAB-89/CAB-228 領域) に属する。

### 14.7 未解決 (起票先付き・規則 42)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 残 6: `no value for %storemerge*.in.reg2mem` 2 (領域が書く reg を store で運べない) | OTT 既定の未修復 dropped 分岐 | (a) CAB-89 / CAB-228 (icall 領域) にコメント |
| 残 6: 間接 call `call qword ptr [rax+0xe0]` 1 | 同上 | (a) 同上 |
| 残 6: `bind xmm1 @1801a9da0` (tan) 1 | tan の bit-exact | (a) CAB-272 自身にメモ (継続) |
| 残 6: `and rax, [rip+0x6443f]` (log, multi-def movq) 1 | log の bit-exact | (a) 同上 |
| 残 6: `bind xmm5 @1801bd172` (cvt, SSE 多定義 vpxor/vmovss) 1 | cvt の bit-exact | (a) 同上 |
| tan 残 29/40 (ret の entry/call phi が未合成: ret @1801a9c9e は phi(entry xmm0, call 結果) だが `%rax.0.reg2mem` 経路を拾う) | tan bit-exact 11/40 | (b) 次タスク (CAB-272 に提案) |
| leaf native CRT 経路 crash (log 8/SVF 8/cvt 23) | leafspec の crash 除外 | (a) CAB-256 にコメント (LIFTLIB-3 から継続) |

### 14.8 新類型行案 (DEFECTS.md 形式・規則 44)

| 症状 (silent) | 根本原因 | 観測 (証拠) | 検出信号 | 修復 |
|---|---|---|---|---|
| 領域値の名前に埋めた機械語 VA を「値の定義 VA」と誤認し、正当な値を非支配と誤判定して修復が失敗する | `%p1r_<va>_<salt>_<tag><n>` の `<va>` は**タグ**。relay 値は他所の VA をタグに使うため `block_of(va)` は def block にならない | LIFTLIB-4: `merge xmm2` 4 件 + `bind xmm0` 1 件 (全 15 の大半) が誤 FAIL。`LL_NO_VDB_DOM=1` で 6 → 14 に戻る | 領域値名の `<va>` と `ix.defs` の実 block が一致しない件数 | `Region.vdb` (`nm()` で定義 block を記録) で判定。`merge_in` は `cur_va` 設定後に回す |
| 同一機械語アドレスの IR 命令が原本/領域で重複し、末尾 (領域) を拾うため別経路の経路固有 SSA を参照して非支配になる | p1 は領域を再構成すると同一 VA に IR 命令が 2 本になるが、`value_defined_at` は無条件に末尾を採る | LIFTLIB-4: `bind xmm1` 5 のうち 3。`LL_NO_ORIG_PREF=1` で 6 → 9 | 同アドレスの IR 命令数 ≥ 2 のうち領域側が採られた件数 | 原本 (dst が `%p1r_` 等でない) を優先。領域 block は**ラベルでなく dst 名**で判別 |
| `_reissue_load` で或る pred に挿入した load 値を、別 pred の relay block から store して非支配になる | relay block は終点ごとに新規作成されるが、値の def block は 1 つだけ | LIFTLIB-3 から潜没 (leaf の phi 合成で初発動)。emcc "does not dominate all uses" | `%p1r_…_rl<N>` が複数 relay block から store される | `Region.vdbld` に (alloca, ty) を覚えておき `_for_block` で relay 自身で再 load |

### 14.9 既存テスト T12 の更新理由 (規則 45 に基づく訂正)
T12 は「join split が発動すること」を assert していたが、LIFTLIB-4 で領域値支配が直ったため **join split は発動しなくなった** (対象 site は DAG 側で扱える)。重要なのは**性質** (自己辺が無い = CAB-238 §6 の無限ループが起きない) なので、assert を「自己辺 0 本」に変更した (実測 self_edges=0)。E7 param sweep 8 combo も ott e2e で完走を確認済み。

## 15. LIFTLIB-5 (#342) — tan / tanf bit-exact・SVF 20/40 (未達)

- 既知類型との関係: 該当なし (DEFECTS.md D1a〜D16 未登録。新類型行案は §15.5)
- 検証起点 commit: `7e00ff2` (clean HEAD ではなく ws-342 worktree。`bash liftlib_e2e.sh` はコミット済み状態で実行)

### 15.1 結論
| leaf (leafspec 40 scenario) | LIFTLIB-4 | LIFTLIB-5 |
|---|---|---|
| tan 1801a9be0 | 11/40 | **40/40** (mismatch 0 / crash 0) |
| tanf 1801ba860 (spec 新設) | — | **40/40** |
| SVF reset 180126040 | 2/40 + crash 8 + trap 1 | **20/40** + crash 7 + mismatch 13 + trap 2 (**未達**) |
| cvt 1801bc890 | 11/40 + crash 23 + trap 6 | 26/40 + crash 14 + mismatch 0 + trap 0 |
| exp / log | 40/40 / 32/40 + crash 8 | 不変 |

tan / tanf は `expect_match_min: 1.0` で gate 化した。SVF は未達のため gate 無し。

### 15.2 原因と修復 (tan)
1. **call の def 範囲** (`mc.py`): call は VOLATILE 全部を def にしていたため、callee が書かない `r10` (入口 sign) が call を跨ぐと bind 不能。callee 機械語の書込集合 (推移閉包) に絞る (`LL_NO_CALLEE_PRESERVE`)。
2. **領域の多定義 bind** (`p1.py`): 領域は D からしか入らないが、生存側 S だけが書く def も候補に入れて復元不能になっていた。領域に流れる def に限定 (`LL_NO_REGION_DEFS`)。
3. **setcc の i1** (`p1.py`): `xor r,r ; setcc r8` の結果が i1 で GPR bind に使えなかった。直前 8 命令内に同 reg のゼロ化がある時のみ `zext i1 → i64` で復元 (`LL_NO_SETCC_I1`)。
4. **合流点 dead reg** (`p1.py`): 合流で live でない reg が束縛不能でも領域全体を捨てていた。dead なら合成せず捨てる (`LL_NO_DEAD_JOIN`)。
5. **GPR rsp spill/reload** (`p1.py`): `mov [rsp+k], r64` / 逆を領域内で扱う (`LL_NO_GPR_SPILL`)。tan 単体の結果には効かないが領域再構成を通す語彙として追加。
6. **ret / RX の複製 call** (`leafabi.py`): p1 が call を複製すると単一 SSA が ret を支配しない。全複製の戻りを alloca (i128) に store し ret/RX 前で load (`LL_NO_RET_PHI`)。RX は call 後の xmm0 読み手を全て差し替える (`LL_NO_RX_ALL`)。
7. すべて `mc.LEAF_EXT` (leaf cfg のみ ON) の内側。FA/KH/OTT 既定は不変 (§15.4)。

### 15.3 ハーネス修正 (SVF/cvt の測定が変わった理由)
`native_runner.c` / `wasm_runner.mjs` は MS x64 ABI の引数レジスタを「gpr/xmm 独立カウント (SysV 的)」で割り当てていた。MS x64 は**位置**で決まる (第 N 引数 = rcx/rdx/r8/r9 か xmm0..3 の N 番目)。`(this, float, float)` の 2 つ目の float が xmm0 に入り xmm2 が 0 になっていたので、位置対応に直した。これで SVF 2/40 → 20/40、cvt 11/40 → 26/40 (trap 6 → 0)。`diff.py` に `ret_bits` を追加 (f32 戻りは下位 32bit のみ比較)。

### 15.4 ネガティブコントロール (tan leafspec 一致数, 各 switch を 1 つだけ止めた実測)
| switch | tan | 判定 |
|---|---|---|
| (全 ON) | 40/40 | — |
| `LL_NO_CALLEE_PRESERVE=1` | 11/40 | 効いている |
| `LL_NO_REGION_DEFS=1` | 11/40 | 効いている |
| `LL_NO_SETCC_I1=1` | 11/40 | 効いている |
| `LL_NO_DEAD_JOIN=1` | 11/40 | 効いている |
| `LL_NO_RET_PHI=1` | emcc 失敗 (does not dominate) | 効いている |
| `LL_NO_GPR_SPILL=1` / `LL_NO_RX_ALL=1` | 40/40 | tan には不要 (SVF/汎用の語彙。効果は未測定) |

### 15.5 検証 (実測)
`bash tools/liftlib/liftlib_e2e.sh` (HEAD `7e00ff2`、nproc=4): **ALL PASS / real 2m21.641s / 終了時 load average 0.99, 0.92, 0.69**。FA 400/400・KH 366/366・OTT checks 8/0・`--auto none` SHA 42/42・注入 94/94・T15 (残留 6) 不変。
経過: LEAF_EXT 導入前は OTT 既定で emcc 失敗 + T15 が 15→14 でずれたため、拡張を leaf cfg に限定した。

### 15.6 未解決 (起票先)
| 未解決 | 起票先 |
|---|---|
| SVF 20/40: mismatch 13 + trap 2 + crash 7。`this+0x10/0x14/0x18` (tanf 結果 `%18` を読む addss/mulss) の xmm0 差し替えが RetDec の insn.addr ずれで一部効かない | #342 (Refs で継続) |
| cvt: 26/40 + crash 14 (CRT 経路 `jmp *rax`) | #256 系 (leaf native CRT 経路) |
