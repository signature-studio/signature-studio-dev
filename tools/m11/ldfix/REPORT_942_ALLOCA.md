# REPORT_942_ALLOCA — 通常 boot の unit 17 trap の書込み元 (alloca 縮退) の特定と、alloca 修正の A/B (#942 受入 2・1)

既知類型との関係: alloca 縮退 (RetDec が Delphi のローカル record を `alloca i64` に潰す)。`tools/m11/alloca/m11_alloca.py` (R8 escape gap・CAB-129 / #132) が既に扱う類型で、新規類型の判定はしない。DEFECTS.md は変更しない。

## 0. 結論

- 通常 boot (`run_stage4.mjs`) の unit 17 (VA 0x55790) の `memory access out of bounds` は、**既存の lift 欠陥 (alloca 縮退) が原因**。ldfix (F3a/F3c) の修復とは無関係。
  - 機構: `function_44bb70` の 392 B record (`stack_var_-416`・入口で `rep stosq` 0 初期化) の中の slot `0x10aa10b8` が、`function_44bae0` の `stack_var_-88` (`alloca i64` = 8 B) を callee `function_44ba50` が越えて書く `GetCPInfo` (20 B・`arg1+44` から) に壊される。書込み後の値は `0x100000000`。その slot を `_UStrAsg` (`function_4133f0`) が旧値として読み、`-8` で trap する。
  - 根拠 1 (書込み元の特定): 観測フック (下記 §2) で、slot の値は `44ba50` 入口 = 0 → `call GetCPInfo` の直後 = `0x100000000` と変わった。
  - 根拠 2 (因果): `function_44bae0` の `stack_var_-88` **だけ**を `[11 x i64]` に拡幅すると、unit 17 の OOB は消える (§3 の only44bae0)。
- 本番の build (`m11_build.sh`) は `alloca/m11_alloca.py` を既に通す。この issue が使う snapshot `work/boot_final3.ll` (qstore・alloca 前) には適用されていないため、ldfix_e2e の base/fix は両方とも unit 17 で止まる。
- alloca pass 全適用 (2377 alloca) では、通常 boot は unit 0x16fde0 (survey の unit 56 と同じ trap 箇所・IR `function_8c6530`) まで進む (units_run 17 → 52)。unit 17 の trap は消える。
- ldfix の修復件数 (F3a 2 / F3c) は boot の結果を変えない (base = fix)。受入 3 は変更なし。

## 1. 測定 (HEAD `10fc87e9`・測定 commit。コード差分は新規の診断スクリプトのみ)

- e2e: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/ldfix_e2e.sh` → **57.6 秒・rc 0・judge PASS**・終了後 load 0.92 / 0.54 / 0.36。stage4 units 17/942・icall 24・threw `memory access out of bounds` (base = fix)。survey ok 136 / trap 9 (base = fix)。修復件数 F3a 2 / F3c 43 / F1 0 / F2 0 / F3b 0。
  - F3c は本 HEAD で 43 (`REPORT_942_QSTORE.md` の 33 = `c98d2c99` と不一致)。原因未調査 (main の変更による変化と推定するが、未確認。受入 3 の件)。
- A/B: `bash tools/m11/ldfix/alloca_ab_942.sh` (HEAD `10fc87e9`) → **41.0 秒** (全 variant の出力を取得)。

| variant | IR | stage4 units_run / init | icall_ok | threw | dllmain_done | survey ok / miss / trap |
|---|---|---|---|---|---|---|
| raw | snapshot `boot_final3.ll` | 17 / 18 | 24 | OOB | False | 136 / 14 / 9 |
| alloca | raw + `m11_alloca.py` (2377 alloca) | 52 / 54 | 234 | OOB | False | 868 / 47 / 26 |
| only44bae0 | raw の `function_44bae0` `stack_var_-88` だけ `[11 x i64]` | 17 / 18 | 24 | なし | True (下記 注) | 136 / 14 / 9 |

- 注 (only44bae0): `dllmain_done=True` は正常完走ではない。unit 17 の後で `MessageBoxA('Runtime error 0 at 0000000010251740')` が出て `Halt0` → longjmp で抜ける (`M11_TRACE=1` の trace で確認)。unit 17 の OOB は消えたが、Delphi runtime error で止まる別の経路に入る。その VA の意味は未確認。
- alloca 版の survey の先頭 trap unit (unit 番号順): `0x16fde0`・`0x19f9a0`・`0x223840`・`0x25c540`・`0x264260`・... (unit 0x55790・0x158e20・0x243270・0x0 が先頭から消える)。
- survey の分類 (`survey_stage4.mjs`): `m11_call_unit` の戻り値 r = 1 → ok、r = 2 → miss、r = 0 → noproc (proc 無し)、例外 → trap。表は ok / miss / trap だけを出し、noproc は出力していない。
- 件数の内訳 (noproc は導出値。出力していない):

| 区分 | raw | alloca | 差 (alloca − raw) |
|---|--:|--:|--:|
| ok (r=1) | 136 | 868 | +732 |
| miss (r=2) | 14 | 47 | +33 |
| trap (例外) | 9 | 26 | +17 |
| noproc (r=0・導出) | 783 (= 942 − 159) | 1 (= 942 − 941) | −782 |
| 合計 | 942 | 942 | 0 |

- 注 (survey の母数の訂正): 「base の 783 件は `m11_call_unit` が -1 を返す (テーブル範囲外)」は誤り。-1 を返すのは `i >= D(tbl)` のときだけ (`tools/m11/m11_ov.c`)。D(tbl)=942 は raw 変種の stage4 出力 (17/942) で確認した。alloca 変種の D(tbl) は表に出力していない (未確認)。0〜941 では -1 は返らないので、raw の 783 件は noproc (r=0)。alloca 版の残り 1 件も noproc と読めるが、noproc を出力していないため**実測では未確認** (次 run で出力する)。「942 件すべてが 0/1/2 に分類される」は取り下げる。
- 注 (proc の null 分布): noproc の件数は変種間で大きく違う (raw 783・alloca 1)。これは proc の null 分布が変種で変わっていることを示す。proc 欄は実行時 (boot か survey の先行 unit) に書かれる可能性がある (未確認)。
- 注 (trap 9 → 26・+17 の内訳は**未特定**): per-unit の raw ok/miss/noproc の記録が無いため、増分 +17 が「noproc から新たに trap になった unit」か「既存の ok/miss unit の回帰」かを切り分けられない。VA 一覧も食い違う: 上の「先頭 trap unit」列挙は `0x19f9a0` (unit 87) を含むが、`REPORT_942_APPENDIX.md` の main build の base 26 件には `0x19f9a0` が無い。alloca 版の trap VA 一覧は本測定で保存していないため、どちらが正かは未確認。survey の ok 136→868 は母数の差を含むため、件数の改善とは断定できない。

## 2. 書込み元の特定 (観測フック)

方法: `watch_ir_942.py` が snapshot IR に観測フックを入れる (`m11_wh(id, addr)` = `watch_shim_942.c`。stdio・malloc を使わず、固定アドレス `0x11FFF000` のリングに `(id, *addr の 8B)` を記録する)。`watch_slot_942.mjs` が通常 boot 後にリングを読む。`WATCH_ADDR=0x10aa10b8` (unit 17 の trap の `UStrAsg dest`、`M11_TRACE=1` の trace で得た値) を監視した。

| hook id | 位置 | 0x10aa10b8 の値 |
|---|---|---|
| 190 | `function_44bb70` 入口 | `0x10ab000000000002` |
| 180 | `function_44bae0` 入口 (`44bb70` の先頭で `rep stosq` 392 B を 0 化した後) | `0x0` |
| 300 | `function_44ba50` 入口 | `0x0` |
| 301 | `call GetCPInfo` の直後 (`44ba50` 内) | **`0x100000000`** |
| 302 | `44ba50` の `ret` 直前 | `0x100000000` |
| 201 | `44bb70` の最初の call (44bae0) の直後 | `0x100000000` |

- 変化は hook 300 と 301 の間に 1 回。書込み元は `GetCPInfo` (`tools/m11/m11_win.c`: `memset(b,0,20)`・`*(unsigned*)b=1`・`b[4]='?'`)。
- 対応する IR: `function_44bae0` の `%stack_var_-88 = alloca i64` (8 B) を `function_44ba50` が `arg1+44` から `GetCPInfo` に渡す。20 B の書込みは `alloca` の外に出る。
- 注: フック版の最初の試行 (stdio 版) は malloc で配置を変え、値の推移が一致しなかった。リング版で、フック無しの trace の trap (unit 17・`dest=0x10aa10b8`・`old=0x100000000`) と一致することを確認した。

## 3. 因果の切り分け

- only44bae0 (`stack_var_-88` だけ拡幅): unit 17 の OOB が消える (units_run 17 のまま、dllmain_done=True の Runtime error 経路へ)。
- alloca 全適用: unit 17 を越えて、units_run 52、trap は unit 0x16fde0 (`function_8c6530` の `i32.store`・OOB)。`REPORT_942_TRAPSITE.md` §2 の unit 56 (引き金は未確定) と同じ trap 位置。
- 両者から、unit 17 の原因は `function_44bae0` の alloca 縮退で確定する。他の alloca 縮退は unit 17 以降の trap に効いている可能性がある (未切り分け)。

## 4. 受入への反映

- 受入 1 (trap 9 件の原因): **部分**。unit 0x55790 (17) は起点確定 (観測フック・§2)。unit 0x158e20 (53)・0x243270 (138)・0x0 (158) は alloca 全適用で先頭の trap から消えるが、起点は未確定 (他の alloca 縮退の寄与は未切り分け)。unit 0x16fde0 (56)・0x25c540 (144)・0x264260 (149) は alloca 版でも trap のままとの記録があるが、per-unit の保存が無く未確認。unit 0x19f9a0 (87) の残存は §1 の注のとおり未確定。残 trap の引き金は未確定 (次 run)。
- 受入 2 (boot threw の原因): **部分**。unit 17 の原因 (既存の alloca 縮退 44bae0 `stack_var_-88`。ldfix 起因ではない・raw IR に既存) は確定。alloca 全適用でも boot は unit 0x16fde0 で threw (`memory access out of bounds`) するため、boot threw の原因としては未了。
- 受入 3 (件数反映): 変更なし。F3c 33 → 43 は原因未調査 (§1)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| alloca 適用後の boot trap (unit 0x16fde0・`function_8c6530` の `i32.store` の引き金) | 受入 2・1 | #942 (次 run) |
| only44bae0 の Runtime error 0 (`0x10251740`) の意味。`dllmain_done=True` を正常完走と見なさない判定が必要 | 測定の判定 | #942 (次 run) |
| survey の noproc (r=0) 件数と VA の未出力 (raw 783 件・alloca 1 件)。alloca 変種の D(tbl) の未出力。trap 9 → 26 の内訳 (noproc 由来か既存 unit の回帰か) と unit 87 (0x19f9a0) の残存の食い違い | 測定の母数・受入 1 | #942 (次 run) |
| ldfix_e2e の入力 (snapshot = qstore・alloca 前) を本番順 (alloca → ldfix → qstore) にするか | 測定の基準 | PM agent の判断待ち (既定案: 現行 (alloca 前) を維持) |
| F3c 33 → 43 の変化の原因 (原因未調査。main の変更は推定) | 受入 3 | #942 (次 run) |
| work-m11 の IR と現 main の不一致 | 測定の母体 | #942 (次 run) |

## 6. 差分 (`docs/WORKFLOW.md` §6)

- 測定 commit: `10fc87e9` (診断スクリプトを追加した commit。e2e・A/B の実行経路 (`ldfix_e2e.sh`・`stage4.sh`・`survey_stage4.mjs`・`run_stage4.mjs`・`m11_alloca.py`) は変更していない)。
- 差分 (e2e 経路・A/B 経路): `git diff 10fc87e9 HEAD -- tools/m11/ldfix/ldfix_e2e.sh tools/m11/ldfix/stage4.sh tools/m11/ldfix/survey_stage4.mjs tools/m11/ldfix/run_stage4.mjs tools/m11/alloca tools/m11/m11_ov.c | wc -l` → 0。測定 commit 以降の commit は docs のみ (`f2a58679` = 本 REPORT の新規作成・DOC_MAP 登録、`dd5806e78` = 本 REPORT の訂正、round 2 の訂正 commit = 本 REPORT と PR 本文)。
- main 側: `git diff 8303a813 origin/main -- (同範囲) | wc -l` → 0 (`origin/main` = `a5966bbc7` で確認。round 2 の訂正時点で 0)。

## 7. 再現

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP   # 素材展開後
bash tools/m11/ldfix/ldfix_e2e.sh                               # canonical e2e (base/fix)
bash tools/m11/ldfix/alloca_ab_942.sh                           # raw / alloca / only44bae0 の stage4 と survey
# 書込み元の観測 (WATCH_ADDR の値は M11_TRACE=1 の UStrAsg dest で得る)
mkdir -p tools/m11/ldfix/work/watch942 tools/m11/ldfix/work/stage4/watch942/obj
python3 tools/m11/ldfix/watch_ir_942.py tools/m11/work/boot_final3.ll tools/m11/ldfix/work/watch942/boot_watch.ll
emcc -c tools/m11/ldfix/watch_shim_942.c -o tools/m11/ldfix/work/stage4/watch942/obj/shim_wh942.o -O0 -g1   # shim_*.o は genstubs の除外に入る
bash tools/m11/ldfix/stage4.sh tools/m11/ldfix/work/watch942/boot_watch.ll watch942
S4_NAME=watch942 S4_IMAGE=tools/m11/work/m11_image.bin WATCH_ADDR=0x10aa10b8 node tools/m11/ldfix/watch_slot_942.mjs
```
