# REPORT_1274 — ClassCreate ON の ok 退行 unit 190 の trap 経路 (#1274, 親 #912)

結論 (部分達成): unit 190 の ON の oob は、**現 main では `function_412e40` ではなく `function_407a50` で起きる**。REPORT_912 §3 の記録 (`412e40`) は、現 main では再現しない。trap の経路 (`6cf480 → 6cf2a0 → 6ced90 → 409410 → 407a50`) は実測できた。原因の特定・既存類型への分類・ON の ok 退行 0 は未達 (下記 §4 の起票先)。

既知類型との関係: 該当なし (未切り分け。原因特定は #1274 次 run で `407a50` の lift 内容を確認して判定)。

## 1. 測定条件

- 測定 commit: `851c342e` (origin/main、`Merge pull request #1466 from signature-studio/1275-m11-n78`)。本 PR の `tools/m11` のコード差分 (probe 1 行) は §5b・§6 を参照。
- 素材: `fl-win64` を展開して `FL_WIN64_DIR` に指定 (展開先は `[WIN64]`)。`work-m11` を repo ルートに展開。`toolchain-retdec` を `RETDEC_ROOT` に指定 (`[RETDEC]`)、`toolchain-emsdk` を `EMSDK` に指定 (`[EMSDK]`)。
- IR: `m11_gen_ir2.sh` rc=0 (44.9 s、`ldfix=applied`、F1=902、errors=0)。
- build: `M11_OV_CLASSCREATE=1 m11_build.sh` rc=0 (24.7 s、signature mismatch 0・undefined symbol 0)。OFF (`M11_OV_CLASSCREATE=0`) も rc=0。
- survey: `SV_RAW=1 node survey_units.mjs` (ON 12.2 s、OFF 12.8 s、いずれも load は低い)。

注: 最初の試行では `FL_WIN64_DIR` を `…/extracted/..` の形で指定したため、IR の PE パスと現 PE が一致せず build が `exit 1` で拒否された (`m11_build.sh` の PE 指紋検査が働いた)。`FL_WIN64_DIR` を fl-win64 の正しい展開先 (`[WIN64]`) に指定して IR を作り直して解消した。

## 2. 結果 (ON と OFF の unit 単位比較、942 unit)

| 構成 | ok | oob | abort | halt0 | miss | noproc | other |
|---|--:|--:|--:|--:|--:|--:|--:|
| ON (`M11_OV_CLASSCREATE=1`) | 869 | 15 | 2 | 7 | 47 | 1 | 1 |
| OFF (既定) | 870 | 16 | 0 | 7 | 47 | 1 | 1 |

kind が変わった unit (OFF → ON):

- 190: ok → oob (ok 退行。本 issue の対象)
- 304: oob → abort、555: oob → abort (`function_535c2e` の IR 未定義。#1275 の対象)

## 3. unit 190 の trap 経路 (ON・current main)

`SV_RAW=1 SV_ONLY=190` の生 frame (wasm の関数 index と命令 offset) を `oob_insn.py` で逆引きした。

| 順 | wasm fn (export 名) | offset | 命令 |
|--:|---|---|---|
| 1 | 1873 `function_407a50__lifted` | 0x13ce5c | `i64.load offset=0` (`[ptr-8]` 相当、`ptr = wrap(arg-8)`) |
| 2 | 1871 `function_407a50` | 0x13c7ce | `call 1873` |
| 3 | 1901 `function_409410__lifted` | 0x140eba | `call 1871` |
| 4 | 316 `function_409410` | 0x80ce8 | `call 1901` |
| 5 | 4473 `function_6ced90` | 0x21d263 | (呼出し元。`6ced90` は定数 `1028` を `409410` に渡す: `%m11sf2830 = trunc i64 1028`) |
| 6 | 4479 `function_6cf2a0` | 0x21dc9f | `call 6ced90` |
| 7 | 4482 `function_6cf480` | 0x21df06 | `call 6cf2a0` |
| 8 | 11520 `m11_tr_function_6cf480` | 0x346573 | (trampoline) |

- `410360` (0x41037d の `ICALL` 呼出し) は、この trap の frame に**現れない**。ON で差し替えた `410360` は経由していない。
- 生 frame が示すのは「trap 直前の関数は `407a50`」だけで、`407a50` に渡る引数の**実値は未測定** (probe 未挿入)。

## 4. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `407a50` の `i64.load [arg-8]` が見る実 pointer 値と、ON でその参照先の内容が変わる経路 (ON-only override の書込みか、`6ced90` の定数 1028 側か) | 原因の特定 (受入条件 1) が未達 | #1274 (本 issue、次 run) |
| 既存 DEFECTS 類型への分類 (受入条件 2) | 未達。`407a50` の lift 内容の確認が前提 | #1274 (本 issue、次 run) |
| ON の ok 退行 0 (受入条件 3) | unit 190 の 1 件が残る | #1274 (本 issue、次 run) |
| REPORT_912 §3 の `function_412e40` 記録と、現 main の `function_407a50` の差 | 記録の食い違い。どちらの IR/commit で起きたかは未切り分け | #912 (親 issue へ申し送り) |

## 5. 再測定 (次 run、測定 commit `8483b900` = origin/main `Merge #1631`)

- IR: `m11_gen_ir2.sh` rc=0 (44.5 s、ldfix=applied、F1=902、errors=0)。素材は `FL_WIN64_DIR` (`[WIN64]`)、`RETDEC_ROOT` (`[RETDEC]`) で指定。
- build: `M11_OV_CLASSCREATE=1` rc=0 (25.7 s、signature mismatch 0・undefined 0)、`=0` rc=0。
- survey: `SV_RAW=1 node trap_triage/survey_units.mjs` (ON 12.5 s、OFF。load 0.6 以下)。
  - ON: `ok 869 / oob 15 / abort 2 / halt0 7 / miss 47 / noproc 1 / other 1`
  - OFF: `ok 870 / oob 16 / halt0 7 / miss 47 / noproc 1 / other 1`
  - `survey_diff.py` (OFF → ON): ok 退行 unit は **190 の 1 件** (ok → oob)。304・555 は oob → abort (#1275)。
- unit 190 の生 frame (`SV_ONLY=190 SV_RAW=1`、ON) は §3 と同じ経路 (`407a50` → `409410` → `6ced90` → `6cf2a0` → `6cf480`) を示す。前回 PR #1490 の結果と一致。
- 注: 全 unit の通常 survey で unit 190 の `frames` 欄の先頭は `function_412e40` を示す。`SV_ONLY` の単独実行 (生 frame) と全体実行で最内フレームが違う。どちらが REPORT_912 §3 の `412e40` に対応するかは未切り分け (#912 へ申し送り)。
- 静的確認: `407a50` (`@function_407a50`) は `arg < 2601` で `(arg+7)/8` の表 (`18770492` 基点) を引く枝と、それ以外の枝を持つ連結リスト操作。`409410(1028)` は `sext(1028)` を渡す (1028 < 2601 なので表引き枝)。
- 未実施: `407a50` 入口の実 pointer 値の計測 (probe 機構が `m11_post.py` / `m11_ov.c` に無く、新設が必要)。受入条件 1 の未達はこのため。起票先は #1642 (親 #1274)。
  - 訂正 (次節 §5b): 既存の `trap_triage/probe_entry.py` で `407a50` の入口値は採れる。新設は不要だった。

## 5b. 407a50 入口の probe 実測 (測定 commit `1e3ee7af` = origin/main)

- 素材: fl-win64 (`[WIN64]`)・toolchain-retdec (`[RETDEC]`)・toolchain-emsdk (`[EMSDK]`)・work-m11 を展開 (`tools/m11/work/` 配下)。IR `m11_gen_ir2.sh` rc=0 (45.2 s、ldfix=applied、F1=902、errors=0)。build ON rc=0 (25.0 s)。
- コード差分: 測定時は `probe_entry.py` の 1 行修正 (`(?:__lifted)?`) を作業ツリーに入れて実行した。測定 commit `1e3ee7af` から本 PR の HEAD までのコード差分はその 1 行のみで、その行は測定で実際に実行されたコード。`git diff 1e3ee7af HEAD -- tools/m11 ':(exclude)*.md'` の出力 (md を除外するのは、この REPORT 自身の更新で出力が変わらないようにするため):

```diff
diff --git a/tools/m11/trap_triage/probe_entry.py b/tools/m11/trap_triage/probe_entry.py
index 39480f0a..5a9c1929 100644
--- a/tools/m11/trap_triage/probe_entry.py
+++ b/tools/m11/trap_triage/probe_entry.py
@@ -18,7 +18,7 @@ n = 0
 if fns == ['all']:
     fns = sorted(set(re.findall(r'^define [^\n@]*@function_([0-9a-f]+)\(', src, re.M)))
 for f in fns:
-    pat = re.compile(r'(^define [^\n@]*@function_%s\(([^)]*)\)[^\n]*\{\n[^\n]*:[^\n]*\n)' % f, re.M)
+    pat = re.compile(r'(^define [^\n@]*@function_%s(?:__lifted)?\(([^)]*)\)[^\n]*\{\n[^\n]*:[^\n]*\n)' % f, re.M)
     m = pat.search(src)
     if not m: print('no define for', f, file=sys.stderr); continue
     args = re.findall(r'(i64|ptr|i32) (?:nonnull )?(%arg\d+)', m.group(2))
```

- probe: `probe_entry.py` の正規表現を `function_<hex>(?:__lifted)?(` に変更 (`407a50` は lift 本体が `function_407a50__lifted`。変更前は `no define` で 0 件)。probe は読み取りのみ。
- 単独 unit 190 (ON・OFF とも): `407a50` 入口 1 回、`arg1` = `0x404` (= 1028、`6ced90` の定数と一致)。単独実行は前 unit の状態を持たないため ON/OFF で差は出ない。
- 全 unit (942) の probe 版 survey: ON `ok 866 / oob 20`、OFF `ok 871 / oob 15`。probe 無しの §5 (ON 869/15、OFF 870/16) とは一致しない。**probe 版 build は通常 build と結果が一致しない** (`[pe]` 挿入自体が挙動を変える)。以下の入口列は probe 版の結果。
- unit 190 の `407a50` 入口 `arg1` 列 (先頭 6 件):

| 順 | ON | OFF |
|--:|--:|--:|
| 1〜6 | 0x404, 0x28, 0x16, 0x22, 0x88, 0x88 | 同左 (一致) |
| 7 | (trap まで無し) | 0x88 |
| 8〜17 | (無し) | 0x88, 0x3e, 0x40, 0x32, 0x16, 0x20, 0x28, 0x28, 0x20, 0x18, 0x44 |

- 読み取り: 先頭 6 件は ON と OFF で一致する。ON は 6 件目の後で trap し (§3 の生 frame 先頭が `407a50`)、OFF は同じ `0x88` の入口をさらに続けて 17 件まで進む。**入口の引数は同じで、参照先の状態が ON と OFF で違うと推定される (未確認)**。入口の引数が同じことまでしか確認していない。
- 未確定: `[arg-8]` の読み先の値は取れていない (probe の `q()` は image 外候補 (`0x10000` 未満) を読まず `dead` を出す)。ON の差がこの読み先に当たるかは未確定。
- ON-only override (`m11_ov.c` の `410360`→`9b4b00`) は `[rbx+0x54]`・`[rbx+0x34]`・`9b5450` のフィールド 0 クリアを書く。`407a50` の参照先との重なりは未照合。
- 次の確認 (#1642): (a) 6 件目 `0x88` の入口で `407a50` 内の load アドレスを採る (`q()` の範囲拡大、または load 直前の値の dump)、(b) `PROBE_WATCH` で ON-only の書込みが (a) の参照先に当たるかを切り分ける。
- 既知類型: 該当なし (未判定)。`407a50` は spin (`__asm_pause`・`Sleep`) を含み、類型判定は (a)(b) の後。

## 5c. 407a50 入口の参照先の実測 (次 run の受入条件 1 の途中結果)

- 測定 commit: `8cd50a1d` (base は origin/main `984ff34f`)。下表の値はこの commit の probe の結果で、**撤回済み** (下記の訂正を参照)。素材は fl-win64 (`[WIN64]`)・toolchain-retdec (`[RETDEC]`)・toolchain-emsdk (`[EMSDK]`)・work-m11 を展開。IR `m11_gen_ir2.sh` rc=0 (35.8 s、ldfix=applied、F1=902、errors=0)、build ON rc=0 (18.3 s)。
- probe: `probe_entry.py` の `407a50` 入口に読み取り専用の 2 行を追加 (`[raw407]`: `[arg-8]` の値、`[chain407]`: `arg1 < 2601` の表引き (`18770492 + (arg+7)/8`) から `rbx` (`16404744 + 16*b`) → `[rbx+8]` → `[[rbx+8]+24]` の chain)。`rd64`/`rd8` は image 範囲 (`0x10000`〜`0x20000000`) のみ読み、範囲外は `0xdead` を返す。
- 訂正 (レビュー指摘 1): 旧 `[raw407]` 行は上限 `0x1500000` だけを判定し、下限 `0x10000` の判定が無かった。そのため `arg1-8` が image 範囲外 (表の入口 1〜6 では 0x3fc・0x20・0xe・0x1a・0x80) でも低位アドレスを直接 deref していた。表の `[arg-8]` 値 (`0`・`0x10bd4e00`・`0x10bd4da00000`・`0x4e000000000010bd` 等) はこの範囲外読みを含むため、文書 (範囲外は `0xdead`) と一致しない。`[raw407]` は `rd64(p)` に直した (修正は commit `470cb820`)。修正後の値は未測定。
- 撤回: 下表の `[arg-8]` 列は採らない。`[chain407]` 列は `arg1 < 2601` の枝でだけ `rd8`/`rd64` を使うが、旧 probe の値を根拠にした ON/OFF の差 (入口 5 以降の `m`) も確定扱いしない。
- 未実施 (本 run): 修正 probe での ON/OFF 再測定。`toolchain-retdec` / `toolchain-emsdk` / `work-m11` が本 run の `$ARTIFACTS_DIR` に無く、PR 本文にも `oc_artifacts:` 行が無いため (`docs/WORKFLOW.md` §11)。再測定には `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk work-m11` を本文に書いて再起動が要る。
- ON・OFF とも全 942 unit の probe 版 survey (`SV_ERR_LOG` で unit 番号付きの全 stderr を採取)。unit 190 の `407a50` 入口を順に並べた:

| 順 | 入口 arg1 | `[raw407]` の `[arg-8]` | `[chain407]` (ON / OFF) |
|--:|--:|--:|---|
| 1 | 0x404 | 0 | 同じ (`m=1`) |
| 2 | 0x28 | 0x10bd4e00 | 同じ (`m=10bd4e90`) |
| 3 | 0x16 | 0x10bd4da00000 | 同じ (`m=10be5240`) |
| 4 | 0x22 | 0x4e000000000010bd | 同じ (`m=10bd4ec0`) |
| 5 | 0x88 | 0 | **ON `m=10bbe510` / OFF `m=10bbe5a0`** (差 0x90) |
| 6 | 0x88 | 0 | ON `m=10bbe510` / OFF `m=10bbe5a0` (5 と同じ差が残る) |

- 読み取り: 入口 1〜4 は ON/OFF で完全一致する。差は 4 件目の後、5 件目 (0x88) の入口で初めて出る。ON の `m` は OFF より 1 ノード (0x90) 手前を指す。OFF は 17 件まで入口が続き、ON は 6 件目の後で trap する。
- 入口 6 件目の時点で、ON の list 参照は 1 ノード分ずれている。ON-only override (`m11_ov.c` の `410360`→`9b4b00`) がこのリストの 1 ノード分の進みを変えた、と読めるが、書込元は未特定。
- 書込元の特定 (`PROBE_WATCH=fa5310:18`、`--watch` の `[chg]`) は未完了。watch 版の survey では unit 190 区間に `[chg]` が 0 件 (unit 15〜891 の別 unit では多数出る)。watch 版は `m11_pw` を入れるため、`[pe]`/`[chain407]` の build と挙動が違う。この 2 つの build を同一条件で比べていない。
- 未確定: ON で 1 ノードずれる書込元、既存 DEFECTS 類型への分類 (受入条件 2)、ON の ok 退行 0 (受入条件 3・4)。いずれも次 run の作業 (起票先 #1642)。
- 注意: probe を入れた build は通常 build と結果が一致しない (§5b の 866/20 対 869/15 と同じ理由)。§5c の値は probe 版の結果。

## 5d. ON-only 差分の切り分け (測定 commit `60932d35` = origin/main `Merge #1766`)

- 素材: fl-win64・toolchain-retdec・toolchain-emsdk・work-m11 を展開。IR `m11_gen_ir2.sh` rc=0 (50.7 s、ldfix=applied、F1=902、errors=0)。build ON・OFF rc=0。
- 基準 (`SV_RAW=1`、全 942 unit、probe 無し): OFF `ok 870 / oob 16` (13.2 s)、ON `ok 869 / oob 15 / abort 2` (12.2 s)。§5 と一致。unit 190 は ON で `oob` (全体 survey の `frames` 先頭は `function_412e40`)。
- 切り分け (ON build を変えて全 unit survey。いずれも unit 190 は ON と同じ `oob`):

| 変更 | 結果 (ok / oob) | 読み |
|---|---|---|
| `9b4b00` の書込みを 1 文ずつ外す (8 通り) | 869 / 15 (全 8 通り同一) | 単独では効かない |
| `9b4b00` の書込みを全部外す (mask=255) | 869 / 15 | 本体の書込みは原因ではない |
| `41c130`・`9b4b00` の table 差し替えを外す (`M11_NO_TBL`) | 869 / 15 | table 差し替えは原因ではない |
| `M11_OV_413060=1`・`M11_OV_CLASSCREATE=0` | 870 / 16 (OFF と同一) | `413060` の override 単独では ok 退行は出ない |
| `410360` の `m11_vcall` 経路を外す | 未測定 (build 失敗) | マクロ `M11_NO_TBL` を使う行 (863 行目) が定義 (889 行目) より前にあり、コンパイル不可 |

- 結論 (部分): ON の ok 退行は `9b4b00` の書込み・41c130/9b4b00 の table 差し替え・`413060` の単独 override では説明できない。残る候補は `410360` の vcall 経路 (`m11_vcall` → `ICALL_AT`) で、次 run で定義順を直して測る。
- 測定に使った一時変更 (`M11_9B_SKIP`・`M11_NO_TBL` の define) は本 PR に含めない (`m11_ov.c` は commit 前に `git restore` で戻した)。
- 注記: 本 run は REPORT の追記のみのコード差分 0 のため、再測定の commit 指定は §5 のまま。

## 5e. 修正 probe の ON/OFF 再測定 (#1642・測定 commit `91655f69`、tools/m11 の code は `4c2f69d1` と同一)

- 素材: fl-win64 (`[WIN64]`)・toolchain-retdec (`[RETDEC]`)・toolchain-emsdk (`[EMSDK]`)・work-m11 を展開。IR `m11_gen_ir2.sh` rc=0 (F1=902、errors=0)。build `M11_OV_CLASSCREATE=1`・`=0` とも rc=0 (signature mismatch 0・undefined 0)。
- probe: `probe_entry.sh <tag> 407a50` (修正済み `[raw407]`: `rd64` 版。範囲外は `0xdead`)。ON・OFF とも全 942 unit の probe 版 survey。
  - ON: `ok 869 / oob 14 / halt0 10 / miss 47 / other 1 / noproc 1`
  - OFF: `ok 870 / oob 13 / halt0 10 / miss 47 / other 1 / noproc 1`
  - probe 版は通常 build と結果が一致しない (§5b と同じ)。
- unit 190 の `407a50` 入口 `arg1` (ON・OFF 共通): 0x404, 0x28, 0x16, 0x22, 0x88, 0x88 (ON はここで trap)。OFF はさらに 0x88, 0x3e, 0x40, 0x32, 0x16, 0x20, 0x28, 0x28, 0x20, 0x18, 0x44 と続く。
- `[chain407]` の `m` (入口 5 件目 0x88): ON `0x10bbe510`、OFF `0x10bbe5a0` (差 0x90)。入口 1〜4 は ON/OFF で一致。
- `[raw407]` の `[arg-8]` 値は全入口で `dead` (参照先が image 範囲外)。§5c の範囲外読みによる値は採らない。
- watch 版 (`PROBE_WATCH=fa5310:18 probe_entry.sh onw all`): 全関数入口の probe。ok 839 / oob 47 と通常 build から大きく変わるため、書込元の判定には使えない (watch build は挙動を変える)。`[chg]` 22 件は未解析。
- 未達 (受入条件 2〜4): ON で 1 ノードずれる書込元の特定、既存類型 (DEFECTS) への分類、ON の ok 退行 0。起票先: #1642 (次 run)。
- 参考 (main 取り込み由来・測定 commit 外): `git diff 7e665077 91655f69 -- tools/m11 ':(exclude)*.md'` は 4 files (48 insertions, 3 deletions)。本 PR の変更ではなく main 側の変更で、`m11_build.sh` は `M11_TRACE_ISOLATE` (既定 1 = 従来どおり) と `M11_KEEP_BOOT_O` (既定 0 = 従来どおり) の分岐を追加、`probe_entry.sh` は `M11_KEEP_BOOT_O=1` を渡す 1 行のみ。既定値の経路は変わらない。ldfix の results (jsonl・tsv) は data。上の §5e は、この差分を含む code で測定した値。

`probe_entry.sh` の `M11_KEEP_BOOT_O=1` は probe 測定の経路を変える (probe 版 boot.o を残す。旧版は build の `cc` で boot.o を上書きする)。そのため、下記の再測定で ON/OFF の値を取り直した (測定 commit `91655f69` = `tools/m11` の code が現 HEAD `4c2f69d1` と同一の状態)。

- 測定 commit `91655f69` の再測定: `M11_OV_CLASSCREATE=1 probe_entry.sh <tag> 407a50` と `=0` を各 1 回 (IR は `m11_gen_ir2.sh` で再生成、rc=0、F1=902、errors=0)。
  - ON: `ok 869 / oob 14 / halt0 10 / miss 47 / other 1 / noproc 1` (2 回目・3 回目で再現)
  - OFF: `ok 870 / oob 13 / halt0 10 / miss 47 / other 1 / noproc 1`
  - 上の旧経路の値と一致した。値は変わらない。
- 1 回目の ON は `ok 136 / oob 8 / miss 797 / halt0 1` で、2 回目以降は再現しなかった。`m11_gen_ir2.sh` の直後、初回 build の直後に得た値。原因は未特定 (単発の異常値として記録する。ON の survey 値はこの 1 回を除く 2 回で判断した)。
- 通常 build の対照 (probe 無し、`SV_RAW=1`、同一 restore 後の build): `ok 869 / miss 47 / other 1 / halt0 7 / oob 15 / abort 2 / noproc 1`。§5 の基準と一致。
- 未達 (受入条件 2〜4): ON で 1 ノードずれる書込元の特定、既存類型 (DEFECTS) への分類、ON の ok 退行 0。起票先: #1642 (次 run)。

```diff
# tools/m11/m11_build.sh (抜粋)
+ -DM11_TRACE_ISOLATE=${M11_TRACE_ISOLATE:-1}
+ if [ "${M11_KEEP_BOOT_O:-0}" != 1 ] || [ ! -f work/obj/boot.o ]; then cc work/boot_final3.ll work/obj/boot.o; fi
+ if [ "$(cat work/ov_trace_isolate.stamp 2>/dev/null || echo 1)" != "${M11_TRACE_ISOLATE:-1}" ]; then rm -f work/obj/ov.o; fi
# tools/m11/trap_triage/probe_entry.sh
- bash m11_build.sh > work/probe/build_$tag.log 2>&1 || ...
+ M11_KEEP_BOOT_O=1 bash m11_build.sh > work/probe/build_$tag.log 2>&1 || ...
```

## 5f. 410360 vcall 経路の切り分け (測定 commit `32663fde`、#1642)

- 素材: fl-win64・toolchain-retdec・toolchain-emsdk・work-m11 を展開 (`work-m11` は `tools/m11/work/` を内包するため、展開先は `tools/m11/` 直下)。IR `m11_gen_ir2.sh` rc=0 (51.4 s、ldfix=applied、F1=902、errors=0)。
- 切り分け変更: `m11_ov.c` の `m11_vcall` に `M11_NOVCALL` (既定 0) を入れ、1 のとき ICALL_AT を呼ばず `self` を返す。`m11_build.sh` の CF に `-DM11_NOVCALL=${M11_NOVCALL:-0}` を追加。既定 0 では出力は変わらない。
- **注意 (キャッシュ)**: `ov.o` は `work/ov_*.stamp` で一部の macro だけ無効化される。`M11_NOVCALL` は stamp の対象外のため、最初の測定 (`ov.o` 再利用) は `M11_NOVCALL=1` が効いていなかった可能性がある (869/15 は stale の疑い、未確定)。`rm -f work/obj/ov.o` の後に測り直した値のみ採る。
- 測定 (全 942 unit、`SV_RAW=1`、各 build は `ov.o` を作り直した後):

| build | ok / oob / abort / halt0 | unit 190 |
|---|---|---|
| OFF (`M11_OV_CLASSCREATE=0`) | 870 / 16 / 0 / 7 | ok |
| ON (`M11_OV_CLASSCREATE=1`) | 869 / 15 / 2 / 7 | oob |
| ON + `M11_NOVCALL=1` (410360 の vcall 経路を外す) | 869 / 15 / 2 / 6 | oob |

- `survey_diff.py` OFF→ON: ok 退行 unit は **190 の 1 件** (ok→oob)。kind 変化は 190 (ok→oob)・304・555 (oob→abort, #1275)。
- `survey_diff.py` ON→ON+NOVCALL: 変化は unit 314 の halt0→oob の 1 件のみ (kind 変化、ok 退行なし)。unit 190 は oob のまま。ok 退行は 0。 (注: 本行の NOVCALL 合計は 941 で不完全。§5g 参照。unit 314 は未再確認)
- 読み: 410360 の vcall 経路 (`site 0x41037d`) を外しても unit 190 の oob は消えない。unit 190 の trap は 410360 を経由しない (§3 と一致)。受入条件 1 の「原因の特定」は依然未達。
- 注意 (§5d の再検討): §5d の「9b4b00 の書込みを 1 文ずつ外す (8 通り)」「table 差し替えを外す」の測定は `define` の差し替えで、`ov.o` の stamp 対象外。stale な `ov.o` が使われていた可能性があり、§5d の「ON-only 差分は説明できない」は未確認に格下げする。再測定は未実施 (次手)。
- 未達 (受入条件): 1 (unit 190 の `[arg-8]` 参照先の変化の特定)・2 (DEFECTS 類型への分類)・3 (ON の ok 退行 0 の unit 単位確認: 190 が残る)。起票先: #1642。

## 6. 差分 (§5e の測定 commit `91655f69` から本 PR の HEAD まで)

測定 commit `91655f69` から本 PR の HEAD (`4c2f69d1`) までの `tools/m11` のコード差分は 0 行 (`git diff 91655f69 HEAD -- tools/m11 ':(exclude)*.md'`)。本 PR の変更は REPORT のみ。§5e の値は、この HEAD と `tools/m11` が同一の code で測定した値。

参考 (測定 commit 外): `7e665077` から `91655f69` までの main 取り込み由来の `tools/m11` 差分は 4 files (48 insertions, 3 deletions)。内訳は §5e の diff (`m11_build.sh` の 2 分岐、`probe_entry.sh` の `M11_KEEP_BOOT_O=1` 1 行) と ldfix の results (jsonl・tsv、data)。
- `git status --porcelain=v1 -- tools/m11`: 本 commit の時点で 0 行 (作業ツリーに tools/m11 の未コミット変更なし)。
- `find tools/m11/trap_triage -type f -size +20M`: 0 件 (20MiB 超の blob なし)。

## 5g. ov.o 再作成後の NOVCALL 再測定 (測定 commit `5229fe5f` = origin/main、#1642)

- 素材: fl-win64・toolchain-retdec・toolchain-emsdk・work-m11 を展開 (`work-m11` の展開先は `tools/m11/` 直下)。`m11_gen_ir2.sh` rc=0 (51 s、F1=902、errors=0)。
- 各 build の前に `work/obj/ov.o` を消してから作り直した (§5f の stale 疑いへの対処)。全 942 unit の survey は各 13〜14 s。

| build | ok / oob / abort / halt0 | unit 190 |
|---|---|---|
| ON (`M11_OV_CLASSCREATE=1`) | 869 / 15 / 2 / 7 | oob |
| OFF (`M11_OV_CLASSCREATE=0`) | 870 / 16 / 0 / 7 | ok |
| ON + `M11_NOVCALL=1` (ov.o 作り直し) | 869 / 16 / 2 / 6 | oob |

- `survey_diff.py` OFF→ON: ok 退行 unit は **190 の 1 件** (ok→oob)。§5f の結果と一致。
- `survey_diff.py` ON→ON+NOVCALL: ok 退行 0。変化は halt0→oob の 1 件のみ (halt0 7→6、oob 15→16 と整合)。unit 190 は oob のまま。**この 1 件の unit 番号は本 run の出力に保存していなかったため、特定できていない** (§5f の unit 314 は未確認)。
- 同一構成の値の食い違い: §5f の ON+NOVCALL 行 (869/15/2/6) は ok+oob+abort+halt0 の合計が 892 で、miss 47・other 1・noproc 1 を足すと 941 となり、全 942 unit と一致しない。§5g の同行 (869/16/2/6) は合計 893 で 942 と一致する。§5f の NOVCALL 行は survey が欠けた状態の値である可能性が高いが、原因は未特定。
- 断定の撤回: 前版の「§5f の 869/15 は stale な ov.o によるものだった」は根拠が無いため撤回する。本 run で ov.o を作り直したのは §5g の 3 build のみ。
- 結論の範囲: 作り直した単発の NOVCALL (869/16/2/6) では unit 190 が oob のまま。ここから言えるのは「vcall 経路を外しても 190 の oob は消えなかった (1 回・未再現)」まで。410360 の vcall 経路が原因でないとは断定しない。NOVCALL は未再現のため、再測定が必要。
- 未確定: §5d の `9b4b00` 書込みマスク測定は define 差し替えで、ov.o の stamp 対象外のため、stale の可能性が残る。再測定は未実施 (次 run: `m11_ov.c` の書込みマスクを `ov.o` 作り直しで測る)。
- 未達 (受入条件): 1 (ON で 1 ノードずれる書込元の特定)・2 (DEFECTS 類型への分類)・3 (ON の ok 退行 0 の unit 単位確認: 190 が残る)。起票先: #1642。
