# REPORT_944 — `function_413060` の OFF 実害の実測: 到達計数・独立 gate・dest 観測・ネガコン (#944, 親 #705)

結論 (Refs #944。Closes しない):

- **既定 build (計測なし) の OFF は ok=869 / trap=25** で、main と同一 (§0)。前 fix 時の値と一致する。
- 計測 build (`M11_INSTR_413060=1`) の OFF は ok=871 / trap=23。計測用の probe と dest 観測を入れると集計が変わるため、計測 build の値は**同一 build 内の比較にだけ使う**。
- 受入条件 1 (到達計数): 計測 build の survey で **35 unit** に `function_413060` が呼ばれ、呼出し合計 **227 回** (§1 末尾の列挙)。
- 受入条件 2 (独立 gate): `M11_OV_413060=1` で 413060 だけを C 転記版に切替。OFF/ON の survey 判定ラベルは 942 unit 全て一致。
- 受入条件 3 (ネガコン): dest 観測 (§2) で既知変更 (b) `Q(dest)=p+0x40` が OFF と**指紋差と呼出し数差を作る** (感度あり)。受入条件 3 を #1149 へ移管する扱いは、PM の確認コメントが無いため**採らない**。本 PR で達成とする。

## 0. ベースラインと計測 gate (指摘 2 への対応)

計測用の probe (`function_413060` の index 8) と dest 観測 hook は、`M11_INSTR_413060=1` のときだけ post と C に入る (既定 0)。既定 build の post 出力は main と一致 (`cmp` で同一)。

| build | ok | noproc | miss | trap | clobber | 備考 |
|---|--:|--:|--:|--:|--:|---|
| main (`origin/main`・既定) | 869 | 1 | 47 | 25 | 0 | `m11_survey` 1 回 (`m11_build.sh` 既定・post の `cmp` 一致) |
| PR `329db65e` 既定 (`M11_INSTR_413060=0`) | 869 | 1 | 47 | 25 | 0 | main と同一の post・同一の集計 |
| PR 計測 build (`M11_INSTR_413060=1`) OFF | 871 | 1 | 47 | 23 | 0 | 計測コードを含む。計測の比較専用 |

- 以前の 871/23 は、既定 build に計測 probe と dest 観測が無条件で入っていたことが原因。計測 gate を分けたことで既定の 869/25 に戻った (旧 `M11_DEST_READ=0` の切り分けは無効だった: wrapper 自体が残っていたため)。
- 既定 build と main の post 出力 (`boot_final3.ll`) は `cmp` で一致。

## 1. 測定 (計測 build・`bash tools/m11/trap_triage/repro_705.sh`・直列・単発)

コマンド: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/m11/trap_triage/repro_705.sh` (commit は本 PR の HEAD)。全体 2 分 0.2 s。

| 構成 | ok | noproc | miss | trap | clobber | 413060 unit 数 | 呼出し | dest 観測 n | dest 指紋 | elapsed | load (開始) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|---|--:|--:|
| OFF (`M11_OV_413060=0`, lift 版) | 871 | 1 | 47 | 23 | 0 | 35 | 227 | 227 | `da181b71c575c7f1` | 12.631 s | 1.27 |
| ON (`M11_OV_413060=1`, C 転記版) | 871 | 1 | 47 | 23 | 0 | 35 | 227 | 227 | `491ce0111dba2bc1` | 12.400 s | 1.18 |
| OFF 再実行 (決定性) | 871 | 1 | 47 | 23 | 0 | 35 | 227 | 227 | `da181b71c575c7f1` | 12.479 s | 1.24 |
| ネガコン (b) (`M11_NEG_413060=1`) | 868 | 1 | 47 | 26 | 0 | 35 | 180 | 180 | `95d57073be04e723` | 11.314 s | 1.15 |

- unit ラベル (`ok`/`trap`/`miss`/`noproc`) は OFF と ON で 942 unit 全て一致 (差分 0 unit)。
- 計数 (ok/noproc/miss/trap/clobber/呼出し 227) は OFF と ON で一致。
- ネガコンは呼出し数 180 (227 → 180) と ok/trap が変わる。既知変更の副作用で、survey の計数上も OFF と差が出ることを示す。
- 集計の出所: `repro_705.sh` の `[repro_705]` 行 (survey の `M11_SURVEY` JSON) から直接取った。

### 到達 unit (35 件・VA と呼出し数・合計 227)

`index:VA:呼出し数` (計測 build OFF の `f413060_units`):

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

### 旧記録 (参考・canonical ではない)

- `5dbc6db9` (前 fix run): OFF 11.293 s / ON 11.277 s、ok=869 / trap=25。計測 probe を含む build の値ではない (前 fix 時は既定 build に計測コードが無かった) ため、現 PR の既定 build (869/25) と一致する。
- `5dbc6db9` (前回レビュー run): OFF 14.199 s / ON 14.113 s、ok=869 / trap=25。同一 HEAD でも elapsed は 11〜14 s で揺れる。
- `8f7a2303` (旧 HEAD): OFF 14.03 s / ON 13.83 s、ok=869 / trap=25。
- elapsed は run ごとに揺れるため、判定の根拠にしない (判定は計数・指紋のみ)。

## 2. 感度 (受入条件 3・ネガコン) と dest 観測

- 観測手段: 計測 build のみ。`m11_post.py` が 413060 の wrapper (OFF) に、`m11_ov.c` が ON 版 function_413060 に、`m11_dest_obs(dest)` を呼ぶ。`m11_rt.c` が呼出し後の `*dest` (文字列ポインタ) を FNV 風に畳み、`_m11_dest_obs_hhi/hlo/n` で export。survey が `dest_obs_n`・`dest_obs_hash` として出力する。
- 決定性: OFF を 2 回測って指紋が一致 (`da181b71c575c7f1`)。
- ネガコン (b): `M11_NEG_413060=1` で dest に `+0x40` を書く既知変更。OFF と指紋差 (`95d57073be04e723` ≠ `da181b71c575c7f1`)、呼出し数も 227 → 180 に変わる。**感度あり**。
- OFF/ON の dest 指紋は異なる (`da181b71c575c7f1` ≠ `491ce0111dba2bc1`)。survey の計数は一致。指紋は heap 上の値を含むため、ON 版の割付順や値の差を含み得る。この差が意味的な差かビルド差かは未切り分け。判定は survey 差 0 (§1) のみを根拠とし、「影響なし」とは結論しない (§4 (a))。

## 3. 再現 (受入条件 4)

`bash tools/m11/trap_triage/repro_705.sh` (`FL_WIN64_DIR`・`work/ir_conditions.json` 生成済み・work-m11 展開済み)。`[repro_705]` 行の実測 (本 PR HEAD):

```
[repro_705] off: rc=0 elapsed=12.631 s load=1.27
[repro_705] ok=871 noproc=1 miss=47 trap=23 clobber=0 f413060_calls=227 dest_obs_n=227 dest_obs_hash=da181b71c575c7f1 f413060_units=35
[repro_705] on: rc=0 elapsed=12.400 s load=1.18
[repro_705] ok=871 noproc=1 miss=47 trap=23 clobber=0 f413060_calls=227 dest_obs_n=227 dest_obs_hash=491ce0111dba2bc1 f413060_units=35
[repro_705] off2: rc=0 elapsed=12.479 s load=1.24
[repro_705] ok=871 noproc=1 miss=47 trap=23 clobber=0 f413060_calls=227 dest_obs_n=227 dest_obs_hash=da181b71c575c7f1 f413060_units=35
[repro_705] neg: rc=0 elapsed=11.314 s load=1.15
[repro_705] ok=868 noproc=1 miss=47 trap=26 clobber=0 f413060_calls=180 dest_obs_n=180 dest_obs_hash=95d57073be04e723 f413060_units=35
[repro_705] unit ラベルの OFF/ON 差分: 0 unit []
[repro_705] 計数の OFF/ON 不一致: なし
[repro_705] dest 指紋の OFF 決定性 (off == off2): 一致 (da181b71c575c7f1 / da181b71c575c7f1)
[repro_705] ネガコン (neg) の dest 指紋 95d57073be04e723 vs OFF da181b71c575c7f1: 差あり (感度あり)
[repro_705] dest 指紋の OFF/ON 差: あり (491ce0111dba2bc1)
[repro_705] PASS
```

既定 build の基準 (計測なし): `m11_survey` の `ok=869 / trap=25` (main と同一、§0)。

## 4. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) OFF/ON の dest 指紋差 (`da18…` ≠ `491c…`) の意味 (意味的差かビルド差か) | ON 版の値の同一性は未証明。survey の判定差は 0 | #1149 ([M11-N67]) |
| (b) 残り 14 関数の D4 判定 | 同型 D4 の有無 | #901 ([M11-N48]) |
| (c) ON 構成 (410360 含む) での 413060 の寄与 | ON の ok 退行との関係 | #704 |
| (d) #509 (LD-9 ldfix F3c 門拡張) との統合要否 | 検出を ldfix で拾えるか | #509 |

(e) 解消済み (旧「871/23 の原因未特定」): 計測 probe と dest 観測を既定 build から分離した。既定 build の OFF は main と同じ 869/25 (§0)。871/23 は計測 build にだけ出る値で、計測コードの影響。

## 5. 環境

- 素材: `fl-win64` (`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`)・`work-m11` (`tools/m11/work/`)・`toolchain-emsdk` ([EMSDK]、`docs/REFERENCES.md`)。
- `work-m11` は `ir_conditions.json` を含まないため、`m11_gen_ir2.sh` を実行して生成 (38 秒・ldfix F1=902 F3c=36 errors=0)。
