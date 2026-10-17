# PY-275 (#3944): TUndoEvent_MovedFXTracks の生成結果の格納先と、slot 1 の受け手の絞り込み

親: #3902 (PY-269)。前段: `tools/python/REPORT_PY269.md` §1・§3 (未解決)。
既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブルによる解析)。

## 結論

- **受入 1 (生成結果の格納先) は確定**: 0x101ca60 が `classref` 経由で生成した TUndoEvent_MovedFXTracks のインスタンスは、`0x1019b30(Self, dl=0x16, r8=生成結果)` で **Self の `[Self+0x40]` の map** に、キー `0x16` で格納される。0x1019b30 は `[Self+0x54]` の bit `1<<0x16` (0x400000) も立てる。0x101ca60 の判定 `[Self+0x54] & 0x400000` と対応する。
- **受入 2 (受け手の絞り込み) は部分達成**: キー `0x16` を取り出すのは 0x101cab0 の 1 箇所 (`0x102bb20(Self[+0x40], 0x16)`) だけ。取り出したオブジェクトは 0x1021b10 (初期化) に渡され、slot 1 は呼ばない。キー表を回す 0x101a6e0 の 6 件の getter のうち、キー 0x16 を引き得るのは表由来の 4 件。ただし、表の全要素が実行時に 0x16 になるかは静的に確定できない (§3)。格納配列 `[map+8]` を直接読む経路の全件列挙は未了 (§3)。
- **1638 件の `call [X+8]` のうち、`[Self+0x40]` のキー取り出し (0x102bb20) と同じ関数内にあるのは 0x101a6e0 の 6 件だけ** (`0x101aac4`・`0x101abb5`・`0x101ad33`・`0x101b0db`・`0x101b238`・`0x101b3f2`)。残りの 1632 件は、この関数内でキーを取り出していない。ただし、取り出した値を別の経路 (格納配列 `[map+8]` の直接読出し等) で受け取る可能性は未確認 (§3)。

## 0 対象と前提

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` を `tar --zstd -xf ... --wildcards '*block00031_PE.bin'` で `$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin` に展開 (2.9 秒、22,227,016 バイト)。
- 逆アセ: `pe_callgraph.py` の `load()`・`function_starts()`・`around`・`callers`。
- 検証: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/pe_py275_probe.py` → P1〜P9 ALL PASS、終了 0、所要 38.4 秒 (n=1、load average 0.65)。前段 `pe_py269_probe.py` (C1〜C11) は ALL PASS、終了 0、所要 39.4 秒 (n=1、load average 0.65)。
- 測定 commit: `6f0a0171e` (コードを変えた最後の commit。`pe_py275_map_readers.py` の `ARR` を読出し (`mov reg, qword ptr [...]`) に限定した修正)。本 REPORT の §0・§4・§5・§6 の測定値はすべてこの commit で測った。`pe_py275_probe.py` の最後の変更は `a35ffb975`。

## 1. 受入 1: 格納先

| 段 | 関数 | 実測 (probe の検査名) |
|---|---|---|
| 生成 | 0x101ca60 | `classref` 0x1012e78 経由で 0x1021560 が生成 (r8 = Self)。戻り値 rax を `0x1019b30(rcx=Self, dl=0x16, r8=rax)` (P1) |
| 格納 | 0x1019b30 → 0x102bb80 | `rcx=[Self+0x40]` (map)・`edx=0x16` のキーで 0x102b750 が (キー, 値) を格納 (P2・P3) |
| フラグ | 0x1019b30 | `[Self+0x54] |= 1<<0x16` (0x400000)。0x101ca60 の `test [Self+0x54], 0x400000` と対応 |

- 0x101ca60 は、フラグが立っていれば既存の格納値を使い、立っていなければ生成して格納する形と読める。

## 2. 受入 2: 取り出しと受け手

| 項目 | 実測 |
|---|---|
| キー 0x16 の取り出し (`0x102bb20` の `dl=0x16`) | 1 件、0x101cab0 内 (P4) |
| 0x101cab0 の後続 | `0x1021b10` (初期化。`[rcx+0x404]` と 0x1f6 バイトの表を埋める)。slot 1 は呼ばない (P5) |
| キー表 (0x101a6e0 の表ポインタ `[rbp+0x118]`) に 0x16 を書く箇所 | 1 件、0x101a9b9 (`mov byte ptr [rax+0xc], 0x16`。`rax = [rbp+0x118]` は 0x101a991〜0x101a9bd で一貫) (P6)。0x101a6e0 の表ポインタも `[rbp+0x118]` (0x101aa06 の `mov rdx, [rbp+0x118]`) |
| 0x101a6e0 の getter 6 件 | 表由来 (`dl=[rbp+0xe7]`) 4 件 (0x101aa92・0x101ad01・0x101b206・0x101b3c0) と、固定キー `0xb` 2 件 (0x101ab83・0x101b0a9) (P7) |
| 0x101a6e0 の slot 1 呼出し | 6 件 (0x101aac4・0x101abb5・0x101ad33・0x101b0db・0x101b238・0x101b3f2)。各 getter の直後 (`call [rax+8]`) |
| `call [X+8]` の全件 | 1638 件 (P8。PY-269 C3 と一致) |
| キー 0xb の格納元 | 0x101cc60 (0x16 とは別の生成関数) (P9) |

- 0x101a6e0 の slot 1 呼出し 6 件のうち、キー 0x16 で取り出した値が呼出し時点で TUndoEvent_MovedFXTracks であるかは、表 `[rbp+0x118]` の内容 (実行時データ) に依存する。本 REPORT は静的に確定しない (§3)。
- 表ポインタの食い違い (#4964 の指摘) は解消: 表ポインタは `[rbp+0x118]` (0x101a991〜0x101aa06 で読まれ、0x16 を書く 0x101a9b9 もこの値経由)。`[rbp+0xd0]` は別変数で、0x101aa29・0x101aacf で読まれる (表ポインタではない)。#4761 のコメント `[rbp+0xd0]` は誤り。
- 1632 件の残りは、0x102bb20 を呼ぶ 26 関数 (0x101a6e0 以外。0x102bb20 の呼出し元は計 27 関数) の中にはない。ただし、これは「キーで取り出す経路」の外側を見ただけで、`[map+8]` の配列を直接読んで slot 1 を呼ぶ経路の除外にはならない (§3)。

## 3. 限界 (未解決)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x101a6e0 のキー表 (表ポインタ `[rbp+0x118]`) の内容 (実行時に 0x16 が入る条件) | 6 件の slot 1 呼出しのうち、実際に TUndoEvent_MovedFXTracks を受けるかの確定 | #4995 (PY-4850) へ追記。動的確認が要る |
| 1632 件の残りが、格納配列 `[map+8]` を 0x102bb20 以外の経路で読んで slot 1 を呼ぶか | 受入 2 の「残りは受け手ではない」の確度。0x102b750 は `[map+8]` の配列に値を格納し、0x102b6c0・0x102b610 で添字を計算する (逆アセ確認のみ・未追跡) | #4995 (PY-4850)。`[map+8]` の読出し箇所を全件列挙し、同インスタンスかを確定する |

## 4. 検証

- `pe_py275_map_readers.py` (§5 の候補列挙): M1・M2 ALL PASS、終了 0、所要 40.4 秒 (n=1、load average 0.32)。候補 3 関数。
- probe: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/pe_py275_probe.py` → P1〜P9 ALL PASS、終了 0、所要 38.4 秒 (n=1、load average 0.65)。
- 前段: `pe_py269_probe.py` → C1〜C11 ALL PASS、終了 0、所要 39.4 秒 (n=1、load average 0.65)。
- コード差分: 測定 commit `6f0a0171e` から HEAD までの flapi 差分は空 (`git diff 6f0a0171e HEAD -- tools/python/analysis/flapi` の出力 0 行)。前回の測定 commit `5cb0fb182` からの差分は次の 2 ファイル: `pe_py275_map_readers.py` (4 行。`ARR` の読出し限定) と `pe_py275_map_slot1.py` (新規 62 行。main 取り込み後の merge `a181d9b3d` で入った §6 の probe)。`5cb0fb182` 以前の `pe_py366b_probe.py` の追加は別 PR の probe で、本 REPORT の測定対象外。

## 5. 受入 2 後半の候補 (解析補助・上限ではない)

`pe_py275_map_readers.py` の条件 (関数内に `[reg+0x40]` の読み・配列要素の読出し `mov reg, qword ptr [base+idx*8+8]`・`call [reg+8]` が同居) で 3 関数:

| 関数 | 0x102bb20 (キー取り出し) | 所見 |
|---|---|---|
| 0xc3b930 | なし | 配列読みの元は `[rbp+0xd0]+0x18` (map 由来ではない)。slot 1 の受け手は未確定 |
| 0xc3bc00 | なし | 配列読みの元は `[rbp+0xa0]+0x18`。0xc3bd98 の slot 1 の受け手は `[rbp+0xa0]+0x10` 経由 (map ではない) |
| 0x1046a30 | なし | 大関数 (4904 命令)。`[rbp+0x40]` 直接読みあり。受け手の同一性は未確定 |

- 0x1304060 は、旧 `ARR` (store `qword ptr [..], reg` も数えた判定) では候補に入っていた。読出し限定の修正後は候補外 (格納配列 `[rax+rcx*8+8]` へのアクセスは store のみで、読出しは 0 件)。slot 1 呼出し 0x1304d5d の受け手 `rbx` の出所 (`mov rbx, rdx` 0x1304ad9・`mov rbx, rax` 0x1304ba3) は未確定。
- 0x102bb20 を呼ぶ 27 関数のうち、候補 3 関数には含まれない。
- 候補 3 関数の受け手の同一性は、前方の単純な追跡 (40 命令) では確定できなかった (スタックへの退避が多い)。受入 2 後半は未達のまま子 issue へ分割する。

## 6. #4995: 格納配列 `[map+8]` の直接読みと slot 1 の共存 (部分達成)

- 本節の probe `pe_py275_map_slot1.py` は main 取り込み後の merge `a181d9b3d` で入った新規 probe。§0・§4 の測定 (`pe_py275_probe.py` 等) とは測定対象が別。本節の値は測定 commit `6f0a0171e` の HEAD でも再測定 (下記 検証) した。

- 格納配列の値読出し `mov r, qword ptr [base + idx*8 + 8]` は 360 件 (`pe_py275_map_slot1.py` Q1)。`call qword ptr [reg+8]` は 1638 件 (Q2・PY-269 C3 と一致)。
- 同一関数内に両方が共存する関数は 7 件: 0x69b640・0x8c9d20・0xb70190・0xc3b930・0xc3bc00・0xd328f0・0x1046a30 (Q3〜Q5)。#4964 が挙げた 4 関数のうち 0xc3b930・0xc3bc00・0x1046a30 を含み、0x1304060 は含まない (格納配列の読出し 0 件)。
- 0x1304060 は格納配列の読出しを 0 件持つ (store のみ)。slot 1 呼出しは 0x1304d5d の 1 件で、呼出し元は 0x1304481 のみ。受け手は格納配列由来ではない可能性が高いが、未確定。
- 0xd328f0 は格納配列の読出し 4 件を持つ。#4964 のコメントは「map 由来ではない」と書くが、読出し元 (`[rax + rcx*8 + 8]` の `rax`) を確定していないため、本 REPORT は否定も肯定もしない。
- 7 関数の逆アセ (`around`) で確認できた事実:
  - 0xc3b930: 読出し (0xc3b9fd) の値を `[rbp+0x78]` に置く。slot 1 (0xc3bb2e) の receiver は `[rbp+0xd0]+0x10` の別オブジェクトで、読出し値とは別経路。
  - 0xc3bc00: 読出し (0xc3bcb4) の値を `[rbp+0x60]` に置く。slot 1 (0xc3bd98・0xc3bde3) の receiver は `[rbp+0xa0]+0x10` と `[rdx+0xa0]+0x10`。読出し値とは別経路。
  - 0xd328f0: 読出し 4 件 (0xd329b2・0xd32a32・0xd32a94) と slot 1 (0xd32b89; receiver は `[rbp+0xe0]+0xb0`)。読出し値との結び付きは未確定。
  - 0x1046a30・0x8c9d20・0xb70190・0x69b640: 読出し値と slot 1 receiver の結び付きは未確定 (0x69b74b・0x69b88e が読出し元)。
- **未確定 (受入条件の「同インスタンス確定」は 0 件)**: 7 関数すべてで、読出し値と slot 1 receiver が同じ TUndoEvent_MovedFXTracks かは確定していない。確定には各関数で「読出し値 → 変数 → receiver」の流れを手作業で追う必要がある。レジスタ・スタックを追う自動追跡を試作したが、既知の候補 (0xc3bc00 等) を検出できず信頼できなかったため、probe からは除いた。probe は関数の共存の列挙のみ。
- 0x101a6e0 の表ポインタ: 逆アセで `[rbp+0x118]` に一貫 (0x101a6ed で 0 初期化、0x101a8f1 で 0、0x101aa06 で読み)。`[rbp+0xd0]` は 0x101a6f8 で 0 初期化され、0x101a9ff で `lea`、0x101aa29 で読まれる別変数。#4761 のコメントの `[rbp+0xd0]` は誤り。REPORT §2 の `[rbp+0x118]` が正しい。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 7 関数の受け手の同インスタンス確定 (手作業追跡) | 受入条件の残り。slot 1 が TUndoEvent_MovedFXTracks を受けるかの確定 | 子 issue #4995 へ移送 |
| `pe_py275_map_slot1.py` の自動追跡が候補ゼロ | 自動化の信頼性。結論には使っていない | #4995 |

- 検証: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/pe_py275_map_slot1.py` → Q1〜Q5 ALL PASS、終了 0、所要 28.1 秒 (n=1、load average 0.96、HEAD `5e11efbe6` で再測定)。

## 7a. #5471: 3 関数の受け手の追跡 (関数内で確定・関数をまたぐ箇所は未確定)

- 本節の probe: `pe_py275_receivers.py` (R1〜R12)。対象は 0x69b640・0x8c9d20・0xb70190 の 3 関数。関数の範囲は次の int3 パディングまで (0x69b640..0x69be16・0x8c9d20..0x8ca20e・0xb70190..0xb702eb)。
- 関数内の命令だけで確定した事実:

| 関数 | [map+8] 読出し | 読出し値の行き先 (関数内) | slot 1 呼出し | slot 1 の receiver の出所 | 判定 |
|---|---|---|---|---|---|
| 0x69b640 | 69b74b (キー取得)・69b88e (値) | 69b88e の値は `[rbp+0xe0]`・`[rbp+0xd8]` に入り、算術と 69b8c5 の格納にだけ使われる。69b340 へは `r8` 引数として渡る (69bb8e) | 5 件。69b79e・69ba6c・69bdcc・69be0c は `[Self+0x44]` (`[rbp+0x120/0x128]` 経由)。69b7f1 は `0x68b3a0` の戻り値 (大域変数の singleton) | 読出し値を receiver に使う箇所は関数内にない | probe の検査範囲 (R6: 呼出し直前 3 命令と `[rbp+0xd8]`・`[rbp+0xe0]` の 2 スロット) では、読出し値が receiver になる箇所を検出しなかった。69b340 内の receiver 出所は未追跡 |
| 0x8c9d20 | 8c9e38 (`rsi`) | `rsi` は 8c9e38 以降、各種 helper の引数 (`rcx`・`rdx`・`r8`) としてだけ使われる | 1 件 (8ca1be)。receiver `[rbp+0x28]` は 8c9d8f で virtual call `[rax+0x10]` の戻り値を 1 回だけ書かれる | 読出し値と別経路 | probe の検査範囲 (R9: receiver スロットの書込みを 1 箇所に限定) では、読出し値が receiver になる箇所を検出しなかった。`rsi` を受けた helper (8c9a70・8c9c70・8c9a60・8cabf0・8c63d0・8c6530・8c67c0・8c7370・8c7450) 内の slot 1 は、関数本体の列挙では 0 件だが、関数をまたぐ受け渡しは未追跡 |
| 0xb70190 | b7024b (`[Self+0x950]` の固定テーブル) | 新規オブジェクト `rdi` (0xb721a0 の戻り値) の `+0x18` に格納される。`rdi` はこの関数内で他に渡されない | 1 件 (b70297)。receiver は `[Self+0x988]` (b7028a) | 読出し値と別経路 | probe の検査範囲 (R10〜R12) では、読出し値が receiver になる箇所を検出しなかった。`rdi` の出所 (0xb721a0 の結果) は関数外に渡らないことを命令列で確認 |

- **同インスタンスの確定は 0 件**。3 関数とも、probe の検査範囲では「読出し値が slot 1 の receiver になる」箇所を検出しなかった。ただし、0x69b340 (69b640 からの r8 引数)・0x8c9a70 ほか (8c9d20 からの rsi 引数) の内部は、この probe では追っていない。確定には、これらの callee の receiver を追う必要がある。
- 検査の限界: R6 は呼出し直前 3 命令の文字列一致だけを見る。別レジスタ経由の受け渡しは対象外。
- 検証: `FL_WIN64_DIR=<展開先> python3 tools/python/analysis/flapi/pe_py275_receivers.py` → R1〜R12 ALL PASS、終了 0、所要 29.7 秒 (HEAD `5e11efbe6` で再測定、n=1、load average 0.96)。素材は `$ARTIFACTS_DIR/fl-win64.tar.zst` (2.3 GB) から `block00031_PE.bin` (22,227,016 バイト) を 2.9 秒で展開。

### 7b. #5471 未解決 1: 0x69b340 (0x69b640 の r8 引数の先) の slot 1 receiver

- 0x69bb8e の `call 0x69b340` の r8 は `[rbp+0xd0]` (= `[rbp+0xe0]` の複写。`[rbp+0xe0]` は 0x69b893・0x69bb1b で算術・格納される map 値)。
- 0x69b340 の slot 1 呼出しは 2 件 (69b496・69b52e)。receiver は 69b48d `mov rbx, [rcx]` (rcx = `[[this+0x10]]`・69b465) と 69b52b `mov rbx, [rax]` (rax = `[this+0x10]`・69b4fb) で、いずれも `[this+0x10]` 由来。r8・rsi (map 値) 由来ではない。
- 0x69b340 は map 値 (`rsi` = 旧 `r8`) を `r8` (begin)・`r9` = `rsi+rdi` (end) の組で 0x691a40 (69b455・69b4b5・69b54b) に渡す。範囲の形で、オブジェクトの receiver としては使われていない。ただし 0x691a40 の内部は未追跡 (下表の未解決)。
- 判定: 0x69b340 の**関数内**では、map 値が slot 1 の receiver になる箇所はない。0x69b640 の未解決 1 のうち「0x69b340 内の receiver 出所」は解決。残り: 0x691a40 (map 値を r8/r9 範囲として受ける) の内部で slot 1 が呼ばれるか。
- 検証: `FL_WIN64_DIR=<展開先> python3 tools/python/analysis/flapi/pe_py275_receivers.py` → R1〜R15 ALL PASS、終了 0 (R13〜R15 を追加)。所要 37.9 秒 (測定 commit `479b81053`、n=1、load average 0.51)。素材 `fl-win64.tar.zst` から `block00031_PE.bin` を 2.9 秒で展開。

## 7. #5472: 4 関数の読出し値と slot 1 receiver の流れ (関数内で確認)

- 本節の逆アセ (`pe_callgraph.py around`・`pe_py5472_slot1_receivers.py`) は子 #5472 の結果。関数内のスロット流れだけを見る (関数境界を越える流れは見ない)。
- 確認の対象は、`[map+8]` の読出し値の格納先スロットと、slot 1 呼出し直前の `mov rbx, [reg]` の元 (receiver の取得元) が関数内で交わるか。

| 関数 | 読出し値の格納先と後続 | slot 1 呼出し (receiver の取得元) | 判定 |
|---|---|---|---|
| 0xc3b930 | 0xc3b9fd → `[rbp+0x78]` → 0xc3bb38・0xc3bb49 の rip 相対 call の引数のみ | 0xc3bb2e (`[rbp+0x98]` = `[[rbp+0xd0]+0x10]`)。0xc3bbac は `0xc3bb80` 側 (別関数) | 読出し値は receiver にならない (関数内) |
| 0xc3bc00 | 0xc3bcb4 → `[rbp+0x60]` → 0xc3bd9b の rip 相対 call の引数・0xc3bd78 の格納のみ | 0xc3bd98 (`[rbp+0x78]` = `[[rbp+0xa0]+0x10]`)・0xc3bde3 (`[rdx+0x78]` = `[[rdx+0xa0]+0x10]`。0xc3bdc0 側の別関数) | 読出し値は receiver にならない (関数内) |
| 0xd328f0 | 読出し 4 件 (0xd329b2・0xd32a32・0xd32a94・0xd32b50) はいずれも引数・データコピー・`[rbp+0x90]`→`[rbp+0x88]` の rip 相対 call 引数。`[rbp+0x78]` は 0xd32b7a の 1 件 (receiver 用) | 0xd32b89 (`[rbp+0x78]` = `[[rbp+0xe0]+0xb0]`)。0xd32b89 は 0xd328f0 側に属する | 読出し値は receiver にならない (関数内) |
| 0x1046a30 | 0x104ab4f → `[rbp+0x508]` → 0x104ab73〜0x104ad77 の field 読出し・0x104ad67 の引数・`[rbx+0x1f0]` の receiver (0x104ad81) | slot 1 (0x1048636・0x104b583) の receiver は `[rip+x]` 由来 `[rax+0x5c]` (グローバルの `+0x5c`)。読出し値は slot 1 の receiver にならない | 読出し値は slot 1 の receiver にならない (関数内) |

- 4 関数とも、読出し値が slot 1 の receiver として渡る経路は関数内に無い。0x1046a30 は `[rbp+0x508]` を receiver とする間接 call が `[rbx+0x1f0]` (slot 1 ではない) の 1 件 (0x104ad81)。
- **未確定 (受入条件の「同インスタンス確定」は 0 件)**: 関数内の流れは確認したが、読出し値が関数の外 (引数として渡った先 0x417fc0・0x40c660・0xd32560 等) で格納され receiver に戻る経路は未追跡。receiver の `[[reg+0xa0/0xb0/0xd0]+0x10]` が TUndoEvent_MovedFXTracks を指すかも未確定。
- 検証: `FL_WIN64_DIR=<展開先> python3 tools/python/analysis/flapi/pe_py5472_slot1_receivers.py` → `EXPECT` の逆アセ行 28 件 (読出し・格納・receiver 取得・slot 1 呼出し) と `[rbp+0x508]` 格納の 1 件 (0x1046a30 内) の計 29 行が完全一致 ALL PASS、終了 0。測定 commit `c11573df5` (修正前 HEAD で実測。所要 36.98 秒、n=1、load average 1.02 (測定直後))。probe は文字列の完全一致を固定するだけで、同一インスタンス性は確定しない。
- probe が固定していない手読みの結論 (probe 行には無い。上の表の記述はこれらを含むが、文字列としては固定していない):
  - 0xd328f0: 読出し 4 件のうち 0xd329b2・0xd32a32・0xd32a94・0xd32b50 は probe に無い (引数・コピー先の手読み)。
  - 0xc3b930: 0xc3bb38・0xc3bb49 (rip 相対 call の引数) は probe に無い。0xc3bb16 の `rax` の元 (`[[rbp+0xd0]+0x10]`) は手読み (probe の `mov [rbp+0x98], rax` は格納のみ)。
  - 0x1046a30: receiver の根 `[rip+x]` 側は probe に無い。probe が固定するのは `mov rax, [rax]` 以降の `[rax+0x5c]` (2 段) までで、`[rip+x]` の具体的な命令は手読み。
