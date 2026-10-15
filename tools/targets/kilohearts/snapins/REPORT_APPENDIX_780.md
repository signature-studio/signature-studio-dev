# REPORT APPENDIX 780 — KH-17 (#780): Ladder Filter (ksla) の process 閉包を x64c で測る

> 本付録は #780 (親 #61 KH-6) の Ladder の**閉包測定**。lift・wasm・native との bit-exact 比較は未実施 (§4。子 #3721 [KH-60] で実施)。
> 本体の導線は `snapins/REPORT.md`・`REPORT.md` §4 (難度表 36-41)。

## 0. 結論 (先出し)

- **Ladder の process は `LadderDsp` の vtable slot 14 = `0x1804d9930` (620 B)**。slot 14 が process であることは、既存 13 本 (`snapins.json` の `proc`、Gain〜Limiter) すべてで同じ index と一致することを確認して決めた。
- process は `this` の vtable を**間接 call** で呼ぶ: `call [rax+0xa0]` (slot 20 = `0x1804d9ba0`) と `call [rax+0x78]` (slot 15 = `0x1804d9820`)。`LadderDsp` が独自に override する slot は `0, 7, 14, 15, 20` の 5 本 (slot 20 は base `SnapinDsp<LadderDspModel>` に無い独自 slot)。
- flelift `x64c` で **5 root** の閉包 = **98 関数 / 7,766 命令** (`--closure 1000`)。unsup は **4 種 38 site** (`rcpps` 34・`addsubpd` 2・`vpmovsxdq` 1・`vshufps` 1)。IAT import 17 種。trap 0。
- **ネガコン**: root を process 1 本にすると閉包は **2 関数 / 178 命令** で unsup 0。間接 call の先 (slot 15・20) を根に入れないと Ladder の DSP 本体は閉包に入らない。
- 残り (lift の unsup 38 site・scenario・native 比較) は子 #3721 [KH-60] に移した。Slice EQ → Filter Table は子 #3722 [KH-61]。

## 1. 数え方の定義

| 項目 | 定義 |
|---|---|
| process VA | `LadderDsp` (`.?AVLadderDsp@ladder@@`) の vtable の slot 14。既存 13 本の `snapins.json` の `proc` が `GainDsp`〜`LimiterDsp` の slot 14 と一致 (`idx [14]`)。既存の harness の先頭コメントにも同じ対応がある (`tools/targets/kilohearts/license/harness/scen_{gain,clipper,gate,haas,matrix,quickeq}.h`) |
| roots | `LadderDsp` vtable の slot のうち `SnapinDsp<LadderDspModel>` (`0x1818589f8`) と値が異なるもの (= 独自 override + slot 20)。no-op `0x1800128a0` は除外。計 5 本: `0x1804d9820 0x1804d98b0 0x1804d9930 0x1804d9ba0 0x1804db990` |
| 閉包 | `x64c.py --closure 1000`。roots から直接 call/jmp (即値先) を辿った関数集合。**間接 call は辿らない** (= root として明示したものだけが閉包に入る) |
| functions | `lift_meta.json` の `functions` 件数 (IAT thunk・tail 吸収は x64c の仕様どおり関数に数えない) |
| insns | `lift_meta.json` の `ninsn` |
| unsup sites | `lift_meta.json` の `unsup_sites` 件数 (`unsup` の値の合計と一致: 38) |

## 2. 測定 (再現: `KH_CORE=<HeartCore.core_64> OUT=<work 配下> bash scripts/ladder_x64c_closure.sh`)

| 条件 | functions | insns | unsup (種: site) | imports | traps |
|---|--:|--:|---|--:|--:|
| 閉包 (roots 5) | **98** | **7,766** | rcpps 34・addsubpd 2・vpmovsxdq 1・vshufps 1 (計 38) | 17 | 0 |
| ネガコン (root = process のみ) | 2 | 178 | 0 | 0 | 0 |

- 入力: `HeartCore.core_64` 76,642,304 B (sha256 先頭 16 hex `d55ce8b4c0ad7ebe`)。素材 `plugins-kilohearts` の `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/*` → `HeartCore.core_64` (`scripts/extract_installer.sh` の Windows 部分と同じ手順)。
- `--img 0x180000000`・`--img-size 0x625c000` は上の入力に合わせて `scripts/ladder_x64c_closure.sh` に固定した値。別 build の `KH_CORE` で使う前に、その PE の ImageBase・SizeOfImage を確かめること (スクリプトは検査しない。§5)。
- 再現実行: 同一 HeartCore で 2 回実行し、閉包 98 / 7,766 / unsup 38 が一致 (1 回目は commit 前の同内容のスクリプト、2 回目は測定 commit `9f02a5b69` の HEAD `4213316bb`)。
- 所要: x64c 閉包 1 回 約 14 s。スクリプト全体 (rtti_walk + 2 閉包) 約 29 s (load 4 vCPU)。
- unsup の内訳 (`rcpps` 34 site): 既存 snap-in の rcpps 実機近似 (`snapins/REPORT.md` §13・`scripts/rcpps_probe.c`・`approx_tables.b64`) と同じ型。x64c 側には未実装 = 次の作業の最初の項目。

## 3. 測定 commit と差分

- 測定 commit: `9f02a5b69` (`scripts/ladder_x64c_closure.sh` を追加した commit)。この commit の HEAD で再実行し、§2 と同じ値 (98 / 7,766 / unsup 38 / ネガコン 2 関数 / 178 命令) を得た。
- 測定 commit から HEAD までのコード差分: `git diff 9f02a5b69 HEAD -- tools/targets/kilohearts/scripts tools/targets/kilohearts/snapins/lift tools/targets/kilohearts/snapins/harness tools/targets/kilohearts/snapins/scripts tools/targets/kilohearts/snapins/run_all.sh tools/targets/kilohearts/snapins/snapins.json` の出力は 0 行 (本付録と `docs/DOC_MAP.md` の登録行のみが後続 commit で増える)。

## 3b. 681e2e811 時点の再測定 (未実施)

- 本 PR の HEAD (`681e2e811`) で閉包を再測定していない。入力の `plugins-kilohearts` (HeartCore.core_64) が本 run の `$ARTIFACTS_DIR` に無く (`fl-win64.tar.zst` のみ)、`fl-win64` の中にも `HeartCore` は無い。
- 従って、この付録の §0・§2 の「unsup 38」は `9f02a5b69` の値で、**681e2e811 では一致しない可能性が高い**。`x64c.py` は 681e2e811 で `addsubpd` (`i_addsubpd`)・`vshufps`・`vpmovsxdq`・`rcpps` (`i_rcpps`) を持つ (`9f02a5b69` には無い。main 取り込み由来)。`git diff 9f02a5b69 681e2e811 -- tools/flelift/x64c.py` が測定ずれの原因。
- 681e2e811 の unsup 件数・閉包 98 / 7,766 の再確認は、`plugins-kilohearts` を `oc_artifacts` で取得できる run で行う。それまで本付録の数値は `9f02a5b69` の値として読むこと。
- `build.py ladder --path s0` の wasm 574,270 B は本 PR の run で再現していない (`/opt/retdec` と `/opt/emsdk` も無い)。「通過」の主張は取り下げる。

## 4. 未実施・未達 (受入条件との対応)

| 受入 | 状態 |
|---|---|
| 段階順に 1 本ずつ bit-exact (Ladder → Slice EQ → Filter Table) | **未達** (Ladder は閉包測定まで。lift・wasm・native 比較は未実施)。子 #3721 [KH-60] (Ladder)・#3722 [KH-61] (Slice EQ → Filter Table) に移した |
| ネガコン・数え方の定義・再計算スクリプトを REPORT に書く | 数え方 = §1、ネガコン = §0・§2 (process 1 本の閉包)、再計算 = `scripts/ladder_x64c_closure.sh`。bit-exact 用のネガコン (1 bit 改変の検出) は未実施 |
| 既存 14 本の `run_all.sh` が不変 | `snapins.json` の既存 14 エントリは main と同値 (`ladder` 行の追加のみ)。`lift/gen_simd.py` に addsubpd を 4 行追加。`run_all.sh` 本体は未実行 (`ladder` の scenario が無く、既存 14 本の bit-exact 実測は本 PR では行っていない) |

## 5. 次の作業 (未解決)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| x64c に rcpps の実機近似を入れる (閉包 34 site) | Ladder の unsup の大半。これが無いと lift が通らない | #3721 [KH-60] |
| addsubpd 2・vpmovsxdq 1・vshufps 1 の x64c 対応 | 小。同じ子で扱う | #3721 [KH-60] |
| 間接 call (`[rax+0xa0]` slot 20 / `[rax+0x78]` slot 15) の wasm 側の dispatch 方式 | `this` 依存の vtable 呼び出し。native 比較の scenario で `this` の vtable を実物で組む必要がある (snapins の `scenarios` と同じ型) | #3721 [KH-60] |
| Ladder scenario・bit-exact 比較・ネガコン (1 bit 改変) | 受入の本体 | #3721 [KH-60] |
| `ladder_x64c_closure.sh` の `--img`・`--img-size` を PE から読む (または一致を検査する) | 別 build の `KH_CORE` で閉包が黙って狂う。本 PR では見送り: スクリプトを変えると測定 commit 以降のコード差分が 0 でなくなり、再測定が要る。再測定の入力 `plugins-kilohearts` は本 PR の run で取得できない | #3721 [KH-60] (閉包を次に測るときに入れる) |
| Slice EQ (kpeq) → Filter Table (ksft) の bit-exact 化 | 親 #780 の受入の残り | #3722 [KH-61] |

## 6. 付録の位置づけ

- `docs/DOC_MAP.md` に本付録の行を登録 (pr-lint の DOC_MAP 未登録チェック用)。
- 数値の正本は本付録。`snapins/REPORT.md` には書かない (行数上限 250 のため。本付録へのリンクだけを後で足す)。
