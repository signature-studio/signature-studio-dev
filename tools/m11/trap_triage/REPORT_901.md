# REPORT_901 — `412d60(&slot)` 同型呼びの残り 14 関数の D4 判定 (#901, 親 #705)

既知類型との関係: D4 (`docs/DEFECTS.md`)。判定の正本は機械語。

結論: 残り 14 関数は**いずれも D4 ではない** (機械語で addref/release が同 slot で釣り合う)。
受入条件 2 の「D4 と判定した site の OFF 実測」は対象 0 件のため実施不要。受入条件 1 は全 14 件で達成。

## 1. 環境

- 素材: `fl-win64` (`extracted/block00031_PE.bin`)・`work-m11` (`tools/m11/work/boot_final.ll`)。展開して使用。
- 作業 branch `901-m11-d4-remaining-14` (worktree `ws-901`、base `origin/main` = `99b87bc2`)。
- capstone / pefile は user install。

## 2. 判定基準

413060 (D4 確定) は、冒頭で `old := [rbx]` を slot に退避し、末尾で `lea rcx,[rbp+0x28]; call 412d60` で解放する。
引数そのものに対する `412f30` (addref) が無いまま `412d60(&slot)` を呼ぶのが D4 の機械語上の形。

残り 14 関数の判定規則 (`judge_412d60_901.py`):

- 冒頭で引数レジスタを `[rbp+off]` に退避し、その slot に対して `mov rcx,[rbp+off]; call 412f30` (addref) がある。
- 末尾で同じ slot に対して `lea rcx,[rbp+off]; call 412d60` (release) がある。
- addref と release が同じ slot で揃えば「slot の値は文字列ポインタで、対で管理されている」→ not D4。

## 3. 判定結果 (機械語・PE 実測)

| 関数 | 退避 slot | addref (412f30) | release (412d60) | 判定 |
|---|---|---|---|---|
| 418f80 | [rbp+0x48] (arg2) | あり | あり | not D4 |
| 419990 | [rbp+0x298] (arg2) | あり | あり | not D4 |
| 419ed0 | [rbp+0x298] (arg2) | あり | あり | not D4 |
| 41a080 | [rbp+0x70] (r8) | あり | あり | not D4 |
| 43bc40 | [rbp+0x60] (arg1) | あり | あり | not D4 |
| 664e40 | [rbp+0x78] (arg2) | あり | あり | not D4 |
| 667c40 | [rbp+0x60] (arg1) | あり | あり | not D4 |
| 72d930 | [rbp+0x80] (r8) | あり | あり | not D4 |
| 72df20 | [rbp+0x88] (r9) | あり | あり | not D4 |
| 72e240 | [rbp+0x58] (arg2) | あり | あり | not D4 |
| 786d50 | [rbp+0xc0] (rcx) | あり | あり | not D4 |
| 818d30 | [rbp+0x60] (arg1) | あり | あり | not D4 |
| 819580 | [rbp+0x80] (r8) | あり | あり | not D4 |
| 81ac40 | [rbp+0x50] (rcx) | あり | あり | not D4 |

補足の確認:

- 上記 slot は関数内で途中書き換えされていない (multi-store は 419990 の 0x278 / 664e40 の 0x58 / 72df20 の 0x30 で、いずれも退避 slot ではない)。
- 冒頭の退避より前に、引数レジスタを経由した旧値ロード (`mov r,[arg]`) は無い (`PRE-LOAD-OF-ARG` の走査で 0 件)。
- IR (`tools/m11/work/boot_final.ll`) との突合は本 REPORT では行っていない (機械語判定のみが根拠)。

## 4. 限界

- 判定は「addref と release の釣り合い」による。413060 のように「引数レジスタを退避せず `[rbx]` のロード結果を退避する」形は `judge_412d60_901.py` では検出しない (`no-match` を返す)。今回の 14 件は全て引数レジスタ退避の形なので、この限界は判定結果に影響しない。
- 残りの 413060 の OFF 実害測定は #944 ([M11-N52]) で扱う (#705 の受入条件 1)。本 REPORT の範囲外。

## 5. 再現

```sh
FL_WIN64_DIR=<fl-win64 展開先> python3 tools/m11/trap_triage/judge_412d60_901.py 413060 418f80 419990 419ed0 41a080 43bc40 664e40 667c40 72d930 72df20 72e240 786d50 818d30 819580 81ac40
```

実測 (2026-10-13, 本 run, HEAD = 本 PR のコミット): 判定 15 関数の出力は `judge901` 実行で 15 行。14 関数 すべて `not D4`、413060 のみ `no-match` (§4 の限界どおり)。elapsed=0.12s、maxrss=75036KB (`/usr/bin/time`)。survey は実行していない。
