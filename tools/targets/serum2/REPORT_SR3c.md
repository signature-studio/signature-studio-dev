# Serum 2 SR-3c: muParser 窓外 6 関数の帰属 (#867 / #71 残件)

親: `REPORT.md` §11.5 (muParser 窓の組込み関数登録側)。再現: `bash scripts/sr3_run.sh` → `python3 scripts/sr3c_muparser_attr.py` → `python3 scripts/sr3c_chain.py` (`work/` 要・素材 `plugins-serum2` 要)。

## 0. 測定の範囲

- 本節以降の実測値は、作成 commit `4fd267b3` の作業時に `plugins-serum2` を展開して得た値である (§4)。
- 修正 commit (本 run) では素材 `plugins-serum2` が無く、`work/` も無いため、スクリプトの再実行はしていない。
- 本 run で再確認できたのは、コミット済みの `out/sr3_verify.txt` と `out/sr3_gap_blocks.tsv` の該当行のみ。

## 1. 窓外 6 関数の実体

窓 = muParser cut 窓 0x18091ace0–0x18099a6d0 (cut 204 関数)。6 関数はいずれもこの外。

6 関数はすべて `.pdata` 関数である (`out/sr3_verify.txt` の OUT 行は `.pdata` の index から出た size で、`out/sr4_funcs.tsv` でも 4 件が `pdata`)。`out/sr3_gap_blocks.tsv` に先頭を持つ行は無い。

| 関数 VA | size (`.pdata`) | 参照する数学名 (`.rdata`) | 直接 call/jmp の呼出元 (確認済み) | 呼出元の所属 |
|---|---:|---|---|---|
| 0x1809e3240 | 275 | `acos` (0x180fdc5dc) | 0x1809e3231 | gap ブロック 0x1809e3220 (22 B) |
| 0x1809eb7b0 | 293 | `log2` (0x180fdc880) | 未確定 | 未確定 |
| 0x1809ef030 | 306 | `sinh` (0x180fdc69c) | 0x1809ef021 | gap ブロック 0x1809ef010 (22 B) |
| 0x1809ef7b0 | 184 | `sqrt` (0x180fdc5b0) | 未確定 | 未確定 |
| 0x180a0a3e0 | 253 | `acos` (0x180fdc5dc) ほか | 未確定 | 未確定 |
| 0x180a0f3f0 | 32 | `log10` (0x180fdc890) | 未確定 | 未確定 |

- size は `out/sr3_verify.txt` (コミット済み) と一致する。
- 呼出元 2 件 (0x1809e3231・0x1809ef021) の所属は `out/sr3_gap_blocks.tsv` (コミット済み) で確認した。
- 他の 4 関数の呼出元は、本 run では未確定。旧 run の記録は §5 に分けて残す (未再検証)。

## 2. 数学名表 (名前ポインタ表)

- `.rdata` 0x180fae640 に `(ID, 名前ポインタ)` の 16 バイト組の表がある (旧 run の 0x180fae600 付近の記述は、この表の範囲を指す)。
- `scripts/sr3c_muparser_attr.py` 出力 (作成時): name table `rva 0x180fae640` 24 件 (`exp` `pow` `log` `log10` `sinh` `cosh` `tanh` `asin` `acos` `atan` `atan2` `sqrt` `sin` `cos` `tan` `ceil` `floor` `fabs` `modf` `ldexp` `_cabs` `_hypot` `fmod` `frexp`)。
- 表を指す RIP lea は **1 件** (`0x180a0ea64`、所属 `0x180a0ea50` 345 B)。この関数は表を線形探索する dispatch (ID 一致で `call 0x180a0a6a0` / `call 0x180a03b50`) である。旧 run の「lea 参照元 5 関数・12 参照」は作成時の出力では再現しなかったため撤回する (§5 に記録のみ)。
- `.rdata` の `(begin, end, unwind)` 3 つ組 (0x18111df10/0x18111e35c/0x18111e534/0x18111f634 ほか) と `.pdata` に、窓外 6 関数の VA の int32 RVA が現れる (`scripts/sr3c_chain.py` の出力)。`.rdata` の 3 つ組は `.pdata` の複製で、dispatch 表ではない。
- 呼出経路 (`scripts/sr3c_chain.py`、作成時の出力): dispatch `0x180a0ea50` の直接 call/jmp 呼出元は **2 件** (`0x180a0e406` 所属 `0x180a0e2f0` 378 B、`0x180a0e5a4` 所属 `0x180a0e470` 421 B)。さらに 2 段目の呼出元は `0x1809e9844` (所属 `0x1809e9790` 451 B)、`0x1809ea5f5`・`0x1809ea7b2`・`0x1809ea80d`。所属 VA は本出力では未確認。
- 窓外 6 関数の VA は、この経路 (3 段目まで) の出力に現れない。

## 3. 結論

- **帰属は未確定**。数学名表の ID から関数を引く dispatch 側は、静的走査 (直接 call/jmp・RIP 相対 lea) では特定できなかった。
- 6 関数が muParser の組込み関数か、Serum 側の別の数学関数かは、この結果だけでは判定できない。
- 次の手段: 動的トレース (Serum2 を実行し、数学名表の参照時点で実行中の関数を記録)。実行環境の整備が前提のため、#71 に継続。
- 静的走査は 3 段目までで止まる。間接呼出 (`call qword ptr`・vtable・関数ポインタ登録) は静的に追えないため、動的トレースが必要。

## 4. 実測 (作成 commit `4fd267b3` 時点の記録・本 run では未再現)

- 素材: `plugins-serum2` を `tar --zstd -xf $HOME/artifacts/plugins-serum2.tar.zst --wildcards '*Install_Xfer_Serum2_2.1.5.exe'` で `$RUNNER_TEMP/serum2` に展開 (1.7 s)。入力 sha256 `501e7bb3…5283` (§11 と一致)。
- `sr3_run.sh` (作成時): 42.7 s (real) / user 24.6 s・4 core。cut 1,510 関数 / 1,464,181 B、lift 33,791 → 32,281 関数。§11.6 の基準と一致。
- `sr3c_muparser_attr.py` (作成時): 2.0 s。`sr3c_chain.py` (作成時): 10.0 s。初回実行は `lea` の VA/RVA 取り違えで 0 件となったため修正し、修正後の出力を §2・§3 に載せた。
- 作成 commit での変更: `scripts/sr3c_chain.py` の追加。`out/` の生成物は変更なし。

## 5. 履歴 (旧 run の記録・本 run では未再検証のため参考値)

以下は前回 run の記録で、現在の測定値ではない。§1〜§4 と照合していない。

| 関数 VA | 旧 run の直接呼出元 | 旧 run の所属 |
|---|---|---|
| 0x1809eb7b0 | 0x1800bbb06・0x18088fb25 | 未記録 |
| 0x1809ef7b0 | 「十数箇所」 (件数のみ・VA 未記録) | 未記録 |
| 0x180a0a3e0 | 直接 call/jmp なし | 間接 or 登録テーブル経由と推定 |
| 0x180a0f3f0 | 0x1809eb0a1 ほか | 未記録 |

- 旧 run の「窓外 6 関数の呼出元は cut 表 (muParser / 他ライブラリ) のどれにも属さない。muParser 窓の拡張 (呼出閉包) だけでは帰属しない」は、旧 run の記録。本 run では再確認していない。
- 旧 run の「lea 参照元 5 関数・12 参照」は §2 で撤回済み。
- 旧 run の「6 関数の 8 バイト絶対ポインタは 0 件」は、現行 `sr3c_chain.py` が絶対ポインタを走査しないため、現行出力の根拠にならない。
