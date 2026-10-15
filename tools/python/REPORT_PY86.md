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
  | 0xbe6040 | D | 3 (0+3+0) | 1 | 2 | 0 | - |
  | 0x6cb1c0 (対照) | - | 5 (0+5+0) | 5 | 0 | 0 | - |

  - 「偶然の一致」は、候補の窓を含む命令を前後 12 バイトから逆引きしても fn を指すオペランドが無いもの (`.text` 内のデータ上の偶然の一致)。A・B の 8 関数は命令参照 0 件で、`jmp`・Jcc・短距離ジャンプ・即値・RIP 相対の参照は無い。
  - 0xbe6040 の命令参照 1 件は `lea rax,[rip+0x21bc]` (0xbe3e7d・7 バイト・次命令 0xbe3e84 + 0x21bc = 0xbe6040)。同じ窓を 0xbe3e7e の `lea eax` も覆うが、同一の窓を重複して拾っている。
  - 非整列の 8 バイトポインタ (0xc155ee・0xc1855a・0x60007a・0x81e8b1) は VMT のスロットではない。0xc155ee と 0xc1855a の直後は ShortString (`ReceiveFrom`・`ReceiveMsg`)、0x60007a の直後は `TGraphicControl`。0x81e8b1 の近傍は 8 バイト間隔の関数ポインタ列と `TQuickGraphicControl` の名前。表の所属クラスは未確認 (子 #3337 で確認する)。
