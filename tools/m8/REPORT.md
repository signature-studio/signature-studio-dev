# tools/m8/REPORT.md — M8 (pattern C value-flow 接続 + idx_store32 正本差分 + missing 10 stub)

> **参照専用 (LIFTLIB-1 / #224)**: 本 dir の lift IR pass・スクリプトは新規実行・改変しない。IR pass の正本は `tools/liftlib` (対応表: `tools/liftlib/README.md`「旧 dir pass → liftlib 対応表」)。既存 e2e 成果物・本 REPORT は歴史として残置し、旧成果物に対する既存 e2e (`tools/m7/m6_e2e.sh`・m8/m9/m10 の `*_e2e.sh`) が引き続き PASS することは `tools/liftlib/REPORT_APPENDIX_B.md` §15 で実測。

- 日付: 2026-10-10。基点 HEAD = 805110b (M7 検収後)。工域: tools/m8/ のみ新規追加
  (tools/m5/m6/m7 は読取のみ, 改変 0 行; work/, __pycache__ は tools/m8/.gitignore で除外)。
- 検証環境: node v26 / emcc 6.0.12 (`[EMSDK]`) / Python 3.14 / RetDec 5.0 産物を m6 work 再利用。
- 検収コマンド: `bash tools/m8/m8_e2e.sh` (**exit 0**, tools/m8/work/e2e_result.json)。

## 0. 結論一覧

| 課題 | 結果 |
|---|---|
| (1) tools/m8 雛形 + ir8_valueflow.py (pattern C) | **実装+実証** — DSP 係数計算群 2 箇所の value-flow 破れを dsm 突合で特定し接続。t1 出力が `param 不応答 constant` から **param 応答 diffs=192 / 入力応答 diffs=225** (512 値中, M7 は 0/0) に変化 |
| (2) idx_store32 disp 前加算偏差 | **修正+検証** — tools/m8/ir7_argpass_fixed.py に正本差分を写す。実測: fsetparam(5, 0.5) → obj+544 (= 5*4+0x20c, 機械語 [rcx+rax*4+0x20c] 通り) に 0x3f000000 store / chunk[idx5*4] 同値 (tools/m8/idx_store_check.mjs)。Tail 6 case 全部の member mirror store が正位置へ |
| (3) missing 新規 10 種 (tools/m8/m8_rt.c) | **実装**。probe 直呼 (trap8) は **OK 14 / FAIL 5** (m7 baseline OK 6 / FAIL 13)。うち純計算 leaf #2/4/5/7 の **bit-exact 19/19 OK** (rt_leaf_test.mjs)。fail-fast 保持: #6 (caller broken-lift OOB 待ち) / #8 (Win API MultiByteToWideChar, M4 外挿待ち) / #11 (未初期 lock 構造 deref → fail-fast 保持) |
| (4) t1 bit-exact 512/512 | **未達 (M9 引継)** — 不応答の原因 (per-sample DSP 系未接続) は解消したが, 現出力は巨大値スケール (0x0c17fa41 系) / junk 残存 (§3)。bit-exact 参照実装 (JS 移植 or native unit) も未整備のまま |
| (5) m8_e2e.sh / REPORT / コミット | **完了** — 検収 15 項目全 OK (§1) |

## 1. m8_e2e.sh 検収数値 (実測 2026-10-10, e2e_result.json)

```
signature mismatch               : 0      (期待 0)
undefined symbol                 : 47 種  (function_18*: 23 / Win・CRT API: 24)   ← M7 57 種から m8_rt.c 10 stub 分消滅
simd decl def / callsite mismatch: 0 / 0
t1 (param 全零 sweep)            : 512 行, 2 run SHA 一致 b5a91b9b2ee8da1e6a904ff9cf93903a8337f4e68fcb1534cea9abbca387df12
t1 value-flow 応答 (T1SVF=1)     : param 0.5→0.9 diffs=192 / 入力 +0.3 diffs=225  (M7 実績 0/0)
t3                               : [OK] mem[0x30260ce0] == 0x2DDFA232 (m6 と同一)
trap8 (probe 直呼)               : OK 14 / FAIL 5   ← m7 検収 (OK 6 / FAIL 13) の missing-function 10 種解消
rt_leaf bit-exact (#2/4/5/7)     : OK 19 / NG 0
```
※ m6 側 baseline (m6_e2e: t1 SHA f34a6a46…, trap OK 6/FAIL 13) は tools/m6 系列
  を 1 行も変更していないためそのまま維持 (M7 側検収と同一状態)。

## 2. (1) ir8_valueflow.py — pattern C の concrete な接続点 2 件

tools/m7 REPORT §3-(a) pattern C (xmm 引数は i32 raw-bits + `__asm_*` 疑似経路) の
中で「DSP 係数計算群の value-flow 断絶」を M8 冒頭に dsm↔IR 突合と NaN-tracer
(msimd8_dbg.c: f32 lane helper の入出力 bits を ring buffer 追跡) で機械的に特定した。

### [F1] accessor arg-trunc 誤訳 (SVF 係数 accessor function_180126030)

- 機械語 (dsm 0x180126030): `movss xmm0,[rcx+0x24]; ret` — obj ポインタ +0x24 の
  f32 bits 返し (getC(x) accessor)。
- lift IR (closure/full 両方同形): `%0 = trunc i64 %arg1 to i32; movss(i32 %0); ret`
  — ポインタ値の下位 32bit を f32 bits と誤訳して返す → caller
  (processReplacing function_18011ec20) に garbage 係数が流れる。
- 修正: 忠実形 (add [arg, 0x24] → inttoptr → load i32 → movss → ret) へ本体再生成
  (本 pass の mode=accessor; 1 件適用, 形不一致は assert; 180126010/1801260c0 は
  dsm 突合で faithful 判定済みのため対象外)。

### [F2] SVF への xmm1 入力 alias 脱落 (function_1801260c0 = 1st order SVF)

- 機械語: ABI (rcx=obj, **xmm1=input sample**) で
  `movss xmm5,[rcx+0xc]; movss xmm3,[rcx+8]; movss [rcx+0x1c],xmm1; …` の SVF。
- closure lift: signature を (i64)=rcx のみとし xmm1 を drop。かつ摘出 xmm1 値の
  位置に `alloca i128` 未初期化読み (`%3 = load i128, ptr %0`) が差込まれる
  (broken-lift body) → 実行時に wasm stack garbage (0xffc00000 = -qNaN) が係数流へ投入
  (NaN-tracer 実測: 出生 op 無し → uninit spill 読み転写, 64 事象は ctor 段から)。
- 呼出側 per-sample block (0x18011f9cc..fbe の 16 callsite) では機械語が各 call 直前に
  `movaps xmm1, xmmK` (K=前段乗算結果 / accessor ret) を敷く (pattern B と同型)。
- 修正: (i) 16 callsite を 2-arg 化 — dsm 逆走査で setter (`movaps xmm1, xmmK`) を
  求め, closure IR 上「直前の call〜現在の call 間の 1 個の `%X = call i128
  @__asm_movaps__4(%V)`」を xmm1 bits とみなして `trunc i128 %X → zext → 2nd arg`
  追加 (full lift 側 !insn.addr による var 名照合は closure/full lift の番号ずれ
  (%1310 vs %1311 事象) のため主照合には用いていない — dsm setter 照合方式を採用), (ii) callee 本体を dsm 原典の
  ins 単位忠実転写 (f32 bitcast + fmul/fsub/fadd の fp 順序一致; raw-bits store).
  既存 `define i64 @function_1801260c0(i64 %arg1)` (m6_full_extract splice 版) を差替。

### 追加確定事実 (報告への記載義務)

- m7 REPORT §3-(c) の出力値記述「-6.0f (0xffc00000)」は**誤記** — 0xffc00000 は
  f32 **-qNaN bits** (16 進列は m7 harness が DataView.getUint32 の BE 読みで出力し
  ていた事情を含む「0000c0ff」列記載は endianness 経由)。M8 直測では
  `L samples 2..255 = 0xffc00000 (qNaN) / R 全 000` である。
- t1 processReplacing の実行路線は obj **+584 (0x248) flag byte で attractor が切替**:
  `≠0 → dec_label_pc_18011efb0 (簡素 per-sample 箪笥; SVF 不使用)`,
  `==0 → dec_label_pc_18011f950 (SVF 16 観音 chain: setParameter と連動する coeff
  ramp 群 + 1260c0 連鎖)`。t1 harness 既定の param 0.5 sweep では 0x248=1 で
  SVF 路線が一度も通らない (M8 追加した T1SVF=1 option で 0x248 を強制 0 にして
  SVF 路線を駆動 = 上記応答数値の計測条件)。
- param cascade 冒頭 (obj+806 flag byte / idx19 case): `T1Z=19` で 0 → dirty path
  回避, rc 0 復帰は M7 検収どおり。M8 では更に 0x248 flag と processReplacing
  冒頭 system control ([arg1+96]/[arg1+100] == 2 分岐) を踏査済み
  (obj 既定値 2/2 = 抑制なし)。

## 3. (4) t1 bit-exact 512/512 未達 — 事実上の残存障害 (M9 引継)

1. SVF 路線接続後の出力は param/input 応答を持つが, 値のスケールが破綻側
   (0x0c17fa41 系 問い合わせ階層雛形; 0x19DEE8xx junk からの変化)。
  推定残存 area: (a) coefficient ramp stream 群 (resume が obj+648/656/664/672 基点
   に書込む ramp と setParameter chunk の接続),
   (b) obj+584 (0x248) flag 路線分岐の他方 (0x248=1 側 per-sample loop) 未探査,
   (c) 出力 copy 系 (`mov qword ptr [rcx + r8*8], rax` 群) の L/R 配置。
2. bit-exact 参照が無い (M6 REPORT §8-(ii) のまま): native_fx 単位分割 or
   JS 参照実装の着手要 (M8 未着手)。
3. `__asm_*` 疑似 215 箇所のうち本 pass が機械的に接続したのは SVF 系
   16 callsite + accessor 1 件のみ。残は IR 側 reg2mem 型流れのまま (未検証;
   NaN-tracer の出生 op 検出 0 件ゆえ本 t1 経路では未発火)。
4. broken-lift OOB 2 件 (function_1801c69cc/c91cc = c38c8 family) は M8 でも未着手
   (trap8 FAIL 2 個; m6 REPORT §7-6 の预案を踏襲)。

## 4. (2) idx_store32 正本差分 (tools/m8/ir7_argpass_fixed.py)

- tools/m7/ir7_argpass.py からの copy に**1 箇所の 1 式修正**のみ (他は byte 一致
  copy): idx_store32 を `shl i64 idx,2` → `add i64 base,` → `add i64 …, disp` 順の
  正本形に置き換え (旧: `(idx+disp) << 2`)。
- tools/m7 側の正本は **コミット分離せず未改変** (指示 (2) の copy 方式を採用;
  ir8_valueflow 系 ir7 依存の re-run 全てを tools/m8 内で完結させた)。
- 検証: idx_store_check.mjs で fsetparam(5, 0.5) → obj+544 = 0x3f000000 確認
  (旧式では (5+0x20c)<<2 = 別 slot に落ちて機械語とずれる)。argpass 20 cases
  (argpass8_report.json) の全 drive 再検証済み
  (m7 検収表記の chunk/flag/TAIL_AB/CLAMP 分類は変化なし; TAIL_IDX/TAIL_IDX_x2 の
  6 case は idx≠0 の member mirror store も機械語通り bit 正位に修正)。

## 5. (3) m8_rt.c — missing 新規 10 種の処置 (trap8 実測 OK 14 / FAIL 5)

| # | 関数 | 処置 | probe |
|---|---|---|---|
| 1 | function_1801bfab4 | Win API (GetModuleHandleW) 参照値 0 stub | OK |
| 2 | function_1801c0ac8 | **dsm 忠実 port (bit-exact 検証 19/19 OK)** | OK |
| 3 | function_1801c1438 | UCRT 報告系 no-op | OK |
| 4 | function_1801c17e0 | dsm 忠実 (double quiet bit; bit-exact OK) | OK |
| 5 | function_1801c17fc | dsm 忠実 (f32 quiet bit22; bit-exact OK) | OK |
| 6 | function_1801c24d0 | **fail-fast 保持** (本体内で lock 管理; caller broken-lift OOB 待ち) | FAIL (missing function) |
| 7 | function_1801c33e0 | dsm 忠実 (lit mem 0x30260ce0/0x26c520 直読; bit-exact OK) | OK |
| 8 | function_1801c6744 | **fail-fast 保持** (Win API MultiByteToWideChar = M4 file API 外挿待ち) | FAIL (fail-fast) |
| 9 | function_1801c67a0 | dsm 忠実 port (module refcount inc chain + c69a4 tail port) | OK |
| 10 | function_1801c6a04 | dsm 忠実 port (xadd [rcx+0x15c] dec) | OK |
| 11 | function_1801c721c | dsm 忠実 port (CRT lock 族) — **probe では未初期 lock 構造 deref を guard fail-fast** | FAIL (fail-fast) |
| — | broken-lift OOB 2 (c69cc/c91cc) | 未着手 (M9 引継; m6 REPORT §7-6) | FAIL x2 |

- bit-exact 検証: #2 c0ac8 は u16 比較 leaf (NUL 比較 / n=0 / 片方 NUL の 4 口径) の
  想定値を JS 側で算出して突合。#4/#5 は bits 値。#7 は linear memory 実値参照
  (m6_data install 値)。→ tools/m8/rt_leaf_test.mjs (OK 19 / NG 0)。
- 保守: m8_ptr_ok() guard (linear memory 0x30000000..0x36000000) を全 deref
  wrapper に配置し, probe 直呼の garbage deref を fail-fast 収束させ silent
  corruption を防止。

## 6. コミット内容

- 新規 15 file (`tools/m8/`): ir8_valueflow.py / ir7_argpass_fixed.py / m8_rt.c /
  m8_build.sh / m8_e2e.sh / m8_quickbuild.sh (診断高速 build) / rt_leaf_test.mjs /
  trap8_test.mjs / t1_sel8.mjs / t3.m8.mjs / idx_store_check.mjs / crumbs.mjs (label
  breadcrumb tracer) / nanring.mjs + msimd8_dbg.c + msimd8_core.h (NaN tracer) /
  .gitignore (work/, __pycache__/) / REPORT.md (本書)。
- tools/m5/m6/m7, src/, tools/shim/, README・docs/ は **読取のみ (改変 0 行)**。
- work/ 産物 (ott_m8.ll / ott_m8.cjs / t1_out 系 hex / log / json) は commit 対象外
  (tools/m8/.gitignore)。

## 7. M9 引継 (まとめ)

1. SVF 路線の係数 ramp 上流 (obj+648/656/664/672… stream と setParameter chunk
   書込みの接続) と出力 copy 部の L/R 配置 — output 0x0c17fa41 系巨大値スケールの
   正常化が次の一手。
2. obj+584 flag (0x248) 路線分岐のもう一方 (`dec_label_pc_18011efb0` per-sample
   簡素 path) の broken point 探査 (t1 既定 T1SVF 無し condition)。
3. bit-exact 参照 (JS 移植版 or native unit bit 分割) — M6 REPORT §8-(ii).
4. broken-lift OOB 2 件 (c38c8 family, ir6_shift 算術合成 base remap)。
5. NaN-tracer (msimd8_dbg.c) の ring buffer 記録は M9 の新規接続点特定で
   1 コマンド再実効の実測資産 (出生 op 無し = uninit/spill 誤翻の判別)。

## 8. #4218 置換の同一性実測 (2026-10-16, issue #4465)

- 対象: `171b28c2a` (絶対パス直書きを REPO_ROOT 相対に置換: m7/m6_e2e.sh・m8/m8_e2e.sh・m8/m8_quickbuild.sh)。
- 方法: 置換前 `171b28c2a^` と置換後 `171b28c2a` の detached worktree で `bash tools/m8/m8_e2e.sh` を各 1 回実行し、`tools/m8/work/e2e_result.json` と stdout を比較。両 worktree では測定 worktree の repo 直下を repo root とし、解析 dir (`[ANALYSIS-DIR]`) を `$ANALYSIS_DIR` (analysis-ott-binaries 展開先) として参照。素材は work-m6-ott / analysis-ott-binaries / toolchain-emsdk (emcc 6.0.12)。
- 両回とも `m8_build.sh` が emcc を実行して `ott_m8.cjs` を再生成 (タイムスタンプが実行時刻)。

| 項目 | 置換前 (`171b28c2a^`) | 置換後 (`171b28c2a`) |
|---|---|---|
| e2e_result.json | 同一 (diff 0) | 同一 |
| stdout (時刻除く) | 同一 | 同一 |
| 所要 (real) | 4.984 s | 4.737 s |
| exit | 1 | 1 |

- 一致項目: signature mismatch 0 / undefined 47 (function_18* 23・Win/CRT 24) / simd 0・0 / t1 512 行・determinism 一致 / t1 value-flow diffs 192・225 / t3 OK 1 / rt_leaf OK 19・NG 0。
- **不一致 (両回共通・置換とは無関係)**: trap8 OK 15 / FAIL 4 (期待 14 / 5。§5 の 2026-10-10 実測 OK 14 / FAIL 5 から変化)。`m8_e2e.sh` の §4 判定が NG のため exit 1。置換の前後で同じ値のため、#4218 の置換は挙動を変えていない。trap8 の差分の原因は未調査 (未解決表に記載)。

### 差分確認 (測定 commit `171b28c2a` → HEAD)

測定 commit `171b28c2a` から PR head `a11ae4f4e` までの `git diff 171b28c2a a11ae4f4e -- tools/m7 tools/m8` は REPORT.md の追記 (文書のみ) の 20 行だけで、実行されるファイル (`*.sh`・`*.py`・ソース) の差分は 0 行。`git log 171b28c2a..a11ae4f4e -- tools/m7 tools/m8` は REPORT 追記の commit のみ。main 取り込み後の再測定は不要 (`docs/WORKFLOW.md` §6)。
