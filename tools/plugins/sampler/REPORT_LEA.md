# tools/plugins/sampler/REPORT_LEA.md — #627 lea [rip+X] 参照を root に足した推移閉包 + host 呼出面・kernel 依存の再計測 (REPORT.md §2b の付録 2)

`REPORT.md` の行数上限 (250 行、`docs/DOC_MAP.md` §1) のため分割。 節番号は REPORT.md に合わせる。 前提の定義・語彙は `REPORT_INDIRECT.md` §2b。

## 2c. lea 経路を root に加えた閉包 (total2) と lift

検証 HEAD: **c402faf** (main d7da2d2 を取り込んだ現 HEAD。 `lea_e2e.sh` / `lea_nega.sh` は main 上で再実行、§6b)。 旧基点 042f869 (rep_stosb_memset が stub の時代) の値は本節の表から差し替え済み。 既知類型との関係 (`docs/DEFECTS.md`): **該当なし** (差分試験は範囲外。 f80 の扱いは下記 L-3)。
再現: `bash tools/plugins/sampler/lea_e2e.sh` (算出 → lift → 判定 → host/kernel 再計測) / `bash tools/plugins/sampler/lea_nega.sh` (ネガコン)。 `lift/plugin_closure.py` は変更していない。

定義 (`closure_lea.py`): total = #537 の推移閉包。 lea root = 閉包内の関数が `lea reg,[rip+X]` で開始 VA を取っている非共通関数 (閉包に無いもの)。
lea root を足して `call/jmp rel32` で広げ、新たに入った関数の lea 先が無くなるまで繰り返す (固定点)。 total2 = 固定点の閉包。 callee = total2 − total − lea root。

| プラグイン | total (#537) 関数 / B | lea root 1 巡目 関数 / B | lea root 全巡 (巡数) 関数 / B | callee 関数 / B | **total2 関数 / B** | total2 が非共通に占める割合 (関数 % / B %) | 非共通のうち total2 外 関数 / B |
|---|--:|--:|--:|--:|--:|--:|--:|
| FL Keys | 83 / 32,838 | 1 / 75 | 1 / 75 (1) | 0 / 0 | **84 / 32,913** | 54.9 / 42.2 | 69 / 45,083 |
| FPC | 323 / 125,155 | 7 / 2,424 | 7 / 2,424 (1) | 11 / 3,850 | **341 / 131,429** | 42.6 / 31.7 | 460 / 282,526 |
| Fruity Granulizer | 158 / 44,232 | 7 / 1,355 | 7 / 1,355 (1) | 0 / 0 | **165 / 45,587** | 62.5 / 45.9 | 99 / 53,659 |
| Fruity Slicer | 188 / 56,098 | 7 / 1,355 | 7 / 1,355 (1) | 0 / 0 | **195 / 57,453** | 57.2 / 48.9 | 146 / 60,123 |
| Fruity Slicer 2 (殻) | 193 / 67,571 | 5 / 1,613 | 5 / 1,613 (1) | 0 / 0 | **198 / 69,184** | 39.8 / 23.6 | 300 / 224,378 |
| Slicex | 680 / 257,677 | 24 / 4,329 | 25 / 4,350 (2) | 4 / 372 | **709 / 262,399** | 60.5 / 51.6 | 463 / 245,992 |
| Soundfont Player | 1,998 / 760,611 | 102 / 27,505 | 102 / 27,505 (1) | 24 / 3,428 | **2,124 / 791,544** | 65.6 / 73.3 | 1,116 / 289,032 |
| 計 | 3,623 / 1,344,182 | **153 / 38,656** | 154 / 38,677 | 39 / 7,650 | **3,816 / 1,390,509** | 59.0 / 53.7 | 2,653 / 1,200,793 |

- 1 巡目の lea root は issue の 153 関数 / 38,656 B と一致 (検査 L2)。 total2 は total より **+193 関数 / +46,327 B** (+5.3 % / +3.4 %)。 固定点までの 2 巡目が出たのは Slicex だけ (+1 関数 / 21 B)。
- 分母の非共通 = §2 と同じ (計 6,469 関数 / 2,591,302 B)。 total2 外の非共通は 2,653 関数 / 1,200,793 B のまま残り、**閉包はなお下限** (性質は未判別: 未参照 / RVA32 表 / 命令内即値 / total2 外からの呼出のみ)。
- 非共通のうち total2 外の割合: 関数 41.0 % / B 46.3 %。 lea 経路を足しても取りこぼしの大半は埋まらない (lea は 38,656 B で total 外 1,247,120 B の 3.1 %)。

### lift 結果 (`lea_lift.sh` → `judge.py shells`、RetDec は `lift_from_ll.sh` で `.ll` 出力後に停止)

| プラグイン | block | ranges 関数 / B | final.ll define | 未実装 helper | f80 関数 (raw → lowering 後) | `emcc -c` (raw → lowering 後) | lift 秒 |
|---|--:|--:|--:|--:|--:|--:|--:|
| FL Keys | 22386 | 84 / 32,913 | 88 | 0 | 0 | 0 | 4 |
| FPC | 23617 | 341 / 131,429 | 343 | 0 | 0 | 0 | 11–12 |
| Fruity Granulizer | 23658 | 165 / 45,587 | 165 | 0 | **3 → 0** | **1 → 0** | 5 |
| Fruity Slicer | 23662 | 195 / 57,453 | 197 | 0 | **3 → 0** | **1 → 0** | 6 |
| Fruity Slicer 2 (殻) | 23663 | 198 / 69,184 | 198 | 0 | **3 → 0** | **1 → 0** | 8 |
| Slicex | 24172 | 709 / 262,399 | 713 | 0 | 0 | 0 | 24 |
| Soundfont Player | 24175 | 2,124 / 791,544 | 2,138 | 0 | 0 | 0 | 64–65 |

- **7/7 通過** (lift_rc 0 / lowering 後の `emcc -c` rc 0 / lowering 後の f80 0)。 range 欠落監査 (`indirect_defs.py --lift-dir lealift --ranges-dir lea`): 全 7 本で ranges の全関数 (計 3,816) が final.ll に define あり (欠落 0)。
- **L-3 f80 (新規の観測)**: lea 由来の関数が x87 を含む。 Granulizer の `function_7442c0` / `function_7443e0`、Slicer の `function_7534f0` / `function_753610`、Slicer 2 の `function_851760` / `function_851880` は lea root (total に無い)、各 block の残り 1 本 (`function_7594e0` / `function_770e00` / `function_8527b0`) は total 内の関数で、**#537 の final.ll には f80 を含む関数が無かった** (f80 0)。
  lowering 前の `emcc -c` は `no libcall available for fmul with type f80` / `do not know how to soften fp_extend` で rc 1 になる。 そこで `lea_lift.sh` は f80 を検出した block に限り **`p0c/f80_lower.py` (x86_fp80→f64、#197 の成果物) を明示の段として通し**、judge には lowering 後の値を渡す (raw 値は CSV の `f80_raw` / `emcc_c_rc_raw` / `lowered` 列に残す)。
  **f80→f64 は拡張精度の丸めが変わり bit-exact を保証しない** (#197)。 通過 ≠ 正しさ。 3 block とも lowering の適用は機械的に通ったが、差分試験は範囲外。 **該当 3 block の PASS は lowering 後の値による** (judge.py の出力「lowering 後の値で判定した block」に列挙。 raw は `f80_raw` / `emcc_c_rc_raw`)。
  **機序 (実測で確認した部分)**: 同一関数 `function_7594e0` (Granulizer、total 内) は #537 の閉包 ranges にも total2 の ranges にも含まれ、関数本体の x86_fp80 は total2 の `p.final.ll` で 2 命令 (`fpext float → x86_fp80` 等)。 ranges の関数集合は同じなので、閉包の選択が直接の原因ではない。 **#537 の final.ll で f80 0 になった差の原因 (RetDec の同一 .ll 内の他関数の型伝播か、lift の入力差か) は未解明**。 起票先: §7b。
- 未実装 helper は main 上で 0 (`rep_stosb_memset` は #629 で実装済み、§6b)。 旧基点 (042f869) では Granulizer・Slicer 各 1 だった (#538 は解消済み)。

### 検査 (`closure_lea.py`、不合格で exit 1)

**L1** total・base・root が `indirect.json` (#537) と一致 / **L2** lea 1 巡目が `indirect.json` の lea 残と一致 / **L3** 固定点の独立検証 (total2 の全関数について `call/jmp rel32` 先・`lea` 先の非共通関数が全て total2 内。 BFS とは別ループ) /
**L4** total ⊆ total2 ⊆ 非共通 / **L5** 別算法 (E8/E9 の byte 走査) の過大近似に total2 が含まれる / **L6** 反例注入 / **L7** 実データの偽到達先の数え上げ。

### C4 の補強: 偽の到達先の検出方法 (反例入力と実データの census)

#537 の C4 は過大近似が total と同数で、「偽の到達先を拾っていない」ことの強い裏付けではなかった。 total2 でも同じ (byte 走査版の閉包 = total2、7 本とも同数: 84 / 341 / 165 / 195 / 198 / 709 / 2,124 関数、B も一致)。 補強は 2 点。

1. **反例入力 (L6、検出器の識別力)**: 閉包内の関数 1 本 (7 本それぞれ別の関数) の本体を `mov rax, imm64` (imm64 の中に E8 rel32 を埋める) に差し替え、E8 の rel32 が **total2 外の非共通関数 t を指す**ようにする。
   命令境界を見る capstone 版は t を拾わず、byte 走査版だけが t を拾う。 **7/7 本で「capstone: なし / byte 走査: 拾う」を実測** (t は FL Keys 0xa6b0 / FPC 0xcab0 / Granulizer 0xa6d0 / Slicer 0xa6d0 / Slicer 2 0xcab0 / Slicex 0xcab0 / Soundfont Player 0xa6b0)。
   この検出器は偽の到達先を区別できる。 `lea_nega.sh` NC6 は capstone 側を byte 走査にした検査器が L6 で FAIL することを確認する。
2. **実データの census (L7)**: total2 の関数本体の E8/E9 全オフセットのうち、capstone が `call/jmp rel32` として復号した命令の先頭でないもの (機会) と、その rel32 の先が別 `.pdata` 関数の開始になるものを数えた。
   機会 / 先が関数開始 / うち total2 外の非共通 = FL Keys 123 / 0 / 0、FPC 540 / 0 / 0、Granulizer 166 / 0 / 0、Slicer 273 / 0 / 0、Slicer 2 258 / 0 / 0、Slicex 980 / 1 / 0、Soundfont Player 3,886 / 2 / 0 (計 6,226 機会)。 **閉包を偽に広げうる到達先 (total2 外の非共通関数を指すもの) は 0 件**。
   関数開始を指した 3 件 (Slicex 1・Soundfont Player 2) は total2 内の関数宛てで、閉包の大きさに影響しない。 L7 は `hit_out == 0` を不合格条件にした。 NC7 は census の境界判定を外し閉包内も偽と数えると FAIL することを確認する。
   結論: **byte 走査が total2 と同数になるのは、命令境界外の E8/E9 に偽の到達先が実在しないため** (反例が検出できる検出器で 0 件)。 total2 の過大計上は無く、この点で total2 は下限側の保守的な値という以前の位置づけが強まった。 範囲外: total2 外から入る到達 (§2c 冒頭の「性質未判別」) は本検査では判別できない。

## 3b. total2 の host 呼出面・kernel 依存 (`facts_total.py`、#196 / #197 への入力)

`closure_facts.py` (§3・§4) と同じ走査 (`host_calls.scan` の taint・`kernel_matrix.scan_dll`) を DLL ごとに 1 回走らせ、call site の所在関数を base / total / total2 の関数集合で分類した。 検査 (不合格で exit 1): **F1** base 段が `closure_facts.py` の facts.json と一致 / **F2** 段の単調性 / **F3** 線形走査 (`ids_crosscheck.py` と同じ別算法) が total2 の taint 版即値 ID を取りこぼさない / **F4** 計測成立 (total2 の host site が全 plugin で 0 でない)。

| プラグイン | host call site base → total → total2 | 即値 ID の種類 | 動的 ID site | total2 で増えた Dispatcher ID (site) / slot | kernel site base → total → total2 | total2 で増えた kernel |
|---|---|---|---|---|---|---|
| FL Keys | 10 → 10 → 10 | 1 → 1 → 1 | 0 → 0 → 0 | 無し | 1 → 1 → 1 | 無し |
| FPC | 35 → 44 → 49 | 5 → 5 → 5 | 3 → 4 → 6 | ID 3: 4→6 site、動的 +3 / slot 0x8 (2)・0x150 (1) | 4 → 5 → 5 | 0x5dee90 (1) |
| Fruity Granulizer | 23 → 30 → 31 | 5 → 7 → 7 | 1 → 1 → 1 | **ID 40 (2)・21 (1) が新規** / slot 0xd8 (1) | 11 → 11 → 11 | 無し |
| Fruity Slicer | 26 → 29 → 30 | 6 → 6 → 6 | 1 → 1 → 1 | 新規 ID 無し / slot 0xd8 (2) | 11 → 11 → 11 | 無し |
| Fruity Slicer 2 | 6 → 8 → 8 | 3 → 4 → 4 | 1 → 1 → 1 | **ID 91 (2) が新規** | 0 → 1 → 1 | 0x5dee90 (1) |
| Slicex | 52 → 63 → 65 | 7 → 7 → 7 | 1 → 2 → 2 | 新規 ID 無し (動的 +1) / slot 0x8 (2) | 11 → 12 → 12 | 0x5de660 (1) |
| Soundfont Player | 0 → 0 → 0 | 0 → 0 → 0 | 0 → 0 → 0 | — | 0 → 0 → 0 | — |

- **host 呼出面の増分は total で 7 本中 5 本、lea で FPC / Granulizer / Slicer / Slicex の 4 本**。 7 本計 host site は base 152 → total 184 → total2 193。 total2 の hs_ids.json (35 ID) 未収載 ID は FPC の 88 (1 site)・Granulizer の 101 (1 site) で、base と同じ。 **Granulizer の ID 40 / 21 と Slicer 2 の ID 91 は `hs_ids.json` 収載済みか否かを `facts_total.json` の `host_ids_not_in_hs_ids` で確認**した結果、上表の「未収載 ID」列に出たのは 88・101 のみ (= 40 / 21 / 91 は収載済み)。
- 線形走査 (F3) は 7/7 本で taint 版即値 ID を取りこぼさない。 線形走査だけが拾う ID (host 以外の slot0 呼出を含む上位集合): FPC 1 / 16 / 80、Granulizer 64 × 4、Slicer 64 × 4、Slicer 2 1 / 16 / 80、Slicex 1 × 2 / 4 / 7 / 16 / 63 × 3 / 64 × 4 / 112、Soundfont Player 2 / 59 (各 1 site)。 host 呼出か別オブジェクトの slot0 呼出かは未判別 (§3 と同じ)。
- **Soundfont Player は total2 でも taint 版の host call が 0 site** (線形走査は ID 2 と 59 を各 1 site 検出)。 total を 1,998 → 2,124 関数に広げても 0 のままで、§3 の「taint (`this+0xbc`) が当てはまらない経路がある」という推定が強まった (原因未調査。 #196 の taint 精密化に入力)。
- **kernel 依存**: kernel call site の 7 本計は base 38 → total 41 → total2 41 (`facts_total.json` の `kernel.<段>.callsites` の合計)。 total2 で新たに現れた Balance 80 実装表の kernel は 0x5dee90 (FPC・Slicer 2)・0x5de660 (Slicex) の計 3 site。 0x5dee90 は #331 の未解決対象 (`p0c/REPORT.md` §14.4) で、FPC と Slicer 2 にも広がる。 DLL 固有 VA のままの呼出先 (Granulizer 0x60b380 / 0x60b550 / 0x60b780、Slicer 0x60d1e0 / 0x60d3b0 / 0x60d5e0、FPC 0x62f4b0 / 0x62f680、Slicex 0x635770) は base と同じで増えていない。
  frontier (total2 から呼ぶ framework 関数) 内の kernel call site: FPC 4 / Granulizer 1 / Slicer 3 / Slicer 2 4 / Slicex 7 (種類は `facts_total.json` の `kernel.total2.kernels_frontier`)。 frontier の関数は lift 対象外 (P0a)。
- 全数値は `work/sampler/facts_total.json` (gitignore) に出る。 再現は `lea_e2e.sh` の最終段。

## 6b. 検証 (コミット済み HEAD f358f17・4 core の Actions runner)

| 項目 | 実測 (main d7da2d2 を取り込んだ検証 HEAD c402faf・4 core の Actions runner) |
|---|---|
| `lea_e2e.sh` 全体 (lift を含む、`work/` 確認済みの状態から。 許容 `ALLOW_UNIMPL` 有りの版) | exit 0・**11 分 09 秒 (`time` 実測、user 28 分 32 秒)**。 `closure_lea` PASS 7 checks × 7、`judge shells` PASS 7/7、`indirect_defs` PASS 7/7、`facts_total` PASS 4 checks × 7 |
| `lea_e2e.sh --skip-lift` (許容 `ALLOW_UNIMPL` 撤去後、既存 CSV の再判定) | exit 0・1 分 33 秒。 `judge shells` PASS 7/7。 許容を空にした状態で main の declares_unimpl 0 × 7 block を確認 |
| `lift` の `declares_unimpl` (main 上の実測) | 7 block 全て 0。 `rep_stosb_memset` の stub は main で解消 |
| `lea_nega.sh` | exit 0・**2 分 43 秒**。 NC0–NC13 の 23 項目 (対照 6 + 破壊 17) が全て期待通り |

- フル e2e (11 分) は c402faf (`lea_lift.sh` の f80 列統一後、`ALLOW_UNIMPL` は有り) で実行。 その後 `ALLOW_UNIMPL` を撤去し、`--skip-lift` と `lea_nega.sh` (撤去後の判定) で確認。 最終 HEAD での再実行の値は §6b の末尾の行に示す。 `work/` の中間生成物は gitignore (`tools/plugins/work/`)。
- 旧 f358f17 / ad39596 の検証 (270 / 269 / 268 s、md5 `ceaf59c63860`、`lea_nega` 222 s) は main 基点の値。 main 取り込み後は上の実測に置き換えた。
- 範囲外: 差分試験 (bit-exact)・wasm リンク・実行時の到達性 (`lea` 先が実際に呼ばれるか)。 通過 ≠ 正しさ (§1 と同じ)。

### ネガティブコントロール (`lea_nega.sh`、対照 = 無改変で rc 0)

| NC | 壊した入力 | 実測 |
|---|---|---|
| NC1 | BFS の entry を 1 つ落とす | L1 FAIL (rc 1) |
| NC2 | lea root を足さない | L2 FAIL (rc 1) |
| NC3 | lea root を足すが `call/jmp` で広げない (固定点にしない) | L3 FAIL (rc 1) |
| NC4 | `indirect.json` の FL Keys `lea_residual_funcs` を +1 | L2 FAIL (rc 1) |
| NC5 | byte 走査閉包を空にする | L5 FAIL (rc 1) |
| NC6 | 反例注入の capstone 側を byte 走査にする (偽の到達先を区別できない検査器) | L6 FAIL (rc 1) |
| NC7 | census の境界判定を外し、閉包内の関数宛ても偽と数える | L7 FAIL (rc 1) |
| NC8 | `judge.py shells` に合成 CSV 6 種 (emcc_c_rc=1 / lift_rc=1 / lowering 後 f80=3 / 許容 0 の block に未実装 1 / 行欠落 / header のみ) | 対照 rc 0 → 6 種全て rc 1 |
| NC9 | `lea_e2e.sh --skip-lift` に emcc_c_rc=1 の行を追記 | rc 1、`[lea_e2e] OK` は出ない (対照: rc 0・OK あり) |
| NC10 | `indirect_defs.py` に FL Keys の final.ll から lea 由来の define (`function_7173b0`) を消した lift-dir | rc 1 (欠落 1) (対照 rc 0) |
| NC11 | `facts.json` (base の正本) の FL Keys ID 2 を +1 | F1 FAIL (rc 1) (対照 rc 0) |
| NC12 | `facts_total.py` の線形走査を空にする | F3 FAIL (rc 1) |
| NC13 | `facts_total.py` の host 走査結果を空にする | F4 FAIL (rc 1) |

NC1–NC7・NC11–NC13 は sed 置換が当たったことを確認してから実行する (当たらなければ NC 自体を FAIL にする)。 初回の NC7 は L7 の FAIL 行が出ず (置換が census の引数を差し替えて例外で落ちていた)、置換を直して再実行した。

## 7b. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| total2 外の非共通関数 2,653 関数 / 1,200,793 B の到達性 (未参照 / RVA32 表 / 命令内即値 / total2 外から呼ぶだけ) | 閉包は下限のまま。 lea は取りこぼしの 3.1 % しか埋めない | 新規 #667 [PLG-G3-6] (起票済み) |
| lea 由来の f80 関数 (Granulizer / Slicer / Slicer 2 各 3) の f80→f64 は bit-exact 未検証 | 差分試験の対象に入れないと精度差が見えない | #197 にコメント (f80_lower.py の適用実績) |
| total2 の host 呼出面 (ID 40 / 21 / 91 と slot 0x8 / 0xd8 / 0x150 の意味未解析) | P0b の応答表の網羅性 | #196 にコメント |
| Soundfont Player の taint 版 host call 0 site (total2 でも) | host 呼出面の過小計上 | #196 にコメント (taint 精密化) |
| 0x5dee90 の依存が FPC・Slicer 2 にも広がる | P0c の未解決 kernel #331 の影響範囲 | #197 / #331 にコメント |
| PLUGIN_MATRIX / 見積 (57.5 人日) への反映 | total2 は #537 の total に +193 関数 / +46,327 B。 見積前提は変わらず | PM 判断 (書き換えていない) |
| 同一関数 `function_7594e0` (Granulizer) の lift で、#537 では f80 0・total2 では f80 2 になる差の機序 (RetDec の同一 .ll 内の型伝播か、lift 入力差か) | #537 の f80 0 (REPORT_INDIRECT.md) の扱い。 閉包の選び方で lift 結果が変わるなら、他の閉包値も再確認が要る | PM 判断: 起票依頼 (未解明。 切り分けは同一関数を total / total2 で個別に lift する実験) |
