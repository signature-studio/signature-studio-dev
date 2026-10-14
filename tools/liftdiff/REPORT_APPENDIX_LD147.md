# liftdiff REPORT 付録: LD-147 (#3180) BOOL 戻り値の import を `i1` で受けて `sext` する型決定 (D25 候補) の実測と修復経路

親: #2821 (LD-133)。前提: `REPORT_APPENDIX_LD84.md` §4 (最初の分岐は `1c0b71` の HeapFree 戻り値)。
LD-133 付録 (`REPORT_APPENDIX_LD133.md`) は main に無い (branch `2821-ld84-remeasure` の未 merge commit `321721b5` のみ。§7)。
既知類型との関係: 新類型候補 **D25** (`docs/DEFECTS.md` 未登録。登録は PM 判断)。D1a〜D23 の該当は無い。LD-84 の HeapFree 応答差 (D24 行案) は PR #3049 で解消済み (`tools/shim/REPORT.md` §6)。

## 結論

- **受入 1 (型決定が rax の差を生むか、`work/` の外で実測): 生む。** `ott.ll` を無改変で複製した orig では、対象 6 case で native `rax=0x1`・wasm `rax=0xffffffffffffffff` (§2)。HeapFree 直後の 1 行 (`sext`→`zext`) だけを変えた複製 hf_zext では、その 6 case の rax が一致した。残る 2 case (1c621c) は別の差で、LD-84 付録 §4 (c) と同じ。
- **受入 2 (修復経路): 決めた。修復は入れず、PM 判断に上げて止める。** 修復箇所は RetDec 産の `ott.ll` の 3 行だけで、RetDec 路線への新規修正は D5 で禁じられる。x64c・flelift・liftlib 側には同じ型決定が見当たらない (import の戻り値は runtime が `RAX` に直接書く)。§5。
- **受入 3 (修復後の 12 case 差 0): 未達。** 修復を入れていないため、修復後の値は未測定。現 HEAD の基準は `cases=12 diff=0` (§3)。
- **受入 4 (BOOL 以外の戻り値の列挙): 完了。** `call i1 @` は 18 件・13 関数・11 API。BOOL 以外は **0 件**。rax へ直接 `sext` されるのは 3 件 (TerminateProcess・HeapFree・TlsSetValue)。§4。

**判定: 部分達成 (受入 1・2・4 達成、受入 3 未達)。** PR は `Refs #3180` (issue の指示どおり)。

## 1. 測定条件

- 作業: worktree `../ws-3180` (branch `3180-ld147-bool-sext`、base `origin/main` = `729a67cb`)。素材 `work-m6-ott` を `tools/{m6,m8,m9,m10,ott}/work/` へ `tar --zstd -xf` で展開。`tools/ott/work/ott.ll` は 957,145 B・sha256 `989cf685e9091c0a1d4a01e7a6b89f7f5bf4da75d5962be8bfd533db8797cd3f` (LD-133 付録の記録と一致)。
- 素材の実在: `analysis-ott-binaries` は `[ANALYSIS-DIR]` 配下の `plugins/ott/binaries/OTT_vst2_win64.dll` (`ANALYSIS_DIR` を環境変数で設定)、`toolchain-emsdk` は `[EMSDK]` の `emsdk_env.sh`。`tools/liftdiff/work/` は素材に無いため空の出力先として作成 (gitignore 対象)。
- 複製: `$RUNNER_TEMP/ld147/` に 3 variant の IR と target JSON。`tools/ott/work/` には書いていない (sha256 は測定前後で不変)。

| variant | 変更 | 変更行 |
|---|---|---|
| orig | なし (byte 一致の複製) | 0 |
| hf_zext | HeapFree の結果だけ | 11891 `%5 = sext i1 %4 to i64` → `zext` (1 行) |
| all_zext | `sext` で直接受けている BOOL 3 API | 6331 (TerminateProcess)・11891 (HeapFree)・15185 (TlsSetValue) |

- 再現 (script: `tools/liftdiff/results/ld147/bool_sext_probe.py`、commit `20ad8352`):

```
python3 tools/liftdiff/results/ld147/bool_sext_probe.py variants --out $RUNNER_TEMP/ld147
python3 tools/liftdiff/results/ld147/bool_sext_probe.py run --out $RUNNER_TEMP/ld147
python3 tools/liftdiff/results/ld147/bool_sext_probe.py rax --out $RUNNER_TEMP/ld147
```

  `run` の中身: `cd tools/liftdiff && python3 liftdiff.py run <target> --fn 0x1801ab1d0,0x1801ab258,0x1801c5e84,0x1801c621c,0x1801c682c,0x1801c69cc --pattern vm0,u16 --notrace --json <res>`。target は `targets/ott_old.json` を複製し、`ir` だけを差し替えたもの。
- 所要 (n=1 each・並列数 1・参考値): 初回 (build 込み) orig 10.91 s・hf_zext 10.06 s・all_zext 10.06 s。HEAD `20ad8352` での再実行 7.39 s・7.36 s・7.74 s。load average (実行前) 0.08 0.24 0.16。
- HEAD 再現: `20ad8352` で `variants`・`run`・`rax` を再実行し、3 variant の `res_*.json` が初回と一致 (`cmp` identical)。

## 2. rax の実測 (受入 1)

| 関数 | pattern | outcome (orig / hf_zext / all_zext) | native rax | wasm rax orig | wasm rax hf_zext | wasm rax all_zext |
|---|---|---|---|---|---|---|
| 1c5e84 | vm0 | diff / diff / diff | 0x1 | 0xffffffffffffffff | 0x1 | 0x1 |
| 1c5e84 | u16 | diff / diff / diff | 0x1 | 0xffffffffffffffff | 0x1 | 0x1 |
| 1c621c | vm0 | diff / diff / diff | 0x1720f22a0 | 0x1801c5e84 | 0x1801c5e84 | 0x1801c5e84 |
| 1c621c | u16 | diff / diff / diff | 0x1720f22a0 | 0x1801c5e84 | 0x1801c5e84 | 0x1801c5e84 |
| 1c682c | vm0 | diff / diff / diff | 0x1 | 0xffffffffffffffff | 0x1 | 0x1 |
| 1c682c | u16 | diff / diff / diff | 0x1 | 0xffffffffffffffff | 0x1 | 0x1 |
| 1c69cc | vm0 | diff / diff / diff | 0x1 | 0xffffffffffffffff | 0x1 | 0x1 |
| 1c69cc | u16 | diff / diff / diff | 0x1 | 0xffffffffffffffff | 0x1 | 0x1 |
| 1ab1d0・1ab258 (vm0/u16 計 4 case) | — | equal (4 case・3 variant とも) | raw 未記録 (equal は raw を残さない) | — | — | — |

- rax 不一致 (raw を持つ 8 case): orig **8** / hf_zext **2** / all_zext **2**。hf_zext と all_zext の残り 2 case は 1c621c のもの。
- **ネガティブコントロール (検出器)**: orig (無改変) で 6 case の rax 差が出る。1 行 (hf_zext) で同じ 6 case が一致する。この 2 つで、差の原因が HeapFree の `sext` であることを 1 行単位で示せた。
- outcome は 3 variant とも 8 case が `diff` のまま。LD-133 付録 §4 (a) の import 呼出し記録の差が残ると推定 (本 run では未検証)。
- 1c621c の rax 差 (native `0x1720f22a0` = heap ポインタ、wasm `0x1801c5e84` = 1c5e84 の VA) は、この型決定とは別。LD-84 付録 §4 (c) と同じで、未特定のまま。

## 3. 既定 build と計装 build の 12 case (受入 3 の現状値・修復なし)

`liftdiff.py run targets/ott_old.json` と `targets/ott_old_blk.json` (同じ fn・pattern・`--notrace`) → `results/ld67/compare_blk.py` → `cases=12 diff=0`。`729a67cb` で測定 (wall 既定 10.09 s・計装 10.33 s)。LD-133 付録 §2 と一致。修復後の値は未測定 (修復を入れていない)。

## 4. `call i1 @` の列挙 (受入 4)

`python3 tools/liftdiff/results/ld147/bool_sext_probe.py enum` (静的。`tools/ott/work/ott.ll` を読むだけ)。

| API (件数) | 呼出し元 (関数・ir 行) | 結果の最初の使われ方 |
|---|---|---|
| HeapFree (1) | function_1801c0b6c (11890) | `sext` → rax (11891) |
| TerminateProcess (1) | function_1801aa5dc (6330) | `sext` (6331) |
| TlsSetValue (1) | function_1801c3dc8 (15184) | `sext` (15185) |
| IsDebuggerPresent (1) | function_1801aa378 (6234) | `icmp` |
| IsProcessorFeaturePresent (2) | function_1801aa5dc (6318)・function_1801be5a8 (11627) | `icmp` |
| WriteFile (6) | function_1801c91cc (17547・17568)・function_1801c96b8 (17841)・function_1801c97bc (17979)・function_1801c98d8 (18141)・function_1801c9b34 (18568) | `icmp` |
| GetConsoleMode (1) | function_1801c9b34 (18410) | `icmp` |
| WriteConsoleW (2) | function_1801d212c (22900・22928) | `select` |
| FreeLibrary (1) | function_1801c38c8 (15063) | 結果未使用 |
| GetStringTypeW (1) | function_1801c65b4 (16574) | 結果未使用 |
| CloseHandle (1) | function_1801d212c (22921) | 結果未使用 |

- 合計 **18 件 / 13 関数 / 11 API**。第一の使われ方は `sext` 3・`icmp` 10・`select` 2・未使用 3 (合計 18)。
- **BOOL 以外の戻り値の `call i1` は 0 件**。修復の対象外になる関数は無い。
- BOOL の根拠: Win32 ドキュメントの戻り値型 (外部資料)。repo 内の宣言 `tools/shim/src/shim.h` で BOOL を確認できたのは HeapFree・TlsSetValue・WriteFile・CloseHandle の 4 件のみ。残りは外部資料による。
- 直接 `sext` しない 15 件 (icmp・select・未使用) の rax への到達は未確認。影響の有無は未検証。

## 5. 修復経路 (受入 2)

| 候補 | 内容 | 判定 |
|---|---|---|
| A | RetDec 産の `ott.ll` の `sext` 3 行を `zext` にする (pass 化を含む) | 行わない。`ott.ll` は旧 RetDec chain (`tools/ott/ott_build.sh`・m6〜m10) の産物で、そこへの新規修正は D5 (`docs/DECISIONS.md`) により禁止。`tools/**/work/` の書換えも禁止 (AGENTS 4-4) |
| B | x64c・flelift・liftlib 側で同じ型決定を直す | 同じ型決定が見当たらない。x64c の import は IR の `i1` を経由せず、runtime が RAX を直接書く: `tools/ott/rt/ott_cpu.c:67` `void imp_HeapFree(void) { R[RAX] = 1; IMP_RET(); }`、`tools/flelift/rt/fle_cpu.c:119` も同じ。`tools/liftlib` に BOOL の戻り値幅の規則は無い (`br i1` の書換えのみ) |

**判断**: 候補 B では直す対象が無く、候補 A は D5 の対象。受入 2 の「x64c/flelift/liftlib 側で直せない場合は PM に判断を上げて止める」に当たるため、ここで止める。修復は入れていない。

PM への選択肢 (案):

1. RetDec 路線の OTT 比較を残すなら、D5 の例外として 3 行の `zext` を承認する。その後、受入 3 (修復後の 12 case) を再測定する。
2. x64c 路線で OTT の clift target を作り、同じ 6 case の rax を実測する。`tools/ott/work/lift/` に OTT の x64c 生成物 (`ott_lifted.c`・`ott_data.c`・`lift_meta.json`) があり、liftdiff の clift route (`ldlib/clift.py`) の入力になりうる。target 化は未実施。
3. D25 を `docs/DEFECTS.md` に登録するだけにし、修復は見送る。

## 6. 検証範囲・範囲外

- 範囲内: 6 関数のうち vm0/u16 の 8 case (既定 build の rax)・`call i1 @` の 18 件 (静的)・既定 build と計装 build の 12 case (HEAD 基準)。
- 範囲外: 計装 build の variant (未測定)・x64c 路線での OTT 実測 (未実施)・実機 Windows の BOOL 戻り値 (未検証)・outcome の残り (§2 の (a)) の検証。
- 測定 commit: `729a67cb` (origin/main)。測定対象の範囲 `tools/liftdiff/{liftdiff.py,ldlib,rt,targets}` `tools/liftdiff/results/ld67` `tools/ott/rt` `tools/shim/src` の `git diff 729a67cb HEAD -- <範囲>` は **0 行** (HEAD `20ad8352`)。追加したのは `tools/liftdiff/results/ld147/` (測定の駆動スクリプト) だけ。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 修復経路の決定 (§5 の A/B・選択肢 1〜3)。受入 3 (修復後の 12 case 差 0) は未達 | D25 の修復が止まる | PM 判断 (#3180 のコメント) |
| D25 を `docs/DEFECTS.md` に登録するか (行案は LD-133 付録 §4 と本付録 §5) | 類型の正本に未登録 | PM 判断 (`docs/DEFECTS.md` は PM が編集) |
| 1c621c の rax 差 (2 case・別件 (c)) | 2 case の rax が一致しない | LD-84 (#2193) の追跡 |
| outcome の残り (計装上の import 記録の差・§2 (a)) | 8 case が `diff` のまま | LD-83 (#2192) 系の PM 判断 |
| `REPORT_APPENDIX_LD133.md` が main に無い (branch `2821-ld84-remeasure` の未 merge commit `321721b5` のみ。#3180 本文の参照が切れている) | LD-133 の根拠の所在 | PM 判断 (取り込み先。本 PR では取り込まない) |
| 直接 `sext` しない 15 件の BOOL 結果の rax への到達 | 影響の有無が未検証 | 修復経路の決定後に PM が判断 |
