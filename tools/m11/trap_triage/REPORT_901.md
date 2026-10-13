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
- 末尾で同じ slot に対して `lea rcx,[rbp+off]; call 412d60` (release, `&slot` 形) がある。
- addref と release が同じ slot で揃えば「slot の値は文字列ポインタで、対で管理されている」→ not D4。
- 順序検査 (order-check): 退避命令より前に引数レジスタ経由のメモリ参照 (旧値ロード `mov r,[arg]`) が無いこと、退避後に退避 slot を再代入する `mov qword ptr [rbp+off], …` が無いことを機械語で走査する。走査結果は `order-check:` 行に出る。
- 上記 `&slot` 形の外にある `mov rcx,[rbp+off]; call 412d60` (値そのものを release する形) は `direct-release:` 行に列挙する。これは §3 の表の判定とは別に扱う (下記)。

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

補足の確認 (すべて `judge_412d60_901.py` の出力。`order-check` 行 14 件 すべて `OK`):

- 上記 slot は退避後に再代入されない (`REWRITE` の走査で 0 件)。multi-store は 419990 の 0x278 / 664e40 の 0x58 / 72df20 の 0x30 で、いずれも退避 slot ではない。
- 退避より前に、引数レジスタを経由したメモリ参照 (`mov r,[arg]`) は無い (`PRE-LOAD` の走査で 0 件)。
- 注: この走査は命令文字列の正規表現による。負例で「退避前の参照」を捏造して検出することは確認した (`order_check(41a080, {0x20: rcx})` は空を返す = 参照が無いので正しい)。ただし検出器が実際に PRE-LOAD を拾う正例は無く、空振りの可能性は残る。この限界は §4 に書く。

### 直接 release 形の 2 件 (41a080 / 819580)

`&slot` 形ではなく、引数の値そのものを `412d60` に渡す形が 2 件ある (`judge_412d60_901.py` の `direct-release:` 行)。

- 41a080: `41a144: mov rcx,[rbp+0x28]; call 412d60` (slot 0x28 = arg2)
- 819580: `819640: mov rcx,[rbp+0x38]; call 412d60` と `81975d: mov rcx,[rbp+0x38]; call 412d60` (slot 0x38 = arg2)

これが D4 ではない理由: `412d60(p)` は `p` を「文字列ポインタを収めた slot のアドレス」として受け取り、`*p` を読んで解放し `*p` を 0 にする (機械語 `412d60`: `mov rax,[rbx]` → `mov [rbx],0`)。したがって `412d60` の引数は PPointer (slot のアドレス) であるべきで、arg2 がその PPointer である限り正しい。

- 41a080 では arg2 が PPointer であることを機械語で示せる: `41a0f2: mov rax,[rbp+0x28]; mov rdx,[rax]` (arg2 を間接参照して `[arg2]` を読む)。`41a144` の release は同じ arg2 を `412d60` に渡しており、`412d60` の `*p` 読みと一致する。
- 819580 も同様: `819734: mov rax,[rbp+0x38]; cmp qword ptr [rax],0` と `819742: mov rcx,[rax]` で arg2 を間接参照しており、`819640` / `81975d` の release は `*arg2` を解放する。
- IR (`tools/m11/work/boot_final.ll`、`work-m11.tar.zst` 展開) でも、`function_41a080` は `%0 = ptrtoint %arg2` を `412d60(%0, …)` に渡し、`function_819580` は `412d60(%arg2, …)` を呼ぶ。機械語と IR は同じ値を渡しており、IR 側で deref が落ちてはいない。
- 対照: D4 の `413060` は、旧文字列の `old := [rbx]` のロードが脱落し、`412d60` に局所 slot のアドレス (`lea`) を渡す ([REPORT_705.md](REPORT_705.md) §3)。41a080 / 819580 は局所 slot のアドレスではなく arg2 の値そのもの (PPointer) を渡しており、この点で D4 の形と異なる。

よって、直接 release 形の 2 件は表の判定 (not D4) を変えない。表は変更しない。

IR との突合は、直接 release 2 件の IR 側の確認 (上記) のみ行った。14 関数全体の IR 突合は本 REPORT では行っていない (機械語判定が根拠)。

## 4. 限界

- 判定は「addref と release の釣り合い」による。413060 のように「引数レジスタを退避せず `[rbx]` のロード結果を退避する」形は `judge_412d60_901.py` では検出しない (`no-match` を返す)。今回の 14 件は全て引数レジスタ退避の形なので、この限界は判定結果に影響しない。
- 順序検査 (order-check) は命令の文字列一致による走査。14 件で 0 件だったが、検出器が実際に PRE-LOAD / REWRITE を拾う正例は持っていない。したがって「0 件」は「その形が見つからなかった」であり、形そのものが無いことの証明ではない。
- 直接 release 形 (41a080 / 819580) の判定は、arg2 が PPointer であることを機械語の間接参照 (上記 §3) と IR の突合で示した。全 `412d60` 呼出 (994 site) を一般化して調べたわけではない。
- 残りの 413060 の OFF 実害測定は #944 ([M11-N52]) で扱う (#705 の受入条件 1)。本 REPORT の範囲外。

## 5. 再現

```sh
FL_WIN64_DIR=<fl-win64 展開先> python3 tools/m11/trap_triage/judge_412d60_901.py 413060 418f80 419990 419ed0 41a080 43bc40 664e40 667c40 72d930 72df20 72e240 786d50 818d30 819580 81ac40
```

実測 (2026-10-13 18:28 UTC, 本 run, 検証 HEAD = `a857c1fe` (本 PR の修正 commit `4df5d48c` を main `8cf483d8` と merge した後)。修正前の `fc7a2949` でも同じ出力): `FL_WIN64_DIR=<fl-win64 展開先> python3 tools/m11/trap_triage/judge_412d60_901.py 413060 418f80 419990 419ed0 41a080 43bc40 664e40 667c40 72d930 72df20 72e240 786d50 818d30 819580 81ac40` の rc=0。15 関数の判定は 15 行 (14 関数 `not D4`、413060 のみ `no-match`)。加えて `order-check` 行 14 件 すべて `OK` (413060 は退避 slot が取れないため `skipped`)、`direct-release` 行 2 件 (41a080 slot 0x28、819580 slot 0x38)。素材は `fl-win64` の `extracted/block00031_PE.bin`。elapsed=0.08s、maxrss=75200KB (`/usr/bin/time`、実行 2026-10-13 18:28 UTC, HEAD `a857c1fe`)。survey は実行していない。
