# 付録 B: §13〜§16 (LIFTLIB-3 / LIFTLIB-4 / LIFTLIB-1 検収 / 環境パス置換) — tools/liftlib/

> **正本**: `tools/liftlib/REPORT.md` (結論・要約)。本書は 250 行上限 (`docs/DOC_MAP.md` §1) のため
> 本体から**そのまま分割移動**した §13〜§16 の全文 (節番号は本体・他節からの参照と一致。内容は削除していない)。
> 他の付録: [`REPORT_APPENDIX_A.md`](REPORT_APPENDIX_A.md) (§10〜§12)・[`REPORT_APPENDIX.md`](REPORT_APPENDIX.md) (§17)。

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

## 15. LIFTLIB-1 (#224) — 旧 dir 参照専用化の検収 (2026-10-13, Actions runner)

既知類型との関係: 該当なし (pass 変更なし。テスト/ e2e スクリプトの入力依存の修正のみ)。

### 15.1 結論
- 対応表 (検収条件 3) を `README.md`「旧 dir pass → liftlib 対応表」に追記。旧 dir `tools/m5〜m10` の REPORT 冒頭に参照専用注記を追加 (スクリプト・成果物は無改変)。
- `liftlib_e2e.sh` は **通常・`--fresh` とも ALL PASS** (条件 1)。旧 e2e 4 本は旧成果物で **全 PASS** (条件 2)。
- 条件 1 の最初の実測は rc=1 だった: unit T4 が旧 FA 中間成果物 `targets/freshair/work/lift_gain/gain_lift.ll` を無条件に読み、`work-liftlib-targets` 素材 (SlateCore/HeartCore のみ) に無かったため。FA の `@__asm_mulss` 宣言は liftlib 自前の RetDec 生出力 `work/fa_gain/fa_gain.drc.ll` にもある (署名 `x(x,d)` / `x(x,x)`) ので、旧成果物が無いときだけそちらへフォールバックさせた。加えて `--fresh` が T4 の入力を先に消していたため、削除を unit の後ろへ移動。

### 15.2 実測 (runner 4 core, 並列 1, 検証 HEAD はこのコミットのコード部。以降の差分は docs のみ)
| コマンド | 結果 | 所要 (実測) / load |
|---|---|---|
| `bash tools/liftlib/liftlib_e2e.sh` (修正前) | rc=1 (unit T4 のみ FAIL, 他は全 PASS) | 73.1 s |
| `bash tools/liftlib/liftlib_e2e.sh` | **ALL PASS**: unit T1..T15 / FA 400/400 / KH 366/366 / OTT 既定 checks 8/0 junkHi 104 / OTT `--auto none` checks 8/0 + IR 7 段一致 + 出力 SHA 42/42 / SIMD 95,400 vector 不一致 0 / 注入 94/94 偽陽性 0 / leafspec PASS | 143.2 s / load 0.93 |
| `bash tools/liftlib/liftlib_e2e.sh --fresh` | **ALL PASS** (同上。RetDec 再 lift 込み regress 84.4 s) | 186.9 s / load 1.31 |
| `M10_SKIP_BUILD=1 bash tools/m10/m10_e2e.sh` | PASS checks 7/0, band 係数 maxdev=0 nbad=0, junkHi 175 | 0.318 s |
| `M9_SKIP_BUILD=1 bash tools/m9/m9_e2e.sh` | PASS checks 6/0 | 0.187 s |
| `bash tools/m8/m8_e2e.sh` (build 含む) | OK: sig mismatch 0 / undefined 47 / trap8 14/5 / rt_leaf 19/0 / t1 SHA b5a91b9b… 2 run 一致 | 4.67 s |
| `bash tools/m7/m6_e2e.sh` | OK: sig mismatch 0 / undefined 57 / t1 SHA f34a6a46… 一致 / trap 6/13 | 3.10 s |

注: 「m6_e2e.sh」の実体は `tools/m6/` ではなく **`tools/m7/m6_e2e.sh`** (`tools/m6/` に e2e スクリプトは無い)。m9/m10 は `*_SKIP_BUILD=1` で旧成果物 (`work/ott_m9.cjs`・`ott_m10.cjs`) を直接検査した (build 再実行は検査対象外)。ネガティブコントロールは本チケットでは追加していない (pass 変更なし; liftlib 側の検出力は §5 / `inject-eval` 94/94 が継続ゲート)。

### 15.3 前提 (Actions 上での再現条件)
`pip install pefile capstone` / `/home/ubuntu/work/analysis → $HOME/analysis`・`/home/ubuntu/work/webstudio → worktree` の symlink / `tools/*/work` は素材 (`work-m6-ott` `work-liftlib` `work-liftlib-targets` `work-icall` `analysis-ott-binaries`) を展開した checkout を worktree に symlink。

### 15.4 検証範囲・範囲外
- 範囲: 上表の e2e が旧成果物・liftlib 成果物に対し PASS すること、対応表の記載。
- 範囲外: 旧 dir スクリプトへの実行禁止の機械的強制 (注記のみ)。`recipes/ott` (#12–16, 18) の insn.addr 駆動汎用化。
- **lift 段を揃える手順 (LIFTLIB-11 / #887 で追記)**: RetDec raw の alloca 並びは実行ごとに変わり得る (k80 の ASLR on/off 間で `run_base` 後も 58 行差、8 本中 2 種を実測)。前後比較で k80 系の成果物を揃えるには、`run_base` の後に `base.canon_alloca_order` を適用して比較する (`tools/liftlib/lift_determinism_e2e.sh` の判定と同じ手順)。詳細は `REPORT_APPENDIX_D.md` §23.4。`run_base` の既定出力は変えていない。

### 15.5 未解決 (起票先付き)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| `OTT_vst2_win64.dll` 等の `/home/ubuntu/work/...` 決め打ち (`tests/test_unit.py`・`m8_e2e.sh` ほか多数) | runner では symlink 必須 | `tools/shared/env.sh` (`ANALYSIS_DIR`) への統一を別チケット (PM が `[LIFTLIB-n]` で起票) |
| `pefile`/`capstone` の依存宣言が無い (requirements 無し) | 新規環境で `ModuleNotFoundError` | 同上 / #284 (CI 基盤) にコメント |
| 旧 dir スクリプトの実行を禁止する機械的な仕組みは無い (注記のみ) | 参照専用は運用依存 | PM 判断 (SUBAGENT_RULES 側の「読取専用」更新と合わせて) |

## 16. 環境パス置換 (#386, 親 #294・先行 #312): tools/liftlib/liftlib の /home/ubuntu を tools/shared へ

既知類型との関係 (DEFECTS.md): 該当なし (パス参照の置換のみで lift/IR には触れない)。

### 16.1 変更
`tools/liftlib/liftlib` の `*.sh *.py *.json *.ts *.mjs` (work/ 除く) の `/home/ubuntu` 参照 2 行を置換。
`liftlib/env.py` が `tools/shared/paths.py` の `PLUGINS_DIR` から `OTT_DLL` を組み、`cli.py` (inject-eval) と `recipes/ott.py` (`DLL`) がそれを参照する。
`tools/liftlib/` 直下 (`tests/test_unit.py`・`lowbase_e2e.sh`・`p1_residual_census.py`・`xmm0_ret_census.py`・`targets/ott_leaf.json`) は本チケット範囲外 (§16.3)。

### 16.2 検証 (検証起点 `origin/main` = ee8f70c、素材は `fl-win64` のみ)
- 受入条件 1: `grep -rn '/home/ubuntu' tools/liftlib/liftlib --include=*.sh --include=*.py --include=*.json --include=*.ts --include=*.mjs --exclude-dir=work | wc -l` → 0 (置換前 2)。
- 受入条件 2 (既定値同一性): `ANALYSIS_DIR`/`PLUGINS_DIR` を unset して `env.OTT_DLL` と `recipes.ott.DLL` を置換前の固定文字列
  `/home/ubuntu/work/analysis/plugins/ott/binaries/OTT_vst2_win64.dll` と文字列比較 → 両方一致 (True)。n=1・直列、load average 0.55 (1 分値)。
- ネガティブコントロール: `PLUGINS_DIR=/nonexistent` → `/nonexistent/ott/binaries/OTT_vst2_win64.dll`、`ANALYSIS_DIR=/x` (PLUGINS_DIR unset) → `/x/plugins/ott/binaries/OTT_vst2_win64.dll` (変数が効いている)。
- 構文: `python3 -m py_compile` 3 本 OK。

### 16.3 検証範囲 / 範囲外 / 未解決
範囲外: `liftlib_e2e.sh` / `python3 -m liftlib ott` の実行。`OTT_vst2_win64.dll` は `analysis-ott-binaries`、lift 入力は `work-m6-ott`・`work-liftlib`、emcc は `toolchain-emsdk` が要り、この run は `fl-win64` のみ取得のため。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| e2e を素材付きで未実行 | 置換行以外の挙動は未検証 (置換は DLL パス定義のみ) | 本 PR のレビュー run (PR 本文の `oc_artifacts:` 行) |
| `tools/liftlib/` 直下 5 ファイルに `/home/ubuntu` が残る | runner では symlink 必須 | 未起票 (2026-10-13 時点で `gh issue list --search "CI-4-liftlib"` は #386 のみ)。親 #294 にコメントで起票を提案 |
