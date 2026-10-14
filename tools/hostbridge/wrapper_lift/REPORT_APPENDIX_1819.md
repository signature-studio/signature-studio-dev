# REPORT 付録 — #1819: batch で `0x570b30` が脱落する原因と修正

> **正本**: `tools/hostbridge/wrapper_lift/REPORT.md` §11。本付録は計測の全文 (REPORT §11 の分割移動)。

## 11. #1819: batch で `0x570b30` が脱落する原因と修正 (測定 commit: 4568c3f3)

- 結論: 原因は RetDec 側の範囲の取り扱い。直前の範囲の終端が対象の開始 VA と**ちょうど隣接**するとき、batch 出力は対象を 1 バイト手前の VA (`0x570b2f`) で `function_570b2f` と出す。定義ヘッダは `0x570b2f` 名になり、`0x570b30` の判定では `no_definition` になる。batch 内の他関数の影響ではない (隣接の有無だけで決まる)。修正は `retdec_batch.py` で定義が出なかった範囲だけを再試行する。block19091 / block23676 とも `no_definition` 0 件。
- 原因の切り分け (block19091、RetDec v5.0、`--select-decode-only`、いずれも exit 0):

| 入力範囲の組 | `0x570b30` の定義 |
|---|---|
| 単独 `0x570b30-0x570bad` | ok |
| 500 関数 batch 全体 (対象は 83 番目) | 脱落 (`0x570b2f` 名で出力) |
| batch の先頭 〜 対象 (prefix, 84 件) | 脱落 |
| 対象 〜 末尾 (suffix, 417 件) | ok |
| `0x56f5c0-0x570b30` + 対象 | 脱落 |
| `0x56f5c0-0x570aa1` + 対象 (直前範囲を短縮) | ok |
| `0x56f5c0-0x570b2f` + 対象 (直前範囲を 1 バイト短縮) | ok |
| `0x56f180-0x56f5b7` + 対象 など、隣接しない 2 件組 | ok |

- 修正 (`4568c3f3`): `lift_set` で exit 0 のとき定義が出なかった範囲を集め、全件欠落でなければ欠落範囲だけを再帰で再試行する。欠落が全件 (または単独範囲) のときだけ `no_definition` とする。分割は従来通り。再試行は範囲が必ず減るので停止する。
- 再測定 (commit `4568c3f3`、`retdec_batch.py` を両 block に 1 回ずつ実行):

| 項目 | block19091 | block23676 |
|---|---|---|
| 関数数 | 19,816 | 19,826 |
| lift_ok | 19,816 | 19,826 |
| lift_fail (`no_definition` 含む) | 0 | 0 |
| RetDec 呼び出し回数 | 41 | 41 |
| RetDec 所要 (seconds_all) | 287.67 s | 289.77 s |
| wall | 287.98 s | 290.08 s |
| load average (開始→終了) | 0.24→1.00 | 1.00→1.00 |

- 環境: `[RETDEC]` v5.0 (`toolchain-retdec`)、`fl-win64` 26.1.7.5653 の展開先。素材は `tar --zstd -xf` で展開済みを確認。
- 未実施: ネガティブコントロール (`--nc`) は本 issue の受入条件外のため未実施。
