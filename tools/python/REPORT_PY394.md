# PY-394 (#4842): G1 (0x15d51a0) の書込み元の列挙 (RIP 相対 1 件 + セル 0x15e4018 経由 444 件の読出しからの追跡)

親: #3889 (PY-265)。前段: `REPORT_PY223.md` (G1 の書込みの訂正)・同文書の「PY-265 (#3889)」節 (直接 1 件・候補 12 件)。既知類型との関係: 該当なし (PE の逆アセンブル読解と検査スクリプト。lift 作業ではない)。

## 結論

- **受入 (G1 の書込み元の列挙): 達成 (静的な範囲内)。** G1 (`0x15d51a0`) への書込みは次の 13 箇所。
  - RIP 相対の直接書込み: 1 件 (`0x12d9629`・`sub dword ptr [rip+0x2fbb70], 1`)。
  - ポインタ格納セル `0x15e4018` 経由 (値 `&G1`) の書込み: 12 件 (下表)。読出し 444 件それぞれから、制御フローを辿ってレジスタの流れを追った結果。
- 旧 PY-265 節の「候補 12 件 (直線の近似で、目視未確認)」は、本 run の CFG 追跡 (分岐・直接 call の先まで辿る機械的な追跡) で同じ 12 件になった。12 件の各命令を人手で読んで確かめたものではない。
- セル `0x15e4018` 自体への書込みは 0 件 (RIP 相対 0 件・8 byte の絶対値 0 件)。このセルはロード時の初期値 (`&G1`) のまま読まれる。

## 測定

- 測定 commit: `de5122899` (`analysis/py394_g1_cell_reads.py` の追加 commit。コードを変えた最後の commit)。本 REPORT・DOC_MAP の変更は後続 commit で、`git diff de5122899 HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (本 PR の範囲では REPORT のみ)。
- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` (`oc_artifacts: fl-win64`)。`block00031_PE.bin` を `tools/python/work/py265/` に展開 (2.3 秒・22,227,016 byte)。
- 検査 (本番): `FL_WIN64_DIR=$PWD/work/py265 python3 analysis/py394_g1_cell_reads.py` → rc 0。所要 132.5 秒 (n=1)、user 130.9 秒、実行直後の load average `0.98 0.98 0.74` (4 コア・並列数 1)。
- 検査 (深さ依存の確認): `PY394_DEPTH=3` で 131.7 秒・結果は同じ (12 件・総 walk steps 1041)。`PY394_DEPTH=4` は 110 秒の上限で打ち切り (結果なし)。深さを変えても結果が変わらないのは、引数に追跡中のレジスタを渡す直接 call が 190 件中 1 件だけで、その先 (`0x103c070`) に G1 の書込みが無いため。

## 方式

`analysis/py394_g1_cell_reads.py`。

1. 読出し: `mov reg, [rip+..]` で `0x15e4018` を指す命令を数える。→ 444 件 (本 PE の `.text` を線形走査。ツールの読出し判定は `mov` の宛先がレジスタで、セルがソースの場合)。
2. 追跡: 読出しの次の命令から制御フロー (fall-through・条件/無条件 jmp の直接先) を辿り、`&G1` を持つレジスタ集合を保つ。`mov`/`lea`/`movsxd`/`movzx`/`movsx` で別名を伝播し、他の書込みで上書きされたレジスタは外す。`ret` で止まる。
3. 書込み判定: 追跡中のレジスタを基底にした `[reg+disp]` への書込み (`mov`・`sub`・`add`・`inc`・`dec`・`and`・`or`・`xor` など) のうち、`-size < disp < 4` (4 byte の G1 に当たる) のもの。
4. 呼出し: 追跡中のレジスタを引数 (rcx/rdx/r8/r9) にして直接 call したら、その先を深さ MAX_DEPTH (既定 2) まで同じ方式で辿る。
5. 未モデル化の検査: 間接 call・解決できない jmp・追跡中のレジスタを基底にした未モデルの書込み・レジスタのスピル (`mov [mem], reg` で追跡中のレジスタを退避) を数える。→ 本 run は全 444 件で 0 件。

## G1 への書込み (受入の結果)

| 番地 | 命令 | 経路 (経由するセル読出し) |
|---|---|---|
| `0x12d9629` | `sub dword ptr [rip+0x2fbb70], 1` (RIP 相対・直接) | 関数 `0x12d94f0` の loop (`pe_rip_refs.py`・`.pdata` で境界確認。REPORT_PY223 の節) |
| `0xc4efe0` | `mov dword ptr [rax], 0` | 読出し `0xc4efd9` |
| `0xc4f418` | `mov dword ptr [rax], ecx` | 読出し `0xc4f40e` |
| `0xdcde4b` | `mov dword ptr [rax], ecx` | 読出し `0xdcde3e` |
| `0xf42909` | `mov dword ptr [rax], 1` | 読出し `0xf42902` |
| `0xf48425` | `mov dword ptr [rax], ecx` | 読出し `0xf4840a` |
| `0xf48454` | `mov dword ptr [rax], 1` | 読出し `0xf4844d` |
| `0x10467b4` | `mov dword ptr [rax], ecx` | 読出し `0x10467ad` |
| `0x10467dd` | `mov dword ptr [rax], ebx` | 読出し `0x10467d6` |
| `0x1071c34` | `mov dword ptr [rax], edx` | 読出し `0x1071c23` |
| `0x1071c85` | `mov dword ptr [rax], ebx` | 読出し `0x1071c7e` |
| `0x12c9343` | `mov dword ptr [rax], ebx` | 読出し `0x12c933c` |
| `0x12c935e` | `mov dword ptr [rax], esi` | 読出し `0x12c9357` |

- 各 `mov dword ptr [rax], …` の `rax` は、直前の `mov rax, [rip+..]` (= `&G1` を持つ) の値。disp = 0 なので、書込み先は G1 そのもの。
- G1 以外 (disp が -size < disp < 4 の外) を指す、セル経由の書込みは 0 件。
- G1 への書込みに至る読出しは 12 件 (上表の「読出し」列。読出しと書込みは 1 対 1)。経路上に直接 call が 1 件以上ある読出しは 186 件、経路上に書込みも直接 call も無い読出しは 248 件 (件数の内訳は重なりを含むので足し合わせない)。

## 検証範囲 / 限界

- 範囲内: `block00031_PE.bin` の `.text` (線形走査)。読出し 444 件それぞれの経路 (分岐・直接 call の先を含む)。
- 限界 (近似): 追跡はレジスタの値の流れだけ。メモリ経由の退避・再格納 (スタック経由) は追わない。本 run の検査では、スピル 0 件・未モデルの書込み 0 件・間接 call 0 件・未解決の jmp 0 件で、追跡が打ち切られた箇所は無い (この結果の範囲内で、経路の取りこぼしは検出されなかった)。
- 限界 (戻り値の経路・未追跡): 直接 call の後は `CALLER_SAVED` (rax を含む) を捨て、walk は `ret` で止まる。よって `&G1` を戻り値 (rax) で呼出し元へ返す経路と、その呼出し元からさらに先の書込みは追っていない。この経路の有無は本 REPORT では確定しない (PY-403 #4921 の残作業)。
- 限界 (呼出し深さ): 直接 call は深さ 2 まで。深さ 3 でも結果は同じ。深さ 4 は時間上限で未完。引数に追跡中のレジスタを渡す直接 call は 190 件中 1 件のみで、その先に G1 の書込みは無い。
- 限界 (他 block): 他の PE block から G1 への書込みは、`REPORT_PY223.md` の全 block 絶対値走査 (0 件) の範囲。RIP 相対は同じ PE の VA 空間内だけを指すため、構造上ここでの走査対象。
- 範囲外: 実行時の値 (G1 が指す dword の中身・どの書込みが実行されるかの条件)。obj・flag の条件は PY-265 の未解決 (`REPORT_PY223.md`) を引き継ぐ。

## 実行条件 (PY-403 #4921・途中経過)

- 確定: 関数 `0x12d94f0` の loop で G1 (`0x15d51a0`) を RIP 相対で参照する命令は 5 箇所 (`0x12d961f`・`0x12d9629`・`0x12d9630`・`0x12d9639`・`0x12d9664`)。全て `0x15d51a0` を指す (`block00031_PE.bin` で RIP 相対 = 次命令アドレス + disp を計算して確認。`0x12d9625` は `jne 0x12d9676` で G1 を参照しない)。loop の形は `while (G1 > 1 && pred(G1)) G1--;` (`pred` = `call 0x12d8d30(ecx=G1, dl=1, r8b=1, r9b=1)`)。
- 確定: G1 への書込みは 13 箇所 = 直接 1 件 `0x12d9629` (`sub dword ptr [rip+0x2fbb70], 1`・loop 内) + セル `0x15e4018` 経由 12 件 (上の表の 12 行)。
- 未確定: `0x12d9629` の実行条件。`0x12d9629` へ入るのは `0x12d964e` の `jne` (`pred` の戻り値 al が真) の 1 経路だけなので、`pred` の真偽と G1 の値に依存する。ここは読解が未了。
- 未確定: `pred` (`0x12d8d30`) の戻り値の真偽条件 (G1 を添字にした 24 byte 表の要素の読み。要素の中身は PE の DATA 側)。loop が回る入力の述語はこれで確定する。
- 結果 (PY-403・静的評価の限界): `pred` (`0x12d8d30`) の真偽は PE の静的データからは決まらない。逆アセンブル全体を読み、戻り値 al は、エントリ `E = 0x193fce0 + G1*0xc0` のフィールド (`+0x00`・`+0x10`・`+0x14`・`+0x20`・`+0x28`・`+0x84` と、`+0x20`・`+0x28` のポインタ先) で決まる。テーブル `0x193fce0` は RVA `0x153fce0` で `.bss` (raw データ無し) に入り、中身は実行時に初期化される。添字 0..0x40 の 65 件はすべて読めず、真偽は確定しない (`analysis/py403_pred_table.py`・`unreadable` 65 件)。loop の入力述語を静的に確定するには、実行時の `0x193fce0` の内容 (デバッガ・トレース) が要る。
- 未確定: 書込み 12 件 (セル経由) それぞれが実行される入力条件。分岐の直前の命令は `analysis/py403_g1_write_context.py` で出せる (12 件とも、直前の分岐と書込みの形を記録済み)。どの値で分岐するかは、呼出し元まで含めた読解が必要で、本 run では完了していない。
- 再現: `FL_WIN64_DIR=$PWD/work/py265 python3 analysis/py403_g1_write_context.py` (rc 0・約 0.1 秒)。

## 再現

```
cd tools/python
mkdir -p work/py265 && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C work/py265 --wildcards '*block00031_PE.bin'
FL_WIN64_DIR=$PWD/work/py265 python3 analysis/py394_g1_cell_reads.py          # rc 0・約 132 秒
FL_WIN64_DIR=$PWD/work/py265 python3 analysis/py265_g1_writers.py              # 直接 1 件・直線近似の候補 12 件 (旧測定)
```

## 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| G1 への書込みの実行時の条件 (どの書込みがどの入力で走るか・G1 の値の意味) | PY-229 (#3659) の前提。obj の分岐 | #4921 (PY-403) |
| 関数 `0x12d94f0` の loop の入力 (`call 0x12d8d30(ecx=G1)` の述語) | 上の条件の一部 | #4921 (PY-403) |
| 戻り値 (rax) 経由で呼出し元へ渡る &G1 の書込み (walk は ret で止まる) | 列挙の完全性は静的近似の範囲 | #4921 (PY-403) |

## PY-4878 (#5169): `0x12d92ee` の書込み先と値の源

- `0x12d92ee` `mov dword ptr [rip+0x6669f4], eax` の書込み先は VA `0x193fce8` (`.bss`)。slot `0x15e4018` (`&G1`) への書込みではない。
- 値の源: `0x12d92e5` `mov rax, [rip+0x30a444]` が `.data` のポインタセル `0x15e3730` を読み、その指す先 `0x15f670c` (`.bss`) の dword を `eax` に入れる。
- 検査: `analysis/py5169_store_12d92ee.py` (PASS)。
- 残り: 実行時にこの書込みが走るか・どの入力か (FL の起動環境が要る)。`0x15e3730` を読む命令は 9 件 (`pe_xref.py`)、書込みは 0 件。
