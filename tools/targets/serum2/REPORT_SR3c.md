# Serum 2 SR-3c: muParser 窓外 6 関数の帰属 (#867 / #71 残件)

親: `REPORT.md` §11.5 (muParser 窓の組込み関数登録側)。再現: `bash scripts/sr3_run.sh` → `python3 scripts/sr3c_muparser_attr.py` → `python3 scripts/sr3c_chain.py` (`work/` 要・素材 `plugins-serum2` 要)。

## 0. 測定の範囲

- 測定 commit: `e3bc68c5` (コードを変えた最後の commit。`scripts/sr3c_chain.py` に 2 段目所属の出力を追加、`scripts/sr3c_muparser_attr.py` に直接呼出元の所属の出力を追加)。
- 本節以降の実測値は、測定 commit で `plugins-serum2` (`$HOME/artifacts/plugins-serum2.tar.zst`) を展開して再測定した値である (§4)。
- 測定 commit から HEAD までのコード差分の証跡は §4 末尾。

## 1. 窓外 6 関数の実体

窓 = muParser cut 窓 0x18091ace0–0x18099a6d0 (cut 204 関数)。6 関数はいずれもこの外。

6 関数はすべて `.pdata` 関数である (`out/sr3_verify.txt` の OUT 行は `.pdata` の index から出た size で、`out/sr4_funcs.tsv` でも 4 件が `pdata`)。`out/sr3_gap_blocks.tsv` に先頭を持つ行は無い。

| 関数 VA | size (`.pdata`) | 参照する数学名 (`.rdata`) | 直接 call/jmp の呼出元 (実測) | 呼出元の所属 (実測) |
|---|---:|---|---|---|
| 0x1809e3240 | 275 | `acos` (0x180fdc5dc) | 1 件: 0x1809e3231 | gap ブロック 0x1809e3220 (22 B) |
| 0x1809eb7b0 | 293 | `log2` (0x180fdc880) | 2 件: 0x1800bbb06・0x18088fb25 | 0x1800bb960 (745 B)・0x18088f9d0 (2570 B) |
| 0x1809ef030 | 306 | `sinh` (0x180fdc69c) | 1 件: 0x1809ef021 | gap ブロック 0x1809ef010 (22 B) |
| 0x1809ef7b0 | 184 | `sqrt` (0x180fdc5b0) | 59 件 (先頭 8 件の所属: 0x1800490c0 905 B ×2、0x1800812d0 1506 B ×4、0x18012f970 218 B、0x1802f62f0 1220 B) | 上記 |
| 0x180a0a3e0 | 253 | `acos` (0x180fdc5dc) ほか | 0 件 (直接 call/jmp なし) | - |
| 0x180a0f3f0 | 32 | `log10` (0x180fdc890) | 5 件 (0x1809eb0a1・0x1809eb0bf・0x1809eb331・0x1809eb35f・0x1809eb395) | すべて 0x1809eae00 (1451 B) |

- size は `out/sr3_verify.txt` (コミット済み) と一致する。
- 呼出元の所属は `scripts/sr3c_muparser_attr.py` の出力 (測定 commit)。gap ブロック内の 2 件は `out/sr3_gap_blocks.tsv` (コミット済み) とも一致 (0x1809e3231 ∈ 0x1809e3220 22 B、0x1809ef021 ∈ 0x1809ef010 22 B)。
- 所属の関数は、いずれも `out/sr3_cut_table.tsv` に無い (cut 対象外)。VA も窓 0x18091ace0–0x18099a6d0 の外。

## 2. 数学名表 (名前ポインタ表)

- `.rdata` 0x180fae640 に `(ID, 名前ポインタ)` の 16 バイト組の表がある (24 件)。`scripts/sr3c_muparser_attr.py` 出力: `exp` `pow` `log` `log10` `sinh` `cosh` `tanh` `asin` `acos` `atan` `atan2` `sqrt` `sin` `cos` `tan` `ceil` `floor` `fabs` `modf` `ldexp` `_cabs` `_hypot` `fmod` `frexp`。
- 表を指す RIP lea は **1 件** (`0x180a0ea64`、所属 `0x180a0ea50` 345 B)。この関数は表を線形探索する dispatch (ID 一致で `call 0x180a0a6a0` / `call 0x180a03b50`) である。旧 run の「lea 参照元 5 関数・12 参照」は実測で再現せず撤回する (§5 に記録のみ)。
- `.rdata` の `(begin, end, unwind)` 3 つ組 (0x18111df10/0x18111e35c/0x18111e534/0x18111f634 ほか) と `.pdata` に、窓外 6 関数の VA の int32 RVA が現れる (`scripts/sr3c_chain.py` の出力)。`.rdata` の 3 つ組は `.pdata` の複製で、dispatch 表ではない。
- 呼出経路 (`scripts/sr3c_chain.py` の出力、測定 commit):
  - dispatch `0x180a0ea50` の直接 call/jmp 呼出元は **2 件**。
    - `0x180a0e406` → 所属 `0x180a0e2f0` (378 B)。その呼出元は `0x1809e9844` → 所属 `0x1809e9790` (451 B)。
    - `0x180a0e5a4` → 所属 `0x180a0e470` (421 B)。その呼出元は 3 件: `0x1809ea5f5` → 所属 `0x1809ea550` (245 B)、`0x1809ea7b2` → 所属 `0x1809ea645` (385 B)、`0x1809ea80d` → 所属 `0x1809ea7c6` (82 B)。
- 窓外 6 関数の VA は、この経路 (3 段目まで) の出力に現れない。

## 3. 結論

- **帰属は未確定**。数学名表の ID から関数を引く dispatch 側は、静的走査 (直接 call/jmp・RIP 相対 lea) では特定できなかった。
- 6 関数が muParser の組込み関数か、Serum 側の別の数学関数かは、この結果だけでは判定できない。
- 次の手段: 動的トレース (Serum2 を実行し、数学名表の参照時点で実行中の関数を記録)。実行環境の整備が前提のため、#71 に継続。
- 静的走査は 3 段目までで止まる。間接呼出 (`call qword ptr`・vtable・関数ポインタ登録) は静的に追えないため、動的トレースが必要。

## 4. 実測 (測定 commit `e3bc68c5`)

- 素材: `plugins-serum2` を `tar --zstd -xf $HOME/artifacts/plugins-serum2.tar.zst -C $RUNNER_TEMP/serum2 --wildcards '*Install_Xfer_Serum2_2.1.5.exe'` で展開 (1.6 s)。入力 sha256 `501e7bb3…5283` (§11 と一致)。
- `sr3_run.sh`: 31.8 s (real) / user 19.0 s・4 core。cut 1,510 関数 / 1,464,181 B、lift 33,791 → 32,281 関数。`out/` の再生成結果は commit 済みと一致 (`git status` に差分なし)。
- `sr3c_muparser_attr.py`: 1.39 s (real)。`sr3c_chain.py`: 6.05 s (real)。測定時の load average 0.22 (4 core)。
- 測定 commit 以降のコード差分: 下記の証跡を参照。

### 鮮度の証跡 (WORKFLOW §6)

- 測定 commit: `e3bc68c5`。
- 測定 commit から HEAD までの `git diff e3bc68c5 HEAD -- tools/targets/serum2`: REPORT_SR3c.md のみ変更 (scripts と out/ は差分 0)。

## 5. 履歴 (旧 run の記録・参考値)

以下は前回 run の記録。§1〜§4 の実測と照合した結果を右列に示す。

| 関数 VA | 旧 run の直接呼出元 | 旧 run の所属 | 測定 commit での照合 |
|---|---|---|---|
| 0x1809eb7b0 | 0x1800bbb06・0x18088fb25 | 未記録 | 呼出元 2 件は一致 (所属 0x1800bb960・0x18088f9d0) |
| 0x1809ef7b0 | 「十数箇所」 (件数のみ・VA 未記録) | 未記録 | 59 件 (件数は一致せず。§1 の数字を採用) |
| 0x180a0a3e0 | 直接 call/jmp なし | 間接 or 登録テーブル経由と推定 | 直接 call/jmp 0 件で一致 |
| 0x180a0f3f0 | 0x1809eb0a1 ほか | 未記録 | 5 件で一致 (所属 0x1809eae00) |

- 旧 run の「窓外 6 関数の呼出元は cut 表 (muParser / 他ライブラリ) のどれにも属さない」は、測定 commit でも再確認した (§1 の所属は cut 表に無い)。
- 旧 run の「lea 参照元 5 関数・12 参照」は §2 で撤回済み。
- 旧 run の「6 関数の 8 バイト絶対ポインタは 0 件」は、現行 `sr3c_chain.py` が絶対ポインタを走査しないため、現行出力の根拠にならない。
