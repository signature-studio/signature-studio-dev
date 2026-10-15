# tools/shared/elastique — élastique 2.2.15 (win x64) 静的 IPP 入口 197 件の API 同定 (T-SH-40 / #2613)

既知の類型との関係: lift 欠陥ではないため該当なし (`docs/DEFECTS.md`)。本件は静的 IPP 節の入口の同定のみ。
所有者限定 tier 専用 (`docs/DECISIONS.md` D20)。公開 tier の成果物には含めない。

本書の更新: #3457 (T-SH-85) の `direct_calls` の範囲の修正と IPPCODE の `lea rip` 走査の拡張 (§1・§3・§5・§6・§7)。

## 0. 結論

| 受入条件 (#2613) | 結果 |
|---|---|
| 1. 197 入口のそれぞれに IPP API 名か「未同定」 | 197 入口を再現 (線形走査)。**一意の API 名 34 入口** (`ippsRealToCplx_32f` 12・`ippsSum_32f` 6・`ippsMagnitude_32fc` 4・`ippsMin_32f` 4・`ippsMax_32f` 4・`ippsSet_8u` 2・`ippsConj_32fc` 2)、**API 族の候補 98 入口** (dsp の同一本体を共有する export 群、24 群。うち 1 入口 `0x1803e71b0` は偶然一致の候補、§3 注)、**未同定 65 入口** (内訳 §3)。修正前 (`93307cc6a`) は 8 / 26 / 163 (§3 の修正前後)。対応表は `data/entries.csv` |
| 2. 同定 API のうち tools/ipp の実装対応が無いもの | 名付けた入口 132 件のうち、**75 件は候補名が全て fail-soft stub のみ** (`tools/ipp` の PoC 未実装。STRICT でのみ fail-fast)、**57 件は実装済み名と stub 名の混在**、実装済みのみは 0 件。stub 名は 88 (§4 に列挙)。#2613 の受入 2 の文言「対応が無い入口が 1 件でも残るなら、D20 の停止条件に従い理由を報告して停止する (その入口は実装しない)」に従い、本 run ではこれらを実装しない |
| 3. 関数ポインタ経由の到達が無いことの確認 | **静的確認 (§6) + unicorn 実行 (§8)**: 静的に IPPCODE 番地を作る命令は `.text` で 0 (IPPCODE 内の `lea rip` が 158 箇所あり、宛先は全て IPPCODE 内・入口 0。#3457 で追加)・データ中のポインタ 0。実行範囲で間接 call/jmp の宛先が IPPCODE 入口に当たるもの 0 件 (実行した間接サイト 75/2,714 のみ)。被覆の拡大は子 #3334 ([T-SH-69]) に移管 |
| 4. REPORT に測定 commit・再現コマンド・差分 | 本書 §1・§2 |
| 追記 (#2613 コメント 2026-10-14 16:23) の 1〜3: dispatch 表の飛び先 186 個の同定・2 段目 251 個の同定・初期化スタブと外向き分岐 | **本 PR では扱わない**。原文のまま子 **#2667** ([T-SH-43]) に移管 (§7) |
| 追記 4: thunk 頭 33 本の到達元 | 静的参照 0 件 (§6)。実行で枠を読む命令は 0 件 (§8)。子 #3334 ([T-SH-69]) に移管 (§7) |

## 1. 対象・素材・測定 commit

- 素材: `fl-win64` (`tar --zstd -xf` 5.6 秒)。`extracted/block24357_PE.bin` (4,997,632 B, sha256 先頭 16 桁 `8551e92209cdd2ce`) を `tools/shared/work/win/elastique_x64.dll` に複製 (gitignore)。
  PE 情報: ImageBase `0x180000000`、`.text` RVA `0x1000`・vsize `0x2f6550`、**IPPCODE RVA `0x2f8000`・vsize `0xef1c2` (= 979,394 B)**、`.pdata` 1,956 関数 (`.text` 内)、export 15 (`Auftakt_CreateInstance` 等)。
- 照合先: `extracted/block24356_PE.bin` (`dsp_ippv2_x64.dll`, ImageBase `0x180000000`, export 446, IPPCODE RVA `0x17e0000`・vsize `0x6dc771`)。
- 検証起点: `93307cc6a` (origin/main。#3457 の基点。前の検証起点は `f3102162`)。
- **測定 commit (コードを変えた最後の commit): `c7e0bee8c`** (`fix(shared): élastique 静的走査の direct_calls を関数範囲で辿り、IPPCODE の lea rip 走査を広げる (#3457)`)。前の測定 commit は `bcab4049` (`fix(shared): élastique 族候補の起点伝播を起点ごとの BFS に直す`)。
  前の測定 commit `f3310a00` は `reach()` が既訪問ノードへ起点名を足したとき子へ伝播させず、族候補 26 入口のうち 16 入口の名前集合が不完全だった (round 1 の差し戻し)。`bcab4049` で修正し、全入口の名前集合を再計算した。
- 差分 (修正の範囲): `git diff f3310a00 bcab4049 -- tools/shared/elastique/ipp_entries.py` (`reach()` を起点ごとの BFS に変更、CSV 列名 `tokens` → `insns`、出力ラベルの探索深さ)。
- 差分 (#3457 の修正の範囲): `git diff 93307cc6a c7e0bee8c -- tools/shared/elastique/ipp_entries.py tools/shared/elastique/data/entries.csv` (`direct_calls` の範囲・`indirect_scan` の IPPCODE 走査・`data/entries.csv` の再集計)。
- 差分 (測定後のコード範囲): `git diff c7e0bee8c HEAD -- tools/shared/elastique/ipp_entries.py tools/shared/elastique/data/entries.csv` → 出力 0 行 (`-- tools/shared/elastique` 全体では、測定後は本書 REPORT.md の更新だけ)。

## 2. 再現

```sh
# 素材の展開 (fl-win64 は docs/WORKFLOW.md §11 の手順)
mkdir -p "$RUNNER_TEMP/fl-win64" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64"
mkdir -p tools/shared/work/win && cp "$RUNNER_TEMP/fl-win64/extracted/block24357_PE.bin" tools/shared/work/win/elastique_x64.dll
FL_WIN64_DIR="$RUNNER_TEMP/fl-win64" python3 tools/shared/elastique/ipp_entries.py   # 実測 (real): 測定 commit `c7e0bee8c` で 44.1 秒 (user 43.9 秒・run 後の load average 0.81)。前の測定 commit `bcab4049` は 38.2 秒 (実行時間は機械負荷で変わるため参考値。出力の一致が検証の対象)
```

- 出力: `data/entries.csv` (197 行・コミット対象) と `tools/shared/work/elastique/facts.json` (中間物・gitignore)。
- 実行ログ (測定 commit `c7e0bee8c` の HEAD 上の出力。§3 の数値の出典。先頭 2 行の素材パスは省く):

```text
linear-sweep entries (distinct call/jmp targets in IPPCODE): 197 (call/jmp sites 810)
pdata (.text 関数) 件数: 1956; 入口のうち呼出元が pdata 関数内にあるもの: 181
dsp export 446: variant 数の分布 (表の項数) {1: 14, 6: 374, 7: 57, 9: 1}
dsp 関数先頭の候補 (pdata 先頭と .text・IPPCODE の rel32 call 着地点): 34866
direct_calls の範囲 (到達集合 5079 本体): {'ret まで (範囲なし)': 1393, 'pdata': 2754, 'pdata SPAN_IPP 打ち切り': 0, 'IPPCODE 次の先頭まで': 932, 'IPPCODE 次の先頭まで SPAN_IPP 打ち切り': 63}
範囲の最後の命令 (mnemonic): {'pdata': {'nop': 2038, 'jle': 393, 'je': 95, 'ret': 57, 'jmp': 48, 'jbe': 32}, 'IPPCODE 次の先頭まで': {'nop': 528, 'int3': 194, 'ret': 119, 'jmp': 23, 'add': 17, 'addpd': 6}}
dsp 候補本体: export 表の variant 2566 個 / export から call で 12 段内 5079 個 / dsp .text 由来の IPPCODE 着地点 2470 個 → 照合対象 6724 個
照合: {'exact_final': 166, 'fuzzy_only': 31}
区分: {'family_candidates': 98, 'trivial_body': 10, 'identified': 34, 'unidentified_no_exact': 31, 'exact_dsp_internal_no_export': 24}
間接 call/jmp の形: {'rax': 261, 'qword ptr [rax]': 100, 'qword ptr [rax + 0x28]': 78, 'qword ptr [rax + 8]': 61, 'qword ptr [rax + 0x58]': 49, 'qword ptr [rax + 0x20]': 44, 'qword ptr [rax + 0x38]': 43, 'qword ptr [rax + 0x30]': 43, 'qword ptr [rax + 0x10]': 41, 'qword ptr [rax + 0x48]': 37, 'table[r10+rax*8]': 33, 'qword ptr [rax + 0x70]': 32}
即値・変位に IPPCODE 番地を含む命令 (.text): 0
lea rip で IPPCODE を指す箇所 (.text と IPPCODE): 158 箇所 / 152 着地点 (うち入口 0)
  うち IPPCODE 内から: 158 箇所 / 152 着地点 (うち入口 0) 例 [('0x18030e133', '0x18030e277'), ('0x18030e147', '0x18030e237'), ('0x18030e15b', '0x18030e1b0'), ('0x18030e167', '0x18030e1f7'), ('0x18030e350', '0x18030e493')] (全件は facts.json)
間接 call/jmp (.text): 2714 箇所 (例 [(6174, 'jmp', 'qword ptr [r10 + rax*8]'), (6222, 'jmp', 'qword ptr [r10 + rax*8]'), (6270, 'jmp', 'qword ptr [r10 + rax*8]')])。IPPCODE 内: 186 箇所
.rdata/.data の IPPCODE 向きポインタ: 0 (うち入口 0、入口外 0)
```

(前の測定 `f3310a00` のログは「export から call で 3 段内 3646 個」と表示していたが、実際の探索深さは `REACH_DEPTH` = 12。表示ラベルを合わせた。数値は不変。)

## 3. 方法と結果

**入口 (197)**: `.text` を線形走査 (invalid byte は 1 byte 飛ばし)。`E8`/`E9` (rel32 の call/jmp) の着地点のうち IPPCODE 内のものを distinct で数える。
呼出箇所は 810。`.pdata` 基準 (呼出元が `.pdata` の関数内にある入口) は **181**。issue 本文の「182」とは 1 差。定義の差は未確定 (§7)。

**本体の正規化**: 先頭から `ret` まで (最大 200 命令) を逆アセンブルし、分岐先を `T`、`[rip ± d]` を `[rip]`、6 桁超の 16 進即値を `A` に置換して SHA-1。
先頭が `jmp rel32` / `jmp [rip+x]` の thunk は 4 段まで追う。今回の 197 入口はいずれも thunk ではなかった (`thunk_hops = 0`)。

**dsp の名付け**: dsp の export 446 件の先頭は CPU 別ディスパッチ `movsxd rax,[rip+X]; lea r10,[rip+T]; jmp [r10+rax*8]` で、表 T の項 (6 が 374 件、7 が 57 件、1 が 14 件、9 が 1 件) が variant 本体。
表の項 (項数の合計 2,666 のうち distinct 2,566 本体。100 件は複数の export で共有) を export 名に対応づけ、**起点 (export) ごとに独立に** direct call を最大 12 段まで辿って到達する本体 (5,079 本体。#3457 の修正前は 3,646) と、dsp `.text` の call 先のうち IPPCODE にある着地点 (2,470) を照合対象 (6,724 本体。修正前は 5,825) とする。
起点ごとの独立 BFS は `bcab4049` での修正。`f3310a00` は既訪問ノードへ起点を伝播させず、名前集合が不完全だった。

**直接 call の範囲 (#3457 で修正)**: 旧 `direct_calls` は本体を先頭から読み、最初の `ret` で止まった。早期 `ret` の後へ `je` で戻る後続ブロックの call を辿れなかった (例: dsp `0xdb08e0` は `0xdb0906` の `ret` の後、`0xdb0907` から `call 0x1a946c0` を持つ)。修正後は範囲の末尾まで線形に読む。範囲は、pdata に入る関数は pdata の End (`.text` 2,754 本体)、IPPCODE (pdata 無し) は次の既知の関数先頭 (`.text`・IPPCODE 内の rel32 call 着地点と pdata 先頭) と 0x2000 バイトのうち近い方 (932 本体。うち 63 本体は 0x2000 で打ち切り)。pdata に入らない `.text` 関数 (1,393 本体) は範囲を決めず、従来どおり `ret` で止める (§7 の子 #3490)。

**判定区分** (上から優先):

| 区分 | 判定 | 件数 |
|---|---|---|
| `trivial_body` | 正規化後 8 命令未満 (偶然一致の余地が大きい) | 10 |
| `identified` | 完全一致 かつ 対応 export 名が 1 つ | **34** |
| `family_candidates` | 完全一致 かつ 対応 export 名が 2 つ以上 (共有本体。API 名に決まらない) | **98** |
| `exact_dsp_internal_no_export` | 完全一致 だが export 名へ 12 段以内に到達しない (dsp の内部関数と本体が同一) | **24** |
| `unidentified_no_exact` | 完全一致が無い (近似比は参考。最大 0.58・中央値 0.30) | **31** |

- 完全一致の合計は 166 (= 34 + 98 + 10 + 24)。thunk 追跡 (`exact_final`) で全て一致し、生の本体 (`exact_raw`) による一致は 0 件。
- 近似比 0.9 以上の入口は 0 件。近似比は同定の根拠に使っていない。

**API 族の候補 (98 入口, 24 群)**: 候補名の集合は `data/entries.csv` の `names` 列で決まる。群の大きさは、2 名の群 23 入口・12 名の群 23 入口・6 名の群 17 入口・3 名の群 8 入口が多い。45〜52 名の群が 15 入口ある (先頭名 `ippiFilterBoxBorder_8u_C1R`・`ippsAndC_32u_I`・`ippiCopy_8u_C3R`・`ippiCopyReplicateBorder_8u_C3R` の群などの型違いを含む)。多数の export が同じ本体を呼ぶ共通の下位関数と見られ、API 名には決まらない。族の到達深さは 1 段が 63 入口・2 段が 27 入口。

注 (偶然一致の候補): 上の ippiResize 族 3 入口のうち `0x1803e71b0` (10 命令・呼出元 33 か所) は `push rcx/rdx/r8/r9; call T; pop ×4; ret` の退避ラッパで、呼出先 `0x1800010a0` は正規化により `T` に伏せられる。dsp の同形ラッパ `0x1839810` と形だけ一致したもので、呼出先の同一性は確認していない。TRIVIAL (8 命令) を超えるため除外されず、偶然一致の候補として残す。未同定へ戻した場合の試算 (`data/entries.csv` から再集計。#3457 時点): 族候補 97・未同定 66 (`exact_dsp_internal_no_export` 25・照合不能 31・自明本体 10)。

**一意の API 名 (34 入口)**:

| API 名 | 入口数 | dsp の対応 (depth = export からの call 段数) |
|---|---|---|
| `ippsRealToCplx_32f` | 12 | depth 1 |
| `ippsSum_32f` | 6 | depth 2 (変種 → 1 段の関数 → 本体。例 `0x1803c47b0`) |
| `ippsMagnitude_32fc`・`ippsMin_32f`・`ippsMax_32f` | 4 ずつ | depth 1 |
| `ippsSet_8u` | 2 | depth 1 |
| `ippsConj_32fc` | 2 | depth 1 |

入口 VA の一覧は `data/entries.csv` (`class` = `identified`)。

**未同定 65 入口**: `exact_dsp_internal_no_export` 24 (dsp 内部関数の本体と一致。最初の一致候補は 15 種の dsp 本体)・`unidentified_no_exact` 31・`trivial_body` 10。
全入口の一覧は `data/entries.csv` (列: `entry_va`・`class`・`names` (名付けた入口のみ)・`origin_exports`・`tools_ipp_poc`・`insns`・`call_sites`・`dsp_rva`・`dsp_depth`・`ratio`)。`insns` は正規化後の命令数 (手順の長さ。トークン列ではない)。

**修正前後 (`93307cc6a` → `c7e0bee8c`, #3457)**: 入口は 197 のまま。区分の遷移は、`exact_dsp_internal_no_export` → `family_candidates` 72・→ `identified` 26・→ 不変 24、`family_candidates` → 不変 26、`identified` → 不変 8、`unidentified_no_exact` 31・`trivial_body` 10 は不変 (区分が変わった入口 98)。`names` が変わった入口は 119、`dsp_depth` が変わった入口は 118。`ratio`・`insns`・`call_sites` は変わらない。`dsp_rva` (候補本体の並び) は 63 入口で変わる (到達集合が増えたため)。例: `0x1803c47b0` は `exact_dsp_internal_no_export` (depth −1) から `identified` (`ippsSum_32f`・depth 2) になった。

## 4. tools/ipp の実装対応 (受入条件 2)

判定元: `tools/ipp/data/ipp_matrix.csv` の `implemented_poc` 列 (PoC 実装 43 名)。それ以外は `tools/ipp/REPORT.md` §11 の fail-soft stub (0 戻し + 呼出カウンタ。STRICT のときのみ fail-fast)。

| 入口の分類 (`tools_ipp_poc`) | 入口数 |
|---|---|
| 候補名が全て stub のみ (`stub_only`) | 75 |
| 実装済み名と stub 名の混在 (`mixed`) | 57 |
| 候補名が全て実装済み | 0 |

stub 名 88 (`implemented_poc = 0`): `ippSetCpuFeatures`・`ippiCopyReplicateBorder_8u_C3R`・`ippiCopyReplicateBorder_8u_C4R`・`ippiCopy_8u_C3R`・`ippiCopy_8u_C4R`・`ippiFilterBoxBorder_8u_C1R`・`ippiFilterBoxBorder_8u_C3R`・`ippiFilterBoxBorder_8u_C4R`・`ippiFilterBox_8u_C4R`・`ippiResizeSqrPixel_8u_C1R`・`ippiResizeSqrPixel_8u_C3R`・`ippiResizeSqrPixel_8u_C4R`・`ippiResize_8u_C3R`・`ippiResize_8u_C4R`・`ippiWarpBilinearQuad_8u_C3R`・`ippiWarpBilinearQuad_8u_C4R`・`ippsAbs_32f`・`ippsAbs_32f_I`・`ippsAddC_64f`・`ippsAndC_32u_I`・`ippsAutoCorr_NormA_32f`・`ippsConjCcs_32fc`・`ippsConjCcs_64fc`・`ippsConjPack_32fc`・`ippsConjPack_64fc`・`ippsConjPerm_32fc`・`ippsConjPerm_64fc`・`ippsConj_32fc`・`ippsConv_64f`・`ippsCopy_16s`・`ippsCopy_64f`・`ippsCopy_64s`・`ippsCopy_8u`・`ippsCplxToReal_32fc`・`ippsCrossCorr_32f`・`ippsFFTFwd_RToCCS_32f`・`ippsFFTFwd_RToCCS_64f`・`ippsFFTFwd_RToCCS_64f_I`・`ippsFFTFwd_RToPerm_32f`・`ippsFFTFwd_RToPerm_32f_I`・`ippsFFTFwd_RToPerm_64f`・`ippsFFTFwd_RToPerm_64f_I`・`ippsFFTInv_CCSToR_32f`・`ippsFFTInv_CCSToR_64f`・`ippsFFTInv_CCSToR_64f_I`・`ippsFFTInv_PermToR_32f`・`ippsFFTInv_PermToR_32f_I`・`ippsFFTInv_PermToR_64f`・`ippsFFTInv_PermToR_64f_I`・`ippsFIR64f_32f`・`ippsFIRGenBandpass_64f`・`ippsFIRGenBandstop_64f`・`ippsFIRGenHighpass_64f`・`ippsFIRGenLowpass_64f`・`ippsFilterMedian_32f_I`・`ippsIIRGetDlyLine64f_32f`・`ippsIIRGetDlyLine_32f`・`ippsIIRGetDlyLine_32fc`・`ippsIIRInit64f_BiQuad_32f`・`ippsIIRSetDlyLine64f_32f`・`ippsIIRSetDlyLine_32fc`・`ippsImag_32fc`・`ippsMagnitude_32fc`・`ippsMax_32f`・`ippsMin_32f`・`ippsMove_16s`・`ippsMove_32s`・`ippsMove_64f`・`ippsMove_64s`・`ippsMulC_64f`・`ippsMulC_64f_I`・`ippsPhase_32f`・`ippsRealToCplx_32f`・`ippsReal_32fc`・`ippsSet_8u`・`ippsSqrt_32f`・`ippsSqrt_32f_I`・`ippsSum_32f`・`ippsThreshold_GTVal_32f`・`ippsThreshold_GTVal_32f_I`・`ippsThreshold_LTVal_32f`・`ippsThreshold_LTVal_32f_I`・`ippsWinKaiser_32f_I`・`ippsWinKaiser_64f_I`・`ippsZero_16s`・`ippsZero_32s`・`ippsZero_64f`・`ippsZero_64s`。
名付けた入口に含まれる実装済み名 21: `ippsCopy_32f`・`ippsFFTFwd_RToCCS_32f_I`・`ippsFFTFwd_RToPack_32f`・`ippsFFTFwd_RToPack_32f_I`・`ippsFFTFwd_RToPack_64f`・`ippsFFTFwd_RToPack_64f_I`・`ippsFFTGetSize_R_32f`・`ippsFFTGetSize_R_64f`・`ippsFFTInit_R_32f`・`ippsFFTInit_R_64f`・`ippsFFTInv_CCSToR_32f_I`・`ippsFFTInv_PackToR_32f`・`ippsFFTInv_PackToR_32f_I`・`ippsFFTInv_PackToR_64f`・`ippsFFTInv_PackToR_64f_I`・`ippsMove_32f`・`ippsMove_8u`・`ippsMulC_32f`・`ippsMulC_32f_I`・`ippsZero_32f`・`ippsZero_8u`。

#2613 の受入 2 の文言に従い、stub のみの 75 入口と混在の 57 入口 (#3457 時点) は本 run では実装しない。実装は別の作業 (`tools/ipp`・#38 系) で扱う。

## 5. 検証・ネガティブコントロール

- **ネガティブコントロール (偶然一致)**: dsp の pdata 関数のうち、IPPCODE への call 先でないもの 3,000 件 (IPP 本体ではないものが大半と推定。厳密な分類は未実施) を、同じ完全一致照合にかけた。一致 **0 件** (`negative_control.exact_matches_with_entries = 0`)。
- **入口数の再現**: 線形走査の 197 は issue 本文の 197 と一致。pdata 基準は 181 (issue 182)。
- **差し戻し round 2 の再実行**: 検証 HEAD `9ecc1301` で §2 のコマンドを再実行した。出力は §2 のログと全行一致。`data/entries.csv` は差分 0 (`git status` に現れない)。script は測定 commit から変えていない (`git diff bcab4049 HEAD -- tools/shared/elastique/ipp_entries.py` = 0 行)。
- **thunk 追跡**: 197 入口すべて `thunk_hops = 0`。
- **IPPCODE 範囲の境界 (#3457)**: 範囲の末尾の命令は、IPPCODE 932 本体のうち `nop` 528・`int3` 194・`ret` 119・`jmp` 23 で、864 本体 (93%) は関数の終端らしい末尾で切れる。残り 68 本体は命令の途中で切れる (境界が関数の終端でない)。pdata の範囲の末尾は `nop` 2,038 が多い (パディング)。
- **境界の有無で入口は変わらない (#3457)**: IPPCODE に境界を入れず `ret` で止める版 (pdata の修正だけを入れた版。CSV に書かず比較のみ) と比べ、197 入口の `class`・`names`・`dsp_depth`・`dsp_rva`・`origin_exports` は 0 件差。到達集合は 4,987 → 5,079 本体 (+92)。
- **pdata の無い `.text` 関数の境界は採用せず (#3457)**: 試行版 (次の既知の先頭を境界にした版。コミットしていない) では、2,339 本体のうち末尾が `ret`/`jmp` で終わるのは 119 本体のみ。区分は族候補 108・`identified` 34・`exact_dsp_internal_no_export` 14 と動いた。範囲の決め方が未確定のため `ret` 停止のまま残し、子 #3490 ([T-SH-87]) に移す。
- **修正の影響 (`f3310a00` → `bcab4049`)**: 入口・区分・照合の件数は不変 (8 / 26 / 122 / 31 / 10)。名前集合が変わったのは族候補 16 入口のみで、旧名の集合は全て新名に含まれる。入口ごとに増えた名は stub 6 名 (`ippsAutoCorr_NormA_32f`・`ippsCopy_16s`・`ippsCopy_32s`・`ippsCopy_64f`・`ippsCopy_64s`・`ippsFIR64f_32f`) と実装済み 3 名 (`ippsCopy_32f`・`ippsFFTInit_R_32f`・`ippsFFTInit_R_64f`)。このうち stub 名の集合で新たに加わるのは 4 名 (`ippsAutoCorr_NormA_32f`・`ippsCopy_16s`・`ippsCopy_64f`・`ippsCopy_64s`) で、stub 名は 24 → 28。名付けた入口の内訳は stub のみ 28 → 18・混在 6 → 16。

## 6. 関数ポインタ経由の到達 (受入条件 3・静的確認)

| 確認 | 件数 |
|---|---|
| `.text` の `lea reg,[rip+X]` で IPPCODE を指す箇所 | 0 |
| `.text` の即値・変位に IPPCODE 番地 (6 桁超の 16 進) を含む命令 | 0 |
| IPPCODE 内の `lea reg,[rip+X]` で IPPCODE を指す箇所 (#3457 で追加) | 158 箇所・宛先 152 着地点 (入口 0) |
| `.rdata`・`.data`・`.pdata`・`_RDATA`・`IPPDATA` 内の IPPCODE 向き 8 byte 値 | 0 |
| `.text` の間接 call/jmp | 2,714 (call 2,373・jmp 341。`r10` を使う表分岐の形 59 件 (うち `[r10+rax*8]` 33 件)) |
| IPPCODE 内の間接 call/jmp (#3457 で数えた参考値。宛先は未解析) | 186 |

IPPCODE 番地を作る命令は、IPPCODE 内の `lea rip` 158 箇所だけ。`.text`・データ・即値は 0。158 箇所は全て IPPCODE 内から IPPCODE への参照で、宛先のどれも入口ではない (入口 0)。146 箇所は ±0x400 以内で、局所の分岐先・分岐表の宛先と見られる (前方 116・後方 42)。関数内のどの位置か、関数ポインタとして使われるかは未確認 (§7)。
間接 call/jmp の宛先の実行時の値は、実行範囲のみ §8 で確認した (§7・子 #3334)。

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 間接 call/jmp (2,714 箇所) の実行時の宛先が IPP に当たらないことの確認 (受入 3) | 実行範囲 75 サイトのみ (§8)。全サイトは未確認 | 子 #3334 ([T-SH-69]) |
| 追記受入 1〜3 (dispatch 表の飛び先 186 個の同定・2 段目 251 個の IPP 同定・初期化スタブと外向き分岐 33 件) | 未実施。本 PR では扱わない | 子 #2667 ([T-SH-43])。親 #2613 の追記コメント (16:23) の原文を移した |
| 追記受入 4 (thunk 頭 33 本の到達元) | 静的参照 0 件。実行で枠を読む命令は 0 件 (§8) | 子 #3334 ([T-SH-69]) |
| 未同定 65 入口 (dsp 内部関数と一致 24・照合不能 31・自明本体 10) | API 名が付かない。tools/ipp の実装対応を判定できない | 本 PR 本文の未解決表 (追跡のみ。`Closes #2613` で閉じるため本表が正) |
| API 族の候補 98 入口 (24 群。うち 45〜52 名の共有本体 15 入口) | 一意の API 名に決まらない | 本 PR 本文の未解決表 (同上) |
| `.pdata` 基準の入口数 181 と issue 本文の 182 | 1 件の定義差 (呼出元の範囲の端の扱い等。未確定) | 本 PR 本文の未解決表 (同上) |
| stub 名 88 (stub のみ 75 入口・混在 57 入口) | 名付けた入口が tools/ipp で未実装 | 既存 #38 (tools/ipp 親) を起票先とする (本 PR では #38 へコメントしない。PM が判断) |
| `.text` の pdata に入らない関数 (到達集合のうち 1,393 本体) の範囲 | `ret` で止まり、早期 `ret` の後の call を辿らない。この関数に当たる入口の区分・名前が変わり得る (試行で族候補 98 → 108) | 子 #3490 ([T-SH-87])。親 #3457 |
| IPPCODE の範囲の末尾が命令の途中で切れる 68 本体 | 境界が関数の終端でない箇所は範囲が不足・過剰になり得る。入口の結果は境界の有無で変わらない (§5) | 本 PR 本文の未解決表 (追跡のみ) |
| `lea rip` 158 箇所の関数内の位置と、関数ポインタとしての使用 | 局所の分岐先と見られるが未確認。入口は 0 件 | 本 PR 本文の未解決表 (追跡のみ) |

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
| 3. thunk 頭 33 本の枠を読む命令 | **0 件** (190 run)。静的は thunk 本体の外で 0 件 (本体内は lea 53・mov 1。付録 §9.6)。到達元の特定は子 #3387 (T-SH-74) |
| 4. 測定 commit・再現・差分 | 測定 commit `982e50c69` (付録 §9.7)。`git diff 982e50c69 HEAD` の出力 0 行 |
