# liftlib REPORT — 共通 lift 修復基盤の統合 (CAB-49 / CAB-54 / CAB-55 / CAB-220 / CAB-239)

- 日付: 2026-10-10 / 担当 dir: `tools/liftlib/` (他 dir は読取のみ) / 再現: `bash tools/liftlib/liftlib_e2e.sh` (キャッシュ時 約 25 秒 + leaf spec 約 4 分, `--fresh` で FA/KH を RetDec lift から約 1 分)
- 数値はすべて本 dir で実測。推定は「推定」と明記。

## 0. 結論 (先出し)

| 項目 | 結果 (実測) |
|---|---|
| (a) OTT | liftlib 側のみで再現: **各段 IR がテキスト完全一致** (base=ott_lift.ll / P1→shift→gdata=ir7e_p1..p3 / memfix0 / memfix1 / 最終 ott_m10.ll の 7 段すべて true) → emcc → **checks 7 / broken 0, band 係数 maxdev=0.0 (nbad 0)**, E7 OOB 不発, census([0x248]=0) 132/69/175/136 = M10 と同値。helper は **自動生成 153 本**で署名不一致 0 / undefined 46 (M10 と同数)。processReplacing 出力 42 組合せ (param×[0x248]×入力振幅) の SHA が **元 m10 成果物と 42/42 一致** |
| (b) Fresh Air Gain | **400/400 シナリオ bit-exact** (全バッファ+guard 比較, 手書きパッチ無し。P1 は機械語から自動再構成)。対照: P1 無効 85 不一致 / F7 無効 376 不一致+trap 2 / F2 無効 400 不一致 |
| (c) Kilohearts Gain | **61 シーケンス×6 ブロック = 366/366 ステップ bit-exact** (元 6 ブロック列を含む)。対照: P1 無効 305 不一致 / F7 無効 全シナリオ hang→trap / F2 は KH では不要 (callee 0) |
| SIMD helper (CAB-54) | 宣言駆動で自動生成。KH census 205 mnemonic の **未被覆 83(効果)/31(共通基盤)/90(合算)/92(host 込) → 1/1/2/2** (残: `pcmpistri`, `vinsertf128`)。**実機 inline asm vs wasm を 192 mnemonic・281 form・95,400 ベクタで突合: 不一致 0** (近似命令 4 種は相対誤差 <1.6·2⁻¹² を許容して 489 件合格) |
| 検出器 (CAB-55) | パターン注入 **94 件 (F7 57 / P1 畳込み 35 / F2 2) を 94/94 検出**, 修復済み IR への偽陽性 0。OTT 生 IR で既知 [F7] 1 件 + **新規 6 件の F7 型脱落**, comis 89 サイトの分類 (§5) |

コミット列: c8027d3 (基盤: base/P1/F7/F2/simd/harness) → 56679d5 (OTT recipe・CLI・e2e・注入評価) → 09b3918 (docs/unit test; feature 完了点) → cf096a6 (lowbase 取り込み CAB-220) → 本チケット (CAB-239)。

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
| ott --lb-base 0x10000 | checks 7/0, band 係数 maxdev 0.0/nbad 0, trap rc 0, **outhash 42/42 equal**, census[0x248]=0 132/69/175/136 = m10 同値。layout: base 0x10000 / arena 0x320000 / GLOBAL_BASE 0x420000 / initial 24MiB / max 64MiB |
| ott --lb-base 0x1230000 | 同じく checks 7/0 + outhash 42/42 (base 依存バグ無しの証拠)。initial 39MiB |
| audit_va.py 0x10000 | DIR64 13,000 全て image 内 (image 外 0) / IAT 375 slot の VA 保持 0 / base 64KiB 境界 → exit 0 |
| x64c 3 構成再現 | 0x10000/16MiB, 0x1230000/40MiB, 0x10000/8MiB の各 89 scenario 50,236 cell — **計 150,708 cell bit 一致 (max_ulp 0 / state_diff 0)** |
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
