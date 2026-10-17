# tools/m11/ldfix — load 取り違え (値↔アドレス / 1 段 deref 脱落) IR 修復 pass (CAB-231)

**判定: 達成**。capstone 機械語 (正本) と RetDec IR の site 単位突合で 5 種類の load 欠陥を機械検出し、
**M11 closure 7,421 関数中 955 関数**を修復した。liftdiff M11 closure 全数差分の A/B 再採点 (同条件順次実行) で
**一致 2,274 → 3,161 (+887)、load_dropped 894 → 3 (-891)、leaf (自己欠陥確定) 1,272 → 389 (-883)**
(m11_e2e.sh 相当の stage4 回帰・unit survey は完全に非劣化、exit 0)。

再現: `bash tools/m11/ldfix/ldfix_e2e.sh` (pass 適用 + emcc 検証 + stage4/survey 回帰、約 8 分。
`--batch` で liftdiff closure 全数 A/B を追加、各約 11 分)。

## 1. 結論 (実測)

liftdiff `batch --set closure` (7,421 関数 × 9 pattern、boot 状態あり) の修復前後 A/B:

| 指標 | 修復前 (base) | 修復後 (fix) | 差 |
|---|--:|--:|--:|
| 一致 (match) | 2,274 | **3,161** | **+887** |
| 不一致 (mismatch) | 2,891 | **2,005** | **-886** |
| 実行不能 (unexec) | 2,256 | 2,255 | -1 (環境ノイズ) |
| `load_dropped` (主因) | 894 | **3** | **-891** |
| `spill_slot_deref` (主因) | 17 | 17 | ±0 (1 関数が match 化、他でタグ入れ替え) |
| leaf (callee 無差分 = 自己欠陥確定) | 1,272 | **389** | **-883** |
| `memory_semantics` (主因) | 208 | 202 | -6 |

- 遷移行列: mismatch→match **915** / match→mismatch 28 (うち 26 件は pass 非適用関数、残 2 件は F2 適用
  関数の「修復により深経路の差分が顕在化」= §4.2) / unexec→mismatch 1。
- **stage4 回帰** (m11_e2e.sh 相当、自 dir ラッパ): base/fix とも到達 stage 4/6、GetMem 13 / FreeMem 1 /
  FastMM_GetMem(407a50) 13 / units_run 17 / 942 / init_count 18 / icall_ok 19 で**完全同一**。
  unit survey (942 隔離) も ok 812 / trap 83 / miss 46 で同一。wasm-ld signature mismatch 0 / undefined 0。
- 3 大個別修正の IR 状態: ①4133f0 (_UStrAsg) 旧値 load 復元済 ②409c80 (Move) `[rcx]` deref 復元済
  (movups i128 系の alloca deref 12 site + `mov r8,[rcx]` 値化 (8B path) 1 site。4B/2B path の
  `store trunc(%arg1)` 形は F3c 未適用の残存) ③4123c0 件数 load 復元済
  (`xor i64 0,0` → `load i32 [arg1]` + loop bound store)。

## 2. 検出パターン分類 (機械語 = capstone 正本との突合)

検出は全て「IR 側の壊れた形」+「機械語側の証拠」の両方を要求する (片方だけでは書き換えない)。
機械語は `.pdata` の RUNTIME_FUNCTION 区間を capstone で線型逆アセンブルし、IR の `dec_label_pc_<VA>`
ブロックに割当てて突合した (`ldmach.py`)。

| pass | 欠陥 (RetDec 側) | 機械語側の証拠 | 修復 | 関数数 |
|---|---|---|---|--:|
| **F1** load_dropped | `add dword [g],1` が `store i32 (&g+1), [g]` に (load 脱落 + 即値がアドレス定数側へ)。`cmp [g],0` も同じ `&g+1` を値読み | rip 相対 RMW `add/sub dword [rip+D], imm` (target = g, imm = C1-C0) + 関数内に g への他 store 無し | `load i32 [g]` → `add` → `store`。後続の同一 `(&g+1)` 値読み (icmp 等) も RMW 結果に復元 | **902** |
| **F2** spill_slot_deref | レジスタ退避 alloca (`%rcx` 等) 自体を bitcast して `load i128, ptr %rcx_alloca` (スタック slot を読む。i128 は 値 8B+隣接 8B) | 同レジスタをベースとする zero-disp メモリ操作が関数内に実在 | アドレスを `inttoptr(load i64, ptr %rcx_alloca)` (= その時点のレジスタ値) に張替え。同ブロック内の全 load/store + ブロック外 uses に対応 | **30** |
| **F3a** 旧値 load 脱落 | `mov rax,[rbx]; mov [rbx],rsi; test rax,rax` の旧値 load が消え dest ポインタ自身に化ける (FreeMem(スタック) OOB) | 3 命令連続 + `je/jne` + rB≡rcx=arg1 (entry copy 込み) | store 直前に `%old = load [dest]` を挿入し、icmp・単一 pred 連鎖の派生値 (add -8/-16, inttoptr)・thread 系ブロックの slot store に配線。整合検証で他 path から未修復 store が来たら全体 revert | **3** (4133f0 / 413480 / 413540) |
| **F3b** 件数 load 0 化 | `mov edi,[rcx]` が `xor i64 0,0` に化け資源文字列初期化ループごと消滅 | ブロック内 zero-disp load 恰好 1 本・IR の `xor i64 0,0` 恰好 1 本・機械語に自己 xor (ゼロ化) 無し・load 先ベースが prologue home 追跡で argN と解決 | xor 行を `zext(load iN, ptr %argN)` に置換。ループ bound の reg2mem slot (entry store 欠落) には count を store | **5** (4123c0 含む) |
| **F3c** ベース値 store 化 | `mov r8,[rcx]` の読みが消え `store i64 %arg1, [dest]` に (ポインタ値をデータとして書く) | ブロック内 zero-disp load 恰好 1 本 + IR の arg 値 store (生/trunc/zext) + 機械語に rB の生 store 無し (ポインタ store は正当なので除外) | `load <T>, ptr [argN]` を挿入して store 値を張替え | **16** (409c80 の 8B/4B/2B path 含む) |

修復関数の重複: 955 unique (954 が 1 pass、1 が 2 pass)。emcc 全体 IR コンパイル通過を毎回確認。

## 3. 修復率と残存の理由

- **load_dropped 892 件中 890 件修復 (99.8%)**。残 2 件 (0x10d35b0 / 0x106d220) は IR 形が 3 連パターン
  (`ptrtoint→trunc→store`) から外れる変種 (store 先が reg2mem slot / 値が `select` 合流) で、
  機械語 RMW は存在するが IR 側の形が一般化の範囲外。fix2 の採点で第 3 の変種 (0x108ec70) も
  同類として検出された。変種は検出済み・未修復 (§8 の拡張候補)。
  なお F1 は load_dropped 判定外の unit fini proc 等にも効き、合計 902 関数を修復した。
- **spill_slot_deref**: 静的 67 関数 / 102 site のうち **30 関数を修復**。未修復 46 site は「機械語にその
  レジスタの zero-disp メモリ操作が無い」(機械語側で裏取りできない = RetDec がレジスタを再割当てした
  もの等) で保守的に見送り、11 site は bitcast の他用途が残るため部分修復のみ。liftdiff 主因 17 件のうち
  9 件に適用し **1 件 (69cb10) が match 化**。残 8 件は `arg_drop` / `zero_init_drop` / `icall_drop` 等
  複合欠陥を持ち (§4.2)、spill 修復だけでは verdict が反転しない。
- **F3a**: シグネチャ一致 3 関数全件修復 (`_UStrAsg` 系一族の全数)。4133f0 の verdict は mismatch 残存
  だが、残差分は「src refcount path の別欠陥」で旧値 load 欠落そのものは機械語と IR の差分照合で解消を
  確認 (§4.2)。
- **F3b**: 厳密条件を満たした 5 関数のみ修復 (4123c0 含む)。候補 124 site のうち shape 不一致 26 /
  base 未解決 57 は未修復 (誤修復リスクを優先)。
- **F3c**: 候補 88 ブロック中 16 関数を修復。`no_store` 149 / `reg_store` 52 は機械語と IR の形が
  合わないため見送り。

## 4. 検証 (定量的)

### 4.1 liftdiff closure 全数 A/B
§1 の表の通り。同一 boot_state.json (native で unit 0..16 実行済の状態) を base/fix で共用し、
同一 PE・同一 pattern・同一 shard 数で実施。

### 4.2 個別関数の差分検証
- **4133f0 (_UStrAsg)**: 修復前 wasm は旧値の refcount 減算を一切書かず (native は `[old-8]` を -1)、
  修復後は wasm も `[old-8]` を -1 した (mem diff に新規出現 = 修復した動作)。native 側が [old-8] を
  減算し wasm が減算しない「FreeMem(スタック) OOB」の直接原因は解消。verdict は src refcount 経路の
  別差分で mismatch 残存 (本 ticket の範囲外: p01 case で native が加算する cell に wasm が追従しない
  問題 = COW increment 経路の別欠陥)。
- **409c80 (Move)**: movups i128 path (409c8f/409ce0) は `load i128, ptr %ldfxb*_p` (= [rcx 値]) /
  `store i128, ptr %ldfxb*_p` (= [rdx 値]) に修復され、n≥16 copy の alloca deref は解消。
  8/4/2 バイト path (409ca4/cb9/ccc) は F3c が `mov r8,[rcx]` 等を復元。p01 残差分は
  `store i64 %arg1` 以外の経路 (rep 系 helper 経由 = `rep_string_helper` タグ) で別 ticket 課題。
- **F2 適用 2 関数で match→mismatch (6a7d20 / 9567c0)**: いずれも修復自体は機械語と一致することを確認
  (6a7d20: `movdqu xmm7,[rcx=arg1]` → `load i128, ptr [arg1]`。9567c0: `add dword [r8=arg3],1` →
  `[arg3]` への load/add/store)。差分が顕在化したのは修復前は alloca deref が偶然ポインタ正規化と
  合致して match になっていた経路で、修復後に (a) 6a7d20 の i128 fill が SIMD helper
  (`__asm_movdqu__36` が i64 を返す = 上位 8B 切捨て, RetDec 元 IR 由来の既知 class) の影響で
  16B パターン全体を書けないこと、(b) 9567c0 のループ内カウンタ読みの下流で別差分 (3002 cell) が
  見えるようになったこと。修復の機械語整合は保たれているため、後続の simd_helper / 複合欠陥 ticket に
  引継ぐ。
- **4123c0**: `xor i64 0,0` → `zext(load i32, ptr %arg1)` + `%rdi.0.in.reg2mem` への loop bound store
  を復元 (機械語: `mov edi,[rcx]; ... sub edi,1; test edi,edi; jne`)。verdict は unexec のまま
  (native が全 pattern で落ちる関数で比較不能) — IR レベルの正しさは機械語突合で確認。

### 4.3 実行ノイズの定量
match→mismatch の揺れは shard 実行時の負荷で発生する (native timeout / wasm crash 判定が動く)。
base1 (14 shard, 単独) と base2 (12 shard, 順次) でも 一致 2,275→2,274 / wasm_trap 380→377 の揺れ。
代表関数 (5e0eb0) を両 target で単体再実行すると**両方 match**。本 REPORT の A/B は同条件
(shards 12, boot_state 共有, base→fix の順次実行) で取り直した値 (§1) を用いる。

### 4.4 m11 stage4 回帰 + OTT/FA/KH 系
- stage4 (FastMM4 実行) と survey の全数値が base/fix で完全同一 (§1)。既存 tools/m11 ファイルは
  1 行も変更していない (build は `tools/m11/ldfix/work/stage4/` に独立生成、`stage4.sh` 参照)。
- **OTT / Fresh Air / Kilohearts 系 (liftlib 適用系統) は非該当**: 本 pass は tools/m11 の boot_final3.ll
  (M11 closure) にのみ適用し、tools/liftlib・tools/ott・targets 系は一切変更していない
  (git diff で tools/m11/ldfix/ 以外無変更を確認)。既存 bit-exact e2e への影響経路がない。

## 5. D7 (tools/icall) との統合方針

tools/icall REPORT の D7 は「live-in レジスタ経由の zero-disp 参照の load が消える」欠陥で、本 pass の
F3a/F3b/F3c と同根。icall では PE 書換え (`lea B,[B+8]; op [B-8]` 補償) で回避したが、本 pass は
**IR 後修復** (消えた load を IR に足す) で対処した。統合方針:

1. **検出器の共通化**: `ldmach.py` (zero-disp memop 抽出 + home 追跡) は icall の `audit_icall.py`
   (間接 call 集計) と同じ capstone→IR block 対応基盤。CAB-223 で `liftlib` に統合する際は
   「memop 監査 (本 pass) + icall 監査 (icall)」を 1 つの capstone スキャナに束ねる。
2. **適用順**: icall pass は PE 書換え (lift 前 ingrained)、ldfix は IR 後処理 (lift 後)。両者は排他でなく、
   icall 書換え済み PE を lift した IR にも ldfix を掛けてよい想定 (D7 補償の `lea` は disp≠0 形になるため
   zero-disp 検出に引っかからない = 二重修復は起きない。併用実測は未実施 — CAB-223 で確認)。
3. **FLEngine 12,559 命令の取り込み**: icall REPORT の D7 残 (書換え derefix 12,559) は ldfix の
   F3b/F3c が IR 側で吸収できる形。M11 closure での実測 (F3b 5 / F3c 16 関数) は厳密条件のため
   被覆は一部 — 条件を段階的に緩める場合は §7 の拡張順に従う。

## 6. CAB-223 (liftlib 一本化) への統合手順

1. `tools/m11/ldfix/ldmach.py` を `liftlib/liftlib/machscan.py` として移管 (PE/.pdata/capstone/block
   割当ては plugin closure でも共通。依存は capstone + pefile のみ)。
2. `ldfix.py` の 5 pass (F1/F2/F3a/F3b/F3c) を `liftlib/liftlib/passes/ldfix.py` に移し、
   `--pe` 由来の機械語証拠を liftlib の pass 鎖オプション (`--pe` 指定時のみ有効) にする。
   pass 適用位置は **m11_passes 相当の IR 整形後・m11_post (weak 化/sigfix) 前**を推奨
   (本実装は boot_final3.ll = post 後に対しても動作確認済みだが、sigfix の 0 詰めと干渉しない
   先側が安全)。
3. 回帰は本 dir の `targets/m11_ldfix.json` 形式 (liftdiff target = 修復 IR を指すだけ) をそのまま使う。
   合否判定は `liftdiff.py batch` の verdict 反転数と `load_dropped` 減少 (§1 の表を base 値として保存)。
4. m11 側は `m11_gen_ir2.sh` の最後に `python3 ldfix.py boot_final.ll boot_final_ldfix.ll --pe ...`
   を 1 行足すだけ (m11_e2e.sh 等の既存ファイル変更は要承認 — 本 ticket では未実施、ldfix_e2e.sh で代替)。

## 7. 常設化 (CAB-131) — 概要と付録への導線

**判定: 達成 (stage 5 進捗測定込み)**。CAB-231 の ldfix を `m11_gen_ir2.sh` に常設組み込みし、
残存していた `load_dropped` 変種 3 関数を **F1v pass (新設) で吸収して `load_dropped` 892→0**。

- **再現**: `bash tools/m11/m11_e2e.sh --full` (ldfix 込みで再生成) + `bash tools/m11/ldfix/embed_e2e.sh --batch` (A/B 検収)
- **主要実測** (全て `REPORT_APPENDIX_AB.md` に詳細):
  - 既存 e2e 回帰 (stage4 / survey / shimx_link 純リンク) は base↔fix **全数値完全同一** (非劣化)
  - 通常起動の `units_run` は **17/942 のまま** (stage 5 未達)。進捗は「残欠陥の確定」と「halt0 53 unit の対応表更新」
  - F1v 4 関数のうち 3 関数 (`10d35b0` / `106d220` / `108ec70`) は match 化。`126c000` は icall_drop 支配で不反転
- **変更したファイルは 2 件のみ**: `m11_gen_ir2.sh` (+13 行)・`ldfix.py` (+180 行 = F1v pass)
- **付録 (詳細・A/B 全表・halt0 対応表)**: [`REPORT_APPENDIX_AB.md`](REPORT_APPENDIX_AB.md)
  (常設化の組込手順・A/B 検証・残存ボトルネック優先順・halt0 53 unit 対応表・CAB-233 引継ぎ)

## 8. 成果物 (tools/m11/ldfix/)

| パス | 役割 |
|---|---|
| `ldfix.py` | 本体。F1/F2/F3a/F3b/F3c 修復 pass (`--pe` 機械語突合, `--report` JSON, `--only` 単関数) |
| `ldmach.py` | capstone 機械語スキャナ (.pdata 関数区間 / memop 解析 / IR ブロック割当て) |
| `ldfix_e2e.sh` | 1 コマンド検証 (pass 適用 → emcc 検証 → stage4 base/fix → survey → judge; `--batch` で liftdiff A/B) |
| `stage4.sh` / `run_stage4.mjs` / `survey_stage4.mjs` / `judge_e2e.py` | m11_e2e.sh 相当 stage4 回帰の自 dir ラッパ (既存 tools/m11 ファイル未変更) |
| `embed_e2e.sh` / `embed_sx_ab.sh` / `sx_halt0_ab.sh` | 常設化 A/B 検収 (stage4 + survey・`--batch` で liftdiff 全数 / alloca 足場 mainline+shimx 純リンク A/B / halt0 足場 survey A/B) |
| `halt0_map.py` | survey JSON → halt0 発生点 × unit 対応表抽出 |
| `targets/m11_ldfix.json`・`targets/m11_ldfix_embedded{,_post}.json` | liftdiff 用 target (修復 IR / 常設化 IR / post 後・F1v 分離用) |
| `render_target.py` | targets/*.json の `${FL_WIN64_DIR}` 等を `tools/shared/paths.py` の値で展開し `work/targets/` に出力 (liftdiff は env を展開しないため e2e が経由する) |
| `results/halt0_map_*.json` | halt0 対応表実測 (CAB-129 受入時 / 今日 base / 今日 fix) |
| `work/` | 生成物 (gitignore): ldfix_fixed.ll, ldfix_report.json, batch_base*.jsonl, batch_ldfix*.jsonl, stage4/{base,fix}/ |

> **正本**: 本ファイル (`REPORT.md`) が ldfix の正本。CAB-131 常設化の A/B 詳細は付録
> [`REPORT_APPENDIX_AB.md`](REPORT_APPENDIX_AB.md)。

## 8. 未解決・次タスク提案

1. **F1 変種の吸収** (store 先が reg2mem / 値が select / `store trunc(%argN)` の 4B/2B 形): 残 3 件
   (0x10d35b0 / 0x106d220 / 0x108ec70) と Move の 4B/2B path。機械語 RMW は既に特定済みなので
   IR 形を数種追加するだけで良い。
2. **F3b/F3c の条件段階緩和**: 現在「恰好 1 本」制約のため候補 124/88 のうち修復は 5/16 関数。
   機械語データフロー (レジスタ→SSA 対応) を本格実装すれば `arg_drop` 312 / `callsite_arg_drop` 310 系にも
   展開できる (m11 REPORT §2-2/2-3 の残課題)。
3. **spill 複合欠陥の個別修復**: F2 適用 8 関数が `arg_drop` / `zero_init_drop` / `icall_drop` を併発
   (§3)。verdict 反転には複数 pass の同時適用が必要 (icall pass との結合試験を推奨)。
4. ~~**m11 への常設組み込み**: §6-4 の 1 行追加~~ → **CAB-131 で実施済み** (詳細は付録 `REPORT_APPENDIX_AB.md`)。
5. bitcast 残存による静的タグの残存: F2 修復後に使われなくなった bitcast 行の DCE (分類器の
   `regslot_deref` が静的カウントのため付き続ける。意味上の問題なし)。

## 9. 絶対パス除去 (#351、親 #294)

`/home/ubuntu` 直書き 6 箇所 (`ldfix_e2e.sh`・`embed_e2e.sh`・`halt0_map.py`・`targets/*.json` x3) を
`tools/shared` の `FL_WIN64_DIR` に置換 (既定値は従来と同一)。sh は `source tools/shared/env.sh`、py は `paths.py`。
JSON は `${FL_WIN64_DIR}` プレースホルダとし、e2e が `render_target.py` で展開した `work/targets/*.json` を liftdiff に渡す
(liftdiff `build_wasm.load_target` は area 外で env を展開しないため)。

既知類型との関係: 該当なし (lift 出力に触れない)。検証起点: `origin/main` 2c3e526。

| 検査 | コマンド | 実測 |
|---|---|---|
| 残存 | `grep -rn '/home/ubuntu' tools/m11/ldfix --include=*.sh --include=*.py --include=*.json --include=*.ts --include=*.mjs` (work/ 除く) | 0 件 (置換前 6 件) |
| 構文 | `bash -n *.sh` / `py_compile halt0_map.py render_target.py` | 5 sh・2 py すべて OK |
| 既定値で同一 | env 未設定で `render_target.py` → `git show HEAD:<json>` と `cmp` | 3/3 byte 同一 |
| 上書き | `FL_WIN64_DIR=/x/y` で render / `halt0_map.py` の `FL_WIN64_DIR` | `pe` が `/x/y/extracted/...` / `/x` |

置換前後の e2e 出力同一性 (#351 受入 2) の実測 (2026-10-13, runner, 素材 fl-win64 / work-m11 / work-liftdiff / toolchain-emsdk 展開, capstone+pefile は venv):

| 比較 | 方法 | 結果 |
|---|---|---|
| 工程 1 (`ldfix.py`) | 置換後 HEAD を、PE パスだけ旧 `/home/ubuntu/work/analysis/win64` に揃えて実行 | `ldfix_fixed.ll` (21,771,834 B) と `ldfix_report.json` が**バイト一致** (F3c=26) |
| render 済み target | 旧 JSON (`5984f7e^`) と `render_target.py` 既定展開 | 3/3 byte 同一 |
| `ldfix_e2e.sh` 全工程 | 置換前 (`33fd25a2` のうち置換対象 6 ファイルだけを `5984f7e^` に戻した tree) と置換後 (`33fd25a2`) のログ | パス正規化後に**完全一致** (30 行。置換前 50 秒 / 置換後 61 秒) |

注意 (置換とは無関係): 比較基点を `5984f7e^` 全体にすると、その間の他 PR の `ldfix.py` 変更で F3c が 0 → 26 と変わる。比較は置換対象以外が同一の tree で行うこと。

既存欠陥 (#757 で修正・下記は実測): 修正前は stage4 が到達せず (`m11_simd.c: '../msimd11_core.h' file not found`・boot `missing function: __asm_movapd__112`)、base / fix とも survey ok 0・units_run 0 でも `judge_e2e.py` が PASS と判定していた。原因は `stage4.sh` が header を `work/stage4/` に置かず、simd.o が link されていなかったこと。`stage4.sh` で header を配置 (`cp "$M11/msimd11_core.h" "$S4/msimd11_core.h"`) し、`judge_e2e.py` に「stage4 到達 (>=4) と survey ok >=1」の前提を入れた。確認できた事実: `__asm_movapd__112` は `tools/m11/shimx_link/results/classes_boot_final3.json` に含まれる (件数の実測なし)。修正後の `ldfix_e2e.sh` 実測 (測定 run https://github.com/signature-studio/signature-studio-dev/actions/runs/38483922151 attempt 1・headSha `7a246871`・測定 commit `f8b90732` = origin/main・素材 fl-win64 / work-m11 / work-liftdiff / toolchain-emsdk / toolchain-retdec 展開・`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`・foreground 1 回・`timeout 1500 bash tools/m11/ldfix/ldfix_e2e.sh > $RUNNER_TEMP/ldfix_e2e.out 2>&1`): rc 0・64 秒・load 1.06 (開始) / 1.09 (終了)。出力全文 (26 行) の sha256 `e564fb6b5c7644960cdb35a3ecea89a150011115cf0041b767bbfd6431fa169a` (先頭 16 桁は作成時の記録と一致)。ログ全文と `work/stage4_{base,fix}.log` の `grep -c` 件数は、`missing function` 0/0/0・`__asm_movapd__112` 0/0/0・`file not found` 0/0/0 (出力/base/fix)。`undefined symbol` は summary 行 `signature mismatch: 0, undefined symbol: 0` の 1/1 件のみで、エラーは 0。`STAGE4_JUDGE {"pass": true, "stage_base": 4, "stage_fix": 4, "survey_ok_base": 136, "survey_ok_fix": 136}`。stage4 base / fix とも getmem 16・units_run 17/942・icall_ok 24・survey ok 136・trap 9 (同一)。修正件数の実測 (同 run・`tools/m11/ldfix/work/ldfix_report.json`): F1=0 / F2=0 / F3a=2 / F3b=0 / F3c=33 (7,421 関数)。**§1〜2 の 955 関数 (F1 902) とは一致しない**。原因は未切り分け。§1 の A/B 表 (一致 3,161 等) は本 run では再測定していない (`--batch` は未実行)。threw `memory access out of bounds` の切り分けは #942 (CI-22) に分割。

### 現行 HEAD での再測定 (#6053)

#4521・#4522 (1e2/1e3 の修復) の close 後に、現行 main で `ldfix_e2e.sh` を 1 回実測した。
**測定 commit `ff41e8aae`** (origin/main = PR #6051 取り込み後。worktree `ws-6053`・branch `6053-ldfix-remeasure`)。
素材は fl-win64 / work-m11 / work-liftdiff / toolchain-emsdk を `$HOME/artifacts` から展開。
`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP timeout 1500 bash tools/m11/ldfix/ldfix_e2e.sh` を foreground で 1 回。
rc 0・74 秒・load 1.32 (開始) / 1.83 (終了)。出力 (43 行) の sha256 `d35a5237b2cb574cd6b07f3dbffa638b3c01f1af6dfff79120c0d51a821136d5`。

| 項目 | base (修復前) | fix (修復後) | 判定 |
|---|---|---|---|
| stage4 到達 | 4 | 4 | OK |
| getmem / freemem / FastMM_GetMem | 16 / 6 / 17 | 17 / 6 / 18 | OK |
| units_run / units_total | 17 / 942 | 17 / 942 | OK |
| init_count / icall_ok | 18 / 24 | 18 / 24 | OK |
| survey ok / trap | 136 / 9 | 136 / 9 | OK |

- `STAGE4_JUDGE {"pass": true, "stage_base": 4, "stage_fix": 4, "survey_ok_base": 136, "survey_ok_fix": 136}`
- エラー件数 (ログ全文・`work/stage4_{base,fix}.log`): `missing function` 0/0/0・`__asm_movapd__112` 0/0/0・`file not found` 0/0/0・`FAILED` 0/0/0。`undefined symbol` は summary 行の `undefined symbol: 0` のみ (base/fix の各ログには `undefined symbol: 1` の 1 行が出るが、エラーではない)。
- 修復件数 (`work/ldfix_report.json`): F1=0 / F2=0 / F3a=2 / F3b=0 / F3c=42 / F4=10 (7,421 関数)。
  前回 (f8b90732) の F3c=33 から変わった (F4=10 は前回の記録に無い項目)。
- 前回測定 (f8b90732) との比較: stage4 の getmem・survey ok (136)・units_run (17) は同じ。F3c の件数だけが増えた。
- `--batch` (liftdiff closure A/B) は本測定では未実行。§1 の A/B 表は更新していない。

**測定 commit 以降のコード差分 (`git diff ff41e8aae HEAD -- tools/m11/ldfix`)**: 本測定は HEAD = `ff41e8aae` で行った。
この REPORT の追記以外に `tools/m11/ldfix` のコードは変えていないため、コード差分は 0 (REPORT.md のみ)。
