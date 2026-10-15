# tools/shared/elastique 付録 — 間接 call/jmp の被覆拡大と枠の読み手 (T-SH-69 / #3334)

親: `REPORT.md` §9 (要約)。§8 (#2643・測定 commit `2781377b`) の続き。所有者限定 tier 専用 (`docs/DECISIONS.md` D20)。
既知の類型との関係: 該当なし (`docs/DEFECTS.md`)。Windows 実行ではない (unicorn・§8 と同じ)。

## 9.1 結論

| 受入条件 (#3334 の本文) | 結果 |
|---|---|
| 1. export 15 件と thunk 頭 33 本を FL ホストに近い引数で実行し、間接サイト数 (/ 2,714) を書く。引数規約の調べ方と被覆の広げ方を書く | **部分**。合成引数の変種 3 種 (`base`・`rate48k`・`obj`) の和集合で **77 サイト** (§8 の 75 から +2)。FL の実呼出し形は未確定 (§9.2)。残りは子 **#3386** (T-SH-73) |
| 2. 広げた実行で、間接宛先が IPPCODE 入口 (197) に当たるものの件数 | **0 件** (和集合 79 edge)。陰性対照で検出器が 1 件を検出することを確認 (§9.4)。入口以外の IPPCODE への間接宛先は 1 件 (§9.5) |
| 3. thunk 頭 33 本の枠を読む命令 (実行時の到達元) | **0 件** (190 run)。静的は thunk 本体の外で 0 件 (本体内は lea 53・mov 1。§9.6)。到達元の特定は子 **#3387** (T-SH-74) |
| 4. 測定 commit・再現コマンド・差分 | 測定 commit `982e50c69` (§9.7) |

## 9.2 引数規約の調べ方と、被覆の広げ方

**調べ方 (FL の実呼出し形)**: 素材 `fl-win64` を全展開した (`extracted/` 25,166 ファイル・2.3 GB・展開 8.1 秒)。集計は `tools/shared/elastique/fl_callers_scan.py` (実測 5.1 秒・load average 0.2〜0.3)。手順:

```sh
mkdir -p "$RUNNER_TEMP/fl-win64" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64"
FL_WIN64_DIR="$RUNNER_TEMP/fl-win64" tools/shared/work/venv/bin/python tools/shared/elastique/fl_callers_scan.py
```

- PE の import 走査: `extracted/` の全ファイルのうち先頭が MZ で pefile が読めたものは **313 件**。import の DLL 名が `elastique_x64.dll`、または関数名が élastique の export 名の接頭 (`Auftakt_`・`ElPro`・`ElAllocator`・`Declicker_`・`Denoiser_`・`Metering_`・`SolPitchAn_`・`ElResampleSource`) で始まるものは **0 件**。
- 文字列の grep: 全ファイルのバイト列を `Auftakt_CreateInstance`・`ElPro_CreateInstance`・`ElProV3_CreateInstance`・`ElAllocator_SetFunctions`・`ElResampleSource_CreateInstance`・`elastique_x64`・`ElastiquePro` で検索。和集合は **9 ファイル**。export 名 5 種のヒットは `block24357` (élastique 本体の export 表) だけで、他の PE・ファイルには **0**。内訳: `block24357` (élastique 本体)・`block25162` (`Shared\elastique_x64.dll/4997632/...` の 1 行。サイズは本体と一致し、インストーラ等の記録と推定)・`block25163_DATA` (`elastique_x64` の文字列)・`block18976`・`block22444`・`block23605`・`block23610` (C++ RTTI のクラス名 `.?AVCElastiqueProV3@@` 等)・`block19216`・`block23664` (`ElastiquePro` を含む文字列)。
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
- 所要 (実測 real): 初回 (測定時) 13.5 秒 (user 13.5 秒・load average 0.36 → 0.21)。変種別の時間: base 4.66 秒・rate48k 3.09 秒・obj 5.58 秒。同一コードの再実行 3 回 (§9.7) は real 16.24〜16.51 秒 (n=3)。

## 9.4 陰性対照

- 入口集合 (197) に IPPCODE 非入口の既知の間接宛先 `0x1803c4710` を 1 行足した CSV を `DYN_ENTRIES` で渡して実行: `indirect_hits_on_ipp_entries` = **1** (本番は 0)。検出器は入口への間接宛先を数えられる。
- 注意: この実行は `data/runtime_indirect.csv` も上書きする。本番の CSV は通常の実行で戻すこと (§9.7)。

## 9.5 IPPCODE 非入口への間接宛先 (1 件)

- 分岐元 `0x1803c480a` (`call rax`・IPPCODE 内)、宛先 `0x1803c4710` (入口 197 に無い・分類 `ipp_other`)、実行: `thunk:0x180001c20:rate48k`、回数 8。
- 受入 2 の対象は入口 (197) だけなので、0 件の結論は変わらない。宛先の IPP 同定は未実施。起票先は子 **#3420** (T-SH-80)。#2667 (T-SH-43・dispatch 表の飛び先の同定) は PR #3178 で閉じており、本件の宛先はその範囲に入っていない (`REPORT_152.md` に記述が無い)。

## 9.6 枠 (thunk 頭 33 本) の読み手

- 動的: 190 run の全てで、枠の 8 byte と重なる読み取り命令は **0 件** (`slot_readers.csv` は見出しのみ・`thunk_slot_readers_distinct_rip` = 0)。
- 静的: `tools/shared/elastique/static_slot_refs.py` (実測 6.2 秒・1 コマンド: `tools/shared/work/venv/bin/python tools/shared/elastique/static_slot_refs.py`) で、`.text` を線形走査し、rip 相対のメモリ参照の参照先 (次命令の番地 + 変位) が枠の範囲に入るものを数えた。
  - 定義 (script が導出する): thunk 頭 = `.data`・`.rdata` の 8 byte 値のうち、`.text` 番地で先頭命令が `call 0x1803e71b0` のもの (**33 本**・dyn_trace.py と同じ条件)。枠 = その 8 byte の番地 (**33 個**)。thunk 本体 = `[0x180001800, 0x1801bb000)` (最小の頭〜最大の頭を含むページの末尾)。枠の範囲 = `[0x1804afc60, 0x1804b0900)` (最小の枠〜最大の枠 + 0x40)。
  - 結果: 枠の範囲を指す rip 相対の参照は、thunk 本体の**外で 0 件**、本体の内で **54 件** (lea 53・mov 1)。
  - 本体内の mov 1 件: `0x1801bad40` の `mov rax, qword ptr [rip + 0x2f5bb1]` が `0x1804b08f8` を読む。この番地は枠 (33 個) のどれでもない (最大の枠 `0x1804b08c0` は 8 byte で `0x1804b08c8` 未満)。値は `0x1801bb1c0` (関数ポインタ)。したがって枠の読み手ではない。
  - 範囲の末尾を最大の枠 + 8 にすると、この mov 1 件が範囲から外れる (件数の定義に依存する点)。
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

- 再実行 (fix round 1): 上の `dyn_trace.py` を、`dyn_trace.py`・`data/runtime_indirect.csv` が HEAD と同一 (`git status` で差分 0 を確認) の状態で **3 回** 実行した。3 回とも終了コード 0・`data/runtime_indirect.csv` は commit 版と `cmp` 一致。所要 (実測 real) **16.24〜16.51 秒** (n=3・load average (1 分) 0.22 → 0.72)。summary の間接サイト 77 (base 75・rate48k 60・obj 62)・IPPCODE 入口ヒット 0・枠読み 0・uc_error 55 行 (§9.3 と一致)。
- 回数の記録: 前回の記録は、PR 本文と #3334 の完了コメントが「2 回」、本付録が「3 回」で一致していなかった。前回の実行ログは残っていないため、fix round 1 で 3 回再実行して記録を揃えた。
- 陰性対照の再現: 入口 CSV に `0x1803c4710` の行を足したファイルを `DYN_ENTRIES` で渡して実行し、`summary.json` の `indirect_hits_on_ipp_entries` が 1 になることを見る。その後、上のコマンドで CSV を戻す。

## 9.8 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| FL の実呼出し形 (引数規約) の同定と、その引数での被覆 (受入 1 の残り) | 被覆 77 / 2,714 は合成引数の範囲に限られる | 子 #3386 (T-SH-73) |
| 枠 33 本の読み手 (受入 3) | 実行時の到達元が未確定。静的は thunk 本体の外で 0 件 | 子 #3387 (T-SH-74) |
| 入口以外の IPPCODE 宛先 `0x1803c4710` の IP 同定 (§9.5) | 1 件。IPP 関数への間接呼出しの候補 | 子 #3420 (T-SH-80) |
| `rate48k`・`obj` の uc_error 30 件 (19 + 11) の原因 | 実行範囲を狭める可能性 | 子 #3386 に含める (受入に追記済み) |
