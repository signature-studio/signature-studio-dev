# REPORT_944 — `function_413060` の OFF 実害の実測: 到達計数・独立 gate・dest 観測・ネガコン (#944, 親 #705)

結論 (Refs #944。Closes しない):

- **既定 build (計測なし) の OFF は ok=869 / trap=25** (現 HEAD `9d8f6c3f` で実測・main と同一・`boot_final3.ll` は main と `cmp` 一致、§0)。
- 計測 build (`M11_INSTR_413060=1`) の OFF は ok=871 / trap=23。計測 probe と dest 観測を入れると集計が変わる。原因は未特定 (§4 (e))。計測 build は**同一 build 内の比較 (OFF/ON/ネガコン) にだけ使い、既定の基準には使わない**。
- 受入条件 1 (到達計数): 計測 build の survey で **35 unit** に `function_413060` が呼ばれ、呼出し合計 **227 回** (§1 の列挙)。
- 受入条件 2 (独立 gate): `M11_OV_413060=1` で 413060 だけを C 転記版に切替。OFF/ON の survey 判定ラベルは 942 unit 全て一致。
- 受入条件 3 (ネガコン): dest 観測 (§2) で既知変更 (b) `Q(dest)=p+0x40` が OFF と**指紋差と呼出し数差を作る** (感度あり)。

測定 commit: **`9d8f6c3f`** (コードを変えた最後の commit。`git diff 9d8f6c3f HEAD -- tools/m11` は空)。

## 0. ベースラインと計測 gate

計測用の probe (`function_413060` の index 8) と dest 観測 hook は、`M11_INSTR_413060=1` のときだけ post と C に入る (既定 0)。

| build | 測定 commit | ok | noproc | miss | trap | clobber | 備考 |
|---|---|--:|--:|--:|--:|--:|---|
| 既定 (`M11_INSTR_413060` 未設定) | `9d8f6c3f` | 869 | 1 | 47 | 25 | 0 | `m11_survey` 1 回。units 942 |
| main (`origin/main` `c4e93550`・既定) | `c4e93550` | 869 | 1 | 47 | 25 | 0 | 同じ手順で 1 回 |
| 計測 build (`M11_INSTR_413060=1`) OFF | `9d8f6c3f` | 871 | 1 | 47 | 23 | 0 | §1。比較専用 |

- 既定 build の `boot_final3.ll` は main の `boot_final3.ll` と `cmp` で一致 (md5 `4fd74f373c293325c6ee011a0680c962`)。既定 build の post 出力は PR 導入前と同一。
- 既定 build の `M11_SURVEY` 行 (`9d8f6c3f`・直列・単発):
  `{"units":942,"ok":869,"noproc":1,"miss":47,"trap":25,"clobber":0,"trap_oom":1,"trap_other":24,"ok_with_oom":0}`
- gate の理由: 既定 build に計測 probe を無条件で入れると、survey の集計が 869/25 から 871/23 に変わる (`329db65e` 以前の PR 版で確認)。計測を gate で分離して既定の出力を main と一致させた。
- 案 (a) の理由: `M11_OV_CLASSCREATE=1` の build で 413060 の C 転記が有効になる従来の意味を保つため。main では 413060 が `#if M11_OV_CLASSCREATE` の内側にあったので、`#if M11_OV_CLASSCREATE || M11_OV_413060` に変えた。`negctl_595.sh`・`REPORT_595.md`・`DOC_MAP.md` は変更しない (既存の実験を回帰させないため)。

## 1. 測定 (計測 build・`bash tools/m11/trap_triage/repro_705.sh`・直列・単発)

測定 commit `9d8f6c3f`。コマンド: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/m11/trap_triage/repro_705.sh` (全体 2 分 18 秒・判定 `PASS`)。

| 構成 | ok | noproc | miss | trap | clobber | 413060 unit 数 | 呼出し | dest 観測 n | dest 指紋 | elapsed | load (開始) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|---|--:|--:|
| OFF (`M11_OV_413060=0`, lift 版) | 871 | 1 | 47 | 23 | 0 | 35 | 227 | 227 | `da181b71c575c7f1` | 13.719 s | 0.91 |
| ON (`M11_OV_413060=1`, C 転記版) | 871 | 1 | 47 | 23 | 0 | 35 | 227 | 227 | `491ce0111dba2bc1` | 13.784 s | 0.95 |
| OFF 再実行 (決定性) | 871 | 1 | 47 | 23 | 0 | 35 | 227 | 227 | `da181b71c575c7f1` | 13.859 s | 0.97 |
| ネガコン (b) (`M11_NEG_413060=1`) | 868 | 1 | 47 | 26 | 0 | 35 | 180 | 180 | `95d57073be04e723` | 12.907 s | 0.98 |

- unit ラベル (`ok`/`trap`/`miss`/`noproc`) は OFF と ON で 942 unit 全て一致 (差分 0 unit)。
- 計数 (ok/noproc/miss/trap/clobber/呼出し 227) は OFF と ON で一致。
- ネガコンは呼出し数 180 (227 → 180) と ok/trap が変わる。
- elapsed は run ごとに揺れる (同一 build 内で 12.9〜13.9 s)。判定の根拠にしない (判定は計数・指紋のみ)。

### 到達 unit (35 件・VA と呼出し数・合計 227)

`index:VA:呼出し数` (`9d8f6c3f` の計測 build OFF の `f413060_units`):

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

`bash tools/m11/trap_triage/repro_705.sh` (`FL_WIN64_DIR`・`work/ir_conditions.json` 生成済み・work-m11 展開済み)。測定 commit `9d8f6c3f` の `[repro_705]` 実測:

```
[repro_705] off: rc=0 elapsed=13.719 s load=0.91
[repro_705] ok=871 noproc=1 miss=47 trap=23 clobber=0 f413060_calls=227 dest_obs_n=227 dest_obs_hash=da181b71c575c7f1 f413060_units=35
[repro_705] on: rc=0 elapsed=13.784 s load=0.95
[repro_705] ok=871 noproc=1 miss=47 trap=23 clobber=0 f413060_calls=227 dest_obs_n=227 dest_obs_hash=491ce0111dba2bc1 f413060_units=35
[repro_705] off2: rc=0 elapsed=13.859 s load=0.97
[repro_705] ok=871 noproc=1 miss=47 trap=23 clobber=0 f413060_calls=227 dest_obs_n=227 dest_obs_hash=da181b71c575c7f1 f413060_units=35
[repro_705] neg: rc=0 elapsed=12.907 s load=0.98
[repro_705] ok=868 noproc=1 miss=47 trap=26 clobber=0 f413060_calls=180 dest_obs_n=180 dest_obs_hash=95d57073be04e723 f413060_units=35
[repro_705] unit ラベルの OFF/ON 差分: 0 unit []
[repro_705] 計数の OFF/ON 不一致: なし
[repro_705] dest 指紋の OFF 決定性 (off == off2): 一致 (da181b71c575c7f1 / da181b71c575c7f1)
[repro_705] ネガコン (neg) の dest 指紋 95d57073be04e723 vs OFF da181b71c575c7f1: 差あり (感度あり)
[repro_705] dest 指紋の OFF/ON 差: あり (491ce0111dba2bc1)
[repro_705] PASS
```

既定 build の基準 (計測なし): `m11_survey` の `ok=869 / trap=25` (§0)。

## 4. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) OFF/ON の dest 指紋差 (`da18…` ≠ `491c…`) の意味 (意味的差かビルド差か) | ON 版の値の同一性は未証明。survey の判定差は 0 | #1149 ([M11-N67]) |
| (b) 残り 14 関数の D4 判定 | 同型 D4 の有無 | #901 ([M11-N48]) |
| (c) ON 構成 (410360 含む) での 413060 の寄与 | ON の ok 退行との関係 | #704 |
| (d) #509 (LD-9 ldfix F3c 門拡張) との統合要否 | 検出を ldfix で拾えるか | #509 |

(e) 計測 build (`M11_INSTR_413060=1`) の OFF が既定 build と違う 871/23 の原因は**未特定**。計測 probe と dest 観測の追加が原因と推定するが、切り分けは未実施 (`M11_DEST_READ=0` で wrapper を外す切り分けは、wrapper 自体が残るため根拠にならない)。計測 build の値は比較専用とし、既定の基準に使わない。

### DEFECTS.md への行案 (PM 判断。本 PR では DEFECTS.md を編集しない)

- 行案 [C] (D4 の再発例の追記): 「**再発例 (M11 #944, `function_413060` UStrFromPWCharLen)**: `mov rax,[rbx]` (dest の旧値, disp=0) の deref が脱落し、旧値が stack の dest 番地として扱われる。`412d60(&old)` が dest-8 を refcount として減算する。OFF (lift 版) と ON (C 転記版) は survey の判定ラベルが 942 unit 全て一致 (差 0)。測定 [REPORT_944.md §1](tools/m11/trap_triage/REPORT_944.md)」
- 行案 [E] (検出信号の追記): 「D4 を survey で直接見る信号は無い。`function_413060` の到達 35 unit・呼出し 227 回の計数 (`f413060_units`) で到達範囲を、dest 指紋 (`dest_obs_hash`) で値の変化を見る。survey の判定差だけでは感度が出ない (ネガコンの呼出し数差 227→180 で感度を確認)」
- 根拠の出所: `[C]`/`[E]` に対応する reviewer の指摘本文は PR #1152 上に見つからなかった。上の行案は PM 指示の範囲 (REPORT に行案を書く) のみで、既存の測定に基づく。

## 5. 環境

- 素材: `fl-win64` (`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`)・`work-m11` (`tools/m11/work/`)・`toolchain-emsdk` ([EMSDK]、`docs/REFERENCES.md`)。
- `work-m11` は `ir_conditions.json` を含まないため、`m11_gen_ir2.sh` を実行して生成 (43 秒・ldfix F1=902 F3c=36 errors=0・`ir_sha256=f5b27a23…`)。
