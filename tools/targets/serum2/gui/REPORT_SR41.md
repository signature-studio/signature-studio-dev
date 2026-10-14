# REPORT — [SR-41 #2135] SerumController vtable の間接呼出の受信型の逆解析 (静的・部分達成)

- 日付: 2026-10-14 / 親: #2102 (SR-38) / 前段: `REPORT_SR38.md` §2・§3
- 範囲: 静的解析のみ。実 VSTGUI 上の動的確認は範囲外。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `Serum2.vst3` (x86_64-win)。sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283` / 19,236,864 B (SR-38 と一致)。作業用 dir はリポジトリ外。
- 測定 commit: `693bbd63` (`receiver_origin.py` を追加した commit)。このコミット以降にコードは変えていない。

## 0. 結論

| 受入条件 | 判定 |
|---|---|
| 1. 候補 1052 件のうち受信が SerumController (this) のものを確定 | **未達**。受信型は 1 件も確定していない。受信レジスタの直前の定義元を分類し (§2)、子 issue に移した |
| 2. `0x1800c2b50`/`0x1800c6090`/`0x1800c9680` の呼出元の列挙と Splice 経路 | **部分達成**。Splice 生成 `0x180498090` の直接呼出元は 1 件 (`0x1800c995b` in slot 17 `0x1800c9680`) と確定。3 関数への間接呼出元の列挙は受信型が未確定のため未達 |
| 3. patch 後 (demo bit ≡ 0) で Splice 表示が偽になる経路 | **未達**。§3 の材料のみ |
| 4. REPORT に追記 (測定 commit と再現手順) | **達成** (本ファイル) |

本 run で得たもの: 候補の定義元分類ツール (`receiver_origin.py`) の追加、Splice 直接呼出元の確定、demo bit の読み書き箇所の確定。
「直接呼出し 0 件」は、3 関数が vtable 経由でしか呼ばれないことを示すだけで、到達不能を示すものではない。

## 1. 再現手順・実測

```sh
# $S: リポジトリ外の作業用 dir。$P: 本ディレクトリ (tools/targets/serum2/gui)
cd $S
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" --wildcards '*Install_Xfer_Serum2_2.1.5.exe'
7z x -y -oexe_extract Install_Xfer_Serum2_2.1.5.exe '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3'
cp -f 'exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' Serum2_win64.vst3
uv venv -q venv --python 3.14 && uv pip install -q -p venv/bin/python pefile capstone zstandard
venv/bin/python $P/serum_controller_recv.py Serum2_win64.vst3 0x180a2bf58 6 7 17
venv/bin/python $P/receiver_origin.py Serum2_win64.vst3 --top 12
venv/bin/python $P/splice_chain.py Serum2_win64.vst3 0x1800c2b50 0x1800c6090 0x1800c9680 0x180498090
venv/bin/python $P/splice_demo_bit.py Serum2_win64.vst3 0x1800c2b50 0x1800c6090 0x1800c9680
```

- 依存: `pefile` `capstone` `zstandard`。
- 実測 (n=1, 逐次, runner 上。`uptime` の load average は実行前後の 1 分値):
  - 展開: `tar --zstd` 1.8 s (real, 1 entry)。`7z x` の実測は省略。
  - `serum_controller_recv.py` (3 slot): real 24.13 s / user 23.01 s, load 1.04 → 0.55 (実行前後の 1 分値は直前 uptime)。
  - `receiver_origin.py` (`--top 12`): real 25.03 s / user 23.98 s, load 0.58 → 0.73。
  - `splice_chain.py` / `splice_demo_bit.py`: 実行は 1 回のみ。時間は未計測。
- 検証: `sha256sum` は SR-38 と一致。候補件数 1052 は SR-38 と一致。`serum_controller_recv.py` の S=1 / K=1 / U=1050 も SR-38 と一致。

## 2. 受信レジスタの直前の定義元 (`receiver_origin.py`)

候補 1052 件 (disp `0x30`/`0x38`/`0x88`) を、受信レジスタを最後に書いた命令の種類で分類した。
**これは受信型の証明ではない**。`load[base+disp]` の base が this か子オブジェクトかは判定していない。

| 定義元 | 件数 |
|---|---|
| `load[rcx+0x0]` | 528 |
| `load[rbx+0x0]` | 244 |
| `load[rax+0x0]` | 63 |
| `load[rsi+0x0]` | 60 |
| `load[rdi+0x0]` | 46 |
| `load[r14+0x0]` | 20 |
| `copy(rcx)` | 20 |
| `load[rsp+0x90]` | 11 |
| `load[r15+0x0]` | 7 |
| `arith-add` | 7 |
| `other-mov` | 5 |
| `arith-pop` | 5 |

- 1 件あたりの逆解析 (base の定義元を辿って `this` まで遡る) は必要で、`load[rcx]`/`load[rbx]` の 772 件で大半を占める。1 run に収まらないため子 issue に移す。
- 候補 1052 のうち、SR-38 の S/K 分類で確認済みの 2 件は、いずれも受信が子オブジェクトの vtable 呼出 (`[rsi+0x10]` / `[rcx+0x40]`) だった (`REPORT_SR38.md` §2)。

## 3. Splice 経路と demo bit (受入 2・3 の材料)

- `0x180498090` (Splice 生成) の直接呼出元: `0x1800c995b` のみ。所属 `0x1800c9680` (slot 17)。
  - `0x1800c9941` (`mov ecx,0x3a0` → alloc → `call 0x180498090`) へ入る経路は、同関数内に 3 本ある: `0x1800c96b3` の `je` (`[[rcx+0x20408]+0x30] & 1 == 0` のとき)、`0x1800c96cc`・`0x1800c96d9` の `jne` (`[rsi+0x227a0]`・`[rax+0xb8]` の比較が不一致のとき)、`0x1800c993a` の `je`。
  - 所属関数 `0x1800c9680` 内に demo bit `+0x22792` への参照は無い (`splice_demo_bit.py`: 0 hits)。そのため、Splice 生成への到達可否は demo bit ではなく上記の 3 条件で決まる。
  - 前段 (本 run の範囲外): 上記 3 条件の入力 (`[rcx+0x20408]`・`[rsi+0x227a0]`) が demo bit と関係するかは未確定。
- demo bit `+0x22792` の参照は 4 箇所:
  - 書き込み: `0x1800c2cfe` (`mov [rsi+0x22792], al`)、`0x1800c2d42` (`mov [rsi+0x22792], 1`) — 所属 slot 6 `0x1800c2b50`
  - 読み出し: `0x1800c2d52` (`test`) — 所属 slot 6 `0x1800c2b50`
  - 読み出し: `0x1800c6874` (`cmp [rsi+0x22792], 1`) — 所属 slot 7 `0x1800c6090`。`jne 0x1800c68ba` で分岐し、一致時は `0x1800c687d`〜`0x1800c68b5` (dialog/entry 生成のような処理) に入る
- 結論 (本 run の範囲): slot 17 (Splice 生成直接呼出元の所属) は demo bit を読まない。slot 7 は demo bit を読むが、slot 7 から slot 17 への呼出連鎖は未確定 (受信型が未確定のため)。**受入 2 の「経路」・受入 3 の「偽になる経路」は未確定。**

## 4. 残る作業 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) 候補 1052 件の受信レジスタの base を this まで遡り、受信が SerumController (this) のものを確定する。特に `load[rcx]` 528 件・`load[rbx]` 244 件 | 受入 1 | #2174 (SR-43) |
| (b) slot 7 `0x1800c6090` から slot 17 `0x1800c9680` (Splice 生成直接呼出元) への呼出連鎖の有無を確定し、経路があれば demo bit (`0x1800c6874`) の分岐条件を追う。経路が無ければ非到達を静的に示す | 受入 2 (後段)・3 | #2175 (SR-44) |
| (c) 実 VSTGUI 上の動的確認 | SR-30 受入 4 相当 | `#68` 残作業 (GUI lift 時) |
