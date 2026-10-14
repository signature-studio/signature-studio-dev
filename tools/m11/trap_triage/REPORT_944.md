# REPORT_944 — `function_413060` の OFF 実害の実測: 到達計数・独立 gate・dest 観測・ネガコン (#944, 親 #705)

結論 (Refs #944。Closes しない):

- **既定 build (計測なし) の OFF は ok=869 / trap=25** (測定 commit `ba9ba284`・main `53aa0a6a` と同一・`boot_final3.ll` は main と `cmp` 一致、§0)。
- 計測 build (`M11_INSTR_413060=1`) の OFF は ok=871 / trap=23。計測 probe と dest 観測を入れると集計が変わる。原因は**未特定** (§4 (e))。計測 build は**同一 build 内の比較 (OFF/ON/ネガコン) にだけ使い、既定の基準には使わない**。
- 受入条件 1 (到達計数): 計測 build の survey で **35 unit** に `function_413060` が呼ばれ、呼出し合計 **227 回** (§1 の列挙)。
- 受入条件 2 (独立 gate): `M11_OV_413060=1` で 413060 だけを C 転記版に切替。OFF/ON の survey 判定ラベルは 942 unit 全て一致。既定 build (計測なし) でも OFF/ON は 869/25 で一致し、unit 差分 0 (§0)。計測 build の一致 (§1) と合わせて 2 build で確認。
- 受入条件 3 (ネガコン): dest 観測 (§2) で既知変更 (b) `Q(dest)=p+0x40` が OFF と**指紋差と呼出し数差を作る** (感度あり)。

測定 commit: **`ba9ba284`** (コードを変えた最後の commit。`tools/m11/trap_triage/repro_705.sh` に既定 build の測定を追加)。
`git diff ba9ba284 HEAD -- tools/m11 ':!tools/m11/trap_triage/REPORT_944.md'` は空 (コードの差分 0。本ファイルの文書更新のみが後続 commit に含まれる)。
`git diff --stat 9d8f6c3f ba9ba284 -- tools/m11` の変更は `trap_triage/repro_705.sh` の 1 ファイルのみ (既定 build の測定と判定の追加)。

## 0. ベースラインと計測 gate

**#1149 追記 (測定 commit `2f83abc0`・HEAD = `a3641979` 以降を含む main)**: 既定 build の基準は **870/24** (旧 869/25 は `a3641979` 以前の値)。`repro_705.sh` の基準を 870/24 に更新して PASS (§6)。

計測用の probe (`function_413060` の index 8) と dest 観測 hook は、`M11_INSTR_413060=1` のときだけ post と C に入る (既定 0)。

| build | 測定 commit | ok | noproc | miss | trap | clobber | 備考 |
|---|---|--:|--:|--:|--:|--:|---|
| 既定 (`M11_INSTR_413060` 未設定) | `ba9ba284` | 869 | 1 | 47 | 25 | 0 | `repro_705.sh` 内で 1 回。units 942 |
| main (`origin/main` `53aa0a6a`・既定) | `53aa0a6a` | 869 | 1 | 47 | 25 | 0 | 同じ手順で 1 回 (`m11_gen_ir2.sh` → `m11_build.sh` → `m11_survey.mjs`) |
| 計測 build (`M11_INSTR_413060=1`) OFF | `ba9ba284` | 871 | 1 | 47 | 23 | 0 | §1。比較専用 |

- 既定 build の OFF/ON 判定一致 (受入条件 2 の既定 build 版・測定 commit `60051601`・直列・単発・`M11_INSTR_413060` 未設定):

  | 構成 | ok | noproc | miss | trap | clobber | unit ラベル |
  |---|--:|--:|--:|--:|--:|---|
  | 既定 OFF (`M11_OV_413060=0`) | 869 | 1 | 47 | 25 | 0 | 942 unit |
  | 既定 ON (`M11_OV_413060=1`) | 869 | 1 | 47 | 25 | 0 | OFF と差分 0 unit |

  - コマンド: `env -u M11_INSTR_413060 M11_OV_413060={0,1} M11_NEG_413060=0 bash m11_build.sh` → `env -u M11_INSTR_413060 M11_SURVEY_UNITS=<units>.json node m11_survey.mjs`。素材は `fl-win64`・`work-m11`・`toolchain-emsdk` ([EMSDK] 既存・6.0.12)。`m11_gen_ir2.sh` で `ir_conditions.json` を生成 (ldfix F1=902 F3c=36 errors=0)。
  - `boot_final3.ll` の md5 は両 build で `4fd74f373c293325c6ee011a0680c962` (同一。413060 の切替は `m11_ov.o` の再コンパイルで効く。`build_on.log` に `cc m11_ov.c` あり)。
  - 両 build の `M11_SURVEY` 行 (先頭): `{"units":942,"ok":869,"noproc":1,"miss":47,"trap":25,"clobber":0,...}`。survey 所要 OFF 39 s / ON 32 s、load 0.93 / 0.88。
  - unit ラベルの OFF/ON 差分 0 unit (`units_off.json` と `units_on.json` を比較)。
  - 注: `repro_705.sh` は既定 ON の経路を持たないため、本節の既定 ON は上記手順で別途測った。
- 既定 build の `boot_final3.ll` は main `53aa0a6a` の既定 build の `boot_final3.ll` と `cmp` で一致 (md5 `4fd74f373c293325c6ee011a0680c962`)。`boot_final.ll` も `m11_build.sh` 実行後の状態で PR 側と main `53aa0a6a` の間で diff 0 行 (`m11_gen_ir2.sh` 直後の状態は build 前のため比較対象にしない)。
- 既定 build の `M11_SURVEY` 行 (`ba9ba284`・直列・単発):
  `{"units":942,"ok":869,"noproc":1,"miss":47,"trap":25,"clobber":0,"trap_oom":1,"trap_other":24,"ok_with_oom":0}`
- 比較の補足: `origin/main` は現在 `a3641979` まで進んでおり、同じ手順では 870/24 になる (`a3641979` の `tools/m11` 変更による)。本 PR の取り込み元 `53aa0a6a` を基準にした。
- gate の理由: 既定 build に計測 probe を無条件で入れると、survey の集計が 869/25 から 871/23 に変わる (`329db65e` 以前の PR 版で確認)。計測を gate で分離して既定の出力を main と一致させた。
- 案 (a) の理由: `M11_OV_CLASSCREATE=1` の build で 413060 の C 転記が有効になる従来の意味を保つため。main では 413060 が `#if M11_OV_CLASSCREATE` の内側にあったので、`#if M11_OV_CLASSCREATE || M11_OV_413060` に変えた。`negctl_595.sh`・`REPORT_595.md`・`DOC_MAP.md` は変更しない (既存の実験を回帰させないため)。

## 1. 測定 (計測 build・`bash tools/m11/trap_triage/repro_705.sh`・直列・単発)

測定 commit `ba9ba284`。コマンド: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/m11/trap_triage/repro_705.sh` (全体 2 分 27 秒・判定 `PASS`)。

| 構成 | ok | noproc | miss | trap | clobber | 413060 unit 数 | 呼出し | dest 観測 n | dest 指紋 | elapsed | load (開始) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|---|--:|--:|
| 既定 (計測なし) | 869 | 1 | 47 | 25 | 0 | — | — | — | — | 11.108 s | 0.54 |
| OFF (`M11_OV_413060=0`, lift 版) | 871 | 1 | 47 | 23 | 0 | 35 | 227 | 227 | `da181b71c575c7f1` | 11.234 s | 0.72 |
| ON (`M11_OV_413060=1`, C 転記版) | 871 | 1 | 47 | 23 | 0 | 35 | 227 | 227 | `491ce0111dba2bc1` | 11.188 s | 0.83 |
| OFF 再実行 (決定性) | 871 | 1 | 47 | 23 | 0 | 35 | 227 | 227 | `da181b71c575c7f1` | 12.043 s | 0.90 |
| ネガコン (b) (`M11_NEG_413060=1`) | 868 | 1 | 47 | 26 | 0 | 35 | 180 | 180 | `95d57073be04e723` | 10.327 s | 1.01 |

- unit ラベル (`ok`/`trap`/`miss`/`noproc`) は OFF と ON で 942 unit 全て一致 (差分 0 unit)。
- 計数 (ok/noproc/miss/trap/clobber/呼出し 227) は OFF と ON で一致。
- ネガコンは呼出し数 180 (227 → 180) と ok/trap が変わる。
- elapsed は run ごとに揺れる (同一 build 内で 10.3〜12.0 s)。判定の根拠にしない (判定は計数・指紋のみ)。

### 到達 unit (35 件・VA と呼出し数・合計 227)

`index:VA:呼出し数` (`ba9ba284` の計測 build OFF の `f413060_units`):

```
15:0x4a570:2
16:0x54090:1
17:0x55790:1
22:0x67f00:10
53:0x158e20:9
54:0x1658e0:41
56:0x16fde0:21
58:0x177290:12
59:0x177fd0:1
60:0x179610:4
61:0x17fd50:16
62:0x180970:1
63:0x182230:7
95:0x1d2680:1
114:0x223840:3
144:0x25c540:1
149:0x264260:5
158:0x26d1a0:28
189:0x2b7e40:13
190:0x2cf480:12
232:0x2f6b90:1
245:0x333090:1
265:0x3a7360:4
279:0x4136d0:1
280:0x416010:13
307:0x4b2080:4
311:0x4cb690:2
314:0x4e48a0:2
427:0x5db1d0:2
509:0x739ca0:1
616:0x863d20:2
647:0x897ac0:1
659:0x8eaa30:1
880:0xe63540:1
895:0xeddfe0:2
```

件数 35・合計 227 (計測 run の出力から機械的に確認)。

## 2. 感度 (受入条件 3・ネガコン) と dest 観測

- 観測手段: 計測 build のみ。`m11_post.py` が 413060 の wrapper (OFF) に、`m11_ov.c` が ON 版 function_413060 に、`m11_dest_obs(dest)` を呼ぶ。`m11_rt.c` が呼出し後の `*dest` (文字列ポインタ) を FNV 風に畳み、`_m11_dest_obs_hhi/hlo/n` で export。survey が `dest_obs_n`・`dest_obs_hash` として出力する。
- 決定性: OFF を 2 回測って指紋が一致 (`da181b71c575c7f1`)。
- ネガコン (b): `M11_NEG_413060=1` で dest に `+0x40` を書く既知変更。OFF と指紋差 (`95d57073be04e723` ≠ `da181b71c575c7f1`)、呼出し数も 227 → 180 に変わる。**感度あり**。
- OFF/ON の dest 指紋は異なる (`da181b71c575c7f1` ≠ `491ce0111dba2bc1`)。survey の計数は一致。指紋は heap 上の値を含むため、ON 版の割付順や値の差を含み得る。意味的な差かビルド差かは未切り分け。判定は survey 差 0 (§1) のみを根拠とし、「影響なし」とは結論しない (§4 (a))。

## 3. 再現 (受入条件 4)

`bash tools/m11/trap_triage/repro_705.sh` (`FL_WIN64_DIR`・`work/ir_conditions.json` 生成済み・work-m11 展開済み)。測定 commit `ba9ba284` の実測 (全文):

```
[repro_705] default boot_final3.ll md5=4fd74f373c293325c6ee011a0680c962
[repro_705] default: rc=0 elapsed=11.108 s load=0.54
[repro_705] 既定 build 基準 (869/25/0): 一致 (ok=869 trap=25 clobber=0)
[repro_705] off: rc=0 elapsed=11.234 s load=0.72
[repro_705] ok=871 noproc=1 miss=47 trap=23 clobber=0 f413060_calls=227 dest_obs_n=227 dest_obs_hash=da181b71c575c7f1 f413060_units=35
[repro_705] on: rc=0 elapsed=11.188 s load=0.83
[repro_705] ok=871 noproc=1 miss=47 trap=23 clobber=0 f413060_calls=227 dest_obs_n=227 dest_obs_hash=491ce0111dba2bc1 f413060_units=35
[repro_705] off2: rc=0 elapsed=12.043 s load=0.90
[repro_705] ok=871 noproc=1 miss=47 trap=23 clobber=0 f413060_calls=227 dest_obs_n=227 dest_obs_hash=da181b71c575c7f1 f413060_units=35
[repro_705] neg: rc=0 elapsed=10.327 s load=1.01
[repro_705] ok=868 noproc=1 miss=47 trap=26 clobber=0 f413060_calls=180 dest_obs_n=180 dest_obs_hash=95d57073be04e723 f413060_units=35
[repro_705] unit ラベルの OFF/ON 差分: 0 unit []
[repro_705] 計数の OFF/ON 不一致: なし
[repro_705] dest 指紋の OFF 決定性 (off == off2): 一致 (da181b71c575c7f1 / da181b71c575c7f1)
[repro_705] ネガコン (neg) の dest 指紋 95d57073be04e723 vs OFF da181b71c575c7f1: 差あり (感度あり)
[repro_705] dest 指紋の OFF/ON 差: あり (491ce0111dba2bc1)
[repro_705] PASS
```

## 4. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) OFF/ON の dest 指紋差 (`da18…` ≠ `491c…`) の意味 (意味的差かビルド差か) | §8 で差は unit 158 (`0x26d1a0`) の 1 件に絞れた。ただし dest 読出しを入れると ON の unit 158 が ok→trap になるため、観測の副作用と意味的差の切り分けが未了。survey の判定差は読出しを入れた場合のみ 1 unit | #1547 ([M11-N101]・#1149 から分割) |
| (b) 残り 14 関数の D4 判定 | 同型 D4 の有無 | #901 ([M11-N48]) |
| (c) ON 構成 (410360 含む) での 413060 の寄与 | ON の ok 退行との関係 | #704 |
| (d) #509 (LD-9 ldfix F3c 門拡張) との統合要否 | 検出を ldfix で拾えるか | #509 |
| (e) 計測 build (`M11_INSTR_413060=1`) の OFF が既定 build と違う 871/23 の原因 (未特定)。候補: dest 観測 hook の volatile 読出しが不正な dest で trap を生んでいる可能性 (未検証・切り分けは未実施) | 計測 build の値 (871/23) を既定の基準に使えない | #1352 ([M11-N85]) |

(e) の詳細 (起票先 #1352 の受入条件に対応。**#1352 の実測で HEAD `1be53b3f` では計測 build の OFF は 870/24/0 で既定と一致し、871/23 は再現しなかった。dest 読出しを止めても 870/24/0 (`M11_DEST_READ=0`)。詳細は [REPORT_1352.md](REPORT_1352.md)**):
切り分けの実測 (`ba9ba284` と同じ IR・`M11_DEST_READ=0`・INSTR=1・OFF):
`{"units":942,"ok":871,"noproc":1,"miss":47,"trap":23,"clobber":0}`・`f413060_calls=227`。
dest 読出しを止めても 871/23 のまま。よって dest 読出しが原因ではないことだけ分かる。
計測 build の `boot_final3.ll` は既定と比べ、413060 の wrapper が `function_413060__lifted` 化・`@m11_probe(i32 8)` の呼出し・`@m11_dest_obs` の呼出しの 3 点で違う。
どの差 (probe 呼出し・wrapper の改名・dest 観測の宣言) が集計を変えるかは未切り分け。
計測 build の値は比較専用とし、既定の基準に使わない。

### DEFECTS.md への行案 (PM 判断。本 PR では DEFECTS.md を編集しない)

- 行案 [C] (D4 の再発例の追記): 「**再発例 (M11 #944, `function_413060` UStrFromPWCharLen)**: `mov rax,[rbx]` (dest の旧値, disp=0) の deref が脱落し、旧値が stack の dest 番地として扱われる。`412d60(&old)` が dest-8 を refcount として減算する。OFF (lift 版) と ON (C 転記版) は survey の判定ラベルが 942 unit 全て一致 (差 0)。測定 [REPORT_944.md §1](tools/m11/trap_triage/REPORT_944.md)」
- 行案 [E] (検出信号の追記): 「D4 を survey で直接見る信号は無い。`function_413060` の到達 35 unit・呼出し 227 回の計数 (`f413060_units`) で到達範囲を、dest 指紋 (`dest_obs_hash`) で値の変化を見る。survey の判定差だけでは感度が出ない (ネガコンの呼出し数差 227→180 で感度を確認)」

## 5. 環境

- 素材: `fl-win64` (`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`)・`work-m11` (`tools/m11/work/`)・`toolchain-emsdk` ([EMSDK]、`docs/REFERENCES.md`)。
- `work-m11` は `ir_conditions.json` を含まないため、`m11_gen_ir2.sh` を実行して生成 (36 秒・ldfix F1=902 F3c=36 errors=0・`ir_sha256=f5b27a23…`)。

## 6. #1149 追記: dest 観測の OFF/ON 数値差分とネガコン (受入条件 1〜4)

測定 commit: **`2f83abc0`** (`repro_705.sh` の既定基準を 870/24 に更新。コードを変えた最後の commit)。
`git diff 2f83abc0 HEAD -- tools/m11` は空 (本節の文書追記のみ後続 commit)。
コマンド: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 PATH=$HOME/.local/agent-py/bin:$PATH bash tools/m11/trap_triage/repro_705.sh` (直列・単発・全体 182 秒・判定 `PASS`)。
素材: `fl-win64`・`work-m11` (`m11_gen_ir2.sh` で `ir_conditions.json` を再生成 F1=902 F3c=36 errors=0)・`toolchain-emsdk`。

| 構成 | ok | noproc | miss | trap | clobber | 413060 unit | 呼出し | dest 指紋 (`dest_obs_hash`) | elapsed | load (開始) |
|---|--:|--:|--:|--:|--:|--:|--:|---|--:|--:|
| 既定 (計測なし) | 870 | 1 | 47 | 24 | 0 | — | — | — | 16.293 s | 0.78 |
| OFF (`M11_OV_413060=0`) | 870 | 1 | 47 | 24 | 0 | 35 | 227 | `acb2345ddb678281` | 16.247 s | 0.89 |
| ON (`M11_OV_413060=1`) | 870 | 1 | 47 | 24 | 0 | 35 | 227 | `ac2d2efb758d4bb1` | 16.199 s | 1.07 |
| OFF 再実行 (決定性) | 870 | 1 | 47 | 24 | 0 | 35 | 227 | `acb2345ddb678281` | 16.122 s | 1.04 |
| ネガコン (b) (`M11_NEG_413060=1`) | 867 | 1 | 47 | 27 | 0 | 35 | 180 | `18e582921189ec13` | 15.425 s | 1.02 |

- **受入条件 1 (観測手段・決定性)**: dest 書込み後の `*dest` を `m11_dest_obs` で畳んだ指紋を OFF/ON/ネガコンで出力。OFF を 2 回測って指紋 `acb2345ddb678281` が一致 (決定的)。
- **受入条件 2 (ネガコン感度)**: 既知変更 (b) `Q(dest)=p+0x40` は OFF と指紋が異なる (`18e582921189ec13` ≠ `acb2345ddb678281`)。呼出し数も 227 → 180、ok/trap も 870/24 → 867/27 に変わる。感度あり。
- **受入条件 3 (OFF/ON 差分の数値化)**: 指紋は OFF `acb2345ddb678281` ≠ ON `ac2d2efb758d4bb1`。survey の unit ラベル差分は 0 unit (942 unit 全て一致)、計数 (ok/noproc/miss/trap/clobber/呼出し 227) も一致。
  - §2 の「差 0」結論は次のように更新する: **survey 判定 (trap の有無) では OFF/ON に差は出ない。dest の値では差が出る** (指紋差 1 件)。ただし指紋は heap 上の値を含むため、この差が意味的差 (ON の dest 値が実際に変わる) かビルド差 (割付順) かは未切り分け (§4 (a) を継続)。
  - ネガコンは指紋差に加えて呼出し数差 (227→180) を作るが、ON は呼出し数差を作らない。ON と OFF の差は計数では出ず、指紋のみに出る。
- **受入条件 4 (再現手段)**: `tools/m11/trap_triage/repro_705.sh` (基準 870/24 に更新) で PASS。

### §6.1 既定 build の基準更新

`a3641979` 以降の main (`tools/m11` 変更を含む) で既定 build は 870/24 (`repro_705.sh` の旧基準 869/25 は不一致)。
§0 の表と `repro_705.sh` の基準を HEAD の実測値に合わせた。869/25 は `53aa0a6a` 時点の値として残す。

## 7. icall 差分 (受入条件 2 の残り・kind・ok・icall)

測定 commit: **`15beb1fb`** (main 取り込み時点の HEAD。このブランチでコードは変えていない)。
`git diff 15beb1fb HEAD -- tools/m11` は空 (本節の文書追記のみ)。
既定 build は `M11_INSTR_413060` 未設定 (計測なし)。`M11_OV_413060` のみ切り替え (OFF=0 / ON=1)。
コマンド: `env -u M11_INSTR_413060 M11_OV_413060={0,1} M11_NEG_413060=0 bash m11_build.sh` → `env -u M11_INSTR_413060 M11_SURVEY_UNITS=<units>.json node m11_survey.mjs` (直列・単発)。
素材: `fl-win64`・`work-m11` (`m11_gen_ir2.sh` で `ir_conditions.json` 再生成: F1=902 F3c=36 errors=0)・`toolchain-emsdk`。

| 構成 | ok | noproc | miss | trap | clobber | icall_miss | icall_miss_uniq | stub_total | stub_uniq | getmem | freemem | va_calls | survey elapsed | load (開始) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| OFF (`M11_OV_413060=0`) | 870 | 1 | 47 | 24 | 0 | 50 | 3 | 251 | 46 | 2012 | 162 | 36 | 16.323 s | 0.98 |
| ON (`M11_OV_413060=1`) | 870 | 1 | 47 | 24 | 0 | 50 | 3 | 251 | 46 | 2013 | 164 | 36 | 16.072 s | 0.94 |
| OFF 再測定 (決定性) | 870 | 1 | 47 | 24 | 0 | 50 | 3 | 251 | 46 | 2012 | 162 | 36 | — | — |

- 既定 OFF の基準 870/24/0 は §0 (main 基準) と一致。
- unit ラベル (`ok`/`noproc`/`miss`/`trap`) は OFF/ON の 942 unit 全てで一致 (差分 0 unit。`units_off.json` と `units_on.json` を比較)。OFF 再測定の unit ラベルも `units_off.json` と `cmp` 一致。
- `trap_kinds` (unreachable 1 / halt0->longjmp 7 / memory access out of bounds 16) は OFF/ON 一致。`stub_hits` も OFF/ON で一致。
- icall: `icall_miss` 50・`icall_miss_uniq` 3 は OFF/ON/OFF 再測定で一致 (icall の差分 0)。
- 差分: `getmem` 2012→2013・`freemem` 162→164 (ON で +1 / +2)。OFF 再測定は 2012/162 で決定的。差の原因は未切り分け (ON の C 転記版が呼ぶ alloc 回数の差の可能性はあるが未検証)。判定 (unit ラベル・trap・icall) には出ない。
- 感度: icall は差が出ない項目なので、本節の一致は「差なし」の確認であり感度の証明ではない。感度は §2・§6 のネガコン (呼出し数 227→180) が担う。
- 所要 (survey 単発): OFF 16.323 s / ON 16.072 s。elapsed の run 間揺れ (§1) があるため判定には使わない。
- 再現 (受入条件 4・HEAD `c55e6d25`・直列・単発・`m11_gen_ir2.sh` を HEAD で再実行してから実行): `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/m11/trap_triage/repro_705.sh` 全体 154.7 s (`time` の real、load 開始 1.20)・判定 `PASS`。計数は OFF/ON/OFF 再実行/ネガコンで 870/24・870/24・870/24・867/27。dest 指紋は OFF `acb2345ddb678281` (再実行で一致)・ON `ac2d2efb758d4bb1`・ネガコン `18e582921189ec13`。unit ラベル差分 0。
- 注: `repro_705.sh` の既定 build の `boot_final3.ll` md5 は `7304232a4b2a28e1456cb3e7527b653d` (§0 の `4fd74f…` と異なる)。計数 870/24 は §0・§6 の基準と一致。md5 の差の原因は未切り分け (`m11_gen_ir2.sh` を HEAD で再実行した IR から作ったため)。

## 8. #1389 追記: dest の値 (内容) の OFF/ON 差分と切り分け

測定 commit: **`32c10b13`** (コードを変えた最後の commit)。`git diff 32c10b13 HEAD -- tools/m11` は本節の文書追記のみ。
コマンド: `bash tools/m11/trap_triage/repro_1389.sh` (OFF → OFF 再実行 → ON を直列・単発。`cmp_1389.py` で突き合わせ)。全体 103.97 s (`time` の real・load 開始 0.52 / 0.73 / 0.85)。判定 `PASS`。素材: `fl-win64`・`work-m11` (`m11_gen_ir2.sh` で `ir_conditions.json` を再生成)・`toolchain-emsdk`。

観測の変更: 指紋 (ポインタ値の FNV) では値の差か割付の差か区別できないため、`m11_dest_obs` が**呼出し k ごとに dest の文字列の内容** (長さ・UTF-16 本体の FNV・refcount) を記録するように変えた (`m11_dest_rec`)。突き合わせは呼出しの番号ではなく **(unit VA, unit 内の順番 j)** で行う。

### 8.1 結果 (実測)

| 構成 | ok | trap | 呼出し (dest 記録) | unit 158 (0x26d1a0) の ok/trap | 備考 |
|---|--:|--:|--:|---|---|
| OFF (`M11_OV_413060=0`) | 870 | 24 | 227 | ok | 基準 |
| OFF 再実行 | 870 | 24 | 227 | ok | 記録 227 件すべて OFF と一致 (決定性) |
| ON (`M11_OV_413060=1`・読出しあり) | 869 | 25 | 216 | **trap** | unit・順番で揃えた 216 件中の差分 1 件 (呼出しの揃う 35 unit のうち 34 unit は完全一致)。指紋 `bdf43798da38f253` (OFF `acb2345ddb678281`) |
| ON (`M11_DEST_READ=0`・読出しなし) | 870 | 24 | — | ok | 既存の ON 基準 (870/24) と一致 |

- 差分 1 件: unit 158 (`0x26d1a0`) の j=12 (呼出し k=148)。OFF は `*dest` が NULL (len 0)、ON は長さ 1 の文字列 (refcount 1)。
- OFF/ON で unit 158 の呼出し数が 28 → 17 に減る。ON 版はこの unit の後続で trap する (j=17 以降の呼出しが無い)。
- 呼出しのある 35 unit のうち 34 unit は、OFF/ON の記録が呼出しごとに完全一致する (差は unit 158 のみ)。
- 指紋 (`dest_obs_hash`) の OFF/ON 差は、この 1 件 (unit 158) の値差が原因。記録上、他の unit の差は無い。
- 切り分け: 読出し (`m11_dest_rec` の読取り) を止めた ON は 870/24 で既存基準どおり。読出しを入れた ON だけ unit 158 が ok → trap に変わる (`units_on_read0.json` と `units_on.json` の比較で、942 unit のうち差は 158 のみ)。

### 8.2 結論 (受入条件)

1. **OFF/ON の dest の値の比較**: 実施。呼出し 216 件 (揃った数) のうち差は 1 件。
2. **差の箇所**: unit 158 (`0x26d1a0`)・unit 内の j=12 (呼出し k=148)。
3. **結論 (意味的差かビルド差か)**: **未決**。差は「ON で dest の値が変わる」点で意味的差の候補。ただし読出しを入れると ON の unit 158 の結果 (ok→trap) が変わるため、観測の副作用が混ざる可能性を排除できない。現時点では意味的差と断定しない。
4. **決定性**: OFF 2 回で記録 227 件が完全一致。

## 9. #1864 追記: unit 158・j=12 の dest 値差の切り分け (部分)

測定 commit: **`576c4976`** (origin/main。本節の作業では m11 のコードを変えていない。一時の計測変更は全て破棄)。
`git diff 576c4976 HEAD -- tools/m11` は本節の文書追記のみ。

### 9.1 再現 (同一 build 内・決定性)

コマンド: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/m11/trap_triage/repro_1389.sh` (OFF → OFF 再実行 → ON・直列・単発)。判定 `PASS`。全体 1 分 51 秒 (`time` の real・load 開始 0.87 / 0.93 / 0.96)。
- OFF 2 回: 記録 227 件が完全一致 (決定的)。
- OFF/ON: 記録 227 件に対し、ON は 216 件 (unit・順番で揃った 216 件中の差分 1 件)。差は unit `0x26d1a0` の j=12 のみ。OFF `{st 0, len 0, rc 0}` / ON `{st 1, len 1, rc 1}`。

### 9.2 読出しの副作用の切り分け (一時変更・測定後に破棄)

`m11_dest_obs` の読出し・記録を 3 通りに分けて、ON の survey を取った (全て `M11_INSTR_413060=1`・`M11_OV_413060=1`):

| 構成 | ok | trap | unit 158 | 読出し境界外 (st=3) | 備考 |
|---|--:|--:|---|--:|---|
| 記録あり (既定の計測) | 869 | 25 | trap | — | §8 と一致 |
| 記録あり・境界チェック付き (dest 範囲外を検出) | 869 | 25 | trap | 0 件 (216 件中) | dest の範囲外アクセスではない |
| 読出し 1 回のみ・記録なし | 870 | 24 | **ok** | — | 下表の比較で unit ラベル差 0 |

- `units_off.json` (OFF) と `units_readonly.json` (読出し 1 回のみ・記録なし) を 942 unit で比較: **差 0 unit**。
- よって ON の trap は、dest の読出しでも範囲外アクセスでもなく、**記録の書込み (`g_rec_*`・`g_dest_h` への書込み) が計測副作用として unit 158 の結果を変えている**と読める。
- この結論は「読出し 1 回のみ」の ON が 870/24 に戻ることからの推論。`g_rec_*` の線形メモリ上の配置は未確認 (`llvm-nm` で wasm のシンボル表を引けず、未切り分け)。

### 9.3 受入条件の判定 (#1864)

1. **値差が結果に効くか (未確定)**: 読出しのみの ON では unit ラベルに差が出ない (§9.2)。ただし、値差 (j=12 の `len 0→1`) が後続の呼出し・読出しを変えるかは、IR で `0x26d1a0` の後続経路を追うまで確定しない。**未達**。
   - #1945 (測定 commit `e5e3c7c2`): 観測副作用の可能性が高い (詳細は [REPORT_APPENDIX_944.md](REPORT_APPENDIX_944.md) §3)。
2. **REPORT §9.3 追記・§4(a) 更新**: 本節 §9.3 で判定の材料を更新。意味的差か観測副作用かの結論は**未達** (上記 1 が未確定のため、§4 (a) は「観測の副作用が trap を作ることは確認。値差の結果への寄与は未確定」に留める)。
3. **決定的な測定と実測値**: 9.1 の OFF 2 回一致・所要時間・load を記録。**達成**。
