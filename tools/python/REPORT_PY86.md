# PY-86 (#2701): `call [reg+0x1a0]` の受け手を分類 — 受入 2b は部分・受入 4 は未着手

親: #2501 (PY-71)・#2159 (PY-67)。前段: `REPORT_PY71.md` §4、`REPORT_PY67_2159.md` §2。

## 結論

| # | 受入条件 (#2701) | 結果 |
|---|---|---|
| 2b | `call [reg+0x1a0]` の受け手の型と、`0xffe370` を受けるものの件数 | **部分**。実 VMT 呼出し 34 件を分類: Self 型で TPublicChannel が入らない 7 件 (うち 2 件は前提付き・§1)・TPublicChannel の Self 1 件 (候補)・フィールドの受け手 2 件・直接呼出し元等で決まる 24 件。件数は確定しない (未確定 27 件を子 issue へ) |
| 3 | `0xec60ae` の対象型 | 達成済み (PR #2731) |
| 4 | `0x8ed012` の `[rbp+0x70]` の出所と chan 判定 | **未着手**。子 issue へ (`REPORT_PY67_2159.md` §2 の呼出し元 5 件が起点) |

- 誤検出 3 件: `call [rbp+0x1a0]` (rbp 基準のフレーム上の関数ポインタ) は VMT 呼出しではない。`py86_slot52.py` で除外 (`rbp`/`rsp` 基準を除く)。
- 正の対照: `0xffe370` は `TPublicChannel@0xfe2cf8[52]`、`0xfed770` は `TChannel@0xfe2978[52]` と `TPreviewChannel@0xfe2fc8[52]` として引ける。

## 1. 方法

- `analysis/py86_slot52.py <PE.bin> 0x1a0` で、`.text` の線形走査 (py71_slotcallers.py と同じ近似) により呼出しサイトを集める。
- 各サイトについて (a) 所属関数 fn の先頭から呼出しまでの命令 (受け手の出所)、(b) fn の値を VMT のスロットに持つクラス (VMT の自己ポインタ `VMT-0xc8` で判定)、(c) fn の直接呼出し元とその所属 を出す。
- 分類の前提 (A 群の排除): fn を指す参照は、解析 (`py86_slot52.py`) が数えたもの (直接の `call rel32`・8 バイト境界の VMT スロット) と、数えなかったもの (`jmp`・Jcc・短距離ジャンプ・32bit 即値・絶対アドレス・RIP 相対の `lea`・非整列のポインタ) に分かれる。後者は `analysis/py86_refs.py` で群 A・B と群 D の 3 関数 (計 11 関数) を全数確認した (§4)。
  - 群 A の 5 件 (0x61c0b0・0x80dc30・0x826d80・0x82bdd0・0x860cc0): 命令参照 0 件・8 バイト境界の参照は全件 VMT 所属。fn は VMT 経由に限られ、受け手 (Self) の動的型は fn を VMT に持つクラスに限られる。TPublicChannel の VMT に fn が無いので、TPublicChannel は受け手にならない。
  - 群 A の残り 2 件 (0xc16b60 の呼出しサイト 0xc16ba4・0xc1c0d0 の呼出しサイト 0xc1c453): 非整列の参照が 1 件ずつあり、その直後に ShortString の名前 (`ReceiveFrom`・`ReceiveMsg`) が続く RTTI 様の表 (VA 0xc155ee・0xc1855a) の中にある。表の所属クラスは未確認。この 2 件の「TPublicChannel が入らない」は前提付きとする。
- Self の確認: 受け手が Self (rcx の保存先) かは各 fn の先頭命令 (`mov [rbp+X], rcx`・`mov rbx, rcx` など) で確認した (表の「受け手」欄)。

## 2. 分類 (実 VMT 呼出し 34 件)

| 呼出しサイト | 所属 fn | 受け手 (呼出し直前の obj) | fn の所属 VMT (TPublicChannel?) | 直接呼出し元 | 群 |
|---|---|---|---|---|---|
| 0x61c106 | 0x61c0b0 | Self (`[rbp+0x50]`=rcx) | TCustomControl〜TVirtualTreeHintWindow [69] (無) | 0 | A |
| 0x80dc3e | 0x80dc30 | Self (rcx) | TLayeredFormEx・TLayeredForm・TFLHintBarForm・TTutorialHighlightForm [69] (無) | 0 | A |
| 0x826dab | 0x826d80 | Self (rbx=rcx) | TTrackSlider〜TUnlockModule [69] (無・約 60 件) | 0 | A |
| 0x82be2a | 0x82bdd0 | Self (`[rsp+0x48]`=rcx) | TImage [90] (無) | 0 | A |
| 0x860eee | 0x860cc0 | Self (`[rbp+0x80]`=rcx) | TBaseGlassForm〜TForm 系 [69] (無・約 100 件。一覧は一部のみ確認) | 0 | A |
| 0xc16ba4 | 0xc16b60 | Self (rbx=rcx) | TIdStackBSDBase・TIdStackWindows [29] (無) | 0 | A |
| 0xc1c453 | 0xc1c0d0 | Self (`[rbp+0x40]`=rcx) | TIdStackWindows [31] (無) | 0 | A |
| 0xff7930 | 0xff7810 | Self (rbx=rcx) | **TPublicChannel [50]** | 0 | B (候補) |
| 0xb35298 | 0xb35250 | `[rbx+0x18]` (Self のフィールド) | TDBXStreamValue [48] (無) | 0 | C |
| 0xb671a2 | 0xb67190 | `[rcx+0x7a0]` (Self のフィールド) | TGenericPlugin [81] (無) | 0 | C |
| 0x61b134 | 0x61b0d0 | `[rbp+0x50]` (引数の保存先・未確認) | - | 0 | D |
| 0x6cb1db | 0x6cb1c0 | `[rbx+0x58]` (Self のフィールド) | - | 5 | D |
| 0x6f131a・0x6f132f・0x6f1344 | 0x6f12b0 | `[rbx+0x6b8]`・`[rbx+0x6cc]`・`[rbx+0x6d4]` | - | 2 | D |
| 0x6f1352 | 0x6f12b0 | rbx (Self) | - | 2 | D |
| 0x7cf84f | 0x7cf7f0 | rbx (Self) | - | 1 (0x7cf730 TVectorWheel [81]) | D |
| 0x80dc7a | 0x80dc50 | rbx (Self) | - | 1 (0x80ce50) | D |
| 0x80dd2c | 0x80dcc0 | `[rbp+0x48]` | - | 2 | D |
| 0x82052f | 0x820440 | `[rbp+0x28]` | - | 12 | D |
| 0x820858・0x820887・0x8209a3 | 0x8207b0 | `[rbp+0x30]` | - | 1 (0x8261a0) | D |
| 0x8233ef・0x82347a・0x8234b5・0x8234dd・0x8235b9 | 0x823090 | `[rbp+0x48]` (Self: rcx 保存) | - | 0 | D |
| 0x86ca85 | 0x86ca60 | rbx (Self) | - | 1 (0x5de830 TCustomAction 系 [23]) | D |
| 0xb8b4e3 | 0xb8b450 | `[[[rbp+0x70]+0xa0]+0x64]` | - | 1 (0xb8b590) | D |
| 0xbe6647 | 0xbe6040 | `[[rsi+0x18]+0x494]` | - | 0 | D |
| 0xff5b05 | 0xff5aa0 | `[rbp+0x50]` (Self: rcx 保存) | - | 1 (0x1003be0) | D |
| 0x1003773 | 0x1003730 | `0xfe8bb0` の戻り値 | - | 5 (0xe7a470 TEventEditForm [106] ほか) | D |
| 0x1003c63 | 0x1003c20 | `[rbp+0x60]` | - | 3 (0xc4ac00 TAddRenderedChannelData [0] ほか) | D |

- 群の意味: A = Self 型で TPublicChannel が入らない (7 件・うち 2 件は前提付き)。B = TPublicChannel の Self の呼出し (1 件・0xffe370 へ分岐しうる)。C = フィールドを受け手にする仮想メソッド (2 件・フィールドの型が未確定)。D = 直接呼出し元等で決まる (24 件・未確定)。
- D のうち 7 件は VMT にも直接呼出しにも現れず、到達経路は未確認。0x61b0d0 (1 件) と 0x823090 (5 件) は、命令参照 0 件で、非整列の RTTI 様表に参照が 1 件ずつ (VA 0x60007a・0x81e8b1)。0xbe6040 (1 件) は `lea rax,[rip+0x21bc]` (0xbe3e7d) で関数ポインタとして取られる (その呼出し元は未追跡)。残り 17 件は直接呼出し元 (1〜12 件) を辿って決める。
- 件数 (受入 2b): 静的な上限は B 1 + C 2 + D 24 = 27 件。A の 7 件は TPublicChannel を受けない (うち 2 件は前提付き・§1)。確定件数は出せない (D の呼出し元を辿る必要がある)。
- 観察: 0xff7810 (B) の呼出しは `edx = [rbx+0x794]` を引数に取る。`+0x794` は REPORT_PY67 系で追っているフィールドと同じ。

## 3. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 群 B・C・D の 27 件の受け手の型 (呼出し元を辿り、TPublicChannel を受けるか)。群 B は 0xff7810 が TPublicChannel のインスタンスで実行されるかを含む | 受入 2b の件数 | #3337 |
| 群 A の 2 件 (0xc16b60・0xc1c0d0) の非整列の RTTI 様表 (VA 0xc155ee・0xc1855a) の所属クラス | 群 A の判定 (TPublicChannel が入らない) の前提 | #3337 |
| `0x8ed012` の `[rbp+0x70]` の出所と chan 判定 | 受入 4 | #3338 |

## 4. 測定

- 素材: `fl-win64` の `extracted/block00031_PE.bin` (22,227,016 バイト)。`tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64" --wildcards '*block00031_PE.bin'` (2.8 秒)。
- 測定 commit (`py86_slot52.py`): `dc84c2ff` (最後の変更。フレーム基準の除外を入れた後の版)。
- 差分 0 の証跡 (測定 commit から本節を書いた HEAD まで):

  ```
  $ git diff dc84c2ff HEAD -- tools/python/analysis/py86_slot52.py tools/python/src
  (出力 0 行)
  ```

- 測定 commit (`py86_refs.py`): `109fcb71` (追加した版。以後の変更なし)。

  ```
  $ git diff 109fcb71 HEAD -- tools/python/analysis/py86_refs.py
  (出力 0 行)
  ```

- 実測 (逐次・n=2・load 0.40 / 1 分平均。`P=$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin`):
  - `py86_slot52.py "$P" 0x1a0 6`: 49.2 秒 (最終版)。前版 (フレーム除外なし) 48.7 秒。出力は 37 件 → 34 件 (フレーム基準 3 件を除いた差)。

- 再現 (`tools/python` で実行):

  ```
  P=$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin
  python3 analysis/py86_slot52.py "$P" 0x1a0 6
  ```

- 追加確認 (`analysis/py86_refs.py`・§1 の (iii))。実行 3.3 秒 (real・n=1)。load は未計測。

  ```
  P=$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin
  python3 analysis/py86_refs.py "$P" 0x61c0b0,0x80dc30,0x826d80,0x82bdd0,0x860cc0,0xc16b60,0xc1c0d0,0xff7810,0x61b0d0,0x823090,0xbe6040,0x6cb1c0
  ```

  | 関数 | 群 | 候補 (abs32+rel32+rel8) | 命令参照 | 偶然の一致 | 8 バイト境界 VMT 所属 | 非整列 |
  |---|---|---|---|---|---|---|
  | 0x61c0b0 | A | 7 (7+0+0) | 0 | 7 | 7 | - |
  | 0x80dc30 | A | 7 (4+3+0) | 0 | 7 | 4 | - |
  | 0x826d80 | A | 60 (58+2+0) | 0 | 60 | 58 | - |
  | 0x82bdd0 | A | 3 (1+2+0) | 0 | 3 | 1 | - |
  | 0x860cc0 | A | 111 (110+1+0) | 0 | 111 | 110 | - |
  | 0xc16b60 | A | 3 (3+0+0) | 0 | 3 | 2 | 0xc155ee |
  | 0xc1c0d0 | A | 3 (2+1+0) | 0 | 3 | 1 | 0xc1855a |
  | 0xff7810 | B | 1 (1+0+0) | 0 | 1 | 1 | - |
  | 0x61b0d0 | D | 1 (1+0+0) | 0 | 1 | 0 | 0x60007a |
  | 0x823090 | D | 1 (1+0+0) | 0 | 1 | 0 | 0x81e8b1 |
  | 0xbe6040 | D | 3 (0+3+0) | 2 (うち 1 は 0xbe3e7e の誤デコード・§4) | 2 | 0 | - |
  | 0x6cb1c0 (対照) | - | 5 (0+5+0) | 5 | 0 | 0 | - |

  - 「偶然の一致」は、候補の窓を含む命令を前後 12 バイトから逆引きしても fn を指すオペランドが無いもの (`.text` 内のデータ上の偶然の一致)。A・B の 8 関数は命令参照 0 件で、`jmp`・Jcc・短距離ジャンプ・即値・RIP 相対の参照は無い。
  - 0xbe6040 の命令参照は 2 行出る。実在する参照は `lea rax,[rip+0x21bc]` (0xbe3e7d・7 バイト・次命令 0xbe3e84 + 0x21bc = 0xbe6040) の 1 件。もう 1 行の 0xbe3e7e `lea eax,[rip+0x21bc]` は、0xbe3e7d の命令の途中を読んだ重なりの誤デコードで、スクリプトは重複を除かないため出る。
  - 非整列の 8 バイトポインタ (0xc155ee・0xc1855a・0x60007a・0x81e8b1) は VMT のスロットではない。0xc155ee と 0xc1855a の直後は ShortString (`ReceiveFrom`・`ReceiveMsg`)、0x60007a の直後は `TGraphicControl`。0x81e8b1 の近傍は 8 バイト間隔の関数ポインタ列と `TQuickGraphicControl` の名前。表の所属クラスは未確認 (子 #3337 で確認する)。

## 5. 群 D の受け手の追跡 (#5145・部分)

- 対象: 群 D の 15 関数 (24 サイト)。`analysis/py86_group_d.py <PE.bin> <fn,...> 3 6` で、VMT 外の関数を直接呼出し元へ最大 3 段・各 6 件まで辿る。VMT 所属の関数で止める。各ノードに TPublicChannel の所属を出す。
- 測定 commit (`py86_group_d.py`): `4a3d1965a` (追加した版。以後の変更なし)。

  ```
  $ git diff 4a3d1965a HEAD -- tools/python/analysis/py86_group_d.py
  (出力 0 行)
  ```

- 実測 (逐次・n=1・load 0.09 / 1 分平均): 33.6 秒。出力 191 ノード・TPublicChannel を含むノード 0 件。
- 判定できた 2 件 (24 件中):
  - 0x7cf84f (fn 0x7cf7f0): 直接呼出し元は 0x7cf730 のみ。0x7cf730 は TVectorWheel[81] の VMT の関数で、0x7cf730 の rbx=rcx (Self) がそのまま 0x7cf743 で渡される。受け手は TVectorWheel 系。TPublicChannel は含まない。
  - 0x86ca85 (fn 0x86ca60): 直接呼出し元は 0x5de830 のみ。0x5de830 は TCustomAction 系 (VMT[23]・10 クラス) の関数で、Self (rbx=rcx は 0x5de835) は 0x5de861 で rdx に入り、0x5de864 の 0x86ca60 に渡る (rcx は 0x5de857 で全域変数から読み直される)。受け手は TCustomAction 系。TPublicChannel は含まない。
- 未判定 22 件。理由: 直接呼出し元を辿ると、VMT 所属に当たる前に、呼出し元 0 件の関数 (「0 件」の受け手の出所が未確定) で止まる。または深さ 3 の上限で切れる。例: 0x6cb1c0 は 0x6ce5c0 → 0x6cb0b0 (呼出し元 91 件・全て VMT 外) まで。0x820440 は 16 件 (VMT 外)。0x8207b0 は 0x8261a0 → 0x806b70 (呼出し元 0) まで。0x823090・0x61b0d0・0xbe6040 は直接呼出し元 0 件。
- VMT 所属に当たった呼出し元 (0x73d5c0・0x7cf9b0・0x7e5290・0x7f6f20 の先の 0x6f16d0・0x7e2640・0x7f33a0 ほか) は、いずれも TPublicChannel を含まなかった (`py86_group_d.py` の TPublicChannel 欄)。これは「TPublicChannel を含まない」の確認のみで、未判定 22 件の判定ではない。
- 未解決: 未判定 22 件 (0x6cb1c0・0x6f12b0・0x80dc50・0x80dcc0・0x820440・0x8207b0・0x823090・0xb8b450・0xbe6040・0xff5aa0・0x1003730・0x1003c20・0x61b0d0 等)。深さ 3 の上限を超える先と、呼出し元 0 件の関数の到達経路。起票先: #5145 (本 issue の続き。以後の run で本 issue のコメントに追記する)。
### 5.1 global `[rip+0xae51a1]` の出所 (#5493・PY-5352)

- 前提の訂正: #5493 本文の経路「0x80d9c0 → 0x80dcc0」は誤り。`0x80d9c0` は `mov dl,1; call 0x85c440; ret` の thunk で、`0x80dcc0` を呼ばない。`0x80dcc0` の直接呼出しは 0x80d912 と 0x80d9ec の 2 件 (0x80d9ec は 0x80d9d0 の中)。
- 参照の経路 (`analysis/py5493_global.py`・既定値):
  - global `0x16b6d80` を RIP 相対で指す命令は **9 件** (全て読出し・`cmp` または `mov r*, [rip+…]`)。全て fn `0xbd1b30` 内: `0xbd1b45`・`0xbd1b84`・`0xbd1b9d`・`0xbd1bae`・`0xbd1bb5`・`0xbd1bc8`・`0xbd1bd8`・`0xbd1be4`・`0xbd1beb`。
- `0xbd1bd8` (fn `0xbd1b30`): `mov rcx,[rip+0xae51a1]`。解決先は VA `0x16b6d80` (.bss)。`0x80d9c0` へ渡るのは、この `0xbd1bd8` の値 (`0xbd1bdf` の `call 0x80d9c0`)。受け手は `*0x16b6d80` (rcx)。
  - `0x71f86a` (fn `0x71f840`) も `call 0x80d9c0` (rcx=rbx)。
- `0x16b6d80` への RIP 相対の書込みは `.text` 全域で 0 件。`0x16b6d80` の 4 バイト一致は、ポインタ表と同じ `.data` (file offset `0x11de718`・VA `0x15dfd18`) の 1 件のみ。
- `0x16b6d80` の VA を値として持つのは `.data` のポインタ表 VA `0x15dfd18` の 1 箇所のみ。表を RIP 相対で読む命令は **46 件** (範囲 `0x10022ac`〜`0x11fd6a5`・全て `mov` の読出し・書込み 0 件)。`0x11be43d` は `rdx=[0x15dfd18]` (= &global) を `0x11c8950` に渡し、`0x11c8950` は `0x86a470` を呼ぶ。この経路が書込み先の登録かは未確認。
- 所属: `0x80d9c0`・`0x80dcc0`・`0x80d9d0`・`0xbd1b30`・`0x71f840` はいずれも VMT の所属を持たない (`owners 0`)。
- 結論: global の型は**未確定**。書込み元 (表経由の登録 `0x86a470` の先、または global を引数として書く関数) が特定できていない。
- 測定: `analysis/py5493_global.py <PE.bin>`・1 回の線形走査・n=1・real 42.9 秒 (再測定・実行時の load 0.81・uptime の 1 分平均)。出力: global 9 件・表 46 件・直接 call 4 件。素材 `block00031_PE.bin` (`fl-win64`)。前回測定 (42.3 秒) の件数 (1 件・36 件) は誤り。
- 測定 commit (`py5493_global.py`): `e08011bc2` (追加した版。以後の変更なし)。

### 5.2 global `0x16b6d80` の書込み元 (#5493 の続き)

- 書込み経路 (確定): 表 `0x15dfd18` を読む `0x11be43d` で `rdx = &global (0x16b6d80)` を作り、`0x11c8950` → `0x86a470` に渡す。`0x86a470` は `[r8]` (第 3 引数の指す先) に結果を `mov qword ptr [rax], rcx` で書く (`0x86a4e1`)。よって `*(&global)` が書かれる。
- 直接 call の件数 (`analysis/py5493_callers.py`・合計 25 件): `0x11c8950` への直接 call は **23 件**、`0x86a470` への直接 call は **2 件** (`0x10dc775`・`0x11c896d`)。`0x11c8950` の 23 件のうち `0x11be444` は `rdx = &global` を確認済み。残り **22 件** の `rdx` の値は未検証で、`&global` かどうかは確認していない。
- 未確定: 「global の値 (型)」は `0x86a470` の結果 (`[rdx+...]` 経由の `call qword ptr [rax-0x30]` の戻り値) で決まる。その戻り値の生成元 (`[rax-0x30]` のスロット先) は未追跡。
- 測定: `analysis/py5493_writer.py` (表参照 46 件の前後と `0x86a470`・`0x11c8950` の逆アセンブル・real 2 分 05 秒・n=1・単一スレッド)、`analysis/py5493_callers.py` (`0x86a470`・`0x11c8950` の呼出し元 25 件・1 回の走査)。素材 `block00031_PE.bin` (`fl-win64`)。
- 注: `py5493_writer.py` は全命令を保持すると OOM で落ちた (exit 137)。逐次走査に書き直した版を記録する。

### 5.3 global `0x16b6d80` の値の生成元 (#5493・追跡 3 回目)

- 呼出し経路 (確定): `0x11be436` が `rcx = [0xbd0ba0]` (global G1)、`0x11be43d` が `rdx = [0x15dfd18]` (= `&0x16b6d80`)。`0x11be444` で `0x11c8950` → `0x86a470(ctx, G1の値, &0x16b6d80)`。
- `0x86a470` は `rax = obj; call [rax-0x30]` (`rcx = obj`) の戻り値を `*(&0x16b6d80)` に書く (`0x86a4cf`〜`0x86a4e1`)。よって global の値 = **G1 の値 (obj) の動的型の VMT スロット `-0x30` の戻り値**。
- G1 `0xbd0ba0`: RIP 相対の参照は `.text` 全域で 1 件 (`0x11be436`・読出しのみ)。`.data` に VA `0xbd0ba0` を値として持つ箇所は 0 件。書込みは RIP 相対では見つからない (間接書込みの可能性)。
- 結論: 型は**引き続き未確定**。G1 (`0xbd0ba0`) に入る object の生成元が次の未確定点。
- 測定: `analysis/py5493_rcx.py <PE.bin>` (新規・測定 commit `2b293f938`・real 1 分 20.4 秒・exit 0・n=1・load 0.68 → 0.92 (測定前後の `/proc/loadavg`)。出力: G1 `0xbd0ba0` の参照 1 件)。素材 `block00031_PE.bin` (`fl-win64`)。前回測定 (commit `5593cbad3`・real 1 分 19 秒) は docstring の手順 3 を削る前のもの。`py5493_writer.py --dis 86a470`・`--dis 11c8950` (`--nins 60/45`) の逆アセンブルも併せて確認。

### 5.4 `0x11c8950` の呼出し元 23 件の `rdx` (#5493・残件の静的確認)

- 方法: `analysis/py5493_rdx.py <PE.bin> --target 16b6d80` が各直接 call の前 25 命令で `rdx` を最後に書いた命令を探し、RIP 相対の参照先を計算する。`lea` は `rdx = T`、`mov` は `rdx = *(T)` (qword)。`*(T)` が `0x16b6d80` なら target の値、`lea` の基底が rbp/rax などの場合は解決不能として `lea (t 不明)` と出す。
- 結果 (23 件): `&global (0x16b6d80)` になるのは `0x11be444` の 1 件のみ (`*[0x15dfd18]` (表) 経由)。非 global の解決は 18 件 (`lea` 6 件: `&0x152bef8`・`&0x16baaf0`・`&0x16bab98`・`&0x16bba78` ×2・`&0x16bcc00`、表経由の `mov` 12 件: 値 `0x16b8db8`・`0x15372e0` 等の .data 参照先)。解決不能は 4 件 (`lea (t 不明)`: `0xe3469e`・`0xf779c0`・`0xf841f0`・`0x132edc1`、rbp/rax 基底の `lea`)。
- `0x86a470` の直接呼出し 2 件: `0x10dc775` は `r8 = rbp+0x68` (スタック) で global ではない。`0x11c896d` は `0x11c8950` の内部 (ラッパーが `0x86a470` を呼ぶ箇所) で、外部の呼出し元ではない。
- 結論: global `0x16b6d80` の代入元 (書込みサイト) は `0x11be444` 経由の 1 件に限られる。型 (G1 `0xbd0ba0` の値の生成元) は本節では確定しない。
- 測定: `analysis/py5493_rdx.py` (新規・測定 commit `8262bb63f`・real 46.7 秒・n=1・load 0.90 → 1.04)。`analysis/py5493_callers.py` (`0x86a470` 2 件)。素材 `block00031_PE.bin` (`fl-win64`)。
- 未解決 (#5493 の続き): 型の確定 (G1 の間接書込み・実行時値) は #5932 / 親 #5145 の範囲。`lea (t 不明)` 4 件の rbp/rax 基底の解決。

## 6. 群 C の受け手 (#5144) — 未達

対象: `0xb35298` (fn `0xb35250`・受け手 `[Self+0x18]`) と `0xb671a2` (fn `0xb67190`・受け手 `[Self+0x7a0]`)。
`analysis/py5144_groupc.py <PE.bin>` (実行 2.02 秒・n=1・load 1.36 / 1 分平均) で確認した。注: この script は `0xb32764` を Self 書込みとして数えるため、その行は誤検出 (下の箇条書きを参照)。script は main に残し、誤検出の記録として保持する。修正は #5144 (残り) で行う。

- fn `0xb35250` は VMT `TDBXStreamValue@0xb07378` のスロット関数。fn `0xb67190` は VMT `TGenericPlugin@0xb655c8` のスロット関数。VMT 経由の呼出しだけで、直接 `call rel32` の呼出し元は 0 件 (両 fn)。
- 両 VMT の .text スロットは 117 件 (`TDBXStreamValue`) と 119 件 (`TGenericPlugin`)。受け手は呼出し元の動的型で決まり、呼出し元までの直接辿りでは決まらない。
- `TDBXStreamValue` の VMT スロット `[116]` (fn `0xb326f0`) の `+0x18` 書込み (`0xb32764`) は、Self の `+0x18` ではない。`rcx = [rbx+0x58]` (Self の `+0x58` の先) の `+0x18` に、`rax = [rsi+0x58]` の `+0x18` を写す。rbx・rsi は第 1・第 2 引数で、Self の `+0x18` は書かない (`groupc` の出力は、このサイトを Self 書込みとして数えた誤検出)。
- `TGenericPlugin` 側 (`+0x7a0`): `.text` 全域の `mov [reg+0x7a0], …` 書込みは **0 件** (`analysis/py5144_writes.py`・走査範囲は下の「走査範囲」行)。
- 実測 (`analysis/py5144_writes.py`・n=1・load 1.36 / 1 分平均 (測定直前の `/proc/loadavg`)。`P=work/py5144/extracted/block00031_PE.bin`): `0x7a0` は 1.28 秒・0 件、`0x18` は 1.26 秒・74 件 (全域。どのクラスの書込みかは未分離)。
- 走査範囲: `mov` 命令で reg 基底の `[reg+disp]` のみ。rsp/rbp/rip 基底は除外。SSE (`movups`/`movdqu` 等) と index 付きアドレッシング (`[reg+idx*s+disp]`) は走査していない。よって「0 件」は「mov の reg 基底の書込みが 0 件」の意味で、SSE 等による書込みの不在は示さない。
- 未確定の理由: (a) `TDBXStreamValue` の `+0x18` は、全域 74 件から Self 型のものを分ける必要がある。(b) `TGenericPlugin` の `+0x7a0` は、走査範囲 (mov の reg 基底のみ) では書かれていない。コンストラクタ・初期化の経路 (`lea` 経由の VMT 書込み) を VMT の RIP 相対 `lea` 検索で特定できなかった (両 VMT とも参照 0 件)。RTTI / フィールド表から宣言型を引いていない。
- 結論: 群 C の 2 件は**型を確定できなかった**。件数 (受入 2b) の不確定は 27 件のまま (群 C の 2 件は残る)。
- 次に必要な情報: `TDBXStreamValue` のコンストラクタと `TGenericPlugin` の初期化関数 (フィールド表の宣言型)。
- 追加の確認 (`analysis/py5144_ctor.py`・commit `117b91c07`・n=1・1.93 秒 (real)・load 0.47 / 1 分平均): 両 VMT のアドレス (`0xb07378`・`0xb655c8`) を即値 (`mov`・`movabs` 等) または `lea [rip+…]` で参照する命令は .text 全域で **0 件**。生バイト検索 (`fl-win64` の `block00031_PE.bin`) でも、4 バイトの VMT 即値は 4 箇所とも `.text` 内 (生データ offset 0x400〜0xfa3a00・データ領域で命令の一部ではない) で、`.data` (VA 0x13a5000〜) にはヒットしない。TDBXStreamValue (0xb07378) は file offset 0x7066b0 (VA 0xb072b0)・0x707079 (VA 0xb07c79)、TGenericPlugin (0xb655c8) は 0x764900 (VA 0xb65500)・0x764db0 (VA 0xb659b0)。コードからの参照ではない。したがって、この 2 クラスのコンストラクタは、VMT を直接書く形では特定できない (Delphi のクラス参照テーブル等の間接経路の可能性)。
- 結論 (本 run): 群 C の 2 件の受け手の型は**引き続き未確定**。残りの手がかり (フィールド宣言型) は、RTTI / フィールド表の解析 (未着手) が要る。

- 逆アセンブル (`analysis/py5144_dis.py`・素材 `fl-win64` の `block00031_PE.bin`・n=1) で確定した事実:
  - `0xb35250` (TDBXStreamValue のメソッド・`rbx=Self`): `rax=[Self+0x18]` を読み、`call [rax+0x180]` の戻り値を `[Self+0x10]` と比較する。不一致なら `rdi=[rax]`・`rcx=rax`・`rdx=Self`・`r8=&local`・`r9=Self+0x14` を設定して `call [rdi+0x1a0]` (0xb35298)。受け手は `[Self+0x18]` の**オブジェクト**。
  - `0xb67190` (TGenericPlugin のメソッド・薄いラッパー): `rax=[rcx+0x7a0]`・`rbx=[rax]` を読み、`rcx=rax` にして `call [rbx+0x1a0]` (0xb671a2)。受け手は `[Self+0x7a0]` のオブジェクトで、Self の値は渡さない。
- 上の 2 件とも、受け手の型は**フィールドに格納されたオブジェクトの動的型**で決まる。その格納元 (コンストラクタ・代入サイト) を特定しないと型は出ない。VMT 即値・RIP 相対 `lea` では格納元が見つからない (上の「追加の確認」)。
- 実測 (`analysis/py5144_dis.py 0xb35250 0xb352c0`・n=1・real 0.06 秒・load 0.36 / 1 分平均): exit 0・33 行。
- 結論 (本 run): 受け手の出所は「Self のフィールドからの読出し」まで確定した。型の確定 (受入 2b の群 C) は未達のまま。

- 訂正 (VMT アドレスの取り違え・本 run): 上の節の VMT アドレス `0xb07378` (TDBXStreamValue)・`0xb655c8` (TGenericPlugin) は、VMT 本体ではなく **VMT の自己ポインタ (VMT-88) の値**だった。`tools/plugins/inventory/delphi_vmt.py` は VMT 本体の VA を引数に取り、`ClassName` を `vmt-24` から読む。自己ポインタ値を渡すと `ClassName` が機械語になる (既知の正の対照 `TFruityHost` の VMT `0x1314108` は自己ポインタ `0x1314178` で、規約どおり読める)。正しい VMT は `0xb07308` (ClassName=TDBXStreamValue・InstanceSize=152) と `0xb65558` (ClassName=TGenericPlugin・InstanceSize=1984)。
  - 影響: 上の「VMT 即値 0 件」「RIP 相対 lea 0 件」「生バイト検索」の結果は、探した対象が誤り (自己ポインタ値) のため、VMT 本体の参照検索としては無効。正しい VMT (`0xb07308`・`0xb65558`) で `analysis/py5144_ctor.py` を流し直すと、即値・RIP 相対 lea ともに 0 件 (実測 1.88 秒・n=1・load 0.47 / 1 分平均)。生バイト検索 (4 バイト即値) も、両 VMT とも 0 件。
  - 自己ポインタ値 (`0xb07378`・`0xb655c8`) の 4 バイト即値は、.text 内の 2 箇所ずつ (`0xb072b0`・`0xb07c79`・`0xb65500`・`0xb659b0`) にあるが、いずれも機械語の途中で、コードからの参照ではない。
- FieldTable の検証 (`analysis/py5144_fields.py`・新規): 正の対照 `TFruityHost` (VMT `0x1314108`) は FieldTable nil。`TDBXStreamValue` (VMT `0xb07308`) は FieldTable `0xb07720` (Count=0)。`TGenericPlugin` (VMT `0xb65558`) は nil。published フィールドが無いため、`+0x18`・`+0x7a0` の宣言型はここからは引けない (実測 0.049 秒・n=1)。
- 未確定の残り: 受け手オブジェクトの格納元 (コンストラクタ・代入サイト) は、正しい VMT 参照では見つからなかった。宣言型は FieldTable に無いため、RTTI 以外の手段 (フィールドの代入サイトの追跡) が要る。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 群 C の 2 件の受け手の型 (`[Self+0x18]`・`[Self+0x7a0]` に格納されるオブジェクトの動的型。格納元は未特定) | 受入 2b の件数 | #5144 (残り) |
