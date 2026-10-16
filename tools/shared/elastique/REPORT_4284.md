# tools/shared/elastique REPORT — élastique `.text` pdata 関数の RetDec lift (T-SH-110 / #4284)

既知の類型との関係: 本件の lift 結果の欠陥類型の判定は未実施 (lift 出力の意味検証は子 issue に移す)。

## 0. 結論

| 項目 | 結論 (実測) |
|---|---|
| 対象件数の定義 | `.text` 内の pdata 関数 **4,556 件**。`.pdata` の生スロット 5,475 件 (`.text` 4,556 / IPPCODE 919) を RVA で直接読んだ値。REPORT_152 §1.1・REPORT_2614 §1 と一致 |
| `tools/shared/elastique/REPORT.md` の 1,956 | `ipp_entries.py` が pefile の `DIRECTORY_ENTRY_EXCEPTION` で数えた値 (1,956 件しか返らない)。生の `.pdata` (5,475 スロット) と食い違う。pefile は `Unknown UNWIND_CODE` で 1,956 件目で打ち切る (§5)。以後の lift は生 `.pdata` の 4,556 件を正とする |
| RetDec 一括 lift | **失敗**。4,556 件を 1 回で `--select-ranges` に渡すと `[capstone2llvmir]: Should not be possible.` で落ちる |
| 1 関数ずつの lift | **4,471 件 成功 / 85 件 失敗 / 0 件 未実施** (実測・§6 で 4 件を ok に更新。CSV 4,556 行・重複 0。更新前は 4,467 / 89・§2) |
| 受入条件 1 (4,556 件の lift) | **未達**。4,471 件 lift 済み・85 件 失敗 (全て rc=1)。rc=124・137 の 4 件は §6 で lift できた (タイムアウト・メモリ起因) |
| 受入条件 2 (lift 出力の意味検証・D11/D14/D15 判定) | **未達**。本 PR では未実施 (§4) |

## 1. 対象・素材・測定 commit

- 素材: `fl-win64` の `extracted/block24357_PE.bin` (4,997,632 B) を `tools/shared/work/win/elastique_x64.dll` に複製 (gitignore)。RetDec: `toolchain-retdec` (RetDec v5.0・`retdec-decompiler --version` で確認)。
- 測定 commit (コードと CSV を変えた最後の commit): `4961b8e1e` (#5178)。`e068b5dea` (範囲表の生成と rc の記録) 以降、lift 経路の `scripts/` は変わっていない。`e068b5dea..4961b8e1e` の `data/` 差分は 2 つ: `data/entries.csv` の 166 行 (commit `7fe2ea865`・#4535 の direct_calls 修正) と `data/retdec_lift_4284.csv` の追記 (3,392 行・§2)。鮮度の確認: lift 経路 (`scripts/elastique_retdec_lift.sh`・`scripts/elastique_pdata_ranges.py`・`data/`) は `git diff --stat 4961b8e1e HEAD -- <それらのパス>` が 0 行。`scripts/elastique_fail_classify.py` だけが 69 行追加されている (`cddf68a89`・分類専用で lift 経路の外)。
- 件数の確認は `pdata_funcs` (`scripts/elastique_facts.py`) で行った: 生スロット 5,475・`.text` 内 4,556。

## 2. 再現と実測

```sh
mkdir -p "$RUNNER_TEMP/fl-win64" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64"
mkdir -p tools/shared/work/win tools/shared/work/elastique && cp "$RUNNER_TEMP/fl-win64/extracted/block24357_PE.bin" tools/shared/work/win/elastique_x64.dll
# 範囲表 (begin end の 1 行 1 関数・4,556 行)。生成は scripts/elastique_pdata_ranges.py (elastique_facts.py の pdata_funcs を使う)
python3 tools/shared/elastique/scripts/elastique_pdata_ranges.py tools/shared/work/win/elastique_x64.dll > tools/shared/work/elastique/pdata_text_ranges.txt
RETDEC=<retdec-decompiler> bash tools/shared/elastique/scripts/elastique_retdec_lift.sh tools/shared/work/win/elastique_x64.dll tools/shared/work/elastique/pdata_text_ranges.txt tools/shared/work/elastique/lift_fn 4
```

- 一括 (4,556 件を 1 回で `--select-ranges` に渡す・`--select-decode-only` あり): 1.1 秒で `[capstone2llvmir]: Should not be possible.` で失敗 (rc=1)。入力は範囲表から `SEL=$(awk '{printf "%s-%s,", $1, $2}' pdata_text_ranges.txt | sed 's/,$//')` で作った `--select-ranges "$SEL"`。
- 1 回目: 1 関数ずつ・並列 4・`timeout 60` で 540 秒 (`timeout` で打ち切り) 実行。結果行 651 件 (ok 647・fail 4)。
- 2 回目: 1 回目で結果行が無かった 3,905 件 (= 4,556 − 651 結果行) を入力とした。入力リストは保存していないため、件数は 1 回目の結果行数からの算出 (実測ではない)。420 秒 (`timeout` で打ち切り) で実行。結果行 514 件 (ok 499・fail 15)。
- 合計: 結果行 1,165 件 (`0x18002dac0` は両回で fail のため 1 件重複)。一意の 1,164 件のうち **成功 1,146・失敗 18** (`data/retdec_lift_4284.csv`)。
- CSV の 2,200 行の出所 (branch `4363-retdec-pdata-rest` 由来・#4363 の commit。`git show <SHA> -- tools/shared/elastique/data/retdec_lift_4284.csv` で確認):

| commit (author 時刻 UTC) | 内容 | 追記行 |
|---|---|---|
| `806e4f674` (2026-10-15 11:26) | 「残り 1,200 件の RetDec lift 結果を追記」 | 1,200 行 (ok 1,129・fail rc=1 71) |
| `f8d487c0c` (2026-10-15 11:26) | fail 71 行の行末空白の除去のみ (`git diff -w 806e4f674 f8d487c0c` は空) | 追加 0 行 |
| `134fa854c` (2026-10-15 11:38) | 「残り 1,000 件の RetDec lift 結果を追記」 | 1,000 行 (ok 1,000) |

  合計 2,200 行 (ok 2,129・fail rc=1 71)。既存 1,164 行 (ok 1,146・fail 18) と合わせて 3,364 行。実行条件と時間: 3 commit のメッセージと #4363 のコメントには実測時間の記録が無く、未測定。#4363 の方針は 1 関数 1 プロセス・4 並列・`timeout 60` (計画の記載)。
- 3 回目 (#5178): 未実施の 1,192 件 (= 4,556 − 3,364 行) を並列 8・`timeout 60`・`timeout 900` で実行。実測 **8 分 23 秒** (load average 6.9〜7.8・4 コア)。結果 1,192 件 全て ok。`.ll` の空ファイル 0。CSV の合計は **ok 4,467・fail 89 (rc=1 85・rc=124 1・rc=137 3)**・重複 0・未実施 0。
- 測定 commit: 本 PR の最後のコード・CSV 変更の commit。差分は `git diff <測定 commit> HEAD -- tools/shared/elastique` で確認する。
- 失敗の内訳は CSV の status (`fail rc=N`・計 89 件: rc=1 85・rc=124 1・rc=137 3) を正とする。本 PR では RetDec 本体による失敗件の再実行を行っていないため、再実行の時間・load・RSS は未計測 (§5)。
- 旧記載 (18 件の再実行 61 秒・load average 3.9〜4.1) は本 PR の HEAD では再現していない。削除した。

## 2.5 D5 (x64c 主役) との比較

`docs/DECISIONS.md` D5 は主力 lifter を x64c (`tools/flelift`・`tools/liftlib`) とし、RetDec は過去の試験的手段と位置づける。issue #4284 は本件を RetDec のまま進め、D5 との比較を本 REPORT に記録するよう指定している。

- RetDec を採る理由: 親 #3332 の受入 1 と本 issue の本文が RetDec lift を指定している (採用の根拠は issue 側の指定。x64c との比較は本件では測っていない)。
- RetDec の制約 (実測): 一括 lift は不可 (4,556 件を 1 回で渡すと 1.1 秒で `Should not be possible.`・§2)。1 関数 = 1 プロセスが必要で、1 関数あたり 60 秒の上限 (`timeout 60`)。失敗 89 件 (§0・§2)。D5 が挙げる RetDec 路線の構造欠陥 (間接 call 脱落・小さすぎる global 宣言・stack 引数脱落・証明不能な lift) は本件では未確認 (lift 出力の意味検証は子 #4363 の受入)。
- x64c 側の本件の測定: 未実施。D5 の推奨との差は、本 PR では測らない。
- 扱い: D5 の例外承認は本 PR に無い。本件の RetDec 継続は issue 指定に基づく。x64c との比較 (同じ関数の lift) は子 #4363 で行う。

## 3. 成果物

- `scripts/elastique_retdec_lift.sh`: 1 関数 = 1 プロセスの lift 駆動 (一括が落ちるため)。
- `scripts/elastique_pdata_ranges.py`: .pdata の `.text` 内の関数範囲を 1 行 1 関数で出す (4,556 行・§2)。
- `data/retdec_lift_4284.csv`: 4,556 件の `begin,status` (ok 4,467・fail 89)。fail は `fail rc=N` (rc=1 85・rc=124 1・rc=137 3)。
- lift 出力 (`.ll`) は `tools/shared/work/` (gitignore)。commit しない。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| lift 出力の意味検証 (受入 2。`.ll` 4,467 件の D11・D14・D15 判定) | 受入 2 未達。lift の正しさは未確認 | #5574 (T-SH-145 が担当。#5178 は CLOSED) |
| rc=1 85 件 (`Should not be possible.`) の lift 不能 | 受入 1 未達。完全な lift にならない。§6 で 64 件はマスク除去の診断で通るが、マスク除去は意味を変えるので修正にならない | 本 issue #5686 の残り (修正方式は未決。親 #4363 へ報告) |
| rc=1 の結果が実行ごとに揺れる (`0x1801e8d3f` `0x1801cbe40`。`0x1801cd3aa` は rc=1 のみの記録で未確定) | 同じ入力で成否が変わる。単純な決定的な失敗とは言えない | 親 #4363 へのコメント (追跡のみ) |
| pefile の `Unknown UNWIND_CODE` の原因 | pefile 側の原因は未調査 (件数の出典は確定) | 親 #4363 へのコメント (追跡のみ・子は起票しない) |

## 5. 失敗 89 件の分類・件数の出典 (履歴: #5179 時点の CSV。現在は §6 で 85 件)

再現: `python3 tools/shared/elastique/scripts/elastique_fail_classify.py tools/shared/work/win/elastique_x64.dll tools/shared/elastique/data/retdec_lift_4284.csv`
(入力 DLL は `fl-win64` の `block24357_PE.bin` を `tools/shared/work/win/elastique_x64.dll` に複製。sha256 先頭 16 桁 `8551e92209cdd2ce`)。
入力 CSV は main 取り込み後の 4,556 行 (ok 4,467・fail 89)。

| 項目 | 実測 |
|---|---|
| 件数 | 生 `.pdata` 5,475・`.text` 内 4,556・pefile 1,956 |
| fail 行の内訳 (CSV の `status`) | 計 89 件・互いに素: rc=1 85 件・rc=124 1 件 (`0x18001fb40`)・rc=137 3 件 (`0x180018fe0`・`0x180026520`・`0x18002dac0`) |
| rc=1 85 件と EVEX マスク付き命令 | 82 件に `vpshufd` / `vshufi32x4` (`{k}`) がある。3 件には無い。ok 4,467 件のうち同命令を含むものは 0 件。因果は未切り分け (capstone2llvmir の入力を絞る実験は未実施) |
| rc=124・137 の 4 件と EVEX マスク付き命令 | 4 件とも同命令は無い (スクリプトで確認)。原因は未確認 |
| 再実行の時間・load・RSS | **未計測**。本 run の環境で RetDec 本体を使った再実行は行わなかった。時間は §2 の 3 回目 (#5178) の実測のみを正とする |
| rc=137 の原因 | 未確認 (OOM と断定しない。dmesg 不可) |
| 件数の出典 | 生 `.pdata` 5,475 スロット・`.text` 内 4,556・pefile 1,956。pefile の 1,956 は生スロットの先頭 1,956 件 (file 順) の接頭辞。pefile に無い 3,519 件 = `.text` 内 2,600 件 + IPPCODE 919 件 |
| pefile が 1,956 で止まる原因 | pefile の `parse_exceptions_directory` が `Unknown UNWIND_CODE at 0x4a6038` の警告で打ち切る。以後の RUNTIME_FUNCTION は読まれない。確認 (本 run で実行): `pe = pefile.PE(dll, fast_load=True)`・`pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]])`・`pe._PE__warnings` → `['Unknown UNWIND_CODE at 0x4a6038']`、`len(pe.DIRECTORY_ENTRY_EXCEPTION)` → 1956 (pefile 2024.8.26) |

## 6. #5686: rc=124・137 の 4 件の解消と rc=1 の切り分け

測定 commit: `360197018` (lift 経路のコードと CSV を変えた最後の commit)。鮮度: `git diff 360197018 HEAD -- tools/shared/elastique/scripts/elastique_retdec_lift.sh tools/shared/elastique/scripts/elastique_pdata_ranges.py tools/shared/elastique/data` は 0 行。`scripts/elastique_mask_probe.py` だけは `TimeoutExpired` の捕捉を足す変更 (診断用・lift 経路の外。§6.2 の数値はこの変更の前の版で測った)。

### 6.1 rc=124・137 (4 件): timeout と並列メモリが原因。解消

- 単独 1 件 (60 秒上限): `0x18001fb40` rc=124、`0x180026520` rc=124 (いずれも 60 秒で打ち切り)。`0x18002dac0` は単独で rc=0 (30 秒)。
- 上限だけ延ばした単独 lift: `0x18001fb40` rc=0 (69 秒)・`0x180018fe0` rc=0 (69 秒)・`0x180026520` rc=0 (68 秒)。
- 4 並列 (`LIFT_TIMEOUT=300`): `0x18001fb40`・`0x180026520`・`0x18002dac0` が rc=137 (SIGKILL)。`0x180018fe0` は ok。
- ピークメモリ: `0x180026520` を単独 lift したとき maxrss 7,304 MiB (`getrusage` の RUSAGE_CHILDREN)。4 並列では同程度の件が同時に走ると rc=137 (SIGKILL) が出た (実測: 上の並列 4 の結果)。
- 直列 (並列 1・`LIFT_TIMEOUT=300`): `0x18001fb40`・`0x180018fe0`・`0x180026520`・`0x18002dac0` が全て rc=0 (2 回目の実行で `0x18002dac0` 1,213,510 B の `.ll` を確認)。
- 結論: 4 件は timeout と並列メモリの問題で、lift の不能ではない。CSV を `ok` に更新 (`360197018`)。`elastique_retdec_lift.sh` に `LIFT_TIMEOUT` (既定 60) を追加。

### 6.2 rc=1 (85 件): capstone2llvmir の `Should not be possible.`。マスク付き EVEX が関与、ただし実行ごとに揺れる

- 1 件の切り分け: `0x1800c2920` の関数 (1,769 命令) は 261 命令目の `vpshufd zmm1 {k6}, zmm17, 0xb1` (`62 b1 7d 4e 70 c9 b1`) で落ちる。0〜260 番目は通る。
- 診断: 対象関数内の EVEX マスク付き `vpshufd`/`vshufi32x4` (288 件) の `aaa` ビットを 0 にした診断用 DLL (`work/` 内・commit なし) では rc=0 (137,765 B の `.ll`)。
- マスク除去は命令の意味を変えるため、修正ではなく原因の切り分けに限る。
- 85 件の一括確認 (`scripts/elastique_mask_probe.py`・1 件ずつ・各 120 秒上限、時間切れは `timeout` と記録) の旧記録: 元の rc=1 のまま 64 件、マスク除去でも rc=1 が 18 件、rc=0 が 3 件。この内訳の TSV は保存しておらず、RetDec 本体が本 run の runner に無いため再確認できない。

下表は、REPORT に記録されている 3 件の rc を全て書いたもの。「未記録」は記録が無いこと。

| 件 (CSV の status は全て `fail rc=1`) | 直接 1 回目 | 直接 2 回目 | 直列の再走 |
|---|---|---|---|
| `0x1801cbe40` | rc=1 | rc=0 | 未記録 |
| `0x1801e8d3f` | rc=0 | rc=0 | rc=1 |
| `0x1801cd3aa` | rc=1 | rc=1 | 未記録 |

**分類 (3 件とも同じ基準): 「同じ入力で rc=0 と rc=1 の両方が記録されたもの」を揺れ、それ以外を未確定とする。** この基準で、揺れは `0x1801cbe40` と `0x1801e8d3f` の 2 件。`0x1801cd3aa` は記録上 rc=1 のみで、旧記録の「rc=0」とは食い違うため未確定 (probe の旧 rc=0 報告は再現できない)。

- 揺れ 2 件は決定的失敗とは言えない。
- 本 run で CSV の rc=1 85 件は `fail` のまま。揺れを含むため、rc=1 の行を ok に変えるのは測定の根拠が足りない。
- 受入 1 (4,556 件の ok) は未達。4,471 件 ok・85 件 fail。

### 6.3 検証

- 再現コマンド: `RETDEC=<retdec> LIFT_TIMEOUT=300 bash tools/shared/elastique/scripts/elastique_retdec_lift.sh tools/shared/work/win/elastique_x64.dll <ranges> <outdir> 1`。
- DLL: `fl-win64` の `block24357_PE.bin` を `tools/shared/work/win/elastique_x64.dll` に複製。sha256 先頭 16 桁 `8551e92209cdd2ce`。
- RetDec v5.0 (`toolchain-retdec`・commit `53e55b4b26e9b843787f0e06d867441e32b1604e`)。
- 負の対照: 既知 ok の `0x180001000` と `0x180001080` を同じ手順で lift し、rc=0 を確認。
- 未検証: 85 件の揺れの原因、rc=1 の 18 件の原因、RetDec 本体のバグか入力 (EVEX) の扱いか。lift 出力の意味検証 (受入 2) は未実施。
