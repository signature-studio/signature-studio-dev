# liftdiff LD-211 (#4378) — 判定不能 11 関数の this 疑似オブジェクト実行 (付録)

> 親 #3572 (LD-162) の子。前段 [`REPORT_LD158.md`](REPORT_LD158.md) §3.1 の『判定不能 (全実行が segv)』11 関数が対象。
> 測定 commit: 本 PR のコード commit (`git diff <測定 commit> HEAD` は §5)。プローブ: `tests/ld211_fvm_probe.py`。

## 1. 結論

- 11 関数のうち **6 関数** (`45e1a0` `45e280` `45e2e0` `45eb00` `45ecc0` `45ed20`) は、整数引数 1 つを this 疑似オブジェクト (`blob=vmt`) にすると native で実行できた (`ok` 全件)。
  6 件とも rax が書き換わった (入口 SENTINEL 以外)。rdx も書き換わっている。xmm0 は xfill=1 で入口 1.25 から 0 に変わったが、0 は入口 xfill=0 の値と同じで、書かれたかどうかは確定できない。戻りレジスタは rax・rdx・xmm0 のどれかで、呼出し側なしでは確定できない (LD-213 #4423 へ)。
- **5 関数** (`668390` `6683d0` `784520` `8e7e10` `a965c0`) は、this 疑似オブジェクトを 1 引数に与えても、全引数を別々の this 領域にしても segv のまま。判定不能の残件として子 issue に切り出す (§4)。
- 署名 (`targets/m11.json`) は変更していない。6 件の戻り型・戻りレジスタは未確定なので、`ret_override` は付けない。

## 2. 方法 (再現)

- `tests/ld211_fvm_probe.py`: 各関数について (a) 整数 / ptr 引数 `arg` を 1 つだけ `blob=vmt` の this にした case を `arg` ごとに、`xfill` 1 と 0 で実行、(b) 全整数引数を別の arena 領域 (`PTR_SLOTS[0]+0x40*i`) にした case を 1 件実行。
- 前提の build: `liftdiff.py build targets/m11.json` (`work/m11/`)。旧 `work/m11_ldfix/ld_wasm.cjs` は現行 `rt/ld_wasm.c` の `ld_w_snapshot(int)` と合わず wasm 側が起動しないため、使わない。
- 実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tests/ld211_fvm_probe.py` (native のみ。wasm 比較は行わない)。
- 出力: `work/ld211_probe.json` (gitignore)。
- 引数型の確認: 対象 11 関数の sig は `REPORT_LD158.md` §3.4 の関数別表で `i64` / `i64,i64` / `ptr,i64,i64` のみ。`i128` 引数は無いので、fvm case を `i64` / `ptr` に限った `main()` の選別で漏れる引数は無い。

## 3. 実測

| 関数 | 実行 ok | 書換え (rax / rdx / xmm0) | segv の fault (参考) |
|---|---|---|---|
| 45e1a0 | 3/3 | rax=0x7fffffffc1a0, rdx=0x105ba660・x0=0 (xfill=1 は入口 1.25 から変化) | — |
| 45e280 | 3/3 | rax=0, rdx=0x3000・x0=0 | — |
| 45e2e0 | 3/3 | rax=0, rdx=0x555555741600・x0=0 | — |
| 45eb00 | 3/3 | rax=0x7fffffffc1a0, rdx=2・x0=0 | — |
| 45ecc0 | 3/3 | rax=0, rdx=0x3000・x0=0 | — |
| 45ed20 | 3/3 | rax=0, rdx=0x555555741600・x0=0 | — |
| 668390 | 0/3 | — | addr 0x0 @ 0x6683b5 (this+0 の null 読み) |
| 6683d0 | 0/3 | — | addr 0x0 @ 0x6683f5 |
| 784520 | 0/5 | — | arg1 を addr 0x3 として参照 @ 0x50f625 (整数を ptr 扱い)。全 ptr 版は fault 記録なしで segv |
| 8e7e10 | 0/5 | — | addr 0x0 @ 0x8e7fbd |
| a965c0 | 0/7 | — | fault 記録なし (全 ptr 版含む) |

- `xfill` 1 と 0 で同じ結果 (6 件)。rdx が `0x2` `0x3000` などの値なのは、戻り直前に関数内で書かれた値で、戻り値とは限らない (書込み実測)。
- 全 ptr 版 (`allptr`) は 6 件で fvm 単独版と同じ rax/rdx (追加の差なし)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 6 関数の戻りレジスタ (rax・rdx・xmm0 のどれか) と戻り型。`liftdiff run` の判定 (compare) への配線も未実施 | 署名修正の対象外。呼出し側の戻り値利用の確認が要る | [LD-213] #4423 |
| 5 関数 (668390 6683d0 784520 8e7e10 a965c0) の segv。this の内部 (VMT・フィールド) の与え方が未確定 | 判定不能のまま | [LD-213] #4423 (既存) |

## 5. 検証と測定 commit

- 測定: `tests/ld211_fvm_probe.py` を本 PR のコード commit で実行 (§3 の表)。
- 差分: 測定 commit から HEAD までのコード差分 (`git diff 63c667217 <HEAD> -- tools/liftdiff`) の出力は PR 本文の「検証」節に転記する。
