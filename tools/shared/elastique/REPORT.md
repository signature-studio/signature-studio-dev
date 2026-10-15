# tools/shared/elastique — élastique 2.2.15 (win x64) 静的 IPP 入口 197 件の API 同定 (T-SH-40 / #2613)

既知の類型との関係: lift 欠陥ではないため該当なし (`docs/DEFECTS.md`)。本件は静的 IPP 節の入口の同定のみ。
所有者限定 tier 専用 (`docs/DECISIONS.md` D20)。公開 tier の成果物には含めない。

## 0. 結論

| 受入条件 (#2613) | 結果 |
|---|---|
| 1. 197 入口のそれぞれに IPP API 名か「未同定」 | 197 入口を再現 (線形走査)。**一意の API 名 8 入口** (`ippsRealToCplx_32f` 4・`ippsSet_8u` 2・`ippsConj_32fc` 2)、**API 族の候補集合 26 入口** (dsp の同一本体を共有する export 群、7 群。うち 1 入口 `0x1803e71b0` は偶然一致の候補、§3 注)、**未同定 163 入口** (内訳 §3)。対応表は `data/entries.csv` |
| 2. 同定 API のうち tools/ipp の実装対応が無いもの | 名付けた入口 34 件のうち、**18 件は候補名が全て fail-soft stub のみ** (`tools/ipp` の PoC 未実装。STRICT でのみ fail-fast)、**16 件は実装済み名と stub 名の混在**、実装済みのみは 0 件。stub 名は 28 (§4 に列挙)。#2613 の受入 2 の文言「対応が無い入口が 1 件でも残るなら、D20 の停止条件に従い理由を報告して停止する (その入口は実装しない)」に従い、本 run ではこれらを実装しない |
| 3. 関数ポインタ経由の到達が無いことの確認 | **静的確認 (§6) + unicorn 実行 (§8)**: 静的に IPPCODE 番地を作る命令 0・データ中のポインタ 0。実行範囲で間接 call/jmp の宛先が IPPCODE 入口に当たるもの 0 件 (実行した間接サイト 75/2,714 のみ)。被覆の拡大は子 #3334 ([T-SH-69]) に移管 |
| 4. REPORT に測定 commit・再現コマンド・差分 | 本書 §1・§2 |
| 追記 (#2613 コメント 2026-10-14 16:23) の 1〜3: dispatch 表の飛び先 186 個の同定・2 段目 251 個の同定・初期化スタブと外向き分岐 | **本 PR では扱わない**。原文のまま子 **#2667** ([T-SH-43]) に移管 (§7) |
| 追記 4: thunk 頭 33 本の到達元 | 静的参照 0 件 (§6)。実行で枠を読む命令は 0 件 (§8)。子 #3334 ([T-SH-69]) に移管 (§7) |

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
FL_WIN64_DIR="$RUNNER_TEMP/fl-win64" python3 tools/shared/elastique/ipp_entries.py   # 実測 (real): 測定 commit 時 38.2 秒 (load average 0.25 → 0.74)。検証 HEAD `9ecc1301` での再実行 22.4 秒 (実行時間は機械負荷で変わるため参考値。出力の一致が検証の対象)
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
表の項 (項数の合計 2,666 のうち distinct 2,566 本体。100 件は複数の export で共有) を export 名に対応づけ、**起点 (export) ごとに独立に** direct call を最大 12 段まで辿って到達する本体 (3,646 本体) と、dsp `.text` の call 先のうち IPPCODE にある着地点 (2,470) を照合対象 (5,825 本体) とする。
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

注 (偶然一致の候補): 上の ippiResize 族 3 入口のうち `0x1803e71b0` (10 命令・呼出元 33 か所) は `push rcx/rdx/r8/r9; call T; pop ×4; ret` の退避ラッパで、呼出先 `0x1800010a0` は正規化により `T` に伏せられる。dsp の同形ラッパ `0x1839810` と形だけ一致したもので、呼出先の同一性は確認していない。TRIVIAL (8 命令) を超えるため除外されず、偶然一致の候補として残す。未同定へ戻した場合の試算 (script・CSV は変えていない。`data/entries.csv` から再集計): 族候補 25・未同定 164 (`exact_dsp_internal_no_export` 123・照合不能 31・自明本体 10)・名付けた入口 33 (stub のみ 17・混在 16)。stub 名は他の 2 入口が同名を持つため 28 のまま。

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
| 候補名が全て stub のみ (`stub_only`) | 18 (一意名 8 + 族候補 10。族候補のうち 1 入口は §3 注の偶然一致の候補) |
| 実装済み名と stub 名の混在 (`mixed`) | 16 (族候補) |
| 候補名が全て実装済み | 0 |

stub 名 28 (`implemented_poc = 0`): `ippiResize_8u_C3R`・`ippiResize_8u_C4R`・`ippsAutoCorr_NormA_32f`・`ippsConjCcs_32fc`・`ippsConjCcs_64fc`・`ippsConjPack_32fc`・`ippsConjPack_64fc`・`ippsConjPerm_32fc`・`ippsConjPerm_64fc`・`ippsConj_32fc`・`ippsConv_64f`・`ippsCopy_16s`・`ippsCopy_32s`・`ippsCopy_64f`・`ippsCopy_64s`・`ippsCopy_8u`・`ippsCrossCorr_32f`・`ippsFIR64f_32f`・`ippsRealToCplx_32f`・`ippsSet_8u`・`ippsSqrt_32f`・`ippsSqrt_32f_I`・`ippsWinKaiser_32f_I`・`ippsWinKaiser_64f_I`・`ippsZero_16s`・`ippsZero_32s`・`ippsZero_64f`・`ippsZero_64s`。
混在の入口に含まれる実装済み名 5: `ippsCopy_32f`・`ippsFFTInit_R_32f`・`ippsFFTInit_R_64f`・`ippsZero_32f`・`ippsZero_8u`。

#2613 の受入 2 の文言に従い、stub のみの 18 入口と混在の 16 入口は本 run では実装しない。実装は別の作業 (`tools/ipp`・#38 系) で扱う。

## 5. 検証・ネガティブコントロール

- **ネガティブコントロール (偶然一致)**: dsp の pdata 関数のうち、IPPCODE への call 先でないもの 3,000 件 (IPP 本体ではないものが大半と推定。厳密な分類は未実施) を、同じ完全一致照合にかけた。一致 **0 件** (`negative_control.exact_matches_with_entries = 0`)。
- **入口数の再現**: 線形走査の 197 は issue 本文の 197 と一致。pdata 基準は 181 (issue 182)。
- **差し戻し round 2 の再実行**: 検証 HEAD `9ecc1301` で §2 のコマンドを再実行した。出力は §2 のログと全行一致。`data/entries.csv` は差分 0 (`git status` に現れない)。script は測定 commit から変えていない (`git diff bcab4049 HEAD -- tools/shared/elastique/ipp_entries.py` = 0 行)。
- **thunk 追跡**: 197 入口すべて `thunk_hops = 0`。
- **修正の影響 (`f3310a00` → `bcab4049`)**: 入口・区分・照合の件数は不変 (8 / 26 / 122 / 31 / 10)。名前集合が変わったのは族候補 16 入口のみで、旧名の集合は全て新名に含まれる。入口ごとに増えた名は stub 6 名 (`ippsAutoCorr_NormA_32f`・`ippsCopy_16s`・`ippsCopy_32s`・`ippsCopy_64f`・`ippsCopy_64s`・`ippsFIR64f_32f`) と実装済み 3 名 (`ippsCopy_32f`・`ippsFFTInit_R_32f`・`ippsFFTInit_R_64f`)。このうち stub 名の集合で新たに加わるのは 4 名 (`ippsAutoCorr_NormA_32f`・`ippsCopy_16s`・`ippsCopy_64f`・`ippsCopy_64s`) で、stub 名は 24 → 28。名付けた入口の内訳は stub のみ 28 → 18・混在 6 → 16。

## 6. 関数ポインタ経由の到達 (受入条件 3・静的確認)

| 確認 | 件数 |
|---|---|
| `.text` の `lea reg,[rip+X]` で IPPCODE を指す箇所 | 0 |
| 即値・変位に IPPCODE 番地 (6 桁超の 16 進) を含む命令 | 0 |
| `.rdata`・`.data`・`.pdata`・`_RDATA`・`IPPDATA` 内の IPPCODE 向き 8 byte 値 | 0 |
| `.text` の間接 call/jmp | 2,714 (call 2,373・jmp 341。`r10` を使う表分岐の形 59 件 (うち `[r10+rax*8]` 33 件)) |

静的にはどの命令・データも IPPCODE の番地を作らない。間接 call/jmp の宛先の実行時の値は、実行範囲のみ §8 で確認した (§7・子 #3334)。

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 間接 call/jmp (2,714 箇所) の実行時の宛先が IPP に当たらないことの確認 (受入 3) | 実行範囲 75 サイトのみ (§8)。全サイトは未確認 | 子 #3334 ([T-SH-69]) |
| 追記受入 1〜3 (dispatch 表の飛び先 186 個の同定・2 段目 251 個の IPP 同定・初期化スタブと外向き分岐 33 件) | 未実施。本 PR では扱わない | 子 #2667 ([T-SH-43])。親 #2613 の追記コメント (16:23) の原文を移した |
| 追記受入 4 (thunk 頭 33 本の到達元) | 静的参照 0 件。実行で枠を読む命令は 0 件 (§8) | 子 #3334 ([T-SH-69]) |
| 未同定 163 入口 (dsp 内部関数と一致 122・照合不能 31・自明本体 10) | API 名が付かない。tools/ipp の実装対応を判定できない | 本 PR 本文の未解決表 (追跡のみ。`Closes #2613` で閉じるため本表が正) |
| API 族の候補 26 入口 (共有本体) | 一意の API 名に決まらない | 本 PR 本文の未解決表 (同上) |
| `.pdata` 基準の入口数 181 と issue 本文の 182 | 1 件の定義差 (呼出元の範囲の端の扱い等。未確定) | 本 PR 本文の未解決表 (同上) |
| stub 名 28 (stub のみ 18 入口・混在 16 入口) | 名付けた入口が tools/ipp で未実装 | 既存 #38 (tools/ipp 親) を起票先とする (本 PR では #38 へコメントしない。PM が判断) |

## 8. 実行時の間接 call/jmp 宛先 (T-SH-42 / #2643・unicorn 実行)

§6 の「実行時の宛先は未確認」を、unicorn による実行で一部埋めた。Windows 実行ではない (runner に wine・qemu 等が無い)。結論は**実行した範囲**に限る。

### 8.1 測定・再現

- 測定 commit: **`2781377b`** (コードと `data/runtime_indirect.csv` を変えた最後の commit)。以降の commit は REPORT のみ。
- 差分 (測定後のコード範囲): `git diff 2781377b HEAD -- tools/shared/elastique/dyn_trace.py tools/shared/elastique/data/runtime_indirect.csv` → 出力 0 行。
- 再現した結果: 測定 commit の HEAD で 2 回実行し、`summary.json` は一致、コミット済みの `runtime_indirect.csv` は差分 0。
- 素材: §1 と同じ `block24357_PE.bin` (sha256 先頭 16 桁 `8551e92209cdd2ce`) を `tools/shared/work/win/elastique_x64.dll` に置く。

```sh
mkdir -p tools/shared/work/win && cp "$RUNNER_TEMP/fl-win64/extracted/block24357_PE.bin" tools/shared/work/win/elastique_x64.dll
uv venv tools/shared/work/venv && uv pip install --python tools/shared/work/venv/bin/python unicorn pefile capstone
tools/shared/work/venv/bin/python tools/shared/elastique/dyn_trace.py   # 実測 (real): 8.2 秒 (user 8.2 秒)。load average 0.16 → 0.29。出力は tools/shared/work/elastique/dyn/ (gitignore)
```

### 8.2 方法

- 読込: PE を preferred base `0x180000000` に展開。IAT の 79 slot (kernel32 77・WS2_32 2) を `ret` の stub に向ける。`HeapAlloc`・`HeapReAlloc`・`HeapSize` は bump 割当。`ntohl`・`htonl`・`GetModuleHandleW`・`HeapFree`・`GetProcessHeap` は値を返す。他は戻り値 0。
- 実行順: DllMain (`DLL_PROCESS_ATTACH`) → `ElAllocator_SetFunctions` (host の malloc・free の stub を渡す。引数規約は仮定) → export 14 件 × 2 通り → thunk 頭 33 本 × 2 通り。
  - `zero`: rcx・rdx・r8・r9 = 0。`scratch`: rcx = 4 KB の書込み可能領域、rdx = その +4 KB、r8 = 44100、r9 = 2。
- 記録: 命令ごとに、直前が call/jmp (直接・間接とも) なら、次に実行された命令番地を宛先とし、(分岐元, 宛先) を数える。宛先の分類は `ipp_entry` (入口 197・`data/entries.csv`)・`ipp_other`・`text`・`stub:<import>`・`other`。
- 上限: 1 run あたり 3,000,000 命令。

### 8.3 実測

| 項目 | 値 |
|---|---|
| run 数 | 96 (DllMain 1・SetFunctions 1・export 14 × 2・thunk 33 × 2) |
| run の結果 | returned 70・count_limit 1 (`thunk:0x180001aa0:scratch`)・uc_error 25 (`Unhandled CPU exception` 8・`Invalid memory read/write/fetch` 17)。uc_error は合成引数由来と推定 (未切り分け) |
| 命令数 (全 run 合計) | 11,406,760 |
| 分岐 edge (分岐元, 宛先。直接・間接) | 344 |
| 間接 edge (分岐元, 宛先) | 76 |
| 実行した間接 call/jmp サイト | **75 / 静的 2,714 (2.8%)** |
| 間接宛先の種類 | 73 |
| 間接 edge の宛先の分類 | `text` 58・IAT/host stub 17・`other` 1・**`ipp_entry` 0**・`ipp_other` 0 |
| 直接 call/jmp で到達した IPPCODE 入口 (distinct) | 23 (例: `0x1803e71b0` 初期化スタブ・`0x1802f8000`・`0x1802f83b8`) |
| thunk 頭の dispatch `jmp qword ptr [r10 + rax*8]` | 33 サイト全て実行。宛先は全て `.text` (variant 本体) |
| thunk 頭 33 本の枠 (`.data` の 8 byte 値) を読む命令 | **0** (`slot_readers.csv` 0 行) |

`other` 1 件は `jmp rax` (`0x1802f5f80`) の宛先 `0xfdd000000000300f` で、`Declicker_CreateInstance:scratch` の合成引数により壊れた `rax` の値。実 FL で起きる宛先とは見なさない (未確認)。

### 8.4 受入条件への対応

| 受入 (#2643 の本文) | 結果 |
|---|---|
| 間接 call/jmp の実行時宛先を記録 | **部分**: 実行範囲 75 / 2,714 サイト。全サイトは未実行 → 子 #3334 |
| 記録した宛先のうち IPPCODE 入口 (197) に当たるものが 0 件 | **実行範囲で 0 件**。全体の証明ではない |
| thunk 頭 33 本の到達元 (#2613 追記 4) | **未観測**。枠を読む命令は 0 件。thunk は harness が直接呼んだ (合成)。→ 子 #3334 |
| REPORT に測定 commit・再現・差分 | §8.1 |

### 8.5 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 間接サイトの被覆 75 / 2,714 (export の引数規約が不明で、入力を合成している) | 「0 件」の結論が実行範囲に限られる | 子 #3334 (T-SH-69) |
| thunk 頭 33 本の到達元 (枠を読む命令 0 件) | 実プログラム内の呼出元が未確認 | 子 #3334 (T-SH-69) |
| uc_error 25 run の原因 | 合成引数の不適合か emulator の未対応かが未切り分け | 子 #3386 (T-SH-73)。§9 で追記 |

## 9. 被覆拡大と枠の読み手 (T-SH-69 / #3334)

既知の類型との関係: 該当なし (`docs/DEFECTS.md`)。測定・方法・再現・差分は `REPORT_APPENDIX_3334.md` (§9.1〜§9.8)。

| 受入条件 (#3334) | 結果 |
|---|---|
| 1. 被覆を広げた間接サイト数 (/ 2,714) | 合成引数の変種 3 種の和集合で **77 サイト** (§8 の 75 から +2)。FL の実呼出し形は未確定。残りは子 #3386 (T-SH-73) |
| 2. 広げた実行で、IPPCODE 入口 (197) に当たる間接宛先 | **0 件**。陰性対照 (入口 1 件を足すと 1 件検出) で検出器を確認。入口以外の IPPCODE 宛先 1 件は付録 §9.5 |
| 3. thunk 頭 33 本の枠を読む命令 | **0 件** (190 run・静的な厳密参照も 0 件)。到達元の特定は子 #3387 (T-SH-74) |
| 4. 測定 commit・再現・差分 | 測定 commit `982e50c69` (付録 §9.7)。`git diff 982e50c69 HEAD` の出力 0 行 |
