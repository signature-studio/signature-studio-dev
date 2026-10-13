# Serum 2 SR-3c: muParser 窓外 6 関数の帰属 (#867 / #71 残件)

親: `REPORT.md` §11.5 (muParser 窓の組込み関数登録側)。再現: `python3 scripts/sr3c_muparser_attr.py` (`sr3_run.sh` 実行後・`work/` 要)。

## 1. 窓外 6 関数の実体

窓 = muParser cut 窓 0x18091ace0–0x18099a6d0 (cut 204 関数)。6 関数はいずれもこの外。

6 関数はすべて `.pdata` 関数である (`out/sr3_verify.txt` の OUT 行は `.pdata` の index から出た size で、`out/sr4_funcs.tsv` でも 4 件が `pdata`)。`out/sr3_gap_blocks.tsv` に先頭を持つ行は無い。

| 関数 VA | size (`.pdata`) | 参照する数学名 (`.rdata`) | 直接 call/jmp の呼び出し元 | 呼び出し元の所属 |
|---|---:|---|---|---|
| 0x1809e3240 | 275 | `acos` (0x180fdc5dc) | 0x1809e3231 | gap ブロック 0x1809e3220 (22 B) |
| 0x1809eb7b0 | 293 | `log2` (0x180fdc880) | 0x1800bbb06・0x18088fb25 (旧表・未再確認) | 未再確認 |
| 0x1809ef030 | 306 | `sinh` (0x180fdc69c) | 0x1809ef021 | gap ブロック 0x1809ef010 (22 B) |
| 0x1809ef7b0 | 184 | `sqrt` (0x180fdc5b0) | 十数箇所 (旧表・未再確認) | 未再確認 |
| 0x180a0a3e0 | 253 | `acos` (0x180fdc5dc) ほか | 直接 call/jmp なし (旧表) | 間接 or 登録テーブル経由と推定 |
| 0x180a0f3f0 | 32 | `log10` (0x180fdc890) | 0x1809eb0a1 ほか (旧表・未再確認) | 未再確認 |

- 「未再確認」の列は、前回 run の記録 (旧表) で、本 run では `work/` が無く再実行できていない。
- 6 関数の size は `out/sr3_verify.txt` (コミット済み) と一致する。
- 呼び出し元の所属のうち gap ブロック内の 2 件は、コミット済みの `out/sr3_gap_blocks.tsv` で確認した (0x1809e3231 ∈ 0x1809e3220 22 B、0x1809ef021 ∈ 0x1809ef010 22 B)。
- 呼び出し元は cut 表 (muParser / 他ライブラリ) のどれにも属さない。muParser 窓の拡張 (呼出閉包) だけでは帰属しない。

## 2. 数学名表 (名前ポインタ表)

- 旧 run の記述: `.rdata` 0x180fae600 付近に `(ID, 名前ポインタ)` の 16 バイト組の表がある。
- 本 run (2026-10-13, `plugins-serum2` 展開, `sr3_run.sh` 後) の `scripts/sr3c_muparser_attr.py` 出力: name table `rva 0x180fae640` 24 件 (`exp` `pow` `log` `log10` `sinh` `cosh` `tanh` `asin` `acos` `atan` `atan2` `sqrt` `sin` `cos` `tan` `ceil` `floor` `fabs` `modf` `ldexp` `_cabs` `_hypot` `fmod` `frexp`)。
- 表を指す RIP lea は **1 件** (`0x180a0ea64`、所属 `0x180a0ea50` 345 B)。この関数は表を線形探索する dispatch (ID 一致で `call 0x180a0a6a0` / `call 0x180a03b50`) である。旧 run の「lea 参照元 5 関数・12 参照」は本 run の出力では再現しなかったため撤回する。
- 窓外 6 関数の int32 RVA 出現 (`scripts/sr3c_chain.py`): 各関数の VA は `.rdata` の 3 つ組 `(begin, end, unwind)` 表 (0x18111df10/0x18111e35c/0x18111e534/0x18111f634 ほか、各 2 回) と `.pdata` にだけ現れる。`.rdata` の 3 つ組は `.pdata` の複製で、dispatch 表ではない。
- 6 関数の 8 バイト絶対ポインタは 0 件 (旧 run と同じ)。
- 呼び出し経路 (`scripts/sr3c_chain.py`): dispatch `0x180a0ea50` の直接 call/jmp 呼出元は **2 件** (`0x180a0e406` 所属 `0x180a0e2f0` 378 B、`0x180a0e5a4` 所属 `0x180a0e470` 421 B)。さらに呼出元は `0x1809e9844` (所属 `0x1809e9790` 451 B)、`0x1809ea5f5`・`0x1809ea7b2`・`0x1809ea80d` (muParser 窓外側の別関数)。ここで直接 call/jmp の経路が止まる。窓外 6 関数はこの経路上に現れない。

## 3. 結論

- **帰属は未確定**。数学名表の ID から関数を引く dispatch 側は、静的走査 (直接 call/jmp・RIP 相対 lea・絶対ポインタ) では特定できなかった。
- 6 関数が muParser の組込み関数か、Serum 側の別の数学関数かは、この結果だけでは判定できない。
- 次の手段: 動的トレース (Serum2 を実行し、数学名表の参照時点で実行中の関数を記録)。Linux runner では実行環境が未整備のため、#71 に継続。

## 4. 実測

- 素材: `plugins-serum2` を `tar --zstd -xf $HOME/artifacts/plugins-serum2.tar.zst --wildcards '*Install_Xfer_Serum2_2.1.5.exe'` で `$RUNNER_TEMP/serum2` に展開 (1.7 s)。入力 sha256 `501e7bb3…5283` (§11 と一致)。
- `sr3_run.sh` 実測 (本 run): 42.7 s (real) / user 24.6 s・4 core。cut 1,510 関数 / 1,464,181 B、lift 33,791 → 32,281 関数。§11.6 の基準と一致。
- `sr3c_muparser_attr.py` 実測: 2.0 s。`sr3c_chain.py` 実測: 10.0 s (初回実行は `lea` の VA/RVA 取り違えで 0 件となったため修正し、修正後の出力を §2・§3 に載せた)。
- 本 run の変更: `scripts/sr3c_chain.py` を追加 (§2・§3 の出力を再現する)。`out/` の生成物は変更なし。
- 未了: 窓外 6 関数の帰属は、dispatch の呼出元を 2 段 (dispatch → 呼出元 → その呼出元) まで確認したが、6 関数には届かなかった。3 段目以降は未走査。静的な直接 call/jmp・RIP lea・絶対ポインタ・RVA 表では特定不可。間接呼出 (`call qword ptr`・vtable・関数ポインタ登録) の追跡は静的では不完全なため、動的トレース (数学名表 dispatch の実行中に呼ばれる関数の記録) が必要。#71 継続。
