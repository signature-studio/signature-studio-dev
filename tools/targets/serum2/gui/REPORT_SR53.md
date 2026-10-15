# REPORT — [SR-53 #3398] getState 閉包の間接 call の受信型解決 (slot 7 → slot 17 の経路)

- 日付: 2026-10-15 / 親: #2175 (SR-44) / 前段: `REPORT_SR44.md` (測定 commit `917e48fc7`・PR #3407 merge 済み)
- 範囲: 静的解析のみ。動的な確認 (FLEngine 起動・Serum2 の GUI 実行) は範囲外。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `Serum2.vst3` (x86_64-win)。sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283` / 19,236,864 B (REPORT_SR44 と一致)。作業用 dir はリポジトリ外。
- 測定 commit: `55b77e19a` (`slot17_vptr.py --root` の追加)。本ファイルの数値はすべてこの版の出力。`git diff 55b77e19a HEAD -- tools/targets/serum2/gui/slot_reach.py tools/targets/serum2/gui/slot17_vptr.py` は差分 0 行 (main 側の gui 差分 `arg_vtable_callers.py` 100 行は本解析の実行経路に含まれない)。

## 0. 結論

| 受入条件 | 判定 |
|---|---|
| 1. 閉包内の `[reg+disp]` 126 件と `call reg` 23 件の受信型 | **部分達成**。`call reg` 23 件の生の定義元を §2 に出した。`[reg+disp]` 126 件の受信型は未解決 (一部は `+0x88` と無関係と分かった)。残りは §5 |
| 2. slot 7 → slot 17 の経路の有無 | **未確定**。slot 17 を `+0x88` で呼べる受信 vptr は、全 `.text` の rip 参照から `0x180a2bf58` の 1 つだけに絞れた (vtable head の持ち主の型は未確認)。その vptr を読んで `+0x88` を呼ぶ箇所 (`0x1800ab816`) は ctor 閉包の中にあり、slot 7 の閉包 C には 0 件。C の間接 call 149 件が ctor 閉包へ届くかは未解決 |
| 3. `slot_reach.py --disp 0x88` と `--offset` で再現 | **達成**。§1 の手順で 3 回とも同一出力 (md5 一致)。`--reg-raw` と `slot17_vptr.py` を追加 |

「経路なし」とは言わない。slot 7 の direct 閉包 C は変わらず 291 関数で、C 内の `call [reg+0x88]` は 0 件。経路が生じ得るのは、C の間接 call 149 件のうち、ctor 閉包 (547 関数) に入る呼出先を経由する場合である。

## 1. 再現手順・実測 (測定 commit `55b77e19a`)

```sh
# S: リポジトリ外の作業用 dir。P: 本ディレクトリ (tools/targets/serum2/gui)
cd $S
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" --wildcards '*Install_Xfer_Serum2_2.1.5.exe'
7z x -y -o$S/exe_extract Install_Xfer_Serum2_2.1.5.exe '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3'
cp -f 'exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' Serum2_win64.vst3
uv venv -q venv --python 3.14 && uv pip install -q -p venv/bin/python pefile capstone zstandard
A7="--target 0x1800c9680 --target 0x180498090 --target 0x1804986d0 --vtable-head 0x180a2bf58 --offset 0x227a0 --offset 0x22798 --offset 0x20408 --disp 0x88"
venv/bin/python $P/slot_reach.py Serum2_win64.vst3 0x1800c6090 $A7 > slot7.txt
venv/bin/python $P/slot_reach.py Serum2_win64.vst3 0x1800c6090 $A7 --reg-raw > slot7_raw.txt      # call reg の生の定義元
venv/bin/python $P/slot17_vptr.py Serum2_win64.vst3 0x180a2bfe0 --disp-set 0x88 --ctor 0x1800a9f40 --root 0x1800c6090 > vptr.txt
```

- 7z は `-o<dir>` (スペースなし) の形で使う。`-o <dir>` は構文エラーになる。
- 実測 (`slot_reach.py` の A7 版・n=3・逐次・nproc=4)。load は `/proc/loadavg` の 1 分値 (実行直前 → 直後):

| 実行 | real (s) | load (前 → 後) | 出力 md5 |
|---|---|---|---|
| 1 | 13.61 | 0.35 → 0.45 | `c4c99c27…` |
| 2 | 13.75 | 0.45 → 0.57 | `c4c99c27…` |
| 3 | 13.88 | 0.57 → 0.67 | `c4c99c27…` |

- `--reg-raw` 版の md5 `270deec4…`。`slot17_vptr.py` の出力 md5 `ac2ba03a…`。
- 対照: REPORT_SR44 の `slot7.txt` (md5 `c4c99c27…`) と一致。既存の出力は `--reg-raw` を付けても変わらない (`--reg-raw` は定義元の生の命令を後ろに足すだけ)。

## 2. call reg 23 件の生の定義元 (`--reg-raw`)

閉包 C 内の `call reg` の定義元を、disp を正規化しないで出した。`+0x88` の読み出しは 0 件。

| 定義元 (生) | 件数 |
|---|---|
| `call-ret` (戻り値) | 7 |
| `mov rax, [rax]` / `mov r8, [r8]` / `mov rax, [rcx]` (vptr 読み・無 disp) | 7 |
| `mov rax, [rax + 0x8]` | 1 |
| `mov rax, [rsi + 0x358]` / `[rsi + 0x350]` | 2 |
| `mov r15, [rdi + 0x17a0]` | 1 |
| `mov rax, [rsp + 0x3a0]` | 2 |
| `mov rax, [rip + 0x1689e6a]` | 1 |
| `cmove r10, rcx` | 1 |
| `sub rax, rdi` | 1 |

`mov rax, [rax]` 系は vptr を読んだ後の関数ポインタ呼出しである。vptr から `+0x88` を読む形 (`mov rax, [rax + 0x88]`) は 0 件。

## 3. slot 17 を `+0x88` で呼べる受信 vptr

| 項目 | 結果 |
|---|---|
| slot 17 の関数ポインタの格納先 (`.rdata`) | `0x180a2bfe0` の 1 箇所 (REPORT_SR44 §2) |
| `V + disp == 0x180a2bfe0` を満たし、`V` を `.text` の rip 相対で参照する候補 (disp ≤ 0x2000) | 74 件 (全 disp) |
| うち disp `0x88` | **1 件**: `V = 0x180a2bf58` (vtable head。`V[0]` は `.text` の関数ポインタ) |
| 候補 `0x180a2bf58` の参照元 | ctor `0x1800a9f40` の `lea rax, [rip+0x981fa8]` (`0x1800a9fa9`) の 1 件 |
| 閉包 C 内の `[reg+disp]` disp `{0x0, 0x8, 0x10, 0x18, 0x20, 0x50, 0x58, 0x60, 0x70, 0x78, 0xa8, 0xe8, 0x1458}` に一致する候補 | **0 件** (C の `[reg+disp]` のうち slot 17 を指し得るのは disp 0x88 だけ) |
| `0x180a2bfe0` を rip 相対で直接読む命令 | 0 件 |

前提: vptr が `.text` の rip 相対 `lea/mov` で書かれる形 (ctor) に限る。vptr を別オブジェクトからコピーする経路 (copy ctor 等) と、`.text` 外での書込みは見ていない。

したがって、受信 vptr が `0x180a2bf58` 以外のオブジェクトの `[reg+0x88]` は slot 17 を呼ばない (前提の下で)。全 `.text` の `call [reg+0x88]` は 148 件で、C 内は 0 件。

## 4. ctor `0x1800a9f40` の閉包と `+0x88` 呼出し

| 項目 | 値 |
|---|---|
| ctor `0x1800a9f40` の direct 閉包 K | 547 関数 |
| C ∩ K | 180 関数 |
| ctor 自身は C に入る | **No** |
| K 内の `call [reg+0x88]` | **1 件**: `0x1800ab816` (所属 `0x1800ab4d0`) |
| `0x1800ab4d0` は C に入る | **No** (K にだけ入る) |

`0x1800ab816` の受信は `mov rdx,[rax]` (vptr 読み)。その `rax` は `0x1800ab7db` の `call 0x1809cb89c` の戻り値。受信オブジェクトが SerumController かどうかは未確定 (call-ret を経由するため)。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) C の間接 call 149 件 (`[reg+disp]` 126 件の受信オブジェクト (disp は全て 0x88 以外)、`call reg` 23 件の受信 (定義元は §2)) が、ctor 閉包 K (または `0x1800ab4d0`) に入る関数へ届くか | 受入 2 (経路の有無)。届けば slot 7 → `0x1800ab4d0` → slot 17 の候補になる | [SR-49] (#3237)・[SR-53] (#3398) |
| (b) `0x1800ab816` の受信 (`0x1809cb89c` の戻り値) が SerumController の this か | 受入 2。SC なら `+0x88` 経由で slot 17 に届く | [SR-54] (#3399) |
| (c) vptr のコピー経路 (copy ctor 等) と `.text` 外の vptr 書込み | 受入 2 の前提 (§3) | 本 PR の未解決表 (子 issue は起票しない) |

既存の子 issue (#3237 SR-49・#3399 SR-54・#4097 SR-58・#4242 SR-63) と範囲が重なるため、新規の子 issue は起票していない。

## 6. 起動・GUI への影響 (AGENTS 規範 2)

- 静的解析のみ。FLEngine 起動・GUI の実行は**動かしていない**。製品 KPI (dispatch 数・通過 unit 数・最初のウィンドウ) の前後は測っていない。
