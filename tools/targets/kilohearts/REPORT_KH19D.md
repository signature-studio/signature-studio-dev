# KH-19d (#850): 対照 Gain の before 160 閉包を x64c で lift し、build の最初の失敗点を記録する

既知類型との関係: **D11** (DEFECTS.md・ours・同型): PE の絶対 VA リテラル `i64 0x18…` が wasm32 で切り捨てられて OOB (試行 A)。修復の手段は別: D11 の修復は rdata 窓 + PE 実データ、本件は像を shift して VA を wasm32 内へ移す配置 (試行 C)。

- 対象: 対照 Gain (`gain`) の before 160 閉包。root 27 件は `gain_before_160.tsv` の root 行 (機械生成・`verified` 列は全行 `auto`)。
- 素材: `plugins-kilohearts` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B)。
  ImageBase `0x180000000`・SizeOfImage `0x625c000`・AMD64。Windows 側だけを手で展開 (`extract_installer.sh` は macOS 側で停止するため)。展開先は repo 外。
- 測定 commit (lift・build の実測): `196f37ef`。以降の差分は §6 の注記のとおり (smoke の判定追加と再現スクリプト 2 件)。lift・build の入力と出力は変えていない。

## 0. 結論

- 受入 1 の「KH-19b で確定した closure」はまだ確定していない (手検証 160 との差分判定は #2176 待ち)。本節が lift したのは**未確定の before 160** (直接 call 閉包の下界・機械生成)。確定 closure の lift は未実施 (子 issue #3063)。
- x64c で **148 関数**を lift した (§2・測定 commit `196f37ef`)。before 160 との差 12 件 (算術差) の内訳は**未検証** (§3)。
- 最初の build 失敗点: **`fle_data_gen.py` に直書きされた FLEngine 固有の VA `0x42f670` の窓**。Kilohearts の像の外で負の番地になり、emcc が字句エラーで止まる (§4 の B)。範囲内に限る 1 行で解消。
- 既定 ImageBase (`0x180000000`) のままでは wasm32 の番地に収まらない (`memory access out of bounds`・D11 同型)。像を `0x2000000` 起点へ shift すると、compile・link が通る (§4 の C)。ただし正しさは未検証 (bit 突合は範囲外)。

## 1. 再現手順

```
# §5 (FLEngine の敷設出力の cmp・素材は fl-win64 のみ)
tar --zstd -xf ${ARTIFACTS_DIR}/fl-win64.tar.zst -C "$OUT" --wildcards '*block00031_PE.bin'   # → $OUT/extracted/block00031_PE.bin
OUT=<repo 外> bash tools/targets/kilohearts/scripts/fle_data_gen_cmp.sh <$OUT/extracted/block00031_PE.bin>

# §2 (素材: plugins-kilohearts)
tar --zstd -xf ${ARTIFACTS_DIR}/plugins-kilohearts.tar.zst --wildcards '*Offline Installer.zip'
unzip -q -o "Kilohearts Offline Installer.zip" payload.dat -d win
unzip -q -o win/payload.dat index.json 'windows.zip/*' -d blobs
unzip -q -o blobs/windows.zip/1ccb1df8c8f10745 -d winpkg        # → winpkg/HeartCore.core_64

# lift → data 敷設 → emcc compile・link → smoke (出力は repo 外)
KH_CORE=<winpkg/HeartCore.core_64> OUT=<repo 外の出力先> EMSDK=<emsdk のルート [EMSDK]> \
  bash tools/targets/kilohearts/scripts/lift_closure_x64c.sh

# §3 (内訳: lift の出力 $OUT/lift と HeartCore.core_64 が要る)
python3 tools/targets/kilohearts/scripts/closure_breakdown.py <winpkg/HeartCore.core_64> tools/targets/kilohearts/gain_before_160.tsv <OUT>/lift
```

`scripts/lift_closure_x64c.sh` は `gain_before_160.tsv` の root 行から `entries.json` を作り、`tools/flelift/x64c.py` (`--closure 60`・shift 付き)、`tools/flelift/fle_data_gen.py` (shift 付き)、`emcc` (`fle_lift.sh` と同じフラグ)、node の smoke の順に実行する。

## 2. 実測 (測定 commit `196f37ef`・4 vCPU・各 1 回・load average 0.28 → 0.72)

| 段 | 結果 | 時間 (n=1 の参考値) |
|---|---|--:|
| x64c (roots 27・closure 60・`--img 0x180000000 --shift 0x17E000000`) | functions 148・insns 9,502・unsup 285 site (48 mnemonic 種)・unlifted callees 0・imports used 25 (IAT 404 slot) | 13.7 s |
| fle_data_gen (`shift 0x17E000000`) | sections `.rdata` 21.8 MB・`.data` 1.8 MB・`.reloc` 0.8 MB、windows 8、total 24,441,216 B | — |
| emcc compile (`fle_lifted.c`、`-w` なし) | warnings 0・errors 0 | — |
| emcc link (`fle_lift.sh` と同じフラグ) | exit 0・`kh.wasm` 25,295,206 B | 21.0 s |
| smoke (node): `_fle_init` / `_fle_data_install` / `_fle_run(Gain process, 引数 0)` | 3 段とも trap なし。`fle_run` の戻り値 RAX = 303376204 | — |
| スクリプト全体 (測定時点・判定追加前) | exit 0 | 54.5 s |

- 時間は各 1 回の計測 (n=1)。変動の幅 (min–max レンジ) は未取得で、参考値として扱う。
- 本 fix (review round 2) では表の段を再実行していない。`plugins-kilohearts`・`toolchain-emsdk` が `$ARTIFACTS_DIR` に無く、x64c・emcc・smoke を走らせられないため (§6)。上の値は `196f37ef` の実測のまま。
- smoke は**正しさの検証ではない**。入力 spec を与えていないため戻り値の値は意味を持たない。bit 突合は issue の範囲外。
- smoke の `EXC` 判定 (`lift_closure_x64c.sh` の末尾: `ok` が 3 行・`EXC` が 0 行で成功) は本 PR で追加した。判定を通した実行は kh.wasm を作る run が要るため未実施 (§6)。判定ロジックは合成ログで確認した (`ok` 3 行・`EXC` 0 行で通過、`EXC` 1 件で失敗)。
- unsup 285 site: 実行到達時は `ott_unsup` で停止する。多い順は `vmovntdq` 30・`vmovsd` 32・`vmovd` 29・`vmulsd` 25・`vaddsd` 23・`vmovq` 17・`vfmadd213sd` 16 (VEX / FMA 系)。

## 3. 閉包の差分 (x64c 148 vs TSV 160)

- **内訳 (tail jmp・IAT thunk・取りこぼしの件数と番地) は未検証**。HeartCore.core_64 が無く、`closure_breakdown.py` を実 PE に当てて実行できていない。前の確認で得た件数と番地は、未コミットの一時スクリプト由来のため本 REPORT の値として採らない。
- 差 12 は `gain_before_160.tsv` の 160 行と §2 の lift 済み 148 の算術差。逆方向 (lift のみ) の件数と、x64c の関数集合が TSV に含まれるかは未検証。
- 再検証: `closure_breakdown.py` (§1)。期待する出力の形は `TSV 160 行 / lift 済み 148 / TSV 側の未 lift 12 / lift のみ <n>` と内訳 3 分類の件数。分類の仕様は同スクリプトの docstring (IAT thunk = 先頭 `ff 25`・tail jmp = 呼出位置の `jmp rel` が関数を指す・それ以外 = 取りこぼし)。
- 分類の動作は、合成 TSV 3 行 (`ff 25` の行・`jmp rel` の行・どちらでもない行) を FLEngine の PE に当てて 3 分類がそれぞれ出ることを前 fix run で確認した (実 PE の結果ではない)。
- 原因の調査は子 issue #3064 (KH-37)。

## 4. build の失敗点の記録 (同じ入力・手順の 3 試行)

| 試行 | 構成 | 結果 |
|---|---|---|
| A | 既定の VA のまま (`--img 0x180000000 --shift 0`) | compile 警告 0・link exit 0。ただし `_fle_data_install` が `RuntimeError: memory access out of bounds` で停止。VA の 64 bit 定数は 32 bit 番地へ切り詰められる (DEFECTS **D11** と同型) |
| B | shift `0x17E000000` (像を `0x2000000` 起点)・`fle_data_gen.py` は FLEngine 版のまま | **link 失敗** (最初の失敗点)。`fle_data.c:1018374:18: error: invalid suffix 'x' on integer constant` `memcpy((void*)0x-17dbd0990u, w_0, 48u);`。`-0x17dbd0990` = `0x42f670 - SHIFT (0x17E000000)` (python で確認)。`fle_data_gen.py` の `(0x42f670, 0x30)` (FLEngine の vtable 窓・#1936/#2005) は敷設先を `IMG + (VA - IMG) - SHIFT` で書くため、Kilohearts の像の外で負の番地になった |
| C | B + 窓を像の範囲内に限る (本 PR) | **成功**。§2 の実測 |

- 試行 B の原因箇所: `tools/flelift/fle_data_gen.py` の `for a, n in [(0x42f670, 0x30)]`。本 PR で `IMG <= a < IMG + SizeOfImage` の判定を足した。FLEngine (像内) では従来どおり追加される。
- 試行 A の補足 (未確認): 直書き窓は VA 版では `IMG + rva` が打ち消し合い `0x42f670` へ書き込む。emcc の静的領域と重なるかは確認していない。

## 5. FLEngine 側の回帰確認 (HEAD `0f52976e` で実行。以降 `scripts`・`flelift` は未変更)

- `scripts/fle_data_gen_cmp.sh` (素材: `fl-win64` の `block00031_PE.bin`・meta は空の合成値 `{}`):
  - `cmp old/new: 一致 (14820487 B)` — 旧版 (`196f37ef^` の `fle_data_gen.py`) と新版 (HEAD) の出力が一致。
  - ネガティブコントロール `neg (shift 0x17E000000): 差分 200 byte` — shift を与えると出力が変わり、cmp が差を検出することを示す。
- 注意: 確認に使った `lift_meta.json` は空の合成値 (jt / textrefs / IAT なし)。FLEngine の全 lift (`fle_lift.sh`) は再実行していない (§6)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 確定 closure (手検証 160 との差分 0) の lift と build | 受入 1 の「確定 closure」は未確定。本節は未確定の before 160 | #3063 (KH-36・前提 #2176) |
| §3 の内訳 (件数・番地) の再検証 (HeartCore.core_64 が要る)。関数数 148 ≠ 160 の説明 | 内訳は未検証。説明は未確定 | #3064 (KH-37) |
| unsup 285 site (VEX / FMA 系 48 mnemonic 種) | 実行到達時に `ott_unsup` で停止 | #3065 (KH-38) |
| 素材 `plugins-kilohearts`・`toolchain-emsdk` が本 fix の `$ARTIFACTS_DIR` に無い (`fl-win64` のみ)。x64c・emcc・smoke・`closure_breakdown.py` を再実行できない | 判定を含む lift・build の再測定と §3 の検証が未了。本 PR 本文の `oc_artifacts:` 行で次の run が取得する想定 | 本 PR の未解決表 (起票なし) |
| smoke の `EXC` 判定 (`lift_closure_x64c.sh` 末尾の +4 行) は `196f37ef` の測定に無く、未再測定。ネガティブコントロール (`_fle_data_install` を飛ばして trap することの確認) も未実施 | 判定は合成ログのみ確認。build 結果に対する判定は未実行 | #3063 |
| smoke は trap の有無しか見ない。FLEngine の vtable 窓 (#1936/#2005) に当たる Kilohearts 側の窓が無いかは未検討 | 正しさは未確認 | #3063 |
| FLEngine の全 lift (`fle_lift.sh`) での回帰・`fle_data_gen.py` の FLEngine 固有窓 `0x42f670` の直書き (範囲判定で他 PE への誤用は防止) | §5 は敷設出力の一致のみ。窓の引数化は FLEngine 側の meta 生成に触れる | 親 #850 への提案 (PM 判断) |
| bit 突合 (native 対照) | 範囲外 (issue 本文) | 起票なし |

- 測定 commit `196f37ef` からの差分 (`git diff --stat 196f37ef HEAD -- tools/targets/kilohearts/scripts tools/flelift`・HEAD `0f52976e` 時点):
  ```
   .../kilohearts/scripts/closure_breakdown.py        | 54 ++++++++++++++++++++++
   .../targets/kilohearts/scripts/fle_data_gen_cmp.sh | 31 +++++++++++++
   .../kilohearts/scripts/lift_closure_x64c.sh        |  4 ++
   3 files changed, 89 insertions(+)
  ```
  `lift_closure_x64c.sh` の差分は smoke の判定 (末尾の 4 行) だけ。`fle_data_gen.py` と x64c は変わっていない。lift・build の入力と出力は変わらないが、判定を含む再測定は素材が無く未了 (上の未解決表の 3・4 行目)。
