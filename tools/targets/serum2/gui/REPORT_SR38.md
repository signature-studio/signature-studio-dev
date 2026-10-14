# REPORT — [SR-38 #2102] SerumController vtable (head `0x180a2bf58`) の間接呼出の受信型解決 (静的)

- 日付: 2026-10-14 / 親: #2055 (SR-33) / 前段: `REPORT_SR33.md` §2-3・§5 (B)、`REPORT_SR34.md`
- 範囲: 静的解析のみ。実 VSTGUI 上の動的確認は範囲外。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `Serum2.vst3` (x86_64-win)。sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283` / 19,236,864 B (SR-30・SR-33 と一致)。作業用 dir はリポジトリ外。
- 測定 commit: `98b12ae7` (`serum_controller_recv.py` を追加した commit)。このコミット以降にコードは変えていない。

## 0. 結論

| 受入条件 | 判定 |
|---|---|
| 1. `call [reg+0x30/0x38/0x88]` 1052 件のうち、受信が `SerumController` のものを特定し、`0x1800c2b50`/`0x1800c6090`/`0x1800c9680` を呼ぶ箇所を全て列挙 | **未達**。候補 1052 件の列挙は本 run で再現 (件数一致)。受信型は**1 件も確定していない**。所属関数で分類した結果 (§2) は受信型の証明ではない |
| 2. Splice 経路上の呼出元の提示、または非到達の静的証明 | **未達** (1 の後段) |
| 3. patch 後 (demo bit ≡ 0) で Splice 表示が偽になる経路 | **未達** (1 の後段) |
| 4. REPORT に追記 (測定 commit と再現手順) | **達成** (本ファイル) |

本 run で得たもの: 候補 1052 件の再現、SR-33 の vtable 所属 (`SerumController`・slot 6/7/17) の再確認、受信型の**分類ツール** (`serum_controller_recv.py`)。
分類の結果、所属関数が slot 関数または vtable を構築する関数である候補は 2 件だけだった。手で確認すると、その 2 件とも受信は `this` ではなく子オブジェクト (`[rsi+0x10]` / `[rcx+0x40]`) であり、`SerumController` 呼出とは確定しない。
残り 1050 件は分類できなかった。受信レジスタの出自 (this / 子 / 別オブジェクト) を追う逆解析が要り、1 run に収まらないため子 issue に移した。

## 1. 再現手順・実測

```sh
# $S: リポジトリ外の作業用 dir。$P: 本ディレクトリ (tools/targets/serum2/gui)
cd $S
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" --wildcards '*Install_Xfer_Serum2_2.1.5.exe'
7z x -y -oexe_extract Install_Xfer_Serum2_2.1.5.exe '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3'
cp -f 'exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' Serum2_win64.vst3
uv venv -q venv --python 3.14 && uv pip install -q -p venv/bin/python pefile capstone zstandard
venv/bin/python $P/vtable_dump.py Serum2_win64.vst3 0x180a2bf58 20
venv/bin/python $P/indirect_calls.py Serum2_win64.vst3 0x180a2bf58 0x30 0x38 0x88
venv/bin/python $P/serum_controller_recv.py Serum2_win64.vst3 0x180a2bf58 6 7 17
```

- 依存: `pefile` `capstone` `zstandard`。
- 実測 (n=1, 逐次, runner 上。直前の `uptime` の load average 1 分値):
  - 展開: `tar --zstd` 2.4 s (real)。`7z x` (1 entry 抽出) は実測を省略。
  - `vtable_dump.py` (20 slot): load 0.73。
  - `indirect_calls.py` (3 disp): real 9.536 s / user 9.346 s, load 0.41。`count 1052`。
  - `serum_controller_recv.py` (3 slot): real 18.952 s / user 17.788 s, load 0.41。SR-38 の 2 回の実行とも同一出力。
- 検証: `sha256sum` は SR-30/33 と一致。`indirect_calls.py` の件数 1052 は SR-33 §2-3 の 1052 と一致。

## 2. SerumController vtable の確認と候補の分類

- vtable head `0x180a2bf58`: RTTI `.?AVSerumController@@`。slot 6 = `0x1800c2b50` (+0x30)、slot 7 = `0x1800c6090` (+0x38)、slot 17 = `0x1800c9680` (+0x88)。SR-33 §2-2 と一致。
- vtable head を rip 相対で指す `lea` は `0x1800a9fa9` (所属 `0x1800a9f40`) の 1 件。`0x1800a9f40` は `[rsi+0x0]` に vtable を書くコンストラクタ形。
- `serum_controller_recv.py` の分類 (受信型は証明しない。注意は script の docstring):

| 分類 | 定義 | 件数 |
|---|---|---|
| S | 所属関数が vtable の slot 関数 | 1 |
| K | 所属関数に vtable head への lea がある | 1 |
| U | 上記以外 | 1050 |

- S: `0x1800c2f05` (in `0x1800c2b50`) `call [rax+0x30]`。受信 `rax` は `[rsi+0x10]` (子オブジェクト) から来る。`this` ではない。
- K: `0x1800aa893` (in `0x1800a9f40`) `call [rax+0x30]`。受信 `rax` は `[rcx+0x40]` (`rcx` は `[rbp+0x138]`)。`this` ではない。
- 両者とも**受信は SerumController の this ではなく、SerumController 内の子オブジェクトの vtable 呼出**と読める。したがって、どちらも `0x1800c2b50`/`0x1800c6090`/`0x1800c9680` を指すとは確定しない。

## 3. 残る作業 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) 候補 U 1050 件の受信レジスタの出自を逆解析し、受信が SerumController (this) のものを確定する。`0x1800c2b50`/`0x1800c6090`/`0x1800c9680` の呼出元を全て列挙 | 受入 1 | 子 issue (SR-38 子) |
| (b) 上記 (a) の呼出元のうち Splice 生成 `0x180498090` 系への経路を示す、または非到達を静的に示す。`0x1800c6090` の demo bit 分岐 (`0x1800c6874` 以降) の追跡を含む | 受入 2・3 | 子 issue (SR-38 子) |
| (c) 実 VSTGUI 上の動的確認 | SR-30 受入 4 相当 | `#68` 残作業 (GUI lift 時) |
