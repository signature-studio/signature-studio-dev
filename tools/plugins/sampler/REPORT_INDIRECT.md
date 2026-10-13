# tools/plugins/sampler/REPORT_INDIRECT.md — #537 推移閉包 (REPORT.md §2b の付録)

本書は `REPORT.md` の行数上限 (250 行、`docs/DOC_MAP.md` §1) のため §2b を分割移動したもの。 節番号は REPORT.md に合わせる。

## 2b. 推移閉包 (#537): データ参照あり関数を root に足した lift

検証起点 commit: **0f50a1b** (`closure_indirect.py` / `indirect_lift.sh` / `indirect_defs.py` / `indirect_e2e.sh` / `indirect_nega.sh`)。 既知類型との関係 (`docs/DEFECTS.md`): **該当なし** (差分試験は範囲外)。
再現: `bash tools/plugins/sampler/indirect_e2e.sh` (算出 → lift → 判定) / `bash tools/plugins/sampler/indirect_nega.sh` (ネガコン)。 `lift/plugin_closure.py` は変更していない (§2b の root 追加は `sampler/` 側で完結)。

定義 (`closure_indirect.py`): base = §1 の閉包。 root = §2 の「データ参照あり」関数 (非共通 `.pdata` 関数のうち base に無く、開始 VA が qword としてデータ/コード節に載るもの)。
total = base ∪ root から `call/jmp rel32` で到達する非共通関数 (framework 共通ハッシュは frontier で止める。 `plugin_closure.py` と同じ BFS)。 callee = total − base − root。

| プラグイン | base 関数 / B | root 関数 / B | callee 関数 / B | **total 関数 / B** | total が非共通に占める割合 (関数 % / B %) | 非共通のうち total 外 関数 / B |
|---|--:|--:|--:|--:|--:|--:|
| FL Keys | 29 / 18,986 | 35 / 4,432 | 19 / 9,420 | **83 / 32,838** | 54.2 / 42.1 | 70 / 45,158 |
| FPC | 141 / 71,528 | 104 / 30,147 | 78 / 23,480 | **323 / 125,155** | 40.3 / 30.2 | 478 / 288,800 |
| Fruity Granulizer | 90 / 26,101 | 46 / 9,722 | 22 / 8,409 | **158 / 44,232** | 59.8 / 44.6 | 106 / 55,014 |
| Fruity Slicer | 119 / 40,560 | 47 / 6,714 | 22 / 8,824 | **188 / 56,098** | 55.1 / 47.7 | 153 / 61,478 |
| Fruity Slicer 2 (殻) | 51 / 23,778 | 74 / 22,023 | 68 / 21,770 | **193 / 67,571** | 38.8 / 23.0 | 305 / 225,991 |
| Slicex | 158 / 103,786 | 289 / 57,992 | 233 / 95,899 | **680 / 257,677** | 58.0 / 50.7 | 492 / 250,714 |
| Soundfont Player | 433 / 234,911 | 842 / 347,032 | 723 / 178,668 | **1,998 / 760,611** | 61.7 / 70.4 | 1,242 / 319,965 |
| 計 | 1,021 / 519,650 | 1,437 / 478,062 | 1,165 / 346,470 | **3,623 / 1,344,182** | 56.0 / 51.9 | 2,846 / 1,247,120 |

- 閉包の関数数は 1.58–4.61 倍、バイトは 1.38–3.24 倍 (計 3,623 関数 / 1,344,182 B。 base の 3.55 倍 / 2.59 倍)。 root の callee (直接呼出でだけ到達) が 1,165 関数 / 346,470 B あり、§2 の「真の追加量はこの表より大きい」を実測で裏付けた。
- 分母の非共通 = §2 と同じ (計 6,469 関数 / 2,591,302 B)。 割合の列は計 (関数 3,623 / 6,469、B 1,344,182 / 2,591,302)。
- total 外の非共通関数 (2,846 関数 / 1,247,120 B) の性質は未判別 (未参照・qword 以外の参照 (RVA32 表・命令内即値)・total 外から呼ばれるだけの関数のいずれか)。 そのうち **`lea reg,[rip+X]` で total の関数が開始 VA を取っている関数が計 153 関数 / 38,656 B** あり、
  root には加えていない (コードが関数ポインタを組む経路。 取りこぼしの一部。 FL Keys 1 / FPC 7 / Granulizer 7 / Slicer 7 / Slicer 2 5 / Slicex 24 / Soundfont Player 102 関数)。 **推移閉包もなお下限**。
- frontier (total から呼ぶ framework 関数) は FL Keys 126 / FPC 379 / Granulizer 167 / Slicer 185 / Slicer 2 258 / Slicex 678 / Soundfont Player 817 関数で、base の frontier (§1: 77 / 201 / 98 / 131 / 94 / 275 / 159) より増える。 P0a (framework 共有 lib) の必要範囲も広がる。

### lift 結果 (`indirect_lift.sh` → `judge.py shells`、RetDec は `lift_from_ll.sh` で `.ll` 出力後に停止)

| プラグイン | block | ranges 関数 / B | final.ll define | range 内部の追加 define | 未実装 helper | f80 関数 | `emcc -c` | lift 秒 (n=3) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| FL Keys | 22386 | 83 / 32,838 | 87 | 4 | 0 | 0 | 0 | 4–5 |
| FPC | 23617 | 323 / 125,155 | 323 | 0 | 0 | 0 | 0 | 12 |
| Fruity Granulizer | 23658 | 158 / 44,232 | 158 | 0 | 1 (rep_stosb_memset) | 0 | 0 | 5–6 |
| Fruity Slicer | 23662 | 188 / 56,098 | 190 | 2 | 1 (rep_stosb_memset) | 0 | 0 | 6 |
| Fruity Slicer 2 (殻) | 23663 | 193 / 67,571 | 193 | 0 | 0 | 0 | 0 | 8 |
| Slicex | 24172 | 680 / 257,677 | 684 | 4 | 0 | 0 | 0 | 23–24 |
| Soundfont Player | 24175 | 1,998 / 760,611 | 2,012 | 14 | 0 | 0 | 0 | 65–66 |

- **7/7 通過** (lift_rc 0 / `emcc -c` rc 0 / f80 0 / 未実装 helper は §6 の許容内)。 **この 7/7 は `targets.py` の `ALLOW_UNIMPL` (Granulizer・Slicer の `rep_stosb_memset` 各 1 = 空 stub) の許容が効いた結果**。 許容 0 の block に未実装 1 を与えると rc 1 (NC5)。 §1 と同じく通過 ≠ 正しさ。 未実装 helper が増えた block は無い (Granulizer・Slicer の `rep_stosb_memset` 各 1 のまま = #538)。
- `indirect_defs.py` (range 単位の監査): 全 7 本で ranges の全関数 (計 3,623) が final.ll に `define @function_<VA>` として存在 (欠落 0)。 judge の `defines>0` は range 欠落を検出できないため、この監査を gate に加えた。
- Soundfont Player の host call 0 site (§3) は total でも未調査 (`closure_facts.py` の入力は base のまま。 total への拡張は未実施)。

### 検証 (コミット済み HEAD 0f50a1b・4 core の Actions runner)

| 項目 | 実測 |
|---|---|
| 前提 inventory (`work/` 無しから `win_scan`〜`kernel_table` + 閉包) | 485 s (並列 14 プロセス / 4 core、load average 15–17) |
| `closure_indirect.py` | 4.31 s、4 検査 × 7 本 PASS |
| `indirect_e2e.sh` 全体 (3 回、inventory 済みから) | exit 0 × 3: **141 s / 139 s / 138 s** (終了時 load average (1 分) 0.99 / 1.00 / 1.01)。 3 回の `[indirect_lift]` 行 (秒を除く) の md5 が一致、算出表も一致 (`diff`) |
| `indirect_nega.sh` | exit 0、19 s (NC0–NC7 全て期待通り) |

`closure_indirect.py` の 4 検査 (不合格で exit 1): **C1** entry だけから BFS した結果が `plugin_closure.py` の ranges と完全一致 (BFS 実装の同一性) / **C2** root の関数数・バイトが `unreached.json` (§2、`unreached_unique.py` の出力) と一致 (同一定義 = 8 バイト整列 qword 一致 の再計算。 独立検算ではない。 NC2・NC3 で検出力を確認) /
**C3** total ⊆ 非共通 かつ base ⊆ total (framework を lift 対象に混ぜない) / **C4** 別算法: 命令境界を見ず関数バイト列の `E8`/`E9` rel32 を全オフセットで拾う過大近似の閉包に total が含まれる (独立検算は C4 のみ)。
C4 の過大近似は 7 本とも total と同数 (3,623 関数) だった。 capstone 版が取りこぼしていないことは示すが、過大近似側に余分が出なかったので「偽の到達先を拾っていない」ことの強い裏付けではない。

### ネガティブコントロール (`indirect_nega.sh`、対照 = 無改変で rc 0)

| NC | 壊した入力 | 実測 |
|---|---|---|
| NC1 | BFS の entry を 1 つ落とす | C1 FAIL (rc 1) |
| NC2 | root 判定を空にする | C2 FAIL (rc 1) |
| NC3 | `unreached.json` の FL Keys `dataref_funcs` を +1 | C2 FAIL (rc 1) |
| NC4 | ranges 末尾 1 つ (`function_7268d0`) を落として FL Keys を再 lift | 落とした関数 1 → 0、define 87 → 85 |
| NC5 | `judge.py shells` に合成 CSV 6 種 (emcc_c_rc=1 / lift_rc=1 / f80=3 / 許容 0 の block に未実装 1 / 行欠落 / header のみ) | 全て rc 1 |
| NC6 | `indirect_e2e.sh --skip-lift` に emcc_c_rc=1 の行を追記 | rc 1、`[indirect_e2e] OK` は出ない (対照: rc 0・OK あり) |
| NC7 | `indirect_defs.py` に FL Keys の final.ll から define を 1 つ消した lift-dir | rc 1 (欠落 1) (対照 rc 0) |

### `PLUGIN_MATRIX.json` の `lift.closure_*` と見積への影響 (記録のみ。 書き換えは PM 判断)

- `lift.closure_funcs / closure_bytes` は §1 の base と一致する (7 本 × 2 項目一致は `matrix_check.py`)。 total とは 1.58–4.61 倍 (関数) / 1.38–3.24 倍 (B) 乖離する (上表)。 MATRIX は書き換えていない。
- Tier は `win_uniq_bytes` (固有コード量) の閾値で決まる (`tier.py`) ため、閉包の再計算では **Tier 区分は変わらない**。 変わりうるのは「T1 = 1.5 人日・T2 = 4・T3 = 15」の工数前提 (小さな閉包を lift すれば済む) の方。
  total は FPC・Slicex・Soundfont Player で 125–761 KB と base の 1.75–3.24 倍 (B) になり、lift の機械的な通過は 7/7 で変わらない一方、**P0a の frontier 範囲の拡大 (上記) と差分試験の対象関数数 (3.55 倍) が見積に効く**。
  工数への換算は本書では行わない (推定根拠が無い。 #208 の 57.5 人日は据え置き。 PM 判断)。
- `plugin_closure.py` の仕様変更は不要だった (本 PR は `sampler/` だけ)。 受入条件 4 の「他ファミリ (dynamics #200 / PR #506) への適用」は、`closure_indirect.py` が `targets.py` の SHELLS を回す作りなので、対象定義を差し替えれば流用できる見込み (**未検証**)。 dynamics 側の測定は #200 で行う。
