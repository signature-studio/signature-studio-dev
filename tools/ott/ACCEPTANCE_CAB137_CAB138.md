# 検収 REPORT — CAB-137 (OTT-T4 VST entry lift) + CAB-138 (OTT-T5 CRT init / override 置換)

## 0. 結論 (先出し)

- **CAB-137 = PASS (受入・条件 1 件)**。`bash tools/ott/entry/entry_e2e.sh` = **PASS**。native 実機械語 vs
  lift wasm の突合 **85/85 scenario** (nat_crash 0 / FAIL 0 / `dsp_verified 30` + `entry_new_verified 35`)。
  既存 DSP e2e **89 scenario・全 cell bit-exact / max_ulp 0 / state 差 0** を維持 (数値の正本: `tools/ott/REPORT.md`)。
- **CAB-138 = PASS (受入・条件 1 件)**。`bash tools/ott/crtinit/crt_e2e.sh` = **PASS**。新 scenario
  **9/9**・entry 85 を CRT 版 build で再突合 **85/85**・陰性対照 `OTT_CRTINIT=0` が **native SIGSEGV /
  wasm `ott_unlifted` の同一 garbage VA** で両側再現。
- **独立再計算 (別アルゴリズム) は全項目で実装報告と一致**。ただし **lift 集合はコミット済み scenario からは
  207/13,690 (entry)・258/16,374 (crt) で、報告値 209/13,694・260/16,378 ではない**。差分は +2 関数
  (0x180126310 / 0x180126320) / +4 命令で、**coverage の `getp_range` が idx 25..30 まで実行された
  未コミット状態**に由来 (§3.2)。**clean tree で e2e が起動不能な不具合を 2 件発見・修正** (§3.3)、
  **誤記 6 件を修正** (§5)。
- Clean HEAD 再現: HEAD = **4b162ce**、検証対象 = `tools/ott` の **faf8b0d** / **8b31a48**。再現は
  `git archive HEAD -- tools/ott` の snapshot (`work/verify_4b162ce`・`work/verify2_4b162ce`) で実施。

## 1. 数え方の定義 (規則 36)

| 数値 | 定義 (単位・分母・除外) | 集計コマンド |
|---|---|---|
| scenario | VSTPluginMain + 連続 guest 呼出の 1 列。`cmp_entries` は名前を dict キーで保持するため**同名は 1 件に統合**。85 = `entry_scen.scen_list()` 生成 **86 エントリ**のうち一意名 **85** (`op12` を val=1/0 で 2 本使い同名) | `python3 tools/ott/accept/acc_scen_count.py <scen.json>` |
| dispatcher op 値 | `{'c':'disp'}` step の `op` ユニーク値。op* scenario 名 **64** + GUI 4 (op13/14/15/19) + op1 + op0 = **69** | 同上 |
| cell | DSP e2e の出力 f32 1 要素。bit 一致 = native と 32 bit 完全一致 | `bash tools/ott/ott_e2e.sh` |
| lift 関数数 / 命令数 | `lift_meta.json` の `functions` 配列長 (**override 対象は lift しないため除外**) / 同じファイルの `ninsn` | `python3 tools/ott/accept/acc_lift_set.py` |
| coverage 命令 | native 単歩で実行された命令アドレス集合 (`cov_entry.json` / `cov_crt.json` の `insn`) | 同上 |
| us_per_block / realtime_x | 2000 block × 256 sample の計測区間 ÷ block 数 / 11.61 s 音声 ÷ 実測秒 | `MOD=<cjs> REPEAT=7 node tools/ott/accept/acc_perf.mjs` |
| fn 別照合 / garbage VA | `cmp_entries.py` の `.pdata` 関数単位 (`dsp_verified` / `entry_new_verified` / `reach_only`)。garbage VA = native SIGSEGV の `rax` と wasm `ott_unlifted` の引数 (同一値 = 同一 dispatch 先) | `cmp_entries.py --cov <cov> --covdsp ref/cov_all.json` / `python3 tools/ott/accept/acc_crt_table.py` |

## 2. 検証環境とクリーン HEAD 再現 (規則 45)

| 項目 | 実測 |
|---|---|
| HEAD | `4b162ce`。対象 2 commit = **faf8b0d** (15 file) / **8b31a48** (13 file)。**いずれも tools/ott のみ** (他 dir 0 行)・最大 blob **50,581 B ≤ 20 MiB** |
| snapshot | `git archive HEAD -- tools/ott \| tar -x -C tools/ott/work/verify_4b162ce` (688 KB) と verify2_4b162ce。`../m6 ../m8 ../m9 ../m10 ../shim` は読取専用 symlink |
| 未コミット / ロック | tools/ott 内 **0 件** (クリーン)。他 dir に 56 件 WIP (触らない)。`dir:tools/ott`・`ticket:CAB-137` 取得。CAB-137/138 とも In Review・実装報告 1 件ずつのみ・他セッションの進捗コメントなし (規則 46) |
| 負荷 | 16 コア共有。load average は測定中 **1.4 〜 16.4** に振れた (所要と性能に併記) |

## 3. CAB-137 検収

### 3.1 受入条件と実測

| 受入条件 | 実測 (clean HEAD snapshot) | 実装報告 | 判定 |
|---|---|---|---|
| entry 突合 85 scenario | `entry_e2e.sh` = PASS / **85 PASS / nat_crash 0 / FAIL 0** / `dsp_verified 30 / entry_new_verified 35 / reach_only 0` | 85/85 | **PASS** |
| lift 209 関数 / 13,694 命令 | **207 / 13,690** (`unsup 0 種 / unlifted_callees 36 / overrides 6`) | 209 / 13,694 | **条件付き PASS** (定義差・§3.2) |
| getParameter が xmm0 で返す | `getp_range` 20 idx の **xmm0 が 20/20 bit 一致** かつ `out_f` (float* 側) が **20/20 とも 0** (= 書かない) | xmm0 返値・31 path | **PASS** |
| effGetParamName(0) の訂正 | **訂正不要**。idx 0 = **'Depth'**・idx 19 = **'Bypass'**。21 idx すべて native/wasm byte 一致 | (訂正対象は誤り) | **PASS** (数え方の混同) |
| 性能 202.6 µs/blk = 28.7x | load 1.7〜2.8 で 5 回: **202.8 〜 228.3 µs/blk (25.4 〜 28.6x)** | 202.6 / 28.7x | **PASS** (レンジ化・§5) |
| DSP e2e 維持 / fn 別 65 関数 | **89 scenario / 50,236 cell / max_ulp 0 / state_diff_qwords 0**。30 + 35 = **65**・`reach_only 0` | 同 | **PASS** |

- **重複判定**: CAB-137/138 には実装報告が 1 件ずつのみ。CAB-238/CAB-135 の検収コメント
  (fee6fd9 / 5f3e0af) は**別チケット**であり二重登録ではない。今回の検収コメントは各 1 件 (規則 49-3)。
- **下流**: CAB-132 (x64c 汎用化)・CAB-122 (AudioWorklet ABI) はいずれも Backlog。本チケットの成果は
  両者の上流だが、**本検収では起票せず提案コメントのみ** (規則 42(c))。

### 3.2 lift 集合の差分 (独立再計算で特定した根本原因)

| 比較 | entry 版 | crt 版 |
|---|---|---|
| 実装報告 (未 commit の coverage) | 209 関数 / 13,694 命令 | 260 関数 / 16,378 命令 |
| **コミット済み scenario から再現** | **207 関数 / 13,690 命令** | **258 関数 / 16,374 命令** |
| 差分 | +2 関数 / +4 命令 | +2 関数 / +4 命令 |

- **差分 = 2 関数**: `acc_lift_set.py` の集合差が `main-only = {'180126310', '180126320'}`・`snapshot-only = {}` と機械的に確定。2 関数とも `.pdata` の GAP にあり、`getParameter` の **idx 25..30 case** (0x18011e60c..0x18011e68f) 由来。
- **根本原因 = 未コミット coverage**: 実装報告時の coverage は `getp_range` が **idx 25..30 まで実行**された状態 (43 命令・calltgt +2)。コミット済み `entry_scen.py` は `range(20)` = **idx 0..19 のみ**。私は coverage を 2 回取り直し**完全一致 (5219 insn / 104 calltgt)** を確認 → 差異は乱りではなく定義差。
- **影響**: +2 関数のみ。unsup は両方 0 種・unlifted_callees 36/13 で同一・**85/85 と 9/9 に無影響**。

### 3.3 clean tree で e2e が起動不能だった 2 件 (検収中に発見・修正)

| # | 事象 | 原因 | 修正 |
|---|---|---|---|
| 1 | `entry_e2e.sh` [4/7] の `entry_roots.py` が `cov_entry.json` を読めず `FileNotFoundError` | `entry_nat.py` の `--cov` が coverage をファイルに書いていなかった。runner を再利用する `crt_nat.py:85` には `json.dump(out['cov'], open(a.cov,'w'))` がある | `entry_nat.py` に**同じ 2 行を追加** (対称化) |
| 2 | `crt_e2e.sh` [1/6] の `crt_nat.py` が `libottnatcrt.so` を読めず `OSError` | clean tree では [2/6] の `lift_crt.sh` [1/4] で初めて `.so` が構築される (卵が先か) | `.so` が無ければ先にネイティブハーネスだけ build する 5 行を追加 |

- **修正前 (verify_4b162ce)**: `entry_e2e.sh` = RC=1・`crt_e2e.sh` = **FAIL** (9 FAIL / 85 FAIL)。`work/` に成果物が残っている状態では通ってしまうため、clean tree では quality ゲートが空回りしていた。
- **修正後 (verify2_4b162ce・完全 clean)**: 両方 **RC=0 PASS** (entry 281 s・load 2.90〜2.53 / crt 80 s・load 2.17〜2.58)。§3.1・§4.1 と同じ 85/85・9/9。
- **判定**: e2e の再現性の欠陥であり **lift の正しさ (bit-exactness) には影響なし**。ただし規則 45 を満たしていなかったため受入条件として修正を必須とした。

## 4. CAB-138 検収

### 4.1 受入条件と実測

| 受入条件 | 実測 (clean HEAD snapshot) | 実装報告 | 判定 |
|---|---|---|---|
| 新規 scenario 9 本 | **9/9 PASS** (文字列・rax・obj・alog・am counter 全一致) | 9/9 | **PASS** |
| float formatter の native 突合 | 既定 `100/0.0/--`・035 `34/67/-3.5/BYPASS`・mix ` 0/998/-48/19.1/-20.0/BYPASS`・op34 `OTTOut 1/2` — **13 param すべて native と byte 一致** (op7 経由も一致) | 同 | **PASS** |
| entry 85 を CRT 版で再突合 | **85/85 PASS** (nat_crash 0) — 旧 build で nat_crash だった float 経路も含む | 85/85 | **PASS** |
| DSP e2e 89 scenario・全 cell bit-exact / max_ulp 0 | **PASS** (継続・数値は §3.1 と `tools/ott/REPORT.md`) | 同 | **PASS** |
| 陰性対照 `OTT_CRTINIT=0` | native **SIGSEGV rip=0x1801d2750 rax=0xae64b77e88c8000** / wasm **`ott_unlifted 0xae64b77e88c8000` ret=0x301c3e06** | 同 | **PASS** |
| fail-fast 根因 `ror(0^cookie,50)` | `acc_crt_table.py` の **4 方式で 0x0ae64b77e88c8000 に一致**。enc/dec round-trip も確認 | 同値 | **PASS** |
| override 4 件の機械語 lift 置換 | 4 VA がすべて `lifted` に載り、`overrides` は **8 件** (editor_null / am_shim / fls×4 / cs_ex / gstpaft) で CRT 4 件は消えている | 4 件置換 | **PASS** |
| `_handle_error(double)` の実行 | **`err_zero_disp` の 1 scenario**。`_handle_errorf` / `sqrt(d)` / `sqrtf` は lift 済み・**未実行** (coverage 0 scenario) | err_zero_* 3 scenario | **PASS** (定義差・§4.2) |
| lift 260 / 16,378 | **258 / 16,374** (§3.2) | 260 / 16,378 | **条件付き PASS** |
| 性能 186.3 µs/blk = 31.2x | load 2.2〜2.8 で 5 回: **217.4 〜 229.0 µs/blk (25.3 〜 26.7x)**。186.3 は実測下限を下回る | 186.3 / 31.2x | **条件付き PASS** (レンジ化) |

### 4.2 定義差 2 件の明示 (規則 36)

1. **`_handle_error(double)` の実行 scenario 数**: 実装報告は「err_zero_svf / err_zero_pers /
   err_zero_disp の 3 scenario」だが、`cov_crt.json` の機械的検査では **`err_zero_disp` の 1 scenario のみ**
   (0x1c8c00・0x1c1584・0x1c1ae0 すべてが `err_zero_disp` だけで実行)。`err_zero_svf` / `err_zero_pers` は
   `log(0)` に到達していない。**報告の「3 scenario」は誤りで 1 が正**。影響は注記のみ (bit 突合は成立)。
2. **性能の単発値**: 186.3 µs/blk (31.2x) と entry 版 160.0 µs (36.3x) は負荷依存の単発測定。
   レンジで再掲し、単発値同士の「+16%」比較は削除した。

### 4.3 UCRT 遅延解決表の独立検証 (別アルゴリズム: PE 生バイト読み + ror の 4 方式)

```
__security_cookie (0x180260ce0) = 0x2b992ddfa232  (UCRT 静的既定と一致: True) / cookie & 0x3f = 50
api-set 表 0x18026c9f0: entry 数と PE ファイル生値は `tools/ott/crtinit/REPORT.md` §10 (entry 数 = ott_crt.c の APISET_N) と §2.1 (静的状態) の実測を参照 (本節に数値を書き写さない)
  ror(cookie,50) 方法1(関数)/2(式)/3(文字列)/4(下位抽出) = 0x0ae64b77e88c8000 (4 方式一致: True)
enc(NULL) = rol(0,14) ^ cookie = 0x2b992ddfa232 == cookie: True ; decode(enc(NULL)) = 0 round-trip OK
個別 encoded slot: 0x18026c028 / 0x18026c388 / 0x18026cb40 / 0x18026cb88 (matherr hook)
```

- **静的 vs ランタイム (規則 40)**: PE **ファイル生値**は全 entry が 0 埋め (`crtinit/REPORT.md` §2.1 の静的状態。raw 外は 0)。**native CRT 未初期化 (DllMain 未実行) でもランタイム生値は 0**。`ott_crt_init_tables` はこの 0 を `enc(NULL)=cookie` で埋める = C 等価置換。両側が同一状態になることを 9/9・85/85 が実証。
- **fail-fast 根因は確定**: `decode(0) = ror(cookie,50) = 0xae64b77e88c8000 ≠ 0` → CFG dispatch (0x1801d2750 `jmp rax`) が garbage jump。native SIGSEGV の `rax` と wasm `ott_unlifted` の引数が一致。

## 5. 誤記の修正 (本コミット)

1. `entry/REPORT.md` §0: lift **209 関数 / 13,694 命令 → 207 関数 / 13,690 命令** (数え方 = `lift_meta.json` の `functions` 配列長・override 除外を併記)。
2. `crtinit/REPORT.md` §0: lift **260 関数 / 16,378 命令 → 258 関数 / 16,374 命令** (+2 関数の差分原因を明記)。
3. `entry/REPORT.md` §0・§2.2: dispatcher op 「**63 op → 69 op 値**」 (op* 名 64 + GUI 4 + op1 + op0。数え方を併記)。
4. `entry/REPORT.md` §0: 性能 **202.6 µs/blk (28.7x) 単発 → 202.8〜228.3 µs/blk (25.4〜28.6x)** レンジ (load average 併記)。
5. `crtinit/REPORT.md` §6: 性能 **186.3 µs/blk (31.2x)・entry 版 160.0 µs・+16% → 217.4〜229.0 µs/blk (25.3〜26.7x)** レンジ。単発値同士の +16% は削除。
6. `crtinit/REPORT.md` §8: 「lift 集合 **260 関数**時点 → **258 関数**時点」。

- 1・2 に対し実装報告時の coverage が未コミットの `getp_range` (idx 25..30) 由来だった経緯を REPORT に明記 (再現性・規則 45)。
- **`effGetParamName(0)` の指示内容は誤り**: 実測は idx 0 = **'Depth'**・idx 19 = **'Bypass'**。21 idx すべて
  native/wasm が byte 一致しており lift 側に誤りはない。訂正対象は指示側なので REPORT の修正対象外。

## 6. ネガティブコントロール (規則 41)

`crt_e2e.sh` [5/6] の内蔵陰性対照に加え、本検収で 3 件を新規に実施した。

| # | 対象 | 壊し方 | 結果 |
|---|---|---|---|
| N1 (新規) | CAB-137 の入口拡張 | **入口 roots を含まない DSP 版 build** (75 関数) で entry scenario を実行 | `virt_pname`・`getp_range`・`op0`・`full_cycle` の **4/4 が `UNLIFTED function 0x30128ba0` (VSTPluginMain)** で FAIL = 拡張の効果を実証 |
| N2 (新規) | CRT 初期化の C 等価置換 | CRT 版 build で `_ott_crt_init_tables` を呼ばない | `flt_disp_def`・`op34_outprop` の **2/2 が `UNLIFTED function 0xae64b77e88c8000`** で FAIL = 置換の効果を実証 |
| N3 (e2e 内蔵) | 同上 (native 側) | 同上 | native **SIGSEGV rip=0x1801d2750 rax=0xae64b77e88c8000**。wasm と同一 VA・対応 ret 0x301c3e06 |
| N4 (新規) | `getParameter` の xmm0 返値 | `getp_range` の `out_f` (float* 側) が 20/20 とも 0 かを確認 | **20/20 = 0** → float* は書かれず xmm0 返値 (反対なら値が出る) |

## 7. 実測所要 (規則 38: 実測秒 + load average)

| コマンド (snapshot `verify2_4b162ce`・clean) | 実測 | 開始 load |
|---|---|---|
| `entry/entry_e2e.sh` (全工程) / `crtinit/crt_e2e.sh` (全工程) / `ott_e2e.sh` | **281 s** (85/85) / **80 s** (9/9 + 85/85 + 陰性対照 + 既存 e2e) / 18 s (DSP 89 scenario・全 cell) | 2.90 / 2.17 / 2.25 |
| `lift_entry.sh` / `lift_crt.sh` / `run_matrix.py`×2 | 5.8 s / 7.0 s / 5.4 s・0.7 s | 1.4 / 1.7 / 16.4 |
| coverage 再取得 (`entry_nat.py`) × 2 / `acc_perf.mjs` REPEAT=7 × 3 build | 4 分 44 s / 回 (2 回の coverage は**完全一致**)・各 7〜11 s | 14.0 / 1.7〜2.8 |

所要は snapshot ごとの単発測定 (規則 38 の n≥3 は未取得)。ただし**性能値は §3.1・§4.1 のとおり n≥5 レンジ**を取得済み。`verify_4b162ce` (修正前コード + 手動 step 実行) でも同数値を取得。

## 8. 検証範囲 / 範囲外 (規則 40)

**検証した範囲**: clean HEAD snapshot 2 個 (`git archive` 展開・他 dir 書込 0) での全 e2e 再実行
(entry 85/85・crt 9/9 + 85/85・DSP 89 scenario 全 cell)、lift/cov 集合の別アルゴリズム独立再計算 (`accept/` 5 本)、
ror の 4 方式検算、float formatter の native 文字列 byte 突合 (13 param × 集合)、getParameter xmm0 の
bit・`out_f` 突合、override 4 件の lift 載り確認 (機械的)、ネガティブコントロール 4 件、性能 n≥5 レンジ、
commit 範囲 (tools/ott のみ / 最大 blob 50,581 B / 他 dir 0 行)。

**範囲外**: ① 実機 FL Studio での発音・GUI (OTTEditor / VSTGUI / ERect / HWND。surrogate editor=NULL 経路の戻り突合のみ・CAB-122 領域) ② AudioWorklet ABI 結線 (CAB-122) ③ `_handle_errorf` / `sqrt(d)` / `sqrtf` の実行時 bit 突合 (lift 済み・未実行・入力 scenario 未構築 → (a) CAB-138 にコメント済) ④ AVX/FMA unsup 64 種/473 箇所 の解消 (CAB-135・回帰として確認のみ) ⑤ 無限ルーブ (F7@0x180120632 系・LIFTLIB-2 側・本 e2e は完走) ⑥ native `ott_unlifted` 側の RVA 表記 (`0xae64b77e88c8000` は image 外のため正規化されず wasm は `0xae64b77b88c8000` とずれる。同一 VA は別途検証済)。

## 9. 未解決 / 限界と起票先 (規則 42)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| e2e が clean tree で起動不能だった 2 件 (`entry_nat.py --cov` 未書込 / `crt_e2e.sh` の .so 構築順) | 規則 45 を満たせず `work/` 残存時はゲートが空回り | **(b) 本コミットで修正済** (差分は §3.3) |
| lift 集合の報告値 (209/13,694・260/16,378) が未コミット coverage 由来。コミット済みでは 207/13,690・258/16,374 | 報告値の再現性。bit-exactness に影響なし | **(a) CAB-137 / CAB-138 に検収コメント済**。REPORT も訂正済 |
| `_handle_error(double)` の実行 scenario 数の誤記 (3 → 実際は 1) | 注記の正確性のみ | **(a) CAB-138 に検収コメント済** |
| `_handle_errorf` / `sqrt(d)` / `sqrtf` が lift 済み・未実行 | 該当 3 関数の実行時 fidelity は未検証 | **(b) 子チケット候補を提案** (起票は main 判断・規則 42(c)) |
| `effGetParamName(0)` が指示では "Bypass" とされたが実測は 'Depth' (idx 19 = 'Bypass') | 数え方の混同。lift に誤りなし | 本 REPORT §5 に明記。指示側の誤りなので起票不要 |

## 10. 再現

```sh
SNAP=tools/ott/work/verify2_4b162ce/tools/ott   # clean HEAD snapshot (修正込み)
cd $SNAP && bash ott_e2e.sh                     # 18 s: DSP 89 scenario・全 cell bit-exact (max_ulp 0・正本 tools/ott/REPORT.md)
cd $SNAP && bash entry/entry_e2e.sh             # 281 s: entry 85/85 PASS
cd $SNAP && bash crtinit/crt_e2e.sh             #  80 s: 9/9 + 85/85 + 陰性対照 + 既存 e2e PASS
# 独立再計算 (本検収で新規: tools/ott/accept/ 5 本)
cd $SNAP && python3 accept/acc_scen_count.py work/entrylift/scen.json   # scenario/op 数え方
cd $SNAP && python3 accept/acc_lift_set.py      # lift 集合 + coverage 差分の機械検査
cd $SNAP && python3 accept/acc_crt_table.py     # UCRT 表 + ror の 4 方式検算
cd $SNAP && python3 accept/acc_pname.py work/entrylift/matrix_full     # param 名/label/display + xmm0
cd $SNAP && MOD=$PWD/work/entrylift/ottl_entry.cjs REPEAT=7 node accept/acc_perf.mjs   # 性能レンジ
# ネガティブコントロール (§6 N1/N2 と同一)
cd $SNAP && MOD=$PWD/work/lift/ottl.cjs SCEN=$PWD/work/entrylift/scen.json NAME=virt_pname OUT=/tmp/w.json node entry/entry_wasm.mjs
cd $SNAP && OTT_CRTINIT=0 MOD=$PWD/work/crtlift/ottl_crt.cjs SCEN=$PWD/work/crtlift/scen_crt.json NAME=flt_disp_def OUT=/tmp/w.json node crtinit/crt_wasm.mjs
# 前提: ott_e2e.sh が PASS する環境 (python3 capstone/pefile, gcc, emsdk 6.0.12, node ≥22, setarch)
```

## 11. 環境前提 (規則 43)

- 環境: `bash tools/ott/env.sh` で PATH (node 26.10 / emsdk 6.0.12、所在は `docs/REFERENCES.md` `[EMSDK]`) と TMPDIR を修復。`crt_e2e.sh` は node を `$EMSDK/node/24.19.0_64bit/bin/node` に固定 (`NODE` で切替可) し相対パスを参照するため **cwd = tools/ott で実行**すること。必要: python3 (capstone, pefile), gcc/clang, node ≥ 22。DLL = `docs/REFERENCES.md` `[ANALYSIS-PLUGINS]` の `plugins/ott/binaries/OTT_vst2_win64.dll`。snapshot の `../m6 ../m8 ../m9 ../m10 ../shim` は symlink (読取専用)。
- **教訓**: clean tree で e2e を回すと `work/` が空のため step 間の依存 (.so・coverage・scen.json) が露出する。**e2e は `work/` クリア後に 1 回通すまで信用しない** (今回 2 件が隠れていた)。**新規資産** `tools/ott/accept/` (5 本) は他系統でも流用可。

## 12. 既知欠陥類型 (DEFECTS.md) との関係 (規則 44)

`docs/DEFECTS.md` を読了。該当 ID / 該当なし:

- **該当あり**: **D11 / D14 / D16** (data 窓の過小/過大 — 本 e2e の textref 窓 96→256 B と同型・対処済)、
  **D15** (メモリ間接 call 脱落 — `call [rax+0x58/0x60]` と CRT の api-set `jmp rax` (0x1801d2750) が同型・伏線)、
  **D9** (jump table — dispatcher 2 段 switch と `getParameter` 31 case 表。x64c の table 復元で対処済・85/85 が証拠)。
- **該当なし**: D1a/D1b (ucomis 由来 jcc)・D2/D3 (mov128/store)・D7/D8 (stack 引数・rax 戻り値)。ただし検出範囲は 85 + 89 scenario 内 (規則 40)。
- **新類型の行案** (DEFECTS.md は他担当領域なので直接編集せず記載): 「**coverage/scenario の未コミット差分が報告値になる**」(209 vs 207)。症状 = 報告値が clean HEAD で再現しない / 原因 = coverage を採った scenario 定義とコミット済み定義の差 / 観測 = `main-only = {'180126310','180126320'}`、43 命令が getParameter idx 25..30 由来 / 検出信号 = `acc_lift_set.py` の coverage 集合差 / 修復 = coverage の scenario をコミットする、または数え方の定義を必ず書く。
