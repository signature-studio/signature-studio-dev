# REPORT — [SR-33 #2055] Serum 2 demo bit (+0x22792) 読書関数と Splice 生成経路の結線 (静的)

- 日付: 2026-10-14 / 親: #2000 (SR-30) / 前段: `REPORT_SR30.md` §3
- 範囲: 静的解析のみ。実 VSTGUI 上の動的確認は範囲外 (SR-30 受入 4 と同じ)。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `Serum2.vst3`。sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283` / 19,236,864 B (SR-30 と一致)。作業用 dir はリポジトリ外。
- 測定 commit: 本 REPORT と `vt_callers.py` / `direct_reach.py` を追加した commit (このディレクトリのコードはこの commit で初めて追加)。

## 0. 結論

| 受入条件 | 判定 |
|---|---|
| 1. `0x1800c2b50` / `0x1800c6090` の呼出元を全て列挙し、Splice 生成経路上にあるか | **部分達成**。直接 call の呼出元は **0 件**。両関数は `SerumController` vtable (head `0x180a2bf58`) の slot 6 / slot 7 からのみ参照される。間接呼出元の全列挙は未達 (候補 1052 件、受信型の解決が必要) |
| 2. Splice 経路が無ければ、demo bit が Splice 表示の分岐に入らないことを静的に示す | **未達**。`0x1800c6090` の demo bit 読込 (`0x1800c6874`) は、Splice 生成 `0x180498090` へ direct call では届かない (深さ 4 まで)。ただし vtable 経由の経路を排除できていないため、「入らない」とは言えない |
| 3. patch 後 (demo bit ≡ 0) で Splice 表示が偽になる経路を示す | **未達**。demo bit を読む `0x1800c6090` (slot 7) と Splice 生成 `0x1800c9680` (slot 17) は同一 vtable の別 slot。両者の結線は未確認 |
| 4. REPORT に追記 | 本ファイルで達成 |

### 0-1. 前段 (REPORT_SR30) の訂正

- SR-30 §2-2 / §5 (A) は `0x180a2bfe0` (`0x1800c9680` の vtable 位置) の所属クラスを「未確定」としていた。**本 run で解決**: `0x180a2bfe0` は `SerumController` vtable (head `0x180a2bf58`, index 17)。
- 同じ head に `0x1800c2b50` (index 6)・`0x1800c6090` (index 7) も属する。SR-30 §3 が demo bit 読書関数を「SerumEditor 系」と読んでいた箇所は、本 run の RTTI では **SerumController** に当たる。
- 3 関数はいずれも `SerumController` vtable の関数であり、demo bit 関係と Splice 生成は同じオブジェクトの別メソッドとして並ぶ。

## 1. 再現手順・実測 (本 run, runner 上)

```sh
# $S: リポジトリ外の作業用 dir。$P: 本ディレクトリ
cd $S
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" --wildcards '*Install_Xfer_Serum2_2.1.5.exe'
7z x -y -oexe_extract Install_Xfer_Serum2_2.1.5.exe
cp -f 'exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' Serum2_win64.vst3
uv venv -q venv --python 3.14 && uv pip install -q -p venv/bin/python pefile capstone zstandard
venv/bin/python $P/splice_demo_bit.py Serum2_win64.vst3 0x1800c2b50 0x1800c6090 0x1800c9680 0x180498090 0x1804986d0 0x18004fad0 0x1800506b0
venv/bin/python $P/splice_chain.py Serum2_win64.vst3 0x1800c2b50 0x1800c6090 0x1800c9680 0x180498090 0x1804986d0
venv/bin/python $P/vt_callers.py Serum2_win64.vst3 0x180a2bf88 0x180a2bf90 0x180a2bfe0
venv/bin/python $P/direct_reach.py Serum2_win64.vst3 0x1800c9680 4 0x1800c2b50 0x1800c6090 0x180498090
venv/bin/python $P/direct_reach.py Serum2_win64.vst3 0x1800c2b50 3 0x1800c9680 0x180498090 0x1800c6090
```

- 依存: `pefile` `capstone` `zstandard`。
- 実測 (n=1, 逐次, runner 上。直後の `uptime` 1 分 load 0.69 (08:48)):
  - `splice_demo_bit.py` (7 関数): real 3.765 s, user 3.439 s
  - `splice_chain.py` (5 対象): real 10.313 s, user 10.112 s
  - `vt_callers.py` (3 slot): real 21.014 s, user 19.853 s
  - `direct_reach.py` (2 回): real 3.539 s / 3.568 s
- 展開: `plugins-serum2.tar.zst` (2.6 GB) の exe 抽出 2.4 s、7z 展開 6.5 s。

## 2. demo bit 参照と vtable 所属 (受入条件 1)

### 2-1. demo bit 参照 (SR-30 §3 と一致)

| 命令 | 所属関数 | 種類 |
|---|---|---|
| `0x1800c2cfe` `mov byte ptr [rsi+0x22792], al` | `0x1800c2b50` | 書込 |
| `0x1800c2d42` `mov byte ptr [rsi+0x22792], 1` | `0x1800c2b50` | 書込 |
| `0x1800c2d52` `test byte ptr [rsi+0x22792], 1` | `0x1800c2b50` | 読込 |
| `0x1800c6874` `cmp byte ptr [rsi+0x22792], 1` | `0x1800c6090` | 読込 |

### 2-2. 対象関数の所属 vtable

| 関数 | vtable 位置 (.rdata slot) | vtable head | index | RTTI | 呼出元 (direct) |
|---|---|---|---|---|---|
| `0x1800c2b50` | `0x180a2bf88` | `0x180a2bf58` | 6 (`+0x30`) | `SerumController` | **0 件** |
| `0x1800c6090` | `0x180a2bf90` | `0x180a2bf58` | 7 (`+0x38`) | `SerumController` | **0 件** |
| `0x1800c9680` | `0x180a2bfe0` | `0x180a2bf58` | 17 (`+0x88`) | `SerumController` | **0 件** |

- vtable head `0x180a2bf58` を参照する lea は `0x1800a9fa9` (所属 `0x1800a9f40`) の 1 件。コントローラ生成時の vtable 設定と読める (役割は未検証)。
- `splice_chain.py` の slot4 (`0x180ffb93c` `0x180ffc46c` `0x180ffcf38`) は偶然一致の可能性があり根拠にしない。

### 2-3. 間接呼出の候補

- `call qword ptr [reg+disp]` で `disp` が `0x30` / `0x38` / `0x88` のものは **1052 件** (`vt_callers.py`)。
- `disp` だけでは受信オブジェクトの型が決まらない。`0x1800c2b50` / `0x1800c6090` / `0x1800c9680` を指すかは、受信型の解決 (vtable 代入の追跡) なしに判定できない。ここが受入 1 の未達部分。
- 候補のうち `0x1800a0db0` (`+0x88`)・`0x1800ab4d0` (`+0x88`)・`0x180011cb0` (`+0x88`) を個別に確認。`0x1800a0db0` は direct caller `0x180099a60` (所属 `0x1800998a0`) と `0x1800a0f16` (自身の中)、`0x1800ab4d0` は `0x1800aa629` (所属 `0x1800a9f40`)。`0x1800a9f40` は `0x1800a9fa9` で `SerumController` vtable を設定する関数。**この 2 件は SerumController の内部から呼ばれる経路として次の調査対象**。

## 3. 呼出連鎖と demo bit (受入条件 2・3)

`direct_reach.py` (direct call のみ・深さ制限付き):

| 起点 | 深さ | 到達した対象 |
|---|---|---|
| `0x1800c9680` (slot 17) | 4 (75 関数) | `0x180498090` **到達 (深さ 1)**。`0x1800c2b50` / `0x1800c6090`: 未到達 |
| `0x1800c2b50` (slot 6) | 3 (163 関数) | `0x1800c9680` / `0x180498090` / `0x1800c6090`: 未到達 |

- `0x1800c9680` → `0x180498090` (Splice 生成) は direct call 1 段で確定 (SR-30 §2-2 と一致)。
- demo bit を読む `0x1800c6090` は、Splice 生成にも `0x1800c9680` にも direct call では届かない。
- **ただし** `direct_reach.py` は間接 call を辿らない。本結論は「direct call 経路に限って、demo bit 読込から Splice 生成への直接の呼出は無い」まで。vtable (`SerumController`) 経由の経路は未排除。

### 3-1. demo bit 読込の周辺 (参考)

- `0x1800c6874` の周辺 (`0x1800c6838`〜`0x1800c687b`) は、`rbp+0x70` を受け取った関数 `0x1800213c0` の戻り値バイトを入れ替えて `0x1800226b0` を呼んだ後、`cmp byte ptr [rsi+0x22792], 1` で分岐する。分岐先で `[rbp-0x40]` に 4 を書く。読込の結果が何の表示を決めるかは、分岐先の UI 処理まで辿って初めて分かる。本 run では未追跡。
- `0x1800c2d52` の読込は、`0x18000a280` の後で `[rsi+0x90]` (非 0 なら `or dword ptr [rax+8], 0x800010`) を条件にする。`0x1800c2b50` の書込値は `0x18007b280` の戻り値 (`xor al,1`) と定数 1 の 2 経路。

## 4. 結論と未解決

- 受入 1: 直接呼出元 0 件・vtable 所属は確定。間接呼出元の完全列挙は未達。
- 受入 2・3: 未達。demo bit (`0x1800c2b50` / `0x1800c6090`) と Splice 生成 (`0x1800c9680`) は同一 vtable の別 slot であり、結線は未確定。

## 5. 残る作業 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (B) `SerumController` vtable (head `0x180a2bf58`) の受信型の解決: `call [reg+0x30/0x38/0x88]` 候補 1052 件から `0x1800c2b50` / `0x1800c6090` / `0x1800c9680` を指すものを特定。`0x1800c6090` の demo bit 分岐先 (`0x1800c6874` 以降) の追跡を含む | 受入 1 (間接)・2・3 | #2102 (SR-38) |
| (D) 実 VSTGUI 上の動的確認 | SR-30 受入 4 相当 | `#68` 残作業 (GUI lift 時) |
