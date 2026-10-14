# PY-67 (#2159) 3 回目: 受入 3 (`0xec60ae` の対象型) を確定・受入 4 (`0x8ed012` の Self の出所) は部分

親: #2159 (PY-67)・前段: `REPORT_PY67.md` §4〜§5、`REPORT_PY71.md` (PR #2680 で受入 1・2a 達成)。残りは子 #2701 (`[PY-86]`)。

## 結論

| # | 受入条件 (#2159 本文) | 結果 |
|---|---|---|
| 1 | `0x196eba0` の書込み元と書込み先の型 | **達成** (前段: `0x86a4e1`・TGraphEditorForm。`REPORT_PY67.md` §4・§5、`REPORT_PY71.md` §2) |
| 2a | `0xffe370` の所属 | **達成** (前段: TPublicChannel、`REPORT_PY71.md` §3) |
| 2b | `0xffe370` の呼出し元 | **未達・子 #2701** (`call [reg+0x1a0]` 37 件の受け手の型。`REPORT_PY71.md` §4) |
| 3 | `0xec60ae` の対象型 (chan 以外なら除外) | **達成 (PR #2731)**。対象は `[rbp+0x120]` = TPlugListForm のインスタンス (VMT `0xebef58`、親鎖に TChannel 系無し)。**非 chan → 除外** |
| 4 | `0x8ed012` の `[rbp+0x70]` の出所と chan 判定 | **未達・子 #2701**。呼出し元 5 件の Self の出所を §2 に列挙。どれも未確定 |

## 1. 受入 3: `0xec60ae` の対象

- 関数 G2 = `0xec53b0`〜`0xec61dc` (`py59_func.py`)。`0xec60ae` は `mov dword ptr [rax + 0x794], ecx` (`<==` で命令境界を `py59_func.py ... dump` で確認)。`rax` は 0xec6088〜0xec609e で `mov rax, [rbp + 0x120]` と読み直した値で、直前に `cmp dword ptr [rax + 0x7e0], 1` の分岐 (0xec607b) がある。
- `[rbp + 0x120]` は G2 の先頭 `0xec540d: mov [rbp+0x120], rcx` (第 1 引数 = Self) で 1 回だけ書かれる (G2 内の `[rbp+0x120]` への store は 1 件)。
- G2 の direct 呼出し元は 1 件: `0xebf564: call 0xec53b0` (`py67_callers.py`)。直前の `0xebf558: mov rcx, [rip + 0x7fb591]` が Self で、アドレス `X = 0x16baaf0` (.bss)。
- `X` の生成 (`0xebf538`〜`0xebf54b`):
  - `0xebf538: mov rcx, [rip - 0x6af]` → 値 `A = 0xebef58` (`py67_qword.py`)。`0xebef58` は VMT (`.text` 内。Delphi は VMT を `.text` に置く)。
  - `0xebf53f: lea rdx, [rip + ...]` → `&X`。`0xebf546: call 0x11c8950` (前段 `REPORT_PY67.md` §4 の thunk。`rcx = A`・`rdx = &out` を受け、`0x86a470` へ渡す)。
  - `*out = [A-0x30](A)` で、`[0xebef28] = 0x40f960` (`py67_qword.py`。前段の factory F と同じ) → `X` は `A` のインスタンス。
- VMT `0xebef58` (`py71_vmt.py` / `py71_chain.py`): 自己ポインタ OK・TypeInfo 名 `TPlugListForm`・名前一致 OK・インスタンスサイズ `0x8f8`。親鎖は `TPlugListForm 0xebef58 → TBaseGlassForm 0x6f3358 → TChildVectorForm 0x803168 → TVectorForm 0x802bf0 → TUnpaintedWPForm 0x801d60 → TCustomWPForm 0x800d88 → TForm 0x8512a0 → TCustomForm 0x84f4b8 → TScrollingWinControl 0x84cc08 → TWinControl 0x5fded8 → TControl 0x5fa8d8 → TComponent 0x4dd478 → TPersistent 0x4cba08 → TObject 0x401a38`。TChannel 系は現れない。
- `X` への RIP 相対参照 (`py66_riprefs.py`・全走査): `mov [X], 0` が 2 件 (`0xebf7bb`・`0xec6537`)、他は load・比較のみ。非 0 の値を入れるのは `0x11c8950` の out 経由だけ (`lea` の `&X` は `0xebf53f` の 1 件)。
- 受入 3 の結論: `0xec60ae` の対象は `X = TPlugListForm` のインスタンスで、chan (`TChannel` とその子孫) ではない。よって除外する。
- 限界: G2 への間接参照 (`call [reg+..]`) は全走査していない。RIP 相対の参照は `py66_riprefs.py $P 0xec53b0:0xe2c` の `.text` 線形走査 (5,022,467 命令) で確認した: `0xec53b0` を指すものは 0 件。G2 範囲内の参照は `0xec3df9` → `0xec5dff` の 1 件のみ (G2 の入口ではない。命令境界のずれの可能性があり未確認)。即値 (`mov reg, imm`) による参照は本スクリプトの対象外 (レビュー時の線形走査では 0 件と報告されたが、本 REPORT では再現していない)。絶対 8 バイト値 `0xec53b0` の一致は 0 件 (`py67_qword.py ... find`、§5)。

## 2. 受入 4 (未達・子 #2701): `0x8ed012` の `[rbp+0x70]`

- 関数 G1 = `0x8ecbc0`〜`0x8ed069` (`py59_func.py`)。`0x8ed012: mov [rcx + 0x794], rax` は `rcx = [rbp+0x70]` (= 第 1 引数 Self。`0x8ecbcf: mov [rbp+0x70], rcx`)。直前 `0x8ed009: call 0x511fe0` の戻り値を格納する。
- `[rbp+0x70]` の再代入は `0x8ecc06` (dl != 0 のとき `0x410320` = NewInstance 系の戻り値) と `0x8ed028` (dl != 0 のとき `0x410360`) の 2 箇所。直接呼出しの 5 件はすべて `xor edx, edx` (dl = 0) で呼ぶため、Self は呼出し元が渡したオブジェクト。
- G1 の direct 呼出し元 5 件 (`py67_callers.py`):

| 呼出し元 | Self (`rcx`) の出所 | 状態 |
|---|---|---|
| `0xac4c8b` | `[rbp+0x370]` (呼出し元のローカル) | 未確定 |
| `0xb4b619` | `[rbp+0x70]` = 呼出し元の第 1 引数 rcx (`0xb4b5bd`)。dl != 0 なら `0xb4b5f4` で NewInstance の戻り値 | 未確定 (呼出し元の出所へ) |
| `0xb6655f` | `[rbp+0x320]` = 呼出し元の第 1 引数由来 (`0xb66534` で NewInstance 戻り値を格納) | 未確定 |
| `0xb6db99` | `[rbp+0x80]` = 呼出し元の第 3 引数 (r8) | 未確定 |
| `0xc9e07c` | `[rbp+0x90]` = 呼出し元の第 1 引数由来 (`0xc9e051` で NewInstance 戻り値を格納) | 未確定 |

- 結論: `0x8ed012` の Self は、5 件の呼出し元のいずれでも class (VMT) がまだ決まっていない。`dl = 1` の NewInstance は VMT を引数に取るため、各呼出し元の上流 (呼出し元の呼出し元) を遡る必要がある。今回はそこまで到達していない。
- 次の手順: 5 件の呼出し元を含む関数 (`py59_func.py` で範囲を求める) の引数の由来を追い、`dl = 1` の NewInstance に渡る VMT を `py71_vmt.py` で確認する。G1 の Self が chan (`TChannel` 系) の VMT になるかで判定する。

## 3. 間接参照の確認 (受入 3 の限界)

- 絶対 8 バイト値の一致 (`py67_qword.py ... find`): G2 `0xec53b0` は 0 件、G1 `0x8ecbc0` は 0 件 (G2・G1 は direct 呼出しのみ)。X `0x16baaf0` は 1 件 (file offset `0x11e00f8` = `.data` VA `0x15e16f8`)。X を指す `.data` のポインタがあるため、X への間接書込みの経路はある。
- ただし G2 の直前の `0xebf546: call 0x11c8950` で X は再設定され、`0xebf558` まで呼出しは無い (直線的な命令列)。よって G2 の Self (`0xebf558`) は、この call が格納した値 = `TPlugListForm` のインスタンス。間接書込みが X を別の値で上書きする経路は、この区間には無い。
- `0x86a470` の `*out = P` (前段 `REPORT_PY67.md` §4 の範囲外だった項目) は、正常 return する全経路で実行される (`py59_func.py $P 0x86a470 dump` で確認):
  - `0x86a4cf: call [rax-0x30]` (P を返す) から `0x86a4e1: mov [rax], rcx` (`*out = P`) まで jcc・jmp・ret が無い。P は `[rbp+0x48]` 経由で `rcx` に入る。
  - 先行する分岐 `0x86a498: jne 0x86a4ae` と `0x86a4ac: jne 0x86a4b2` は、どちらも `0x86a4b4` に合流する (`0x86a4b0: jmp 0x86a4b4` を含む)。`0x86a4b4` から `0x86a4cf` まで分岐は無い。
  - 関数内の jump は全て前向き (後ろ向きは無い)。`ret` は `0x86a600` の 1 箇所だけ。よって、関数入口から `0x86a4cf` に到達した経路は必ず `0x86a4e1` を通る。
  - 例外: `0x86a4cf` の call や、前段の `0x86a4a5: call 0x410010` が例外・non-return で抜ける経路では `*out` は書かれない。正常 return する経路の結論には影響しない。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 2b: `call [reg+0x1a0]` 37 件の受け手 | 受入 2b | #2701 |
| 受入 4: `0x8ed012` の Self (G1 の 5 呼出し元の出所) | 受入 4 | #2701 |

- #2701 の本文の `0xec60ae` の受入条件 (`[rbp+0x120]` の型と出所) は本 PR で達成した。#2701 の本文でも達成と明記する。

## 5. 測定

- 素材: `fl-win64` の `extracted/block00031_PE.bin` (22,227,016 バイト)。`tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64" --wildcards '*block00031_PE.bin'` で展開 (2.5 秒)。`tools/**/work/` は使わない。
- 追加したコード: `tools/python/analysis/py67_qword.py` (VA の 8 バイト値を読む。`py71_vmt.py` と同じ `.text`/`.data` の扱い)。
- 修正 (commit `fe57eaed`): `.bss` など SizeOfRawData の外の VA に対して、ファイル内の別オフセットの値を出していた (修正前の `0x16baaf0 in .bss qword = 0x410040` は誤り)。修正後は「ファイルに実体なし」と出して終える。前版の結論はこの値を使っていない。

- 測定 commit: `fe57eaed` (`py67_qword.py` の修正 commit。解析コードを変えた最後の commit)。基点 `origin/main` (`580dd294`)。前版の測定 commit `38f903c4` は修正前。
- 差分 0 の証跡 (測定 commit から本節を書いた HEAD まで):

  ```
  $ git diff fe57eaed HEAD -- tools/python/analysis tools/python/src
  (出力 0 行)
  ```

- 実測 (wall・逐次・n=1。測定 commit `fe57eaed`):
  - `py67_qword.py $P 0x16baaf0,0xebee90,0xebef28,0x1306300` と `py67_qword.py $P 0x16baaf0,0xec53b0,0x8ecbc0 find`: 2 回合計 0.12 秒。`0x16baaf0` は `.bss` で「実体なし」、`0xebee90`→`0xebef58`・`0xebef28`→`0x40f960`・`0x1306300`→`0x13063c8`。find は `0x16baaf0` が 1 件 (file offset `0x11e00f8`)、`0xec53b0`・`0x8ecbc0` は 0 件。
  - `py59_func.py $P 0xec60ae dump`: 2.5 秒。`[rbp+0x120]` への store は 1 件 (`0xec540d`)。
  - `py71_vmt.py $P 0xebef58 0x30`: 0.03 秒。VMT・親鎖は §1 の通り。
  - `py66_riprefs.py $P 0x16baaf0`: 61.2 秒 (`decoded 5022467 insns`)。RIP 相対参照の一覧は §1。
  - `py66_riprefs.py $P 0xec53b0:0xe2c`: 60.7 秒 (G2 範囲内の RIP 相対参照は §1 の 1 件)。
  - `py67_callers.py $P 0x8ecbc0,0xec53b0`: 37.9 秒 (`# direct calls: 6`。G1 5 件 + G2 1 件。§2 の表と一致)。
  - `py59_func.py $P 0x86a470 dump`: 2.4 秒 (0x86a470〜0x86a601・size 0x191・出力 99 行 (ヘッダ 1 行を含む))。分岐の確認は §3。
- 再現 (`tools/python` で実行):

  ```
  P=$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin
  python3 analysis/py67_qword.py "$P" 0x16baaf0,0xebee90,0xebef28
  python3 analysis/py67_qword.py "$P" 0x16baaf0,0xec53b0,0x8ecbc0 find
  python3 analysis/py59_func.py "$P" 0xec60ae dump
  python3 analysis/py71_vmt.py "$P" 0xebef58 0x30
  python3 analysis/py66_riprefs.py "$P" 0x16baaf0
  python3 analysis/py66_riprefs.py "$P" 0xec53b0:0xe2c
  python3 analysis/py67_callers.py "$P" 0x8ecbc0,0xec53b0
  python3 analysis/py59_func.py "$P" 0x86a470 dump
  ```
