# tools/plugins/sampler/REPORT_UNREACHED.md — #667 total2 外の非共通関数の参照分類 (RVA32 表・命令内即値・outside からの呼出) と閉包 total3

`REPORT.md` の行数上限 (250 行、`docs/DOC_MAP.md` §1) のため分割。 節番号は REPORT.md に合わせる。 前提の定義・語彙は `REPORT_LEA.md` §2c (total2)。

## 2d. total2 外の非共通関数の分類と total3 閉包

**結論 (先出し)**

- total2 外の非共通 **2,653 関数 / 1,200,793 B** の排他分類 (優先順位 (a)>(b)>(c)>(c-lea)>(d)): **(a) RVA32 表 314 関数 / 27,031 B**、(b) 命令内即値 **0 件**、(c) total2 外の呼出 **750 関数 / 406,591 B**、(c-lea) total2 外の lea **112 関数 / 28,227 B**、**(d) 参照なし 1,477 関数 / 738,944 B**。 排他合計 = 2,653 / 1,200,793 (検査 U4 PASS)。
- 到達しうる根 = (a) ∪ (b_live) = 314 関数 / 27,031 B。 **total3 = 4,231 関数 / 1,456,503 B** (total2 から **+415 関数 / +65,994 B**、うち根 314 + 根から呼ばれて入った 101 (推定ではなく差分の実測))。 未到達 (非共通 − total3) = 2,238 関数 / 1,134,799 B。
- **字義どおり根 = (a) ∪ (b) の上界は 7 本とも total3 と同値** (即値の参照が 0 件のため)。
- **lift**: `judge.py shells` は 7/7 PASS (lift_rc / emcc_c_rc / f80 が全 0) だが、**range 欠落監査 (`indirect_defs.py`) が 5 関数 (4 block) で FAIL**。 `unr_e2e.sh` は exit 1 で `[unr_e2e] OK` は出ない。 欠落 5 件は「畳み込み」ではなく、RetDec が export 名 (`@CreatePlugInstance` 等) で定義したために `function_<VA>` の define が無いもの (下記 §2d-4。 #707 のコメントで訂正)。**5 件とも PE export 関数** (§2d-9)。 修正 (改名) は #720 (未 merge) にある。
- **AC 達成状況**: AC1 達成 / AC3 達成 (d = 1,477 関数 / 738,944 B) / AC2 は **#707 (PR #720) へ分割** (PM 判断 2026-10-13、#667 に記録)。 AC2 の閉包と検査 U1–U5 は PASS、judge 7/7 PASS だが、range 監査 (`indirect_defs.py`) は 5 件で FAIL し、この gate は #707 の merge まで不合格のまま。 gate は緩めていない。 Closes なし (Refs #667)。 PR は ready (非 draft)。

**既知類型との関係** (`docs/DEFECTS.md`): **該当なし** (分類と到達性の判定。 lift の変換規則は変更していない)。 range 欠落 5 件は命名の問題で、既知の D1a〜D16 とは対応づけない。 新類型の候補は取り下げ (§7d)。

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
- 全オフセットの byte 走査 (検査 U1 の別算法) では、nonfw 本体中に VA 下位 32 bit / RVA と一致する 4 バイト列が FPC 1 ・ Granulizer 1 ・ Slicer 1 ・ Slicex RVA 2 ・ Soundfont VA 2 / RVA 8 あるが、capstone は IMM オペランドとして復号しなかった。 **1 件ずつの判定は §2d-8** (即値 0 件、変位 4 件 = RIP 相対の disp 欄の数値一致で参照ではない、偶発 23 件、データ推定 4 件)。 これは byte 走査が capstone の上位集合であることの確認 (U1) に使い、根には入れていない。
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
- **§2d-4 (欠落の原因)**: 5 件は全て RVA32 表 (a) の根で、**開始 VA は全て PE export 表の関数** (FL Keys 0x71f030 `CreatePlugInstance`、Slicer 2 0x842950 `DecodeAudioFile`、0x842fc0 `FinishAudioFile`、Slicex 0x879ed0 `CreatePlugInstance`、Soundfont 0x762c70 `CreatePlugInstance`。 §2d-9 で実測)。 旧版の「畳み込み (`dec_label_pc_<VA>` として親関数の本体に入る)」は**誤り**。 #707 の調査で、RetDec はこれらを独立の関数として出しており、名前だけが export 名になっていたと訂正された (出典: #707 のコメント、コミット 22cb2fd の実測)。 監査 (`indirect_defs.py`) は `function_<VA>` の名前で探すため欠落と判定される。 定義の欠落ではなく命名の不一致。 本 PR の HEAD には改名の後処理が無く、この実測は本 PR では再現していない。 改名は #720 (未 merge・CHANGES_REQUESTED) にある。 いずれも `function_<VA>` を参照する箇所は final.ll に **0 件** (呼出しからは参照されていない)。 改名せずに表経由で `function_<VA>` を呼ぶ経路が入ると、未定義シンボルになる (推定。 wasm リンクは未検証)。
- 比較: 同じ 7 本で total2 の lea 段は欠落 0 (REPORT_LEA.md §2c)。 欠落を「定義を緩めて通す」ことはしていない (監査の定義は不変)。

### 2d-5. 検査 U1–U5 (`closure_unreached.py`、7 本 × 5 検査 全て PASS)

**U1** (i) 別算法: capstone 版の RVA32 集合 ⊆ 非実行節の全オフセット byte 走査、即値 (VA 下位 32 bit / RVA) 集合 ⊆ nonfw 本体の全オフセット byte 走査 / **U2** (ii) 固定点の独立検証: total3 の全関数の call/jmp・lea・即値の先が非共通なら total3 に入る (漏れ 0) かつ 根 (a)∪(b_live) ⊆ total3 (根の漏れ 0) / **U3** (iii) total2 ⊆ total3 ⊆ nonfw、total2 が `lea.json` (#627) と一致 / **U4** (iv) 排他合計 = outside / **U5** (v) outside の 8 バイト VA dataref = 0 (既存の total 定義と整合)。

### 2d-6. 検証の所要 (n=1、逐次・単一プロセス、4 core)

| 項目 | 実測 |
|---|---|
| 前提生成 (初回。 inventory 含む、`win_scan` 〜 `closure_lea`) | 549 s (rc 0。 inventory 段の負荷 load average 17 の時間帯あり) |
| `closure_unreached.py` (7 本) | 26.8 s (rc 0、PASS 5 × 7) |
| `unr_lift.sh` (7 本、逐次) | 138 s (wall、40:15 → 42:33)。 block 別 4 / 13 / 6 / 6 / 8 / 25 / 68 s |
| `unr_e2e.sh` (前提生成込み・work/ 空から、lift・judge・欠落監査まで、HEAD c2dfeaf) | **11 分 59 秒 (719 s、`real`)、rc 1** (judge 7/7 PASS、indirect_defs FAIL 5 件)。 closure_unreached 25.6 s・lift 段は block 別 5 / 13 / 5 / 6 / 9 / 25 / 66 s (計 129 s 前後) |
| `unr_nega.sh` (HEAD c2dfeaf、§2d-7) | 1 分 45 秒 (`real` 104.8 s)、rc 1 (NC6 対照のみ不合格。 他は期待どおり) |

### 2d-7. ネガティブコントロール (`unr_nega.sh`、HEAD c2dfeaf で rc 1 = NC6 対照のみ不合格)

| NC | 壊した入力 | 期待 | 実測 |
|---|---|---|---|
| 対照 | `closure_unreached.py` (無改変) | rc 0 | **rc 0** ✓ |
| NC1 | BFS の seed から (a) RVA32 の根を外す | U2 FAIL | **rc 1 (U2)** ✓ |
| NC2 | 合成 fixture (即値辺あり)。 BFS の辺 (`edge3_of`) から命令内即値を外す | U2 漏れ > 0 | 対照 (無改変) **U2 漏れ 0** ✓ / 即値辺を外す **U2 漏れ 1 → FAIL** ✓。 fixture は `closure_unreached.edge3_of` / `u2_miss` と `closure_indirect.Pe.bfs` の本物を使う。 実データは即値辺 0 件のため sed 変異では識別できない (旧版の「未検証」は撤回) |
| NC3 | 排他分類の (c) に (a) を二重計上 | U4 FAIL | **rc 1 (U4)** ✓ |
| NC4 | capstone 側の RVA32 集合に偽の値 0x7fffff01 を注入 | U1 FAIL | **rc 1 (U1)** ✓ |
| NC5 対照 | `judge.py shells` (無改変 status_run.csv) | rc 0 | **rc 0** ✓ |
| NC5 | FL Keys の行に emcc_c_rc=1 | judge FAIL | **rc 1** ✓ |
| NC6 対照 | `unr_e2e.sh --skip-lift` (無改変、期待値は書き換えず rc 0) | rc 0・OK 行あり | **rc 1 ✗** (AC2 の range 欠落 5 件が残るため。 gate は緩めていない。 PM 判断 (A) まで赤のまま) |
| NC6 | 同 + emcc_c_rc=1 の行を追記 | judge FAIL・rc ≠ 0・OK 無し | **rc ≠ 0・judge FAIL・OK 無し** ✓ |
| NC7 (新規) | 合成 bytes `mov rax, imm64` (= 開始 VA) を `imm_capstone` に入力 | 開始 VA ありで検出 / なしで非検出 | **rc 0** ✓ (即値の検出経路。 BFS 側の辺は NC2 で確認) |

実測: 対照 NC0・NC5 対照・NC1・NC2 (2 件)・NC3・NC4・NC5・NC6 (追記)・NC7 は期待どおり。 **NC6 対照のみ不合格** (AC2 gate 由来)。 `status_run.csv` は各 NC の後に元へ復元 (trap と cp)。

**PM 判断 (2026-10-13、#667 に記録)**: NC6 対照の期待値は書き換えない。 rc 1 は AC2 の range 欠落 5 件 (PE export 関数、§2d-9) が残るためで、#707 (PR #720) の merge で解消する見込み。 解消までは赤のまま残し、その事実を本節で明示する。 merge 後に `unr_nega.sh` を付け替え後の HEAD で再実行し、本表を差し替える。

### 2d-8. byte 走査の一致 31 箇所の判定 (`bytescan_hits.py`、capstone の IMM 集合に入らなかったもの)

判定: 一致位置を含む命令を関数先頭からの線形走査 (capstone) で求め、 即値 = IMM の下位 32 bit が一致 / 変位 = メモリ disp の下位 32 bit が一致 / 偶発 = 含む命令の中に一致するが IMM にも disp にも一致しない / データ = どの命令にも含まれない (線形走査が復号を止めた後)。
対象は 15 (VA 下位 32 bit 一致 / RVA 一致の別)、一致箇所は 31。 **結果: 即値 0 件 / 変位 4 件 / 偶発 23 件 / データ推定 4 件**。

- **変位 4 件** (Slicex 0x497240、Soundfont 0x16d3b0・0x148110・0x132b30): 全て `[rip + disp]`。 参照先は next_ip + disp であり、disp 欄の数値が対象 RVA と一致しているだけ (絶対参照ではない)。 → 参照ではない。
- **偶発 23 件**: 含む命令の符号化バイトそのものが値と一致する例 (例: `cmp byte ptr [rbp + 0x67], 0` の 4 バイト `80 7d 67 00` = 0x00677d80 = VA 0x677d80 (base 0x400000 + RVA 0x277d80))、 call 命令の内部のバイト、 命令境界をまたぐ窓。 いずれも絶対アドレスの即値 (IMM) として一致する命令は無い (capstone の IMM 集合に入らない)。 → 参照ではない。
- **データ推定 4 件** (Granulizer 0xa770、Slicer 0xa770、Slicex 0x3d000 ×2): 含む関数の線形走査が一致位置より前で停止しており、非命令バイト (データ・テーブル) の可能性が高い。 **未確認** (対象は d 集合で、参照元の判定には影響しない)。 起票: §7c。

結論: 即値として絶対参照されている非共通関数は本データで **0 件** (根 (b) = 0 件の判定は、byte 走査の 31 箇所を見ても変わらない)。 ただし データ推定 4 件は未確認。

| プラグイン | 種別 | 対象 (RVA) | 含む関数 (RVA) | 関数内オフセット | VA | 含む命令 | 判定 | 関数の区分 | 対象の区分 |
|---|---|---|---|--:|---|---|---|---|---|
| FPC | VA | 0x43e900 | 0xad30 | 0x116 | 0x40ae46 | `movsd xmm6, qword ptr [rip + 0x47fb41]` | 偶発 (命令内の他のバイト) | total2 | total2 |
| Fruity Granulizer | VA | 0xa770 | 0x22460 | 0x5f66 | 0x4283c6 | `-` | データ (復号範囲外・命令境界外) | outside | d |
| Fruity Slicer | VA | 0xa770 | 0x22470 | 0x5f66 | 0x4283d6 | `-` | データ (復号範囲外・命令境界外) | outside | d |
| Slicex | RVA | 0x497240 | 0x1be90 | 0x13 | 0x41bea3 | `cmp dword ptr [rip + 0x497240], -1` | 変位 | total2 | total2 |
| Slicex | RVA | 0x3d000 | 0x25620 | 0x5302 | 0x42a922 | `-` | データ (復号範囲外・命令境界外) | outside | d |
| Slicex | RVA | 0x3d000 | 0x25620 | 0x5306 | 0x42a926 | `-` | データ (復号範囲外・命令境界外) | outside | d |
| Soundfont Player | RVA | 0x17d130 | 0x180e30 | 0x12c | 0x580f5c | `call 0x6fe090` | 偶発 (命令内の他のバイト) | total2 | total2 |
| Soundfont Player | RVA | 0x17d080 | 0x180e30 | 0x1dc | 0x58100c | `call 0x6fe090` | 偶発 (命令内の他のバイト) | total2 | outside |
| Soundfont Player | VA | 0x277d80 | 0x188390 | 0x200 | 0x588590 | `cmp byte ptr [rbp + 0x67], 0` | 偶発 (命令内の他のバイト) | total2 | d |
| Soundfont Player | VA | 0x277d80 | 0x188390 | 0x323 | 0x5886b3 | `cmp byte ptr [rbp + 0x67], 0` | 偶発 (命令内の他のバイト) | total2 | d |
| Soundfont Player | VA | 0x277d80 | 0x188390 | 0x406 | 0x588796 | `cmp byte ptr [rbp + 0x67], 0` | 偶発 (命令内の他のバイト) | total2 | d |
| Soundfont Player | VA | 0x34e850 | 0x1dbc80 | 0x46 | 0x5dbcc6 | `mov rcx, qword ptr [rbp + 0x50]` | 偶発 (命令内の他のバイト) | total2 | total2 |
| Soundfont Player | RVA | 0x16d3b0 | 0x25ff70 | 0x54 | 0x65ffc4 | `mov rax, qword ptr [rip + 0x16d3b0]` | 変位 | total2 | total2 |
| Soundfont Player | RVA | 0x2e0f00 | 0x26e540 | 0x2b | 0x66e56b | `mov rax, qword ptr [rip + 0x15e03c]` | 偶発 (命令内の他のバイト) | total2 | d |
| Soundfont Player | RVA | 0x2e0f00 | 0x26e540 | 0x6f | 0x66e5af | `mov rax, qword ptr [rip + 0x15ea68]` | 偶発 (命令内の他のバイト) | total2 | d |
| Soundfont Player | RVA | 0x2e0f00 | 0x26eca0 | 0x2f | 0x66eccf | `mov rax, qword ptr [rip + 0x15e348]` | 偶発 (命令内の他のバイト) | outside | d |
| Soundfont Player | RVA | 0x2e0f00 | 0x26ef50 | 0x3c | 0x66ef8c | `mov rax, qword ptr [rip + 0x15e08b]` | 偶発 (命令内の他のバイト) | outside | d |
| Soundfont Player | RVA | 0x2e0f00 | 0x26ef50 | 0x80 | 0x66efd0 | `mov rax, qword ptr [rip + 0x15d5d7]` | 偶発 (命令内の他のバイト) | outside | d |
| Soundfont Player | RVA | 0x148110 | 0x284db0 | 0x21c | 0x684fcc | `mov rax, qword ptr [rip + 0x148110]` | 変位 | total2 | total2 |
| Soundfont Player | RVA | 0x2e0f00 | 0x284db0 | 0x35cd | 0x68837d | `mov rax, qword ptr [rip + 0x1443da]` | 偶発 (命令内の他のバイト) | total2 | d |
| Soundfont Player | RVA | 0x2e0f00 | 0x296910 | 0x74 | 0x696984 | `mov rax, qword ptr [rip + 0x135c53]` | 偶発 (命令内の他のバイト) | total2 | d |
| Soundfont Player | RVA | 0x132b30 | 0x299f50 | 0x65c | 0x69a5ac | `mov rax, qword ptr [rip + 0x132b30]` | 変位 | total2 | total2 |
| Soundfont Player | VA | 0x277d80 | 0x2a6e80 | 0x34 | 0x6a6eb4 | `cmp byte ptr [rbp + 0x67], 0` | 偶発 (命令内の他のバイト) | total2 | d |
| Soundfont Player | RVA | 0x20b900 | 0x2b74d0 | 0x11d | 0x6b75ed | `mov dword ptr [rbp + 0x4c], 0` | 偶発 (命令内の他のバイト) | total2 | d |
| Soundfont Player | VA | 0x277d80 | 0x304ed0 | 0x2c1 | 0x705191 | `cmp byte ptr [rbp + 0x67], 0` | 偶発 (命令内の他のバイト) | total2 | d |
| Soundfont Player | VA | 0x277d80 | 0x304ed0 | 0x2fb | 0x7051cb | `cmp byte ptr [rbp + 0x67], 0` | 偶発 (命令内の他のバイト) | total2 | d |
| Soundfont Player | RVA | 0x20b900 | 0x30d220 | 0x189 | 0x70d3a9 | `movzx rax, byte ptr [rax]` | 偶発 (命令内の他のバイト) | total2 | d |
| Soundfont Player | RVA | 0x36840 | 0x3175e0 | 0x17f | 0x71775f | `mov dword ptr [rax + 0x68], 3` | 偶発 (命令内の他のバイト) | total2 | d |
| Soundfont Player | RVA | 0x36840 | 0x318200 | 0x30a | 0x71850a | `mov dword ptr [rax + 0x68], 3` | 偶発 (命令内の他のバイト) | total2 | d |
| Soundfont Player | RVA | 0x36840 | 0x318a30 | 0x351 | 0x718d81 | `mov dword ptr [rax + 0x68], 3` | 偶発 (命令内の他のバイト) | total2 | d |
| Soundfont Player | VA | 0x277d80 | 0x348610 | 0xeb | 0x7486fb | `cmp byte ptr [rbp + 0x67], 0` | 偶発 (命令内の他のバイト) | total2 | d |

件数 31: データ (復号範囲外・命令境界外) 4, 偶発 (命令内の他のバイト) 23, 変位 4

### 2d-9. PE export 表と (d) (`closure_unreached.py` の `export` 件数、export 表を明示的に parse)

| プラグイン | export ∩ total2 | export ∩ 非共通 outside | export ∩ (d) |
|---|--:|--:|--:|
| FL Keys | 0 | 1 (`CreatePlugInstance` 0x31f030) | 0 |
| FPC | 0 | 0 | 0 |
| Fruity Granulizer | 0 | 0 | 0 |
| Fruity Slicer | 0 | 0 | 0 |
| Fruity Slicer 2 | 0 | 2 (`DecodeAudioFile` 0x442950、`FinishAudioFile` 0x442fc0) | 0 |
| Slicex | 0 | 1 (`CreatePlugInstance` 0x479ed0) | 0 |
| Soundfont Player | 0 | 1 (`CreatePlugInstance` 0x362c70) | 0 |

- export かつ非共通 outside の 5 件は、§2d-4 の range 欠落 5 件と同一の関数 (RVA で一致、VA は base 0x400000 からの換算)。 (d) に入った export は 0 件。
- 閉包の起点 (entries) は ABI impl のみで、export 表は起点にも (d) の除外にも使っていない (`lift/plugin_closure.py`)。 本データでは、export 経由で host から呼ばれる関数が (d) に入る例は 0 件。 ただし export 関数が (a)〜(c-lea) のどれで total3 に入ったかは未確認 (推定: (a) = export address table の値)。
- 含意: 欠落 5 件は dead code ではなく **host から直接呼ばれる入口** である。 §2d-4 の欠落は、wasm 側で入口関数が未定義になることを意味しうる (PM 判断: §7c)。

## 6c. 検証起点・取りこぼし確認

- 検証起点 commit: **b36fef5** (`feat(plugins): sampler unreached-function classification and total3 closure (Refs #667)`)。 分類・total3・lift・e2e は b36fef5 のスクリプトで実行。 fix 版: `closure_unreached.py` に export 件数と分類集合 (`unr/block*.sets.json`) の出力を追加 (分類・total3・ranges は不変)、 `unr_nega.sh` を改訂 (§2d-7)、 `bytescan_hits.py` を新規追加 (§2d-8)。 `unr_e2e.sh` は fix 版の commit 7d3ac70 で全段を実行 (438 s、rc 1)。 その後 `closure_unreached.py` の export 解析 1 行 (`parse_data_directories`) を直し、同 HEAD で再実行 (PASS 5 × 7、total3 不変)。 `bytescan_hits.py` も同 HEAD で実行。 **最新 HEAD c2dfeaf** (fix 2 版): `closure_unreached.py` に `edge3_of` / `u2_miss` を切り出し (分類・total3 は不変)、`unr_nega.sh` の NC2 を合成 fixture に置換、NC6 対照を「無改変で rc 0」に戻した。 `unr_e2e.sh` は全段を再実行 (11 分 59 秒、rc 1)、`unr_nega.sh` は 1 分 45 秒 (rc 1、NC6 対照のみ不合格 = AC2 gate 由来)。
- `git status --porcelain=v1 -- tools/plugins/sampler`: 実行後も空 (取りこぼし・混入なし)。 `tools/plugins/work/` (gitignore) の生成物は未 commit。
- `find tools/plugins/sampler -type f -size +20M` = **0 件**。
- 検証範囲: 分類・閉包・lift の判定 (lift 通過と range 監査)。 範囲外: 差分試験 (bit-exact)・wasm リンク・実行時の到達性・根 314 関数の偶発一致の判別。 通過 ≠ 正しさ。

## 7c. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| RVA32 根 5 関数 (4 block) が `function_<VA>` の define で出ない (RetDec は export 名で定義。 `indirect_defs` FAIL、`unr_e2e.sh` exit 1) | AC2 は #707 へ分割 (PM 判断 2026-10-13)。 改名の修正は #720 (未 merge)。 改名しないと表経由の呼出しで未定義シンボルになりうる (推定) | #707 (PR #720) の merge 後に本 PR を付け替えて再測定 |
| 即値辺が 7 本とも 0 件 → 実データの sed 変異では NC2 が非識別 | NC2 は合成 fixture (§2d-7) で確認済み。 実データで即値辺が現れた engine では再確認 | #667 にコメント |
| 字義の根 (a)∪(b) と (b_live) の差が 0 件 | 差が出るのは即値参照が出た時のみ。 現データでは判断に影響しない | #667 にコメント (設計の記録) |
| 根 314 関数の偶発一致 (数値定数との偶然の一致) は未判別 | RVA32 の判定は「整列 4 バイト値 = RVA」のみ。 表らしさ (連続性) は未検査 | #667 にコメント |
| (d) 参照なし 1,477 関数 / 738,944 B は dead code 候補にすぎない | 間接経路が他にある可能性。 未使用の確定ではない | #667 にコメント / 次タスク (§8c) |
| total3 の wasm リンク・実行時の到達性 | 範囲外。 lift 通過 ≠ 正しさ | #667 にコメント |
| f80 lowering の対象 (lea 段と同じ 3 関数 × 3 block) の bit-exact 未検証 | 差分試験の対象に入るか未定 | #197 にコメント (既存) |
| **AC2 gate 不合格** (range 欠落 5 件 = PE export 関数 5 件、§2d-9) | PM 判断 (2026-10-13): AC2 は #707 へ移譲し、#667 の AC は AC1・AC3 のみ。 gate は本 PR で緩めていない。 #707 の merge まで `unr_e2e.sh` は rc 1 のまま | #707 (PM 判断で移譲済み) |
| **基点 #676 (`627-sampler-lea-closure`) が未 merge** (CHANGES_REQUESTED、main とは 384 commit 差)。 main では `rep_stosb_memset` が実装済み (9b5ea38)。 merge 前に main へ付け替えて再測定が必要 | merge 順: #676 → #720 → 本 PR。 付け替え後に `unr_e2e.sh`・`unr_nega.sh` を再実行 | PM (merge 順は PM 判断で確定) |

| byte 一致 31 箇所のうちデータ推定 4 件 (Granulizer・Slicer・Slicex) の中身の確認 | 参照元の判定には影響しない (対象は d)。 未確認 | #667 にコメント |
| `REPORT_UNREACHED.md` は `docs/DOC_MAP.md` の索引に未掲載 (既存の `REPORT_LEA.md`・`REPORT_INDIRECT.md` も未掲載、grep 確認) | 索引の追記は PM 判断 | PM |

## 7d. 既知類型との関係 (DEFECTS.md の候補行)

- 該当なし (本 REPORT の対象は分類と到達性判定で、lift の変換規則は不変)。
- 取り下げ: 旧版の新類型候補「関数の畳み込み」は誤り (#707 で訂正。 独立関数は出ていて、名前が export 名だった)。 DEFECTS.md への追加は不要 (命名規則の問題で、lift の変換規則は不変)。

## 8c. 次タスク提案

1. 5 関数 (4 block) の定義名を `function_<VA>` へ揃える改名は #720 (#707 の PR) にある (未 merge)。 AC2 は #707 へ分割済み (PM 判断 2026-10-13)。 #676 → #720 の順に merge した後、本 PR を `--base main` へ付け替え、`unr_e2e.sh` と `unr_nega.sh` を再実行して REPORT の実測を差し替える。
2. (c) 750 関数 / 406,591 B の呼び元 (outside 同士の呼出鎖) を辿り、どこまでが dead 側かを確定する。
3. (d) 1,477 関数 / 738,944 B の dead code 候補を、同 DLL 内の他の参照 (未確認の間接経路) で検証する。
