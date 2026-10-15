# MX-26 (#1946) .pdata 無し入口の区間末尾: SHORT の原因分類 (受入 1 は未達)

- 親: #1879 (MX-18) / 前提: #1625 (MX-13)・#1913 (MX-25) (いずれも CLOSED を確認)。
- 素材: `plugins-massivex` → `parse_setup_headers.py` → `extract_massivex.py <exe> work key` → `Massive X.vst3` (95,356,824 B / md5 `622993e76565f49c094063a2b717d6ca`、REPORT_MX25 と一致)。
- 測定 commit: `de9518fda` (本 commit で変えたのは `scripts/mx_tail_diag.py` と本ファイルのみ。`mx_closure.py` は変更 0)。

## 1. 結論

- 受入 1 (`mx_tail_check.py` で SHORT 0 件となる末尾方式) は**未達**。現行の分岐追跡 (`mx_tail_check.py` の `code_end`) を、真の末尾を下回らないように直す方式は、本 PR では作れなかった。
- `mx_closure.py` は変えていない。SHORT のままの末尾を採用すると閉包が過小評価になるため (REPORT_MX18 §3)。
- 受入 2 (置換前後の closure 実測) は、置換を採用しないため対象外。既定経路の再現値を §4 に書いた。
- 受入 3 (e2e PASS・negctl 3 件 FAIL<期待>) は達成 (§4)。

## 2. SHORT の原因分類 (`scripts/mx_tail_diag.py`・実測 1 回)

真の末尾が分かる `.pdata` 関数 186,960 件を、`mx_tail_check.py` と同じ `code_end` で分類した。

| 判定 | 関数数 | 備考 |
|---|--:|---|
| ok (到達末尾 ≥ 真の末尾) | 167,449 | |
| SHORT / pad (真の末尾の後ろが int3/nop/0 だけ) | 333 | 実害なし。ただし SHORT として数えられる |
| SHORT / real (後ろに実コード) | 2,037 | 下記 |
| 間接 jmp を含む | 1,107 | `mx_tail_check.py` は unresolved として返すため SHORT に入らない |
| unresolved (解読不能) | 16,034 | |

- `mx_tail_check.py` の SHORT 2,370 = pad 333 + real 2,037 と一致する (間接 jmp を含むものは SHORT に入らない)。
- real 2,037 件は、到達末尾の後ろに実コードがあるが、関数の制御フローからは届かないもの。例:
  - `0xd40d0` (真 419 B / 到達 0xd2): 到達末尾 `0xd41a2` は関数内の `ret` (0xd41a1) の直後。`0xd41a2` 以降の実コードは、関数内のどの分岐からも届かない。真の末尾 `0xd4273` までの続きは、別の断片 (cold 部など) と見られる。
  - `0xba4f0` (真 458 B / 到達 0x1c1): 到達末尾の直後は `mov` などの実コード。
- real のうち、末尾位置が `.text` 内の rel32 直接分岐 (`e8`/`e9`/`0f 8x`) の目標になっているものは 1,125 件 (バイト走査の粗い指標。データの誤検出を含みうる)。これは「別の関数・断片から飛ばれている」ことを示すが、確定ではない。

## 3. 判定

- SHORT の real 2,037 件は、真の末尾が「関数の制御フローの外にある code 断片」を含むことを示す。.pdata 無し入口の区間末尾を code 側だけで決めると、この断片を落とす (過小評価)。
- 健全な末尾には、「この断片を入口の末尾に含めるか」の判定が要る。その判定を支える情報 (jump table の範囲・文字列窓・データ窓) は MX-13 (#1625) と MX-25 (#1913) で一部揃っている (REPORT_MX25 §5.1)。断片の所属 (cold 部かデータか) を決める基準は未決で、本 PR では決めていない。
- したがって受入 1 は未達。`mx_closure.py` は既定の「次の入口まで」を維持する。
- 残りの pad 333 件は、SHORT の判定基準を「末尾の後ろが埋めだけなら ok」に緩めれば消える。ただし受入 1 の文言 (SHORT 0 件) を満たすかは PM の判断になる。

## 4. 検証 (測定 commit `de9518fda`・n=1)

- `mx_tail_check.py` (MX-18 の再現): `pdata funcs 186960 / ok 162628 / SHORT 2370 / unresolved 21962` (REPORT_MX18 §3 と一致)。
- e2e (`MX_PE=… bash dsp/e2e.sh`): rc 0 / `OK elapsed=28s` / load start `0.78 0.81 0.68` → end `0.87 0.83 0.69`。
- negctl (`MX_PE=… bash dsp/negctl.sh`): rc 0 / NC1 `insns=3118 (base 258087) unsup=5 (base 24002)` → FAIL<期待> / NC2 `insns=4575 (base 258087) unsup=292 (base 24002)` → FAIL<期待> / NC3 `insns=31 (base 258087) unsup=0 (base 24002)` → FAIL<期待>。
- `mx_tail_diag.py` の実行時間: 2m41s (load 1.00 0.86 0.69 時点)。

## 5. 未解決 (追跡先)

| 残件 | 受入 | 起票先 |
|---|---|---|
| SHORT real 2,037 件の断片を末尾に含めるかの判定基準 (code/data の決定則) | 1 | PM 判断 (本 issue の前提。子 issue は未起票) |
| pad 333 件の扱い (埋めだけの SHORT を ok とみなすか) | 1 | PM 判断 |
| 閉包の置換前後の再測定 (入口数・バイト数) | 2 | 受入 1 の方式が決まってから |
