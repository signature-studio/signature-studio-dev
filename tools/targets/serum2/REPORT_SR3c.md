# Serum 2 SR-3c: muParser 窓外 6 関数の帰属 (#867 / #71 残件)

親: `REPORT.md` §11.5 (muParser 窓の組込み関数登録側)。再現: `python3 scripts/sr3c_muparser_attr.py` (`sr3_run.sh` 実行後)。

## 1. 窓外 6 関数の実体

窓 = muParser cut 窓 0x18091ace0–0x18099a6d0 (cut 204 関数)。6 関数はいずれもこの外。

| 関数 VA | size | 参照する数学名 (`.rdata`) | 直接 call/jmp の呼び出し元 | 呼び出し元の所属 |
|---|---:|---|---|---|
| 0x1809e3240 | 275 | `acos` (0x180fdc5dc) | 0x1809e3231 | `.pdata` 外 (gap ブロック) |
| 0x1809eb7b0 | 293 | `log2` (0x180fdc880) | 0x1800bbb06・0x18088fb25 | `.pdata` 関数 (cut 外) |
| 0x1809ef030 | 306 | `sinh` (0x180fdc69c) | 0x1809ef021 | `.pdata` 外 (gap ブロック) |
| 0x1809ef7b0 | 184 | `sqrt` (0x180fdc5b0) | 十数箇所 (0x180049352・0x180081522・0x18012f9b3 ほか) | 全件 cut 外 |
| 0x180a0a3e0 | 253 | `acos` (0x180fdc5dc) ほか | 直接 call/jmp なし | 間接 or 登録テーブル経由と推定 |
| 0x180a0f3f0 | 32 | `log10` (0x180fdc890) | 0x1809eb0a1 ほか (5 箇所以上) | `.pdata` 関数 (cut 外) |

- 呼び出し元は cut 表 (muParser / 他ライブラリ) のどれにも属さない。muParser 窓の拡張 (呼出閉包) だけでは帰属しない。

## 2. 数学名表 (名前ポインタ表)

- `.rdata` 0x180fae600 付近に `(ID, 名前ポインタ)` の 16 バイト組の表がある。ID は 0x5〜0x21 の範囲 (連番ではない)。名前ポインタは `.rdata` 0x180fdc5xx〜0x180fdc8xx の文字列 (`acos`・`log2`・`log10`・`sqrt`・`sinh` 等) を指す。
- この表を `lea` で参照する関数は確認できた: 0x1809fb89c (12 参照)・0x1809f703c・0x1809f78a8・0x1809f8720・0x1809fcd9c。いずれも cut 表の外。
- 6 関数の**アドレス**は 8 バイトの絶対ポインタとしては `.rdata` に 0 件。32 ビット値では `.rdata` 0x18111dxxx・0x18111exxx・0x182107xxx 付近に現れるが、そこは (begin, end, unwind) の並びで、登録表そのものとは判断できなかった (推定)。

## 3. 結論

- **帰属は未確定**。数学名表の ID から関数を引く dispatch 側は、静的走査 (直接 call/jmp・RIP 相対 lea・絶対ポインタ) では特定できなかった。
- 6 関数が muParser の組込み関数か、Serum 側の別の数学関数かは、この結果だけでは判定できない。
- 次の手段: 動的トレース (Serum2 を実行し、数学名表の参照時点で実行中の関数を記録)。Linux runner では実行環境が未整備のため、#71 に継続。

## 4. 実測

- 測定起点: `origin/main` c063c6ba の `sr3_run.sh` (`sr3_*.py` は未変更)。
- `sr3_run.sh` 再現: 43.8 秒 (4 core, user 26.0 s)。cut 1,510 関数 / 1,464,181 B (§11.6 の基準 `699addb` と一致)。
- 素材: `plugins-serum2` (`Install_Xfer_Serum2_2.1.5.exe`) を `work/pl/` に展開 (gitignore)。
- 入力 sha256 `501e7bb3…5283` (§11 と同一)。
