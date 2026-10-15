# PY-4883 付録 (#5192): `[reg+0x60]` 517 箇所の所属関数と書込み 18 件のゲート位置 (親 #4432)

親: #4432 (PY-326)。前段: `tools/python/REPORT_PY73_APPENDIX_3965.md` §1〜§3・`tools/python/REPORT_PY73_APPENDIX_4371.md`。
既知類型との関係: 該当なし (lift 作業ではない。逆アセンブルと直接 call の閉包)。
実装: 0 件 (`provider/`・`host/`・`tests/` は未変更。推測の状態モデルは作っていない)。製品 KPI: 対象外 (起動・GUI に関わらない解析)。

## 結論

- **受入 1 (`[reg+0x60]` 517 箇所のクラス): 未達。** 517 箇所は 272 関数に散らばり、レジスタは `rbx` 308・`rax` 140・`rsi` 34・`rbp` 15・`rdi` 13・`r13` 7。
  所属関数ごとの件数は 17 箇所が最大 (`0x13173a0`)。ただし vtable `V = 0x125b1c0` を指すオブジェクトのクラスは特定できていない。
  V を指す `lea` は 0 件。V の vptr 格納は data 2 件 (`0x125b0f8`・`0x125b2d0`) のみで、そこを書く関数は未特定。`0x40fb40` は vptr 書込みとは確認していない (`0x40fb40` の逆アセンブルは `0x40d210` への call のみ)。ここから先は未追跡。
- **受入 2 (書込み 18 件のゲート前後判定): 部分。** 直接 call の閉包では、書込み関数 12 個のどれも `0xd5c800` (midiNoteOn) に到達しない (0/12)。
  判定できないのは次の 3 点:
  1. 書込み 18 件のうち 4 件 (`0xd1cb19`・`0xfff311`・`0xfff3c3`・`0x1262977`) は所属関数への直接 call 呼出し元 0 件。`0xd1af20`・`0xfff070`・`0x1262970` は間接経路からしか届かない。
  2. `0x1262970` (flagC 書込み `0x1262977`) は `V+0x60` からだけ呼ばれる。その呼出し元 (517 箇所のどれか) が `0xd5c858` より前に走るかは未確定。
  3. ゲート `0xd5c858` は `call 0x11d1430`、そこは `call qword ptr [rax+0x88]` (V+0x88 = `0x1262a90`)。`[rax+0x88]` の 333 箇所の判定は本付録の範囲外。
- **受入 3 (推測で実装しない): 達成。** provider・mock は未変更。

## 測定

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` を `tar --zstd -xf --wildcards '*block00031_PE.bin' -C work/py5192` で展開 (22,227,016 B・1.62 秒)。`work/` は gitignore。
- 再現コマンド (前段と同一の検査):
  - `FL_WIN64_DIR=<展開先> python3 tools/python/analysis/flapi/pe_flag_scope_check.py`: 20.4 秒 (real)・user 20.0 秒・load 0.66。出力は 3649 付録・3965 付録と一致 (writes 18・0/12・V+0x60 `0x1262970`・間接 call `[reg+0x60]` 517・`[reg+0x88]` 333)。
  - `FL_WIN64_DIR=<展開先> python3 tools/python/analysis/flapi/pe_py322_probe.py`: 34.4 秒 (real)。`0xd1af20` の rip 参照 2 件 (`0xd16123`・`0xd16163`)・格納値 `0x1262970` (`0x125b220`)・表 `0xfe2c30`・`0xfe2ed8` と一致。
  - `FL_WIN64_DIR=<展開先> python3 tools/python/analysis/flapi/pe_py5192_reg60.py`: 19.8 秒 (real)。出力 `sites 517 functions 272`。`list` 指定で 517 行の全箇所を出す (`reg60_list.txt`・work/ 内)。
- 測定 commit: 本 PR の最初の commit (`pe_py5192_reg60.py` と本 REPORT を入れた commit)。測定は `origin/main` の `84bf9a6ac` と同じ解析スクリプトで行った。

## 解析 (PE 箇所つき)

| 対象 | 箇所 (RVA) | 内容 |
|---|---|---|
| ゲート呼出し | `0xd5c858` | `call 0x11d1430` (`0xd5c800` 内。`test al,al` で分岐。0 なら `0xfffffffffffffffe` を返して終了) |
| ゲート関数 | `0x11d1430`〜`0x11d1452` | `mov rax,[rip+...]`→`call qword ptr [rax+0x88]` (T の vtable +0x88) |
| flagC 書込み | `0x1262977` | `0x1262970` (= V+0x60 の実体): `mov byte ptr [rax],1; ret`。直接 call 呼出し元 0 件 |
| 格納文脈 | `0xd16123`・`0xd16163` | `lea rax,[rip+...]` (= `0xd1af20`) を callback 構造体の +0x30 に格納し `0x526190` に渡す (3965 付録 §2) |
| vptr 格納 (data) | `0x125b0f8`・`0x125b2d0` | V (`0x125b1c0`) の格納箇所 (PE 全体の 8 byte 走査・前段 probe の `stored` 行)。格納する関数は未特定 |

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `[reg+0x60]` 517 箇所のクラス (vtable V を指すオブジェクトの型) | 受入 1 未達 | 親 #4432 にチェックリストとして残す (次 run で V の vptr 書込み `0x40f977` 周辺から逆引き) |
| 書込み 18 件のうち間接経路の 6 件以上の判定 (`0xd1af20`・`0xfff070`・`0x1262970`) | 受入 2 未達 | 同上 |
| `[reg+0x88]` 333 箇所のうちゲート後に届く経路 | ゲート後の判定の根拠 | 同上 |

## 差分 0 の証跡

- 測定に使った既存スクリプト 3 本 (`pe_callgraph.py`・`pe_flag_scope_check.py`・`pe_py322_probe.py`) は、本 PR で変更していない。
- 新規スクリプト `pe_py5192_reg60.py` のみを追加。
