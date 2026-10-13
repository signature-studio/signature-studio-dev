# REPORT_944 — `function_413060` の OFF 実害の実測: 到達計数・独立 gate・dest 観測・ネガコン (#944, 親 #705)

結論 (Refs #944。Closes しない):

- **正とする測定は commit `8b0f2874` の `repro_705.sh` 実行 (§1)**。同一 build 内で OFF / ON / OFF 再実行 / ネガコンを直列・単発で 1 回ずつ測った。
- 受入条件 1 (到達計数): survey 942 unit のうち **35 unit** で `function_413060` が呼ばれ、呼出し合計 **227 回**。
- 受入条件 2 (独立 gate): `M11_OV_413060=1` で 413060 だけを C 転記版に切替。
- 受入条件 3 (ネガコン): dest 観測 (§2) で既知変更 (b) `Q(dest)=p+0x40` が OFF と**指紋差を作る**ことを確認 (感度あり)。受入条件 3 を #1149 へ移管する扱いについては、PM の確認コメントがまだ無い (未取得)。PM が移管を認めない場合でも、この PR で感度は示せている。
- survey の判定ラベル (ok/trap/miss/noproc/clobber) は OFF/ON で 0 unit 差。一方 dest 指紋は OFF/ON で異なる (§2)。その差の意味は未解明。

## 1. 測定 (commit `8b0f2874`・`bash tools/m11/trap_triage/repro_705.sh`・直列・単発)

| 構成 | ok | noproc | miss | trap | clobber | 413060 unit 数 | 呼出し | dest 観測 n | dest 指紋 | elapsed | load (開始) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|---|--:|--:|
| OFF (`M11_OV_413060=0`, lift 版) | 871 | 1 | 47 | 23 | 0 | 35 | 227 | 227 | `da181b71c575c7f1` | 14.084 s | 0.71 |
| ON (`M11_OV_413060=1`, C 転記版) | 871 | 1 | 47 | 23 | 0 | 35 | 227 | 227 | `491ce0111dba2bc1` | 14.241 s | 0.95 |
| OFF 再実行 (決定性) | 871 | 1 | 47 | 23 | 0 | 35 | 227 | 227 | `da181b71c575c7f1` | 13.550 s | 0.97 |
| ネガコン (b) (`M11_NEG_413060=1`) | 868 | 1 | 47 | 26 | 0 | 35 | 180 | 180 | `95d57073be04e723` | 26.413 s | 0.99 |

- unit ラベル (`ok`/`trap`/`miss`/`noproc`) は OFF と ON で 942 unit 全て一致 (差分 0 unit)。
- 計数 (ok/noproc/miss/trap/clobber/呼出し 227) は OFF と ON で一致。
- ネガコンは呼出し数 180 (227 → 180) と ok/trap が変わる。これは既知変更の副作用で、survey の計数上も OFF と差が出ることを示す。
- 到達 unit (VA, 呼出し数) は §1 末尾の列挙 (35 件・合計 227)。
- **elapsed の揺れ**: 同一 HEAD 系で 13.55〜14.24 s (OFF/ON 各 2 回)。load 0.7〜1.0 の範囲で、OFF/ON の差 (0.16 s) は揺れの範囲内。過去記録の 11.29 s (`ede7a153` 相当の run) や 14.20 s (前回レビュー run) とは実行ごとにずれる。**canonical は `8b0f2874` の上表**。
- 集計の出所: `repro_705.sh` の `[repro_705]` 行 (survey の `M11_SURVEY` JSON) から直接取った。

### 旧記録 (参考・canonical ではない)

- `5dbc6db9` (前回レビュー run): OFF 14.199 s / ON 14.113 s、ok=869 / trap=25。
- `5dbc6db9` (前 fix run): OFF 11.293 s / ON 11.277 s、ok=869 / trap=25。
- `8f7a2303` (旧 HEAD): OFF 14.03 s / ON 13.83 s、ok=869 / trap=25。
- 注意: 前 fix までの ok=869 / trap=25 と、本表の ok=871 / trap=23 は**別 build** の値。§4 (e) を参照。

## 2. 感度 (受入条件 3・ネガコン) と dest 観測

- 観測手段: `m11_post.py` が 413060 の wrapper (OFF) に、`m11_ov.c` が ON 版 function_413060 に、`m11_dest_obs(dest)` を呼ぶ。`m11_rt.c` が呼出し後の `*dest` (文字列ポインタ) を FNV 風に畳み、`_m11_dest_obs_hhi/hlo/n` で export。survey が `dest_obs_hash`・`dest_obs_n` として出力する。
- 決定性: OFF を 2 回測って指紋が一致 (`da181b71c575c7f1`)。
- ネガコン (b): `M11_NEG_413060=1` で dest に `+0x40` を書く既知変更。OFF と指紋差 (`95d57073be04e723` ≠ `da181b71c575c7f1`)、呼出し数も 227 → 180 に変わる。**感度あり**。
- OFF/ON の dest 指紋は**異なる** (`da181b71c575c7f1` ≠ `491ce0111dba2bc1`)。survey の計数は一致。指紋は heap 上の値を含むため、ON 版の割付順や値の差を含み得る。**この差が意味的な差か、アドレスなどのビルド差かは未切り分け**。判定は survey 差 0 (§1) のみを根拠とし、「影響なし」とは結論しない。
- 切り分け: `M11_DEST_READ=0` (読出し無し) の OFF は ok=871 / trap=23 で、読出しは集計を変えない。

## 3. 再現 (受入条件 4)

`bash tools/m11/trap_triage/repro_705.sh` (commit `8b0f2874`・`FL_WIN64_DIR`・`work/ir_conditions.json` 生成済み・work-m11 展開済み)。

```
[repro_705] off: rc=0 elapsed=14.084 s load=0.71
[repro_705] ok=871 noproc=1 miss=47 trap=23 clobber=0 f413060_calls=227 dest_obs_n=227 dest_obs_hash=da181b71c575c7f1 f413060_units=35
[repro_705] on: rc=0 elapsed=14.241 s load=0.95
[repro_705] ok=871 noproc=1 miss=47 trap=23 clobber=0 f413060_calls=227 dest_obs_n=227 dest_obs_hash=491ce0111dba2bc1 f413060_units=35
[repro_705] off2: rc=0 elapsed=13.550 s load=0.97
[repro_705] ok=871 noproc=1 miss=47 trap=23 clobber=0 f413060_calls=227 dest_obs_n=227 dest_obs_hash=da181b71c575c7f1 f413060_units=35
[repro_705] neg: rc=0 elapsed=26.413 s load=0.99
[repro_705] ok=868 noproc=1 miss=47 trap=26 clobber=0 f413060_calls=180 dest_obs_n=180 dest_obs_hash=95d57073be04e723 f413060_units=35
[repro_705] unit ラベルの OFF/ON 差分: 0 unit []
[repro_705] 計数の OFF/ON 不一致: なし
[repro_705] dest 指紋の OFF 決定性 (off == off2): 一致
[repro_705] ネガコン (neg) の dest 指紋 95d57073be04e723 vs OFF da181b71c575c7f1: 差あり (感度あり)
[repro_705] dest 指紋の OFF/ON 差: あり (491ce0111dba2bc1)
[repro_705] PASS
```

## 4. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) OFF/ON の dest 指紋差 (`da18…` ≠ `491c…`) の意味 (意味的差かビルド差か) | ON 版の値の同一性は未証明 | #1149 ([M11-N67]) |
| (b) 残り 14 関数の D4 判定 | 同型 D4 の有無 | #901 ([M11-N48]) |
| (c) ON 構成 (410360 含む) での 413060 の寄与 | ON の ok 退行との関係 | #704 |
| (d) #509 (LD-9 ldfix F3c 門拡張) との統合要否 | 検出を ldfix で拾えるか | #509 |
| (e) 前 fix 時の 869/25 → 本 build の 871/23 の差 | 同一 HEAD 系の集計が build で動く。原因未特定 (`M11_DEST_READ=0` で読出しは無関係、HEAD 版 `m11_post.py` でも 871/23 のため wrapper も無関係。残るのは rt.o/ov.o の再ビルドと C 側の差) | #1149 ([M11-N67]) |

## 5. 環境

- 素材: `fl-win64` (`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`)・`work-m11` (`tools/m11/work/`)・`toolchain-emsdk` ([EMSDK]、`docs/REFERENCES.md`)。
- `work-m11` は `ir_conditions.json` を含まないため、`m11_gen_ir2.sh` を実行して生成 (44 秒・ldfix F1=902 F3c=36 errors=0)。
- build 時間は本 run で未計測 (repro_705 全体 2 分 33 秒、survey 4 回を含む)。
