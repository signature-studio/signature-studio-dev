# tools/shared/elastique 付録 — 間接 call/jmp の被覆拡大と枠の読み手 (T-SH-69 / #3334)

親: `REPORT.md` §9 (要約)。§8 (#2643・測定 commit `2781377b`) の続き。所有者限定 tier 専用 (`docs/DECISIONS.md` D20)。
既知の類型との関係: 該当なし (`docs/DEFECTS.md`)。Windows 実行ではない (unicorn・§8 と同じ)。

## 9.1 結論

| 受入条件 (#3334 の本文) | 結果 |
|---|---|
| 1. export 15 件と thunk 頭 33 本を FL ホストに近い引数で実行し、間接サイト数 (/ 2,714) を書く。引数規約の調べ方と被覆の広げ方を書く | **部分**。合成引数の変種 3 種 (`base`・`rate48k`・`obj`) の和集合で **77 サイト** (§8 の 75 から +2)。FL の実呼出し形は未確定 (§9.2)。残りは子 **#3386** (T-SH-73) |
| 2. 広げた実行で、間接宛先が IPPCODE 入口 (197) に当たるものの件数 | **0 件** (和集合 79 edge)。陰性対照で検出器が 1 件を検出することを確認 (§9.4)。入口以外の IPPCODE への間接宛先は 1 件 (§9.5) |
| 3. thunk 頭 33 本の枠を読む命令 (実行時の到達元) | **0 件** (190 run)。静的な厳密参照も 0 件 (§9.6)。到達元の特定は子 **#3387** (T-SH-74) |
| 4. 測定 commit・再現コマンド・差分 | 測定 commit `982e50c69` (§9.7) |

## 9.2 引数規約の調べ方と、被覆の広げ方

**調べ方 (FL の実呼出し形)**: 素材 `fl-win64` を全展開した (`extracted/` 25,166 ファイル・2.3 GB・展開 8.1 秒)。
- PE 313 件の import 表を pefile で走査: élastique の export 名 (`Auftakt_`・`ElPro`・`ElAllocator`・`Declicker_`・`Denoiser_`・`Metering_`・`SolPitchAn_`・`ElResampleSource`) を import する PE は **0 件**。
- バイナリ文字列の grep (`Auftakt_CreateInstance`・`ElPro_CreateInstance`・`ElProV3_CreateInstance`・`ElAllocator_SetFunctions`・`ElResampleSource_CreateInstance`・`elastique_x64`・`ElastiquePro`): 9 ファイルにヒット。export 名の一致は **0**。内訳: `block24357` (élastique 本体)・`block25162` (`Shared\elastique_x64.dll/4997632/...` の 1 行。サイズは本体と一致し、インストーラ等の記録と推定)・`block25163_DATA` (`elastique_x64` の文字列)・`block18976`・`block22444`・`block23605`・`block23610` (C++ RTTI のクラス名 `.?AVCElastiqueProV3@@` 等)・`block19216`・`block23664` (`ElastiquePro` を含む文字列)。
- 結論: 呼出元は静的に見つからなかった (動的取得か、別の名前の経路と推定。未確定)。同定は子 #3386。

**被覆の広げ方** (`tools/shared/elastique/dyn_trace.py`・測定 commit `982e50c69`):
- `base`: 既存の 2 変種 (rcx・rdx・r8・r9 = `0`・`0`・`0`・`0` / `scratch`)。96 run (DllMain・SetFunctions・export 14 × 2・thunk 33 × 2)。§8 と同じ。
- `rate48k`: export 14 件と thunk 33 本を `(obj, obj+0x1000, 48000, 1)` で実行 (サンプルレート・モノラル)。47 run。
- `obj`: `*_CreateInstance` の `scratch` 変種が POOL 内のオブジェクトを返したもの (実測 1 件: `Auftakt_CreateInstance2:scratch`・rax `0x500e0730`) を rcx に渡し、他の export と thunk 頭を `(o, obj, 44100, 2)` で実行。47 run (上限 3 件まで)。
- 枠読みの検出: 旧版は読み取り先頭が枠の先頭と一致した時だけ数えた。新版は読み取り範囲が枠 (8 byte) と重なる時に数える。
- 出力: 間接 edge の union を `data/runtime_indirect.csv` へ (76 → 79 edge。基底の 76 edge は全て残存)。

## 9.3 実測

| 変種 | run 数 | returned | uc_error | count_limit | 間接サイト |
|---|---|---|---|---|---|
| base | 96 | 70 | 25 | 1 | **75** (§8 と一致) |
| rate48k | 47 | 24 | 19 | 4 | 60 |
| obj | 47 | 24 | 11 | 12 | 62 |
| 和集合 | 190 | – | – | – | **77 / 2,714 (2.84%)** |

- 和集合の間接 edge 79 の分類: `text` 59・stub 18 (KERNEL32 17・host.malloc 1)・`other` 1・`ipp_other` 1・**`ipp_entry` 0**。
- 基底 (75) に無い間接サイトは 2 件: `0x1802da375` (`call [rip+0x10ddf5]`→ HeapAlloc stub・変種 `obj`)、`0x1803c480a` (`call rax`→ `0x1803c4710`・変種 `rate48k`・§9.5)。
- uc_error の内訳: base は §8.3 と同じ (`Unhandled CPU exception` 8・`Invalid memory` 17)。`rate48k`・`obj` の uc_error は未切り分け (子 #3386)。
- 所要 (実測 real): 測定 commit の HEAD で 13.5 秒 (user 13.5 秒・load average 0.36 → 0.21)。変種別の時間: base 4.66 秒・rate48k 3.09 秒・obj 5.58 秒。

## 9.4 陰性対照

- 入口集合 (197) に IPPCODE 非入口の既知の間接宛先 `0x1803c4710` を 1 行足した CSV を `DYN_ENTRIES` で渡して実行: `indirect_hits_on_ipp_entries` = **1** (本番は 0)。検出器は入口への間接宛先を数えられる。
- 注意: この実行は `data/runtime_indirect.csv` も上書きする。本番の CSV は通常の実行で戻すこと (§9.7)。

## 9.5 IPPCODE 非入口への間接宛先 (1 件)

- 分岐元 `0x1803c480a` (`call rax`・IPPCODE 内)、宛先 `0x1803c4710` (入口 197 に無い・分類 `ipp_other`)、実行: `thunk:0x180001c20:rate48k`、回数 8。
- 受入 2 の対象は入口 (197) だけなので、0 件の結論は変わらない。宛先の IPP 同定は未実施。起票先は既存 #2667 (T-SH-43・dispatch 表の飛び先の IPP 同定)。

## 9.6 枠 (thunk 頭 33 本) の読み手

- 動的: 190 run の全てで、枠の 8 byte と重なる読み取り命令は **0 件** (`slot_readers.csv` は見出しのみ・`thunk_slot_readers_distinct_rip` = 0)。
- 静的: `.text` の RIP 相対の参照で、枠の範囲 `[0x1804afc60, 0x1804b0900)` に入るものを数えた。thunk 本体 (`0x180001800`〜`0x1801bb000`) の外では **0 件** (本体の内側は表・索引の参照のみ)。
- 限界: RIP 相対の参照だけを数えた。計算アドレス (基底 + 添字) による読みは見えない。読み手は、ある export の初期化経路で計算された基底から読むと推定 (未確定)。同定は子 #3387。

## 9.7 測定・再現・差分

- 測定 commit: **`982e50c69`** (`dyn_trace.py` と `data/runtime_indirect.csv` を変えた最後の commit)。検証の起点は `origin/main` (`c3ee6daa7`)。
- 差分 (測定後のコード範囲): `git diff 982e50c69 HEAD -- tools/shared/elastique/dyn_trace.py tools/shared/elastique/data/runtime_indirect.csv` → 出力 0 行。
- 再現 (素材は §8.1 と同じ `block24357_PE.bin`):

```sh
mkdir -p tools/shared/work/win && cp "$RUNNER_TEMP/fl-win64/extracted/block24357_PE.bin" tools/shared/work/win/elastique_x64.dll
uv venv tools/shared/work/venv && uv pip install --python tools/shared/work/venv/bin/python unicorn pefile capstone
tools/shared/work/venv/bin/python tools/shared/elastique/dyn_trace.py   # 実測 (real): 13.5 秒。出力は tools/shared/work/elastique/dyn/ (gitignore)
```

- 同一 HEAD での再実行: 測定 commit の HEAD で 3 回実行。`data/runtime_indirect.csv` は 3 回とも `cmp` 一致。
- 陰性対照の再現: 入口 CSV に `0x1803c4710` の行を足したファイルを `DYN_ENTRIES` で渡して実行し、`summary.json` の `indirect_hits_on_ipp_entries` が 1 になることを見る。その後、上のコマンドで CSV を戻す。

## 9.8 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| FL の実呼出し形 (引数規約) の同定と、その引数での被覆 (受入 1 の残り) | 被覆 77 / 2,714 は合成引数の範囲に限られる | 子 #3386 (T-SH-73) |
| 枠 33 本の読み手 (受入 3) | 実行時の到達元が未確定。静的な厳密参照は 0 件 | 子 #3387 (T-SH-74) |
| 入口以外の IPPCODE 宛先 `0x1803c4710` の IP 同定 (§9.5) | 1 件。IPP 関数への間接呼出しの候補 | 既存 #2667 (T-SH-43) |
| `rate48k`・`obj` の uc_error 30 件 (19 + 11) の原因 | 実行範囲を狭める可能性 | 子 #3386 に含める |
