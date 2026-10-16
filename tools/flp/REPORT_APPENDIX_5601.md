# flp #5601 (L-25): Asher Postman・Astes の WAV 未出力 — poll 関数の静的特定

親: #5244 → 本 issue。前提: #5244 (thread 0024 が `ControlOfs7A73…` を sleep なしで検索し続けることを trace で確認)・#5718 (loop `0x12d94f0` の直接呼出し元 `0xed2ac0`・`0x1004a20`)。

## 1. 受入の状況

| 受入 | 結果 | 根拠 |
|---|---|---|
| 1. WAV が出ない原因を記録する (thread 0024 の poll を含む) | **部分達成**。poll 側の候補を静的に 3 つ特定。実行時の確認は未了 (抜け条件は未特定) | §3・§4 |
| 2. 判定表に「特定 / 未特定 (理由)」を書く | 達成 (§5) | §5 |

## 2. 方法 (実行なし・静的)

- 素材: `fl-win64.tar.zst` を `tar --zstd -xf` で展開。対象は `extracted/block00031_PE.bin` (FLEngine_x64.dll・ImageBase `0x400000`)。
- 解析: `tools/flp/s10_findatom_static.py` (PE の import 表・IAT スロット・`jmp *` thunk・`call` 箇所を列挙)。逆アセンブルは `objdump -d --no-show-raw-insn`。
- 実行時の確認は未実施。wine64・gdb は本 run の runner に無く、`s1_wine_probe.sh` の組立ても行っていない。

## 3. 静的解析の結果

### 3.1 FindAtomW / GlobalFindAtomW の所在

| API | IAT スロット (VA) | thunk (`jmp *`) VA | 呼出し箇所 (VA) | 呼出し箇所を含む関数 (VA) |
|---|---|---|---|---|
| `FindAtomW` | `0x1971328` | `0x423360` | `0x817ac9` | `0x817aa0` |
| `GlobalFindAtomW` | `0x1971500` | `0x4238a0` | `0x604edd` | `0x604ea0` |
| `GlobalFindAtomW` | (同上) | (同上) | `0x60657e` | `0x606540` |

- 呼出し箇所は `call 0x423360` / `call 0x4238a0` の全件 (`objdump` 全文での grep)。FindAtomW の呼出しは 1 箇所、GlobalFindAtomW は 2 箇所 (`objdump` で `call 0x4238a0` を 2 件確認)。
- 前 run の停止報告にあった「IAT 解析が通らない」は、`s10_findatom_static.py` では通った (IAT スロットと `jmp *` thunk を PE から直接読んだ)。前 run の解析手順との差は未確認。

### 3.2 atom 名 `ControlOfs%.8X%.8X` の作成

- 書式文字列 (UTF-16LE) は VA `0x620f08` (`.text` 内)。参照は `lea 0x1aa(%rip),%rdx` (`0x620d57`) の 1 箇所。
- 作成関数は `0x620cd0`: `0x43dd60` で書式を整形し、`0x423870` で atom 化する。`0x620cd0` の呼出し元は `0x623869` (`objdump` で 1 件)。書式の VA `0x620f08` は、前 run の停止報告にあった `ControlOfs` の参照元 (RVA `0x220f08`) と一致する。
- もう一つの書式 `Delphi%.8X` (VA `0x620ee4`) も同じ関数で作られる。

### 3.3 poll 候補の上位

| 関数 (VA) | 役割 (静的な読み) | 直接の呼出し元 (`objdump` で数えた件数) |
|---|---|---|
| `0x604ea0` | `GlobalFindAtomW` を呼ぶ。`0x424f90`・`0x423450` の結果で分岐 | 15 箇所 (`0x604f2b`・`0x60516c`・`0x6060a8`・`0x6074d2`・`0x612354`・`0x61371c`・`0x844608`・`0x85c935`・`0x85d6e5`・`0x85de83`・`0x85ff04`・`0x861e75`・`0x86cbba`・`0x86cbda`・`0x121d086`) |
| `0x606540` | `GlobalFindAtomW` を呼ぶ (`0x604ea0` と同形) | 1 箇所 (`0x6065df`。関数 `0x606540` 自身の内側からの再帰呼出し。外部の呼出し元は未確認) |
| `0x817aa0` | `FindAtomW` を呼ぶ。`0x423180` で atom を登録する分岐あり | 1 箇所 (`0x81c032`・関数 `0x81be40`) |

### 3.4 前 run の観測との突き合わせ (未確定)

- thread 0024 の検索 atom は `ControlOfs7A73…` (`7A73` は `0x7A73` 形の名前)。`ControlOfs%.8X%.8X` の書式と形は一致する。
- Harmless (成功対照) で追加されていた `ControlOfs796F…` の名前は、§3.2 の書式で作られる。`796F` が追加されない場合 (Asher・Astes) に poll が抜けない、という前 run の仮説とも矛盾しない。ただし、**どの poll 関数 (`0x604ea0`・`0x606540`・`0x817aa0`) が `7A73` を poll しているかは未確定**。

## 4. 現状と未確定の点

- 静的解析で確定したのは §3.1〜§3.3 まで。実行時の命中は**未測定**。
- thread 0024 の `NtFindAtomW` を発している関数: `0x604ea0`・`0x606540`・`0x817aa0` のどれか (静的には決まらない)。
- 終了条件 (poll が `796F` の追加を待つかどうか): 未特定。

次の一手 (次 run):

1. `tools/flp/s1_wine_probe.sh` で `$RUNNER_TEMP/fl-install` を組み立てる (wine64・gdb が使える runner が必要)。
2. `tools/flp/s10_fn_probe.sh` を実行する (集計行は `hits fn604ea0=… fn817aa0=…`)。実行前に、`rax` (戻り値) と戻り先を記録する処理をこのスクリプトに入れる (現状は未実装)。`0x606540` は break を張っていないので、必要なら追加する。
3. 命中した関数について、直前の `0x424f90` の戻り値 (`cmp %eax,0x2c(%rbp)` の比較) と、Harmless・Asher で比べる。

## 5. 判定表

| 対象 | 判定 | 理由・確認した手段 |
|---|---|---|
| Asher: WAV 不出力の原因 | 未特定 (poll 候補は 3 関数まで絞った) | 静的解析 (§3)。実行時の命中は未測定 |
| Astes: WAV 不出力の原因 | 未特定 (同上) | 同上 |
| thread 0024 の poll 関数 | 候補 (`0x604ea0`・`0x606540`・`0x817aa0` の 3 つ) | 静的解析のみ。実行時の命中は未測定。thread ID で thread 0024 からの呼出しかも未確認 |
| poll の抜け条件 (Asher で止まる理由) | 未特定 | 実行時の確認が未了 (§4) |
| `ControlOfs` 名の作成 | 特定 (`0x620cd0`・書式 `0x620f08`) | 書式の参照元 1 箇所 (§3.2) |

## 6. 再現手順

```sh
mkdir -p "$RUNNER_TEMP/fl-win64" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64"
python3 tools/flp/s10_findatom_static.py   # 標準出力に §3.1・§3.2 の結果。逆アセンブルは $RUNNER_TEMP/fl31.dis
```

`call` 件数の確認 (§3.3): `grep -cE "call +0x604ea0$" "$RUNNER_TEMP/fl31.dis"` が 15。

## 7. 未確認

- 実行時の命中 (§4): 未測定。
- `0x817aa0` の所属 `0x81be40` が関数先頭かどうか: 直前が `int3` の詰め物で、先頭命令が `push %rbp`。関数先頭と見てよいが、上位の解析は未確認。
- `0x604ea0` の呼出し元 15 件の所属: 未確認 (poll の上位トリガ)。
