# flp #5601 (L-25): Asher Postman・Astes の WAV 未出力 — poll 関数の静的特定

親: #5244 → 本 issue。前提: #5244 (thread 0024 が `ControlOfs7A73…` を sleep なしで検索し続けることを trace で確認)・#5718 (loop `0x12d94f0` の直接呼出し元 `0xed2ac0`・`0x1004a20`)。

## 1. 受入の状況

| 受入 | 結果 | 根拠 |
|---|---|---|
| 1. WAV が出ない原因を記録する (thread 0024 の poll を含む) | **部分達成**。poll 側の関数を静的に 3 つ特定。実行時の確認は未了 | §3・§4 |
| 2. 判定表に「特定 / 未特定 (理由)」を書く | 達成 (§5) | §5 |

## 2. 方法 (実行なし・静的)

- 素材: `fl-win64.tar.zst` を `tar --zstd -xf` で展開 (real 6.4 s)。対象は `extracted/block00031_PE.bin` (FLEngine_x64.dll・ImageBase `0x400000`)。
- 解析: `tools/flp/s10_findatom_static.py` (PE の import 表・IAT スロット・`jmp *` thunk・`call` 箇所を列挙)。逆アセンブルは `objdump -d --no-show-raw-insn`。
- 実行時の確認は未実施。wine64 9.0・gdb 15.1・xvfb-run を apt で導入し、`kernel.yama.ptrace_scope=0` に設定したが、インストール木 (`s1_wine_probe.sh`・GUI 起動 2 分超) の組立てが本 run の時間内に間に合わなかった。

## 3. 静的解析の結果

### 3.1 FindAtomW / GlobalFindAtomW の所在

| API | IAT スロット (VA) | thunk (`jmp *`) VA | 呼出し箇所 (VA) | 呼出し箇所を含む関数 (VA) |
|---|---|---|---|---|
| `FindAtomW` | `0x1971328` | `0x423360` | `0x817ac9` | `0x817aa0` |
| `GlobalFindAtomW` | `0x1971500` | `0x4238a0` | `0x604edd` | `0x604ea0` |
| `GlobalFindAtomW` | (同上) | (同上) | `0x60657e` | `0x606540` |

- 呼出し箇所は `call 0x423360` / `call 0x4238a0` の全件 (`objdump` 全文での grep)。FindAtomW の呼出しは 1 箇所、GlobalFindAtomW は 2 箇所。
- 前 run の停止報告にあった「IAT 解析が通らない」は、本 run の `s10_findatom_static.py` では通った (IAT スロットと `jmp *` thunk を PE から直接読んだ)。前 run の解析手順との差は未確認。

### 3.2 atom 名 `ControlOfs%.8X%.8X` の作成

- 書式文字列 (UTF-16LE) は VA `0x620f08` (`.text` 内)。参照は `lea 0x1aa(%rip),%rdx` (`0x620d57`) の 1 箇所。
- 作成関数は `0x620cd0`: `0x43dd60` で書式を整形し、`0x423870` で atom 化する。`0x620cd0` の呼出し元は `0x623869`。書式の VA `0x620f08` は、前 run の停止報告にあった `ControlOfs` の参照元 (RVA `0x220f08`) と一致する。
- もう一つの書式 `Delphi%.8X` (VA `0x620ee4`) も同じ関数で作られる。

### 3.3 poll 候補の上位

| 関数 (VA) | 役割 (静的な読み) | 直接の呼出し元 |
|---|---|---|
| `0x604ea0` | `GlobalFindAtomW` を呼ぶ。`0x424f90`・`0x423450` の結果で分岐 | 14 箇所 (例: `0x604f2b`・`0x60516c`・`0x6060a8`・`0x6074d2`・`0x612354`・`0x61371c`・`0x844608`・`0x85c935`・`0x85d6e5`・`0x85de83`・`0x85ff04`・`0x861e75`・`0x86cbba`・`0x86cbda`・`0x121d086`) |
| `0x606540` | `GlobalFindAtomW` を呼ぶ (`0x604ea0` と同形) | 1 箇所 (`0x6065df`。関数 `0x606540` 自身の内側からの再帰呼出し。外部の呼出し元は未確認) |
| `0x817aa0` | `FindAtomW` を呼ぶ。`0x423180` で atom を登録する分岐あり | 1 箇所 (`0x81c032`・関数 `0x81be40`) |

### 3.4 前 run の観測との突き合わせ (未確定)

- thread 0024 の検索 atom は `ControlOfs7A73…` (`7A73` は `0x7A73` 形の名前)。`ControlOfs%.8X%.8X` の書式と形は一致する。
- Harmless (成功対照) で追加されていた `ControlOfs796F…` の名前は、§3.2 の書式で作られる。`796F` が追加されない場合 (Asher・Astes) に poll が抜けない、という前 run の仮説とも矛盾しない。ただし、**どの poll 関数 (`0x604ea0`・`0x606540`・`0x817aa0`) が `7A73` を poll しているかは未確定**。

## 4. 未確定の点 (実行で確かめる)

- thread 0024 の `NtFindAtomW` を発している関数: `0x604ea0`・`0x606540`・`0x817aa0` のどれか (静的には決まらない)。
- 終了条件: 上の関数が `796F` の追加を待つかどうか。

次の一手 (次 run):

1. `$RUNNER_TEMP/fl-install` を作る (`tools/flp/s1_wine_probe.sh` の組立て部分まで)。
2. FL64.exe 起動後に gdb で `0x604ea0`・`0x606540`・`0x817aa0` の entry に break を張り、命中の有無と戻り先を記録する (s8 の方式。VA は実行時 base で読み替える)。
3. 命中した関数について、直前の `0x424f90` の戻り値 (`cmp %eax,0x2c(%rbp)` の比較) と、Harmless・Asher で比べる。

## 4.1 実行時の測定 (wine64 9.0・gdb 15.1・ptrace_scope=0)

- 組立て: `tools/flp/s1_wine_probe.sh` で `$RUNNER_TEMP/fl-install` を作成 (real 2 m 10 s・GUI 継続で rc=124)。
- 起動時 (GUI のみ・`tools/flp/s10_fn_probe.sh` 90 s): `0x604ea0` の entry 約 40,000 回・`0x817aa0` 0 回。戻り先 `0x7a9374d7` (RVA `0x6074d7`) が大半。
- Asher (`s2_render_probe.sh`・150 s・rc=124・WAV なし。gdb は実行中の `/R` プロセス PID 7302 に attach・60 s): `0x604ea0` 22,867 回・`0x817aa0` 0 回。戻り先の分布は起動時とほぼ同じ (`0x6074d7` 系が 20,302 件)。
- Harmless (同じ `/R` 起動・gdb 60 s): `0x604ea0` 8,727 回・`0x817aa0` 0 回。戻り先の分布は Asher とほぼ同じ (`0x6074d7` 系が 5,210 件)。
- 返り値の比較 (`0x604ea0` の戻り先で `rax` を記録・gdb 25 s each):
  - Harmless: enter 7,641・ret 5,171 (`rax=0` 4,737 件・非 0 434 件)
  - Asher: enter 7,373・ret 5,092 (`rax=0` 4,705 件・非 0 387 件)
- 判定: poll 関数は両者で同じ `0x604ea0` (呼出し元 `0x6074b0` のループ経由)。返り値の 0 / 非 0 の比は両者で近く、**この比較では抜け条件の差を見つけられなかった**。前 run の観測 (Harmless は `796F` の追加あり・Asher はなし) との関係は未確認。`796F` を作る `0x620cd0` の呼出し元を実行時に見る必要がある。
- 注意: 測定はどれも gdb の時間切れ (`timeout`) で終わる。件数は attach した時間の窓に依存し、Asher と Harmless の件数比は意味を持たない。

## 5. 判定表

| 対象 | 判定 | 理由・確認した手段 |
|---|---|---|
| Asher: WAV 不出力の原因 | 未特定 (poll 候補は 3 関数まで絞った) | 静的解析 (§3)。実行時の命中は未確認 |
| Astes: WAV 不出力の原因 | 未特定 (同上) | 同上 |
| thread 0024 の poll 関数 | 特定 (`0x604ea0` が Asher・Harmless の両方で回る。`0x817aa0` は 0 回) | 実行時の entry 命中 (§4.1)。`0x606540` は未確認 |
| poll の抜け条件 (Asher で止まる理由) | 未特定 | `0x604ea0` の返り値は両者で同分布 (§4.1)。抜け条件は別の関数にある |
| `ControlOfs` 名の作成 | 特定 (`0x620cd0`・書式 `0x620f08`) | 書式の参照元 1 箇所 (§3.2) |

## 6. 再現手順

```sh
mkdir -p "$RUNNER_TEMP/fl-win64" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64"
python3 tools/flp/s10_findatom_static.py   # 標準出力に §3.1・§3.2 の結果。逆アセンブルは $RUNNER_TEMP/fl31.dis
```

## 7. 未確認

- 実行時の命中 (§4): 未確認。
- `0x817aa0` の呼出し元 `0x81be40` の上位: 未確認。
- `0x604ea0` の呼出し元 14 件の所属: 未確認 (poll の上位トリガ)。
