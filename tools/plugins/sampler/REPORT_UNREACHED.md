# tools/plugins/sampler/REPORT_UNREACHED.md — #667 total2 外の非共通関数の参照分類 (RVA32 表・命令内即値・outside からの呼出) と閉包 total3

`REPORT.md` の行数上限 (250 行、`docs/DOC_MAP.md` §1) のため分割。 節番号は REPORT.md に合わせる。 前提の定義・語彙は `REPORT_LEA.md` §2c (total2)。

本 PR (#720) は **#667** (`closure_unreached.py`・`unr_e2e.sh`・本 REPORT §2d) と **#707** (export 名の改名・`export_rename.py`・`unr_lift.sh`・`unr_nega.sh`・§2e) の両方を含む。 #708 (#667 の PR) は base ブランチ `627-sampler-lea-closure` が #676 の merge で削除され自動 close されたため、scope を本 PR に再定義した (PM 判断 (b))。

## 2d. total2 外の非共通関数の分類と total3 閉包

**結論 (先出し)**

- total2 外の非共通 **2,653 関数 / 1,200,793 B** の排他分類 (優先順位 (a)>(b)>(c)>(c-lea)>(d)): **(a) RVA32 表 314 関数 / 27,031 B**、(b) 命令内即値 **0 件**、(c) total2 外の呼出 **750 関数 / 406,591 B**、(c-lea) total2 外の lea **112 関数 / 28,227 B**、**(d) 参照なし 1,477 関数 / 738,944 B**。 排他合計 = 2,653 / 1,200,793 (検査 U4 PASS)。
- 到達しうる根 = (a) ∪ (b_live) = 314 関数 / 27,031 B。 **total3 = 4,231 関数 / 1,456,503 B** (total2 から **+415 関数 / +65,994 B**、うち根 314 + 根から呼ばれて入った 101 (推定ではなく差分の実測))。 未到達 (非共通 − total3) = 2,238 関数 / 1,134,799 B。
- **字義どおり根 = (a) ∪ (b) の上界は 7 本とも total3 と同値** (即値の参照が 0 件のため)。
- **lift**: `judge.py shells` は 7/7 PASS (lift_rc / emcc_c_rc / f80 が全 0) だが、**range 欠落監査 (`indirect_defs.py`) が 5 関数 (4 block) で FAIL**。 `unr_e2e.sh` は exit 1 で `[unr_e2e] OK` は出ない。 欠落 5 件は RetDec が export 名で命名したことが原因 (下記 §2d-4・§2e。 旧「畳み込み」説は誤り)。
- **AC 達成状況**: AC1 達成 / AC2 **未達** (閉包と検査 U1–U5 は PASS、range 監査が FAIL。 ※ この時点の結論。 §2e で解消 = AC2 達成) / AC3 達成 (d = 1,477 関数 / 738,944 B)。 Closes ではなく Refs・draft PR が妥当 (PM 判断)。

**既知類型との関係** (`docs/DEFECTS.md`): **該当なし** (分類と到達性の判定。 lift の変換規則は変更していない)。 range 欠落 5 件は既知の D1a〜D16 のどれにも対応づけていない → 新規類型の候補 (§7d 参照。 DEFECTS.md は本 REPORT では編集しない)。

再現: `bash tools/plugins/sampler/unr_e2e.sh` (前提生成 → 分類・total3 → lift → 判定 → 欠落監査) / `bash tools/plugins/sampler/unr_nega.sh` (ネガコン)。 `lift/plugin_closure.py` は変更していない。

### 2d-1. 定義 (`closure_unreached.py`)

- nonfw = 非共通関数 (`closure_indirect.Pe.nonfw`)。 total2 = `closure_lea.lea_fixpoint` の閉包 (#627)。 outside = nonfw − total2。
- **(a) RVA32 表**: outside の開始 RVA が、非実行 (IMAGE_SCN_MEM_EXECUTE が立たない) かつ初期化済み (0x40) の節に、節先頭から **4 バイト整列の LE u32** として載る (.pdata 除外)。
- **(b) 命令内即値**: nonfw の本体を capstone で命令単位に復号し、call/jmp 以外の IMM オペランド値 v が 開始 VA (imm_va: v = base + RVA) または 開始 RVA (imm_rva: v = RVA) に等しい。 b_all = 参照元が nonfw の任意の本体、**b_live = 参照元が total2 内の本体**。
- **(c) call/jmp**: outside 関数からの call/jmp rel32 の先 (outside の呼び元のみ)。 (a)(b) に該当するものを除く。
- **(c-lea)**: outside 関数からの lea [rip+X] の先 (outside の参照元のみ)。 (a)(b)(c) に該当するものを除く。
- **(d) 参照なし**: 上記のいずれも無い (排他)。 字義 (a)(b)(c) のいずれも無い は別列で併記 (c-lea 分が増える)。
- **根 (AC2) = (a) ∪ (b_live)**。 **逸脱の理由**: 字義どおり (b_all) を根にすると、死んだ関数 (outside) の即値参照で根が増える。 本実装は参照元が total2 内の即値に限り、b_all のみで参照されるものは「参照元が到達した時だけ BFS で入る」扱いとした。 字義どおりの上界は下の表に併記する。
- **total3** = total2 ∪ 根 から、辺 = call/jmp rel32 ∪ lea [rip+X] ∪ 即値 (imm_va ∪ imm_rva) で BFS。 辺が全部入っているため 1 回で固定点 (U2 で別ループ検査)。

### 2d-2. 分類表 (関数 / B、排他。 優先順位 (a)>(b)>(c)>(c-lea)>(d))

| プラグイン | 非共通 | total2 | outside | (a) RVA32 | (b) 即値 | (c) call/jmp | (c-lea) lea | **(d) 参照なし** |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| FL Keys | 153 / 77,996 | 84 / 32,913 | 69 / 45,083 | 17 / 986 | 0 / 0 | 14 / 8,271 | 1 / 84 | **37 / 35,742** |
| FPC | 801 / 413,955 | 341 / 131,429 | 460 / 282,526 | 77 / 8,791 | 0 / 0 | 146 / 106,462 | 39 / 12,090 | **198 / 155,183** |
| Fruity Granulizer | 264 / 99,246 | 165 / 45,587 | 99 / 53,659 | 14 / 595 | 0 / 0 | 19 / 4,775 | 5 / 408 | **61 / 47,881** |
| Fruity Slicer | 341 / 117,576 | 195 / 57,453 | 146 / 60,123 | 18 / 873 | 0 / 0 | 32 / 8,466 | 6 / 359 | **90 / 50,425** |
| Fruity Slicer 2 (殻) | 498 / 293,562 | 198 / 69,184 | 300 / 224,378 | 24 / 3,886 | 0 / 0 | 102 / 83,638 | 13 / 4,785 | **161 / 132,069** |
| Slicex | 1,172 / 508,391 | 709 / 262,399 | 463 / 245,992 | 71 / 7,039 | 0 / 0 | 111 / 95,110 | 16 / 4,415 | **265 / 139,428** |
| Soundfont Player | 3,240 / 1,080,576 | 2,124 / 791,544 | 1,116 / 289,032 | 93 / 4,861 | 0 / 0 | 326 / 99,869 | 32 / 6,086 | **665 / 178,216** |
| **計** | 6,469 / 2,591,302 | 3,816 / 1,390,509 | **2,653 / 1,200,793** | **314 / 27,031** | **0 / 0** | **750 / 406,591** | **112 / 28,227** | **1,477 / 738,944** |

排他合計: 314 + 0 + 750 + 112 + 1,477 = 2,653 (検査 U4 PASS、B も一致)。 非共通の計と total2 の計は REPORT_LEA.md §2c と一致 (6,469 / 2,591,302、3,816 / 1,390,509)。

### 2d-3. 非排他の内訳・根・total3・上界 (関数 / B)

| プラグイン | (a) | (b) va / rva | (c) | (c-lea) | (a)(b)(c) いずれも無い | 根 | total2 → total3 (増分) | 上界 (字義 (a)∪(b)) | 未到達 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| FL Keys | 17 / 986 | 0 / 0 | 14 / 8,271 | 1 / 84 | 38 / 35,826 | 17 / 986 | 84 → **108** (+24 / +6,325) | 108 / 39,238 | 45 / 38,758 |
| FPC | 77 / 8,791 | 0 / 0 | 150 / 108,790 | 40 / 12,316 | 237 / 167,273 | 77 / 8,791 | 341 → **432** (+91 / +12,460) | 432 / 143,889 | 369 / 270,066 |
| Fruity Granulizer | 14 / 595 | 0 / 0 | 19 / 4,775 | 5 / 408 | 66 / 48,289 | 14 / 595 | 165 → **180** (+15 / +618) | 180 / 46,205 | 84 / 53,041 |
| Fruity Slicer | 18 / 873 | 0 / 0 | 32 / 8,466 | 6 / 359 | 96 / 50,784 | 18 / 873 | 195 → **214** (+19 / +896) | 214 / 58,349 | 127 / 59,227 |
| Fruity Slicer 2 (殻) | 24 / 3,886 | 0 / 0 | 104 / 84,406 | 14 / 5,175 | 174 / 136,854 | 24 / 3,886 | 198 → **240** (+42 / +9,214) | 240 / 78,398 | 258 / 215,164 |
| Slicex | 71 / 7,039 | 0 / 0 | 119 / 97,907 | 16 / 4,415 | 281 / 143,843 | 71 / 7,039 | 709 → **809** (+100 / +20,329) | 809 / 282,728 | 363 / 225,663 |
| Soundfont Player | 93 / 4,861 | 0 / 0 | 327 / 99,892 | 34 / 6,442 | 697 / 184,302 | 93 / 4,861 | 2,124 → **2,248** (+124 / +16,152) | 2,248 / 807,696 | 992 / 272,880 |
| **計** | **314 / 27,031** | **0 / 0** | 765 / 412,507 | 116 / 29,199 | 1,589 / 767,171 | **314 / 27,031** | 3,816 → **4,231** (+415 / +65,994) | **4,231 / 1,456,503** | **2,238 / 1,134,799** |

- 字義どおり根 (a)∪(b) の上界 = 根 (b_live) と同値。 (b) の実測は 7 本とも 0 件 (capstone 復号の IMM オペランドで非共通の開始 VA/RVA に一致するもの無し)。
- 全オフセットの byte 走査 (検査 U1 の別算法) では、nonfw 本体中に VA 下位 32 bit / RVA と一致する 4 バイト列が FPC 1 ・ Granulizer 1 ・ Slicer 1 ・ Slicex RVA 2 ・ Soundfont VA 2 / RVA 8 あるが、capstone は IMM オペランドとして復号しなかった (推定: 変位部や命令内の偶然一致。 個別には未確認)。 これは byte 走査が capstone の上位集合であることの確認 (U1) に使い、根には入れていない。
- **根 314 関数のうち 309 関数は RetDec 出力で独立の関数として出る。 残り 5 関数 (4 block) が欠落**: §2d-4 を参照。
- 増分 +415 = 根 314 + 根から call/jmp・lea で入った 101 (差分の実測)。

### 2d-4. lift 7/7 (`unr_lift.sh` → `judge.py shells` → `indirect_defs.py`)

| プラグイン | block | ranges 関数 / B | final.ll define | judge (lift_rc / emcc_c / f80) | 未実装 helper | f80 (raw → lowering 後) | emcc -c (raw → lowering 後) | lift 秒 | range 欠落 (`indirect_defs`) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| FL Keys | 22386 | 108 / 39,238 | 112 | PASS | 0 | 0 | 0 | 4 | **1** (0x71f030) |
| FPC | 23617 | 432 / 143,889 | 434 | PASS | 0 | 0 | 0 | 13 | 0 |
| Fruity Granulizer | 23658 | 180 / 46,205 | 180 | PASS | 1 (rep_stosb_memset) | 3 → 0 | 1 → 0 | 6 | 0 |
| Fruity Slicer | 23662 | 214 / 58,349 | 216 | PASS | 1 (rep_stosb_memset) | 3 → 0 | 1 → 0 | 6 | 0 |
| Fruity Slicer 2 (殻) | 23663 | 240 / 78,398 | 240 | PASS | 0 | 3 → 0 | 1 → 0 | 8 | **2** (0x842950, 0x842fc0) |
| Slicex | 24172 | 809 / 282,728 | 813 | PASS | 0 | 0 | 0 | 25 | **1** (0x879ed0) |
| Soundfont Player | 24175 | 2,248 / 807,696 | 2,262 | PASS | 0 | 0 | 0 | 68 | **1** (0x762c70) |

- **judge.py shells: PASS 7/7**。 lift_rc・emcc_c_rc・f80 は全 0 (lowering 後)。 未実装 helper は許容内 (Granulizer・Slicer 各 1 = #538 の既知)。 f80 の lowering (`p0c/f80_lower.py`) は lea 段と同じ 3 block で、bit-exact は未検証 (#197)。
- **indirect_defs.py: FAIL** (欠落 5 件 / 4 block)。 `unr_e2e.sh` は exit 1。 lea 段 (total2) では欠落 0 だったので、欠落は total3 で新たに入った根に由来する。
- **§2d-4 (欠落の原因、実測)**: 5 件は全て RVA32 表 (a) の根。 (下記の訂正 §2e を参照。 旧記述の「親関数への畳み込み」は誤り) RetDec は export 表に載る関数を export 名 (例: `@CreatePlugInstance`) で出力し、`function_<VA>` で出していなかった。 対象は FL Keys 0x71f030 (`CreatePlugInstance`)、Slicer 2 0x842950 (`DecodeAudioFile`) / 0x842fc0 (`FinishAudioFile`)、Slicex 0x879ed0 (`CreatePlugInstance`)、Soundfont 0x762c70 (`CreatePlugInstance`)。 改名前の出力では `function_<VA>` の参照は 0 件。 `export_rename.py` で改名して解消 (§2e)。
- 比較: 同じ 7 本で total2 の lea 段は欠落 0 (REPORT_LEA.md §2c)。 欠落を「定義を緩めて通す」ことはしていない (監査の定義は不変)。

- **訂正 (#707、§2e)**: 上の「親関数の本体に畳み込まれている」は誤り。 5 関数は畳み込まれていない。 RetDec が export 表に載る関数を **export 名で命名**し (`define i64 @CreatePlugInstance`)、`function_<VA>` で出していなかった。 本体は欠けていない。 `dec_label_pc_<VA>:` が define の先頭ラベルとして入っていることを確認済み。

### 2d-5. 検査 U1–U5 (`closure_unreached.py`、7 本 × 5 検査 全て PASS)

**U1** (i) 別算法: capstone 版の RVA32 集合 ⊆ 非実行節の全オフセット byte 走査、即値 (VA 下位 32 bit / RVA) 集合 ⊆ nonfw 本体の全オフセット byte 走査 / **U2** (ii) 固定点の独立検証: total3 の全関数の call/jmp・lea・即値の先が非共通なら total3 に入る (漏れ 0) かつ 根 (a)∪(b_live) ⊆ total3 (根の漏れ 0) / **U3** (iii) total2 ⊆ total3 ⊆ nonfw、total2 が `lea.json` (#627) と一致 / **U4** (iv) 排他合計 = outside / **U5** (v) outside の 8 バイト VA dataref = 0 (既存の total 定義と整合)。

### 2d-6. 検証の所要 (n=1、逐次・単一プロセス、4 core)

| 項目 | 実測 |
|---|---|
| 前提生成 (初回。 inventory 含む、`win_scan` 〜 `closure_lea`) | 549 s (rc 0。 inventory 段の負荷 load average 17 の時間帯あり) |
| `closure_unreached.py` (7 本) | 26.8 s (rc 0、PASS 5 × 7) |
| `unr_lift.sh` (7 本、逐次) | 138 s (wall、40:15 → 42:33)。 block 別 4 / 13 / 6 / 6 / 8 / 25 / 68 s |
| `unr_e2e.sh` (前提込み、lift 込み) | **176 s、rc 1** (indirect_defs FAIL)。 load average (1 分) 開始 1.06 → 終了 1.08 |
| `unr_nega.sh` | 129 s、rc 1 (§2d-7 の NC2 / 対照 NC6 が不一致)。 load average 1.30 → 1.11 |

### 2d-7. ネガティブコントロール (`unr_nega.sh`、9 項目中 7 が期待どおり)

| NC | 壊した入力 | 期待 | 実測 |
|---|---|---|---|
| 対照 | `closure_unreached.py` (無改変) | rc 0 | **rc 0** ✓ |
| NC1 | BFS の seed から (a) RVA32 の根を外す | U2 FAIL | **rc 1 (U2)** ✓ |
| NC2 | BFS の辺から命令内即値を外す (U2 の検証側は残す) | U2 FAIL | **rc 0 ✗**。 即値の辺は 7 本とも 0 件 (§2d-3) のため、外しても結果が変わらない。 **本データでは識別力が無い** |
| NC3 | 排他分類の (c) に (a) を二重計上 | U4 FAIL | **rc 1 (U4)** ✓ |
| NC4 | capstone 側の RVA32 集合に偽の値 0x7fffff01 を注入 | U1 FAIL | **rc 1 (U1)** ✓ |
| NC5 対照 | `judge.py shells` (無改変 status_run.csv) | rc 0 | **rc 0** ✓ |
| NC5 | FL Keys の行に emcc_c_rc=1 | judge FAIL | **rc 1** ✓ |
| NC6 対照 | `unr_e2e.sh --skip-lift` (無改変) | rc 0・OK あり | **rc 1 ✗** (range 欠落監査 FAIL のため。 実データの不合格を正しく検出している) |
| NC6 | 同 + emcc_c_rc=1 の行を追記 | rc ≠ 0・OK 無し | **rc ≠ 0・OK 無し** ✓ |

9 項目中 7 が期待どおり、2 が不一致 (NC2: 非識別、NC6 対照: 実データの FAIL)。 NC 実行後、`status_run.csv` は元の 8 行 (header + 7) に復元した。

## 2e. #707: export 名による命名と改名 (AC2 の解消)

**結論 (先出し)**: §2d-4 の 5 関数 (4 block) は畳み込まれていなかった。 RetDec が PE の export 表に載る関数を **export 名で命名**し、`function_<VA>` で出していなかった。 `closure_unreached.py` の RVA32 根 (a) は export 表の EAT の RVA と一致する。 `export_rename.py` (lift 直後に実行) で範囲 VA に対応する define だけ `function_<VA>` に改名し、監査 (`indirect_defs.py`) の定義は変えずに **7/7 PASS** (`unr_e2e.sh` rc 0)。

**根拠 (実測)**
- FL Keys (22386) の RetDec 出力 `p.drc.ll` の define 112 件のうち 111 件は `function_<VA>`、1 件だけが `define i64 @CreatePlugInstance`。 その先頭ラベルは `dec_label_pc_71f030:` (5 根のうち実測したのはこの 1 件のみ)。
- PE の export 表 (pefile、ImageBase 0x400000 基準): 22386 `CreatePlugInstance` = VA 0x71f030 / 23663 `DecodeAudioFile` 0x842950・`FinishAudioFile` 0x842fc0 / 24172 `CreatePlugInstance` 0x879ed0 / 24175 `CreatePlugInstance` 0x762c70。 5 根すべて export 表の VA と一致。
- 改名対象は 5 件 (`work/sampler/unrlift/<blk>/export_rename.json` の `refs_renamed` は各 1 = define 本体のみ。 他関数からの参照は 0)。 改名後の `p.final.ll` に export 名の define/参照は 0 件 (`grep -c`)。

**改名規則 (`sampler/export_rename.py`)**: export の VA (ImageBase + RVA) が ranges に含まれ、かつ `define @<export 名>(` が出力にある組だけ。 参照 `@<export 名>` も `@function_<VA>` に書き換える。 改名先が既に出力にあれば衝突として異常終了 (黙って上書きしない)。 改名前の出力は `p.prerename.ll` に残す。

**検証 (コミット `22cb2fd`、検証起点。 以後の commit は本 REPORT のみ)**

| 項目 | 結果 |
|---|---|
| `unr_e2e.sh` (前提は生成済み、closure・lift を再実行) | real 3m54.1 s / user 3m51.9 s、**rc 0**、`[unr_e2e] OK` |
| lift 秒 (FL Keys / FPC / Granulizer / Slicer / Slicer 2 / Slicex / Soundfont) | 3 / 9 / 4 / 5 / 6 / 19 / 51 s |
| `indirect_defs` (range 欠落監査) | **PASS 7/7**、欠落 0 (5 根は `define @function_<VA>` で出る) |
| 基線 (改名前、commit `3752fed`) | rc 1、欠落 5 件 / 4 block (§2d-4 と同じ) |
| `unr_nega.sh` | rc 1。 NC0・NC1・NC3・NC4・NC5・NC6・**NC7 (改名を外すと indirect_defs FAIL)** は期待どおり。 **NC2 のみ不一致** (即値の辺が 7 本とも 0 件で U2 が FAIL しない。 §2d-7 の既知の非識別。 本 issue の範囲外、#667 に残す) |
| 負荷 | 前提生成 (基線の初回) で uptime load 最大 16.32 (4 core、inventory の並列)。 本 run の load は未計測 (終了時の 1 分平均 1.00) |

**再検証 (HEAD `7b7a7b9c`、main `c5df4657` を取り込んだ後。 検証起点はこの HEAD)**

| 項目 | 結果 |
|---|---|
| `unr_e2e.sh` (前提生成込み、新規 worktree) | real 757.49 s / user 2447.20 s、**rc 0**、`[unr_e2e] OK`。 `judge.py shells` PASS 7/7、`indirect_defs` PASS 7/7 (欠落 0) |
| `unr_nega.sh` | real 128.54 s / user 129.59 s、rc 1 (NC2 のみ不一致: 即値辺 0 件で非識別。 他は期待どおり。 NC8 (改名先が既存の衝突) は `export_rename.py` 非 0 で ok) |
| total3 (7 本) | FL Keys 108 / Granulizer 180 / Slicer 214 / Slicer 2 240 / FPC 432 / Slicex 809 / Soundfont 2,248 (いずれも §2d-3 と同値。 U1–U5 PASS) |
| `find tools/plugins/sampler -size +20M` | 0 件 |

**再検証 (HEAD `83450b3f`、`TMPDIR=$RUNNER_TEMP`、PR head の検証起点。 コード差分は `1a27d100` 以後なし)**

| 項目 | 結果 |
|---|---|
| `unr_e2e.sh` (前提生成込み) | elapsed 520 s (wall)、**rc 0**、`[unr_e2e] OK`。 load 1.20 → 2.38 (4 core) |
| `judge.py shells` / `indirect_defs` | PASS 7/7 / PASS 7/7 (欠落 0。 FL Keys 108 / FPC 432 / Granulizer 180 / Slicer 214 / Slicer 2 240 / Slicex 809 / Soundfont 2,248) |
| `unr_nega.sh` | elapsed 104 s、**rc 1**。 NC0・NC1・NC3〜NC8 は期待どおり。 NC2 のみ不一致 (期待 1・実測 0。 即値辺 0 件で非識別。 #667 に残す) |

**検証 (コミット `273cc10`、改名失敗の rc 反映 + NC8 追加後。 レビュー指摘への対応)**

| 項目 | 結果 |
|---|---|
| `unr_e2e.sh` (`TMPDIR=$RUNNER_TEMP`、前提込み) | real 369 s、**rc 0**、`judge shells: PASS 7/7`、`indirect_defs: PASS 7/7`、`[unr_e2e] OK` |
| `unr_nega.sh` | real 71 s、rc 1。 NC0・NC1・NC3〜NC8 は期待どおり (**NC8 = 改名先の衝突で `export_rename.py` が非 0 → 期待どおり**)。 **NC2 のみ不一致** (既知。 即値辺 0 件) |
| 負荷 | 開始 load 0.33 (1 分)、e2e 終了時 3.42、nega 終了時 1.71 |

**検証範囲 / 範囲外**: 範囲内は「5 根が独立の define として lift に出ること」と監査の通過。 改名は symbol 名だけの変更で本体は不変 (先頭ラベルの確認は FL Keys の 1 件のみ、残り 4 件は未確認)。 範囲外: wasm リンク、実行時の到達性 (表経由の呼出しで `function_<VA>` が解決されるか)、差分試験 (bit-exact)。 通過 ≠ 正しさ。

**未解決 (起票先)**

| 未解決 | 影響 | 起票先 |
|---|---|---|
| NC2 が非識別 (即値辺 0 件、`unr_nega.sh` rc 1) | 即値検査の識別力は未確認 | #667 にコメント (既存) |
| 改名後の `function_<VA>` の wasm リンク・実行時解決は未検証 | 表経由の呼出しで未定義にならないかは未確認 | #197 / #667 |
| (d) 参照なし 1,477 関数 / 738,944 B は dead code 候補にすぎない | 間接経路の可能性 | #667 (次タスク) |

**既知類型との関係 (`docs/DEFECTS.md`)**: 該当なし。 §7d の「関数の畳み込み」候補は取り下げ (誤り)。 export 名命名は lift の命名規則の問題で、lift の変換規則は変えていない。 DEFECTS.md は編集していない。

## 6c. 検証起点・取りこぼし確認

- 検証起点 commit: **b36fef5** (`feat(plugins): sampler unreached-function classification and total3 closure (Refs #667)`)。 分類・total3・lift・e2e・ネガコンは全て b36fef5 のスクリプトで実行。 以後の commit はこの REPORT のみ。
- `git status --porcelain=v1 -- tools/plugins/sampler`: 実行後も空 (取りこぼし・混入なし)。 `tools/plugins/work/` (gitignore) の生成物は未 commit。
- `find tools/plugins/sampler -type f -size +20M` = **0 件**。
- 検証範囲: 分類・閉包・lift の判定 (lift 通過と range 監査)。 範囲外: 差分試験 (bit-exact)・wasm リンク・実行時の到達性・根 314 関数の偶発一致の判別。 通過 ≠ 正しさ。

## 7c. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (解消・#707) RetDec が RVA32 根 5 関数を export 名で命名 (畳み込みではない、§2e) | 改名で解消 (`indirect_defs` PASS 7/7)。 wasm リンク・実行時の到達性は未検証 | #707 (本 PR) |
| 即値辺が 7 本とも 0 件 → NC2 が非識別 | 即値検査の識別力は本データでは未確認。 即値参照が現れた engine で要再確認 | #667 にコメント |
| 字義の根 (a)∪(b) と (b_live) の差が 0 件 | 差が出るのは即値参照が出た時のみ。 現データでは判断に影響しない | #667 にコメント (設計の記録) |
| 根 314 関数の偶発一致 (数値定数との偶然の一致) は未判別 | RVA32 の判定は「整列 4 バイト値 = RVA」のみ。 表らしさ (連続性) は未検査 | #667 にコメント |
| (d) 参照なし 1,477 関数 / 738,944 B は dead code 候補にすぎない | 間接経路が他にある可能性。 未使用の確定ではない | #667 にコメント / 次タスク (§8c) |
| total3 の wasm リンク・実行時の到達性 | 範囲外。 lift 通過 ≠ 正しさ | #667 にコメント |
| f80 lowering の対象 (lea 段と同じ 3 関数 × 3 block) の bit-exact 未検証 | 差分試験の対象に入るか未定 | #197 にコメント (既存) |

## 7d. 既知類型との関係 (DEFECTS.md の候補行)

- 該当なし (本 REPORT の対象は分類と到達性判定で、lift の変換規則は不変)。
- 新規候補 (PM 判断。 DEFECTS.md は編集していない): 取り下げ (export 名命名、§2e)。

## 8c. 次タスク提案

1. (完了・#707 §2e) 5 関数 (4 block) の欠落は export 名命名が原因で、`export_rename.py` で解消 (AC2 達成)。 残りは改名後の `function_<VA>` の wasm リンク・実行時解決の検証 (#197 / #667 に起票)。
2. (c) 750 関数 / 406,591 B の呼び元 (outside 同士の呼出鎖) を辿り、どこまでが dead 側かを確定する。
3. (d) 1,477 関数 / 738,944 B の dead code 候補を、同 DLL 内の他の参照 (未確認の間接経路) で検証する。
