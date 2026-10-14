# KH-19d (#850): 対照 Gain の before 160 閉包を x64c で lift し、build の最初の失敗点を記録する

既知類型との関係: **D11** (DEFECTS.md・ours・同型): PE の絶対 VA リテラル `i64 0x18…` が wasm32 で切り捨てられて OOB (試行 A)。修復の手段は別: D11 の修復は rdata 窓 + PE 実データ、本件は像を shift して VA を wasm32 内へ移す配置 (試行 C)。

- 対象: 対照 Gain (`gain`) の before 160 閉包。root 27 件は `gain_before_160.tsv` の root 行 (機械生成・`verified` 列は全行 `auto`)。
- 素材: `plugins-kilohearts` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B)。
  ImageBase `0x180000000`・SizeOfImage `0x625c000`・AMD64。Windows 側だけを手で展開 (`extract_installer.sh` は macOS 側で停止するため)。展開先は repo 外。
- 測定 commit (lift・build・smoke・cmp の実測): `f1c40af2` (main `eeca4ded` を取り込んだ後のコード変更の最後の commit)。前回の測定 (`196f37ef`) と全段で同じ値だった (§2・§5)。

## 0. 結論

- 受入 1 の「KH-19b で確定した closure」はまだ確定していない (手検証 160 との差分判定は #2176 待ち)。本節が lift したのは**未確定の before 160** (直接 call 閉包の下界・機械生成)。確定 closure の lift は未実施 (子 issue #3063)。
- x64c で **148 関数**を lift した (§2)。before 160 との差 12 件 (算術差) の内訳は [`REPORT_APPENDIX_3064.md` §1](REPORT_APPENDIX_3064.md) が正本 (§3)。
- 最初の build 失敗点: **`fle_data_gen.py` に直書きされた FLEngine 固有の VA `0x42f670` の窓**。Kilohearts の像の外で負の番地になり、emcc が字句エラーで止まる (§4 の B)。範囲内に限る 1 行で解消。
- 既定 ImageBase (`0x180000000`) のままでは wasm32 の番地に収まらない (`memory access out of bounds`・D11 同型)。像を `0x2000000` 起点へ shift すると、compile・link・smoke の判定が通る (§4 の C・§2)。ただし smoke は trap の有無しか見ない。正しさは未検証 (bit 突合は範囲外)。

## 1. 再現手順

```
# §5 (FLEngine の敷設出力の cmp・素材は fl-win64 のみ)
cd "$OUT" && tar --zstd -xf ${ARTIFACTS_DIR}/fl-win64.tar.zst --wildcards '*block00031_PE.bin'   # → $OUT/extracted/block00031_PE.bin
OUT=<repo 外> bash tools/targets/kilohearts/scripts/fle_data_gen_cmp.sh $OUT/extracted/block00031_PE.bin

# §2 (素材: plugins-kilohearts・toolchain-emsdk)
cd "$OUT" && tar --zstd -xf ${ARTIFACTS_DIR}/plugins-kilohearts.tar.zst --wildcards '*Offline Installer.zip'
unzip -q -o "Kilohearts Offline Installer.zip" payload.dat -d win
unzip -q -o win/payload.dat index.json 'windows.zip/*' -d blobs
unzip -q -o blobs/windows.zip/1ccb1df8c8f10745 -d winpkg        # → winpkg/HeartCore.core_64
tar --zstd -xf ${ARTIFACTS_DIR}/toolchain-emsdk.tar.zst -C "$OUT"   # → $OUT/emsdk

# lift → data 敷設 → emcc compile・link → smoke (出力は repo 外)
KH_CORE=$OUT/winpkg/HeartCore.core_64 OUT=<repo 外の出力先> EMSDK=$OUT/emsdk \
  bash tools/targets/kilohearts/scripts/lift_closure_x64c.sh

# 負例 (§2): smoke から _fle_data_install の段を外す (出力先で実行)
cd <OUT> && sed '/data_install/d' smoke.cjs > smoke_neg.cjs && node smoke_neg.cjs

# §3 (内訳: 機械分類。出力は <OUT>/closure/gain_x64c_closure.json)
python3 tools/targets/kilohearts/scripts/gain_x64c_closure.py $OUT/winpkg/HeartCore.core_64 tools/targets/kilohearts/gain_before_160.tsv <OUT>/closure
```

`scripts/lift_closure_x64c.sh` は `gain_before_160.tsv` の root 行から `entries.json` を作り、`tools/flelift/x64c.py` (`--closure 60`・shift 付き)、`tools/flelift/fle_data_gen.py` (shift 付き)、`emcc` (`fle_lift.sh` と同じフラグ)、node の smoke の順に実行する。smoke の判定 (`ok` 3 行・`EXC` 0 行で成功) を満たさないと exit 1。

## 2. 実測 (測定 commit `f1c40af2`・4 vCPU・各 1 回 (n=1)・開始時 load average 1.02 0.62 0.28)

| 段 | 結果 | 時間 (n=1 の参考値) |
|---|---|--:|
| x64c (roots 27・closure 60・`--img 0x180000000 --shift 0x17E000000`) | functions 148・insns 9,502・unsup 285 site (48 mnemonic 種)・unlifted callees 0・imports used 25 (IAT 404 slot) | 11.1 s |
| fle_data_gen (`shift 0x17E000000`) | sections `.rdata` 21.8 MB・`.data` 1.8 MB・`.reloc` 0.8 MB、windows 8、total 24,441,216 B | — |
| emcc compile (`fle_lifted.c`) | warnings 0・errors 0 | — |
| emcc link (`fle_lift.sh` と同じフラグ) | exit 0・`kh.wasm` 25,295,206 B | 19.1 s |
| smoke (node): `_fle_init` / `_fle_data_install` / `_fle_run(Gain process, 引数 0)` | `init ok` / `data_install ok` / `fle_run(gain process, zero args) ok 303376204`。判定 `smoke: ok=3 (3 が成功) EXC=0 (0 が成功)` で通過 | — |
| スクリプト全体 (`lift_closure_x64c.sh`・判定込み) | exit 0 | 46.0 s |

- **負例 (ネガティブコントロール)**: `_fle_data_install` の段を外すと (§1 の `smoke_neg.cjs`)、`init ok` の後に `fle_run(gain process, zero args) EXC RuntimeError: memory access out of bounds`。`ok` 1・`EXC` 1 となり、判定 (`ok` 3・`EXC` 0) は失敗側に入る。
- 再実行 (`56c6f8cb`・本 fix の検証・n=1): `lift_closure_x64c.sh` は exit 0・`smoke: ok=3 EXC=0`・`kh.wasm` 25,295,206 B で、x64c の functions 148・insns 9,502・unlifted callees 0・imports 25 も上と同じ。負例も同じ (`init ok` の後に `EXC RuntimeError: memory access out of bounds`)。スクリプト全体は 70.0 s。
- 時間は 2 回 (`f1c40af2` の 46.0 s・`56c6f8cb` の 70.0 s) の参考値で、変動は大きい。min–max レンジとしては扱わない (n=2 のため)。
- smoke は**正しさの検証ではない**。入力 spec を与えていないため戻り値の値は意味を持たない。bit 突合は issue の範囲外。
- 前回の測定 (`196f37ef`) と上の値は全段で同じ (functions 148・insns 9,502・`kh.wasm` 25,295,206 B・total 24,441,216 B・cmp 14,820,487 B)。lift 経路 (`tools/flelift/x64c.py`・`fle_data_gen.py`・`rt/`) と `gain_before_160.tsv` は `196f37ef` から変わっていない (`git diff --stat 196f37ef f1c40af2 -- <それら>` は空)。
- unsup 285 site: 実行到達時は `ott_unsup` で停止する。多い順は `vmovsd` 32・`vmovntdq` 30・`vmovd` 29・`vmulsd` 25・`vaddsd` 23・`vmovq` 17・`vfmadd213sd` 16 (VEX / FMA 系)。`fle_lifted.c` の `ott_unsup` 行 (`by zero` の 3 行を除く) を `56c6f8cb` で数え直し、285 site・48 種で一致。

## 3. 閉包の差分 (x64c 148 vs TSV 160)

- 内訳 (件数と番地) は **[`REPORT_APPENDIX_3064.md` §1](REPORT_APPENDIX_3064.md)** が正本 (#3064 KH-37)。本節には再掲しない。
- 再現: `scripts/gain_x64c_closure.py` (§1 の最後のコマンド)。測定 commit `f1c40af2` で再実行し、APPENDIX §1 と一致することを確認した。
- 旧版の `closure_breakdown.py` は削除した (`f1c40af2`)。IAT thunk 判定が REX.W 付きの `jmp` を取りこぼしていたため。同じ分類を二重実装しない。

## 4. build の失敗点の記録 (同じ入力・手順の 3 試行)

| 試行 | 構成 | 結果 |
|---|---|---|
| A | 既定の VA のまま (`--img 0x180000000 --shift 0`) | compile 警告 0・link exit 0。ただし `_fle_data_install` が `RuntimeError: memory access out of bounds` で停止。VA の 64 bit 定数は 32 bit 番地へ切り詰められる (DEFECTS **D11** と同型) |
| B | shift `0x17E000000` (像を `0x2000000` 起点)・`fle_data_gen.py` は FLEngine 版のまま | **link 失敗** (最初の失敗点)。`fle_data.c:1018374:18: error: invalid suffix 'x' on integer constant` `memcpy((void*)0x-17dbd0990u, w_0, 48u);`。`-0x17dbd0990` = `0x42f670 - SHIFT (0x17E000000)` (python で確認)。`fle_data_gen.py` の `(0x42f670, 0x30)` (FLEngine の vtable 窓・#1936/#2005) は敷設先を `IMG + (VA - IMG) - SHIFT` で書くため、Kilohearts の像の外で負の番地になった |
| C | B + 窓を像の範囲内に限る (本 PR) | **成功**。§2 の実測 (compile・link・smoke の判定が通る) |

- 試行 B の原因箇所: `tools/flelift/fle_data_gen.py` の `for a, n in [(0x42f670, 0x30)]`。本 PR で `IMG <= a < IMG + SizeOfImage` の判定を足した。FLEngine (像内) では従来どおり追加される。
- 試行 A の補足 (未確認): 直書き窓は VA 版では `IMG + rva` が打ち消し合い `0x42f670` へ書き込む。emcc の静的領域と重なるかは確認していない。

## 5. FLEngine 側の回帰確認 (測定 commit `f1c40af2` で実行)

- `scripts/fle_data_gen_cmp.sh` (素材: `fl-win64` の `block00031_PE.bin`・meta は空の合成値 `{}`):
  - `cmp old/new: 一致 (14820487 B)` — 旧版 (`196f37ef^` の `fle_data_gen.py`) と新版 (`f1c40af2`) の出力が一致。
  - ネガティブコントロール `neg (shift 0x17E000000): 差分 200 byte` — shift を与えると出力が変わり、cmp が差を検出することを示す。
- 測定 commit 以降の変更: `git diff --stat f1c40af2 HEAD -- tools/targets/kilohearts/scripts tools/flelift` は空 (0 行)。`196f37ef` からの同じ範囲の差分は、本 PR の `fle_data_gen_cmp.sh` (新規)・`lift_closure_x64c.sh` (判定の 4 行) と、main 由来の `gain_x64c_closure.py`・`tools/flelift/boot/*` (lift 経路ではない)。
- 注意: 確認に使った `lift_meta.json` は空の合成値 (jt / textrefs / IAT なし)。FLEngine の全 lift (`fle_lift.sh`) は再実行していない (§6)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 確定 closure (手検証 160 との差分 0) の lift と build | 受入 1 の「確定 closure」は未確定。本節は未確定の before 160 | #3063 (KH-36・前提 #2176) |
| unsup 285 site (VEX / FMA 系 48 mnemonic 種) | 実行到達時に `ott_unsup` で停止 | #3065 (KH-38) |
| smoke は trap の有無しか見ない。入力 spec を与えていないため戻り値は意味を持たない。FLEngine の vtable 窓 (#1936/#2005) に当たる Kilohearts 側の窓が無いかは未検討 | 正しさは未確認 | #3063 |
| FLEngine の全 lift (`fle_lift.sh`) での回帰・`fle_data_gen.py` の FLEngine 固有窓 `0x42f670` の直書き (範囲判定で他 PE への誤用は防止) | §5 は敷設出力の一致のみ。窓の引数化は FLEngine 側の meta 生成に触れる | 親 #850 への提案 (PM 判断) |
| bit 突合 (native 対照) | 範囲外 (issue 本文) | 未定 (#3063 本文どおり。liftlib の差分ハーネスで別途扱う) |
