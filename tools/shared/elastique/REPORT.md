# tools/shared/elastique — élastique 2.2.15 (win x64) 静的 IPP 入口 197 件の API 同定 (T-SH-40 / #2613)

既知の類型との関係: lift 欠陥ではないため該当なし (`docs/DEFECTS.md`)。本件は静的 IPP 節の入口の同定のみ。
所有者限定 tier 専用 (`docs/DECISIONS.md` D20)。公開 tier の成果物には含めない。

## 0. 結論

| 受入条件 (#2613) | 結果 |
|---|---|
| 1. 197 入口のそれぞれに IPP API 名か「未同定」 | 197 入口を再現 (線形走査)。**一意の API 名 8 入口** (`ippsRealToCplx_32f` 4・`ippsSet_8u` 2・`ippsConj_32fc` 2)、**API 族の候補集合 26 入口** (dsp の同一本体を共有する export 群、7 群)、**未同定 163 入口** (内訳 §3)。対応表は `data/entries.csv` |
| 2. 同定 API のうち tools/ipp の実装対応が無いもの | 名付けた入口 34 件のうち、**18 件は候補名が全て fail-soft stub のみ** (`tools/ipp` の PoC 未実装。STRICT でのみ fail-fast)、**16 件は実装済み名と stub 名の混在**、実装済みのみは 0 件。stub 名は 28 (§4 に列挙)。#2613 の受入 2 の文言「対応が無い入口が 1 件でも残るなら、D20 の停止条件に従い理由を報告して停止する (その入口は実装しない)」に従い、本 run ではこれらを実装しない |
| 3. 関数ポインタ経由の到達が無いことの確認 | **静的確認のみ** (IPPCODE 番地を生成する命令 0・データ中のポインタ 0)。実行トレースは未実施 (この runner に wine 等が無い)。子 #2643 ([T-SH-42]) に移管 |
| 4. REPORT に測定 commit・再現コマンド・差分 | 本書 §1・§2 |

## 1. 対象・素材・測定 commit

- 素材: `fl-win64` (`tar --zstd -xf` 5.6 秒)。`extracted/block24357_PE.bin` (4,997,632 B, sha256 先頭 16 桁 `8551e92209cdd2ce`) を `tools/shared/work/win/elastique_x64.dll` に複製 (gitignore)。
  PE 情報: ImageBase `0x180000000`、`.text` RVA `0x1000`・vsize `0x2f6550`、**IPPCODE RVA `0x2f8000`・vsize `0xef1c2` (= 979,394 B)**、`.pdata` 1,956 関数 (`.text` 内)、export 15 (`Auftakt_CreateInstance` 等)。
- 照合先: `extracted/block24356_PE.bin` (`dsp_ippv2_x64.dll`, ImageBase `0x180000000`, export 446, IPPCODE RVA `0x17e0000`・vsize `0x6dc771`)。
- 検証起点: `f3102162` (origin/main)。
- **測定 commit (コードを変えた最後の commit): `bcab4049`** (`fix(shared): élastique 族候補の起点伝播を起点ごとの BFS に直す`)。
  前の測定 commit `f3310a00` は `reach()` が既訪問ノードへ起点名を足したとき子へ伝播させず、族候補 26 入口のうち 16 入口の名前集合が不完全だった (round 1 の差し戻し)。`bcab4049` で修正し、全入口の名前集合を再計算した。
- 差分 (修正の範囲): `git diff f3310a00 bcab4049 -- tools/shared/elastique/ipp_entries.py` (`reach()` を起点ごとの BFS に変更、CSV 列名 `tokens` → `insns`、出力ラベルの探索深さ)。
- 差分 (測定後のコード範囲): `git diff bcab4049 HEAD -- tools/shared/elastique/ipp_entries.py` → 出力 0 行 (本書と `data/entries.csv` の commit では script を変更しない)。

## 2. 再現

```sh
# 素材の展開 (fl-win64 は docs/WORKFLOW.md §11 の手順)
mkdir -p "$RUNNER_TEMP/fl-win64" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64"
mkdir -p tools/shared/work/win && cp "$RUNNER_TEMP/fl-win64/extracted/block24357_PE.bin" tools/shared/work/win/elastique_x64.dll
FL_WIN64_DIR="$RUNNER_TEMP/fl-win64" python3 tools/shared/elastique/ipp_entries.py   # 実測 38.2 秒 (real)、load average 0.25 → 0.74
```

- 出力: `data/entries.csv` (197 行・コミット対象) と `tools/shared/work/elastique/facts.json` (中間物・gitignore)。
- 実行ログ (測定 commit `bcab4049` の HEAD 上の出力。§3 の数値の出典。先頭 2 行の素材パスは省く):

```text
linear-sweep entries (distinct call/jmp targets in IPPCODE): 197 (call/jmp sites 810)
pdata (.text 関数) 件数: 1956; 入口のうち呼出元が pdata 関数内にあるもの: 181
dsp export 446: variant 数の分布 (表の項数) {1: 14, 6: 374, 7: 57, 9: 1}
dsp 候補本体: export 表の variant 2566 個 / export から call で 12 段内 3646 個 / dsp .text 由来の IPPCODE 着地点 2470 個 → 照合対象 5825 個
照合: {'exact_final': 166, 'fuzzy_only': 31}
区分: {'family_candidates': 26, 'trivial_body': 10, 'exact_dsp_internal_no_export': 122, 'identified': 8, 'unidentified_no_exact': 31}
間接 call/jmp の形: {'rax': 261, 'qword ptr [rax]': 100, 'qword ptr [rax + 0x28]': 78, 'qword ptr [rax + 8]': 61, 'qword ptr [rax + 0x58]': 49, 'qword ptr [rax + 0x20]': 44, 'qword ptr [rax + 0x38]': 43, 'qword ptr [rax + 0x30]': 43, 'qword ptr [rax + 0x10]': 41, 'qword ptr [rax + 0x48]': 37, 'table[r10+rax*8]': 33, 'qword ptr [rax + 0x70]': 32}
即値・変位に IPPCODE 番地を含む命令: 0
lea rip で IPPCODE を指す箇所: 0 箇所 / 0 着地点 (うち入口 0)
間接 call/jmp (.text): 2714 箇所 (例 [(6174, 'jmp', 'qword ptr [r10 + rax*8]'), (6222, 'jmp', 'qword ptr [r10 + rax*8]'), (6270, 'jmp', 'qword ptr [r10 + rax*8]')])
.rdata/.data の IPPCODE 向きポインタ: 0 (うち入口 0、入口外 0)
```

(前の測定 `f3310a00` のログは「export から call で 3 段内 3646 個」と表示していたが、実際の探索深さは `REACH_DEPTH` = 12。表示ラベルを合わせた。数値は不変。)

## 3. 方法と結果

**入口 (197)**: `.text` を線形走査 (invalid byte は 1 byte 飛ばし)。`E8`/`E9` (rel32 の call/jmp) の着地点のうち IPPCODE 内のものを distinct で数える。
呼出箇所は 810。`.pdata` 基準 (呼出元が `.pdata` の関数内にある入口) は **181**。issue 本文の「182」とは 1 差。定義の差は未確定 (§7)。

**本体の正規化**: 先頭から `ret` まで (最大 200 命令) を逆アセンブルし、分岐先を `T`、`[rip ± d]` を `[rip]`、6 桁超の 16 進即値を `A` に置換して SHA-1。
先頭が `jmp rel32` / `jmp [rip+x]` の thunk は 4 段まで追う。今回の 197 入口はいずれも thunk ではなかった (`thunk_hops = 0`)。

**dsp の名付け**: dsp の export 446 件の先頭は CPU 別ディスパッチ `movsxd rax,[rip+X]; lea r10,[rip+T]; jmp [r10+rax*8]` で、表 T の項 (6 が 374 件、7 が 57 件、1 が 14 件、9 が 1 件) が variant 本体。
表の全項 (2,566 本体) を export 名に対応づけ、**起点 (export) ごとに独立に** direct call を最大 12 段まで辿って到達する本体 (3,646 本体) と、dsp `.text` の call 先のうち IPPCODE にある着地点 (2,470) を照合対象 (5,825 本体) とする。
起点ごとの独立 BFS は `bcab4049` での修正。`f3310a00` は既訪問ノードへ起点を伝播させず、名前集合が不完全だった。

**判定区分** (上から優先):

| 区分 | 判定 | 件数 |
|---|---|---|
| `trivial_body` | 正規化後 8 命令未満 (偶然一致の余地が大きい) | 10 |
| `identified` | 完全一致 かつ 対応 export 名が 1 つ | **8** |
| `family_candidates` | 完全一致 かつ 対応 export 名が 2 つ以上 (共有本体。API 名に決まらない) | **26** |
| `exact_dsp_internal_no_export` | 完全一致 だが export 名へ 12 段以内に到達しない (dsp の内部関数と本体が同一) | **122** |
| `unidentified_no_exact` | 完全一致が無い (近似比は参考。最大 0.58・中央値 0.30) | **31** |

- 完全一致の合計は 166 (= 8 + 26 + 10 + 122)。thunk 追跡 (`exact_final`) で全て一致し、生の本体 (`exact_raw`) による一致は 0 件。
- 近似比 0.9 以上の入口は 0 件。近似比は同定の根拠に使っていない。

**API 族の候補 (26 入口, 7 群)**: 候補名の集合 (`*` は型違いをまとめた表記。`†` は tools/ipp で実装済み (`implemented_poc = 1`))。

| 件数 | 候補名の集合 | tools/ipp 判定 (§4) |
|---|---|---|
| 6 | `ippsConjCcs_*`・`ippsConjPack_*`・`ippsConjPerm_*` (32fc・64fc), `ippsCopy_16s`・`ippsCopy_32f`†・`ippsCopy_32s`・`ippsCopy_64f`・`ippsCopy_64s`・`ippsCopy_8u`, `ippsFIR64f_32f`, `ippsWinKaiser_32f_I`・`ippsWinKaiser_64f_I` | 混在 |
| 4 | `ippsSqrt_32f`・`ippsSqrt_32f_I` | stub のみ |
| 4 | `ippsConjCcs_*`・`ippsConjPack_*`・`ippsConjPerm_*` (32fc・64fc), `ippsCopy_16s`・`ippsCopy_32f`†・`ippsCopy_32s`・`ippsCopy_64f`・`ippsCopy_64s`・`ippsCopy_8u` | 混在 |
| 3 | `ippiResize_8u_C3R`・`ippiResize_8u_C4R` | stub のみ |
| 3 | `ippsAutoCorr_NormA_32f`, `ippsConv_64f`, `ippsCrossCorr_32f`, `ippsFFTInit_R_32f`†・`ippsFFTInit_R_64f`†, `ippsFIR64f_32f`, `ippsZero_16s`・`ippsZero_32f`†・`ippsZero_32s`・`ippsZero_64f`・`ippsZero_64s`・`ippsZero_8u`† | 混在 |
| 3 | `ippsFFTInit_R_32f`†・`ippsFFTInit_R_64f`†, `ippsZero_16s`・`ippsZero_32f`†・`ippsZero_32s`・`ippsZero_64f`・`ippsZero_64s`・`ippsZero_8u`† | 混在 |
| 3 | `ippsConjCcs_*`・`ippsConjPack_*`・`ippsConjPerm_*` (32fc・64fc), `ippsCopy_32s` | stub のみ |

**一意の API 名 (8 入口)**:

| 入口 VA | API 名 | dsp の対応 (depth = export からの call 段数) |
|---|---|---|
| `0x1802f8db0`・`0x1802f9bc0`・`0x1802fa9d0`・`0x1802fb6e0` | `ippsRealToCplx_32f` | depth 1 |
| `0x1802feda0`・`0x1802ffa80` | `ippsSet_8u` | depth 1 |
| `0x1803e2940`・`0x1803e6a80` | `ippsConj_32fc` | depth 1 |

**未同定 163 入口**: `exact_dsp_internal_no_export` 122 (dsp 内部関数の本体と一致。最初の一致候補は 62 種の dsp 本体)・`unidentified_no_exact` 31・`trivial_body` 10。
全入口の一覧は `data/entries.csv` (列: `entry_va`・`class`・`names` (名付けた入口のみ)・`origin_exports`・`tools_ipp_poc`・`insns`・`call_sites`・`dsp_rva`・`dsp_depth`・`ratio`)。`insns` は正規化後の命令数 (手順の長さ。トークン列ではない)。

## 4. tools/ipp の実装対応 (受入条件 2)

判定元: `tools/ipp/data/ipp_matrix.csv` の `implemented_poc` 列 (PoC 実装 43 名)。それ以外は `tools/ipp/REPORT.md` §11 の fail-soft stub (0 戻し + 呼出カウンタ。STRICT のときのみ fail-fast)。

| 入口の分類 (`tools_ipp_poc`) | 入口数 |
|---|---|
| 候補名が全て stub のみ (`stub_only`) | 18 (一意名 8 + 族候補 10) |
| 実装済み名と stub 名の混在 (`mixed`) | 16 (族候補) |
| 候補名が全て実装済み | 0 |

stub 名 28 (`implemented_poc = 0`): `ippiResize_8u_C3R`・`ippiResize_8u_C4R`・`ippsAutoCorr_NormA_32f`・`ippsConjCcs_32fc`・`ippsConjCcs_64fc`・`ippsConjPack_32fc`・`ippsConjPack_64fc`・`ippsConjPerm_32fc`・`ippsConjPerm_64fc`・`ippsConj_32fc`・`ippsConv_64f`・`ippsCopy_16s`・`ippsCopy_32s`・`ippsCopy_64f`・`ippsCopy_64s`・`ippsCopy_8u`・`ippsCrossCorr_32f`・`ippsFIR64f_32f`・`ippsRealToCplx_32f`・`ippsSet_8u`・`ippsSqrt_32f`・`ippsSqrt_32f_I`・`ippsWinKaiser_32f_I`・`ippsWinKaiser_64f_I`・`ippsZero_16s`・`ippsZero_32s`・`ippsZero_64f`・`ippsZero_64s`。
混在の入口に含まれる実装済み名 5: `ippsCopy_32f`・`ippsFFTInit_R_32f`・`ippsFFTInit_R_64f`・`ippsZero_32f`・`ippsZero_8u`。

#2613 の受入 2 の文言に従い、stub のみの 18 入口と混在の 16 入口は本 run では実装しない。実装は別の作業 (`tools/ipp`・#38 系) で扱う。

## 5. 検証・ネガティブコントロール

- **ネガティブコントロール (偶然一致)**: dsp の pdata 関数のうち、IPPCODE への call 先でないもの 3,000 件 (IPP 本体ではないものが大半と推定。厳密な分類は未実施) を、同じ完全一致照合にかけた。一致 **0 件** (`negative_control.exact_matches_with_entries = 0`)。
- **入口数の再現**: 線形走査の 197 は issue 本文の 197 と一致。pdata 基準は 181 (issue 182)。
- **thunk 追跡**: 197 入口すべて `thunk_hops = 0`。
- **修正の影響 (`f3310a00` → `bcab4049`)**: 入口・区分・照合の件数は不変 (8 / 26 / 122 / 31 / 10)。名前集合が変わったのは族候補 16 入口のみで、旧名の集合は全て新名に含まれる。入口ごとに増えた名は stub 6 名 (`ippsAutoCorr_NormA_32f`・`ippsCopy_16s`・`ippsCopy_32s`・`ippsCopy_64f`・`ippsCopy_64s`・`ippsFIR64f_32f`) と実装済み 3 名 (`ippsCopy_32f`・`ippsFFTInit_R_32f`・`ippsFFTInit_R_64f`)。このうち stub 名の集合で新たに加わるのは 4 名 (`ippsAutoCorr_NormA_32f`・`ippsCopy_16s`・`ippsCopy_64f`・`ippsCopy_64s`) で、stub 名は 24 → 28。名付けた入口の内訳は stub のみ 28 → 18・混在 6 → 16。

## 6. 関数ポインタ経由の到達 (受入条件 3・静的確認)

| 確認 | 件数 |
|---|---|
| `.text` の `lea reg,[rip+X]` で IPPCODE を指す箇所 | 0 |
| 即値・変位に IPPCODE 番地 (6 桁超の 16 進) を含む命令 | 0 |
| `.rdata`・`.data`・`.pdata`・`_RDATA`・`IPPDATA` 内の IPPCODE 向き 8 byte 値 | 0 |
| `.text` の間接 call/jmp | 2,714 (call 2,373・jmp 341。`r10` を使う表分岐の形 59 件 (うち `[r10+rax*8]` 33 件)) |

静的にはどの命令・データも IPPCODE の番地を作らない。間接 call/jmp の宛先の実行時の値は未確認 (§7・子 #2643)。

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 間接 call/jmp (2,714 箇所) の実行時の宛先が IPP に当たらないことの確認 (受入 3) | 静的確認のみ。実行経路は未確認 | 子 #2643 ([T-SH-42]) |
| 未同定 163 入口 (dsp 内部関数と一致 122・照合不能 31・自明本体 10) | API 名が付かない。tools/ipp の実装対応を判定できない | 本 PR 本文の未解決表 (追跡のみ。`Closes #2613` で閉じるため本表が正) |
| API 族の候補 26 入口 (共有本体) | 一意の API 名に決まらない | 本 PR 本文の未解決表 (同上) |
| `.pdata` 基準の入口数 181 と issue 本文の 182 | 1 件の定義差 (呼出元の範囲の端の扱い等。未確定) | 本 PR 本文の未解決表 (同上) |
| stub 名 28 (stub のみ 18 入口・混在 16 入口) | 名付けた入口が tools/ipp で未実装 | 既存 #38 (tools/ipp 親) を起票先とする (本 PR では #38 へコメントしない。PM が判断) |
