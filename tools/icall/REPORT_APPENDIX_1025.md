# tools/icall 付録: #1025 (ICALL-17) Kilohearts Gain の icall 経路 wasm 化と native 差分

REPORT.md §15 相当。REPORT.md の 250 行上限のため別置き。親 #853 (ICALL-12)。

## 結論

**達成 (HEAD `63e150e2`・2026-10-14 19:35 UTC)**。wasm 実行は 61 シナリオ / 366 step すべて trap 0、全バッファと xmm0 が native と bit 一致 (366/366)。差分の原因は runner 側 (`_ott_data_install()` 未呼出しによる data 未敷設) で、`REPORT_APPENDIX_1025_FIX.md` に記す。これより前の節の「未達」「未特定」の記述は、この原因で説明がつく。

## 実測 (HEAD `a42f84e1`・`ws-1025` worktree・2026-10-13 21:36 UTC)

測定 run: PR #1247 の fix モード (レビュー指摘への対応)。HEAD `a42f84e1` を `ws-1025` worktree で実行。2 回 build して sha256 一致。

素材: `work-icall` を `tools/icall/work/` に展開 (`tar --zstd -xf`)。`plugins-kilohearts` / `toolchain-*` は `$ARTIFACTS_DIR` に実在を確認したが、本 build 経路では展開していない (emsdk は [EMSDK] を使用)。

| 項目 | 結果 | 実測 |
|---|---|---|
| 復元後 IR の後処理 (fix_mask / fix_vstore) | 成功 | `fix_mask` hi32_mask_fixed 2 / `fix_vstore` vstore_fixed 1, unresolved 83 |
| ir_flatten | 成功 | global defs removed 485, refs 300, i64 consts shifted 202, dispatch 表 164 entries (non-i64 ret wrapped 7) |
| m11_simd2 + vex_gen + simd_merge | 成功 | vex_generated 61 (unresolved 3: `__asm_vandnpd`・`__asm_vmovsd__27`・`__asm_vpcmpeqq`) / merge: extra_names 66, stubs_replaced_by_extra 63, fail_fast_installed 1, remaining_unimpl_stubs 13 |
| map.json | `blk` = `0x18a25c000`、`cfg_thunks` = `[]` | `python3` で読んだ値。`ncfg` 0 のため `ir_flatten.py --cfg ""` は正しい |
| emcc (-O0, メモリ 0x3c000000, BLK は map.json の `blk`) | 成功 | `kh_route.cjs` 107,844 B / `kh_route.wasm` 生成 (rc 0) |
| 再現 | 1 本 (rc 0) | `bash tools/icall/kh_route_build.sh` → rc 0。同一 worktree で 2 回 build し、`kh_route.cjs` / `kh_route.wasm` の sha256 が一致 |

**wasm のバイト数・sha256 はチェックアウトのパスに依存する**: `-g` のデバッグ情報に絶対パスが埋まるため、worktree が違うと値が変わる。受入値として使うのは「同一 worktree 内で 2 回 build して sha256 が一致すること」のみ。バイト数と build 時間は受入値にしない。

## 鮮度 (測定 commit から現 HEAD まで)

測定 commit `a42f84e1` (コードを変えた最後の commit。`kh_route_build.sh` のコメント修正と REPORT.md の空行削除)。上表は `a42f84e1` の worktree で実測した。`a42f84e1` から現 HEAD までのコード差分は 0 行。

```
$ git diff 44d70d74 a42f84e1 -- tools/icall/kh_route_build.sh tools/icall/ir_*.py tools/icall/rt tools/m2 tools/m5 tools/m11
diff --git a/tools/icall/kh_route_build.sh b/tools/icall/kh_route_build.sh
-# 1. 復元後 IR の後処理 (ICALL_FIX_MASK / ICALL_FIX_VSTORE は OTT と同じ既定 1)
+# 1. 復元後 IR の後処理 (fix_mask / fix_vstore を無条件に実行)
$ git diff a42f84e1 HEAD -- tools/icall/kh_route_build.sh tools/icall/ir_*.py tools/icall/rt tools/m*
(出力 0 行・exit 0)
```

`44d70d74..a42f84e1` の差分はコメント 1 行のみ (実行される行は不変)。`a42f84e1..HEAD` は 0 行。よって上表の数値は現 HEAD のコードに対しても有効 (再測定は不要, WORKFLOW §6)。

fix の内容: BLK を `map.json` の `blk` から取得 (旧 `0x3a25c000` は出典不明のハードコードだったため削除)、`ir_flatten.py --cfg` に `map.json` の `cfg_thunks` を渡す (OTT `ott_route.sh` と同じ生成式)。
`cfg_thunks` が空であることは上表の `map.json` の値で確認済み。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (解消済み) PE の .rdata/.data 敷設: 旧 `ott_data_install` 空定義は廃止し、`data_gen.py` で敷設 (実行段節参照) | wasm 実行の memory access out of bounds の原因候補だったもの | #1025 (本 issue) |
| wasm 実行と native (`liftlib/work/kh_gain/diff` 61 シナリオ) の差分 | 受入条件 1・2 が未達 | #1025 |
| 再現コマンド 1 本化 (実行・差分込み) | 受入条件 3 は部分達成 (`kh_route_run.sh` で実行・native 差分まで 1 本化済み。実行には素材 `plugins-kilohearts toolchain-retdec toolchain-emsdk work-icall work-liftlib` が必要。本 run では未再実行) | #1025 |

## 実行段 (本 run・2026-10-13 23:44〜00:00 UTC)

測定 commit: `a1830d497085222a26e0ae50e95c218d7c82b2cf` (`tools/icall/kh_route_build.sh` と `tools/icall/kh_route_run.sh` を変えた最後の commit。実行段の数値はこの commit の worktree で測定)。

`a1830d49..HEAD` の `tools/icall` のコード差分は 1 行の削除のみ (`s.replace(x, x)` は置換前後が同じ no-op のため、実行結果は不変)。付録自身の文言修正は除く (`git diff a1830d49 HEAD -- tools/icall ':!tools/icall/REPORT_APPENDIX_1025.md'` の出力):

```
diff --git a/tools/icall/kh_route_run.sh b/tools/icall/kh_route_run.sh
index ab3ba4c0..4a9d4642 100644
--- a/tools/icall/kh_route_run.sh
+++ b/tools/icall/kh_route_run.sh
@@ -19,7 +19,6 @@ b = "ret = M['_' + fname](...call);"
 assert s.count(a) == 1 and s.count(b) == 1, "wasm_runner.mjs の形が変わった"
 s = s.replace(a, "if (!M['_ott_run']) {")
 s = s.replace(b, "ret = M['_ott_run'](%d, ...call, ...Array(8 - call.length).fill(0n));" % va)
-s = s.replace("const sig = JSON.parse", "const sig = JSON.parse")
 open(dst, 'w').write(s)
 EOF
 cp "$NAT/scen.txt" "$W/scen.txt"
```

再現: `bash tools/icall/kh_route_build.sh && bash tools/icall/kh_route_run.sh` (素材 `fl-win64 plugins-kilohearts toolchain-retdec toolchain-emsdk work-icall work-liftlib`)。

| 項目 | 実測 |
|---|---|
| BLK | map.json `blk` (0x18a25c000) − 0x150000000 = `0x3a25c000` (前回の 0x18a25c000 は wasm32 の範囲外) |
| flatten 窓 | `--limit 0x0c000000`。既定 0x4800000 では icall section (0x18625c000) と BLK が窓外で shift されず、`memory access out of bounds` の原因だった |
| PE data | `data_gen.py` で `.rdata/.data/_RDATA` 敷設 (空定義を廃止)。`i64 consts shifted` 202 → 8123 |
| wasm | `kh_route.wasm` 50,762,457 B (PE data 込み) |
| wasm 実行 (61 シナリオ, native と同じ scen.txt) | trap 0 / 366 steps。`rax` 一致 173/366 |
| native との比較 | **bit 一致 61/366 steps**。不一致バッファ: self 305・P 293・L 291・R 290 (step 数) |

判定: **受入 1・2 は未達**。wasm が trap せず 366 step を返すところまで成立した。残る差分は float 系バッファ (`self` の f32 フィールド・`L`/`R` 出力) と `rax` の不一致で、原因は未切り分け (候補: `__asm_movss` 系 SIMD helper の lane 扱い、`__icall_comis` のフラグ、`ott_run` の引数 ABI)。

## 再測定と食い違いの特徴 (2026-10-14 01:56〜02:00 UTC)

測定 commit: `4ed14f65` (main)。`a1830d49..4ed14f65` の `tools/icall` 差分は `kh_route_run.sh` の no-op 削除 1 行のみ。`tools/m2 tools/m5 tools/m11 tools/ott/lift tools/liftlib/liftlib/harness` に差分なし。よって上の実行段の数値は本 HEAD のコードに対しても有効 (WORKFLOW §6)。

素材: `plugins-kilohearts` → Installer zip → payload.dat → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B。REPORT と一致)。`work-icall` / `work-liftlib` は main の checkout から worktree の `tools/` へ複製して使用。

| 項目 | 実測 |
|---|---|
| `kh_route_build.sh` | rc 0 / real 61.5 s |
| `kh_route_run.sh` | rc 0 / real 0.35 s / scenarios 61 / steps 366 / wasm_trap 0 |
| 最初の食い違い step | step 0 が 34 シナリオ、step 1 が 27 シナリオ (全 61 シナリオが step 1 以前で発散) |

比較値 (bit 一致・rax 一致)・食い違いの多いバッファは §実行段の表を参照 (再測定で同値)。

### 食い違いの観察 (未切り分け)

- step 0 は全バッファが一致し、`rax` も一致 (0x67)。発散は step 1 以降。
- 最初の発散の代表 (シナリオ 0・step 1): `self` の 16 bit 境界外 (+106) から始まる。`self` +104 は native `0x0000803c` (f32 0.015625)・wasm `0x00000000` (0)、+108 は native 1.0・wasm 0.5。+136 は native `0xb4fa3e3e` (0.186503)・wasm `0xa528083e` (0.132968)。
- 食い違いの頻度: `P` +8 (291)・`L` +0 (275)・`R` +0 (274)・`self` +104 (211)・`self` +106 (64)・`self` +107 (27)。half-word・byte 単位のずれが多く、部分幅ストア (`movss`・`movd` 系) の lane / merge 規則が疑わしい。
- `xmm0` 欄は step 0 で native `0x3e315071`・wasm `0`。(訂正済み: 末尾節参照。runner の表示上の差で、lift の差ではない)

判定: **受入 1・2 は引き続き未達**。wasm 実行は安定 (trap 0) したが、native と bit 一致するのは 61/366 step。食い違いの原因切り分けは次の入口 (下記) に残す。

### 次の入口

1. step 1 で最初に書かれる `self` の f32 フィールド (+104・+108) を生成する命令を、wasm IR 上で特定する (`insn.addr` を `rt_kilohearts-gain/after.0.restored.ll` の `!insn.addr` と突き合わせる)。
2. その命令が `__asm_movss` / `__asm_movd` 系 helper を経由するなら、helper の部分幅 merge 規則を native (`movss` 同等) と比較する。
3. (訂正済み: 末尾節参照。`xmm0` 欄の不一致は runner 側の表示だったので、次の入口には含めない。)

## 再測定と step 1 の差分の切り分け (2026-10-14 03:35〜03:41 UTC・HEAD `72260b63`)

測定 commit: `72260b63` (main)。`4ed14f65..72260b63` で `tools/icall`・`tools/m2`・`tools/m5`・`tools/m11`・`tools/ott/lift`・`tools/liftlib/liftlib/harness` に変更がある (`tools/m11` の `m11_build.sh`・`m11_post.py`・`m11_ov.c` 等)。そのため前回の値を流用せず、HEAD で再測定した。

素材: `plugins-kilohearts` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B) を `tools/icall/work/kh_pe/` に配置。`work-icall` / `work-liftlib` は main の checkout の `work/` を symlink で参照。

| 項目 | 実測 (HEAD `72260b63`) |
|---|---|
| `kh_route_build.sh` | rc 0 / real 1m03s (main の checkout で 1m10s) |
| `kh_route.wasm` | 50,762,353 B (PE data 込み。main の checkout で 50,762,457 B。差は絶対パス由来) |
| `kh_route_run.sh` | rc 0 / real 0.32 s / scenarios 61 / steps 366 / wasm_trap 0 |
| 比較 | bit 一致 61/366 steps / rax 一致 173/366 |
| 不一致バッファ (step 数) | self 305・P 293・L 291・R 290 |

前回 (`4ed14f65`) の 61/61 trap 原因は、PE data 敷設の欠如と BLK・メモリ量だった。現在の `kh_route_build.sh` は step 4 で `data_gen.py` により `.rdata` / `.data` / `_RDATA` を敷設し (`reloc fixed 29550`)、`map.json` の `blk` (0x18a25c000) を使う。よって「PE data 未敷設」は解消済みで、残る差分は data ではなく実行の中身にある。

### 差分の位置 (シナリオ 0)

- step 0: 全バッファ・rax (0x67) 一致。
- step 1: `self` の +104 / +106 / +107 / +108 / +110 と +136 / +152 などが不一致。`P` +8・+9・+10 も不一致。`L` / `R` は先頭から広く不一致 (native と wasm の出力が一致する範囲は少ない)。

| offset | native (f32) | wasm (f32) |
|---|---|---|
| self +104 | `0x3c800000` (0.015625) | `0x00000000` (0) |
| self +108 | `0x3f800000` (1.0) | `0x3f000000` (0.5) |
| self +136 | `0x3e3efab4` (0.186503) | `0x3e0828a5` (0.132968) |
| self +152 | `0x3e348942` (0.176305) | `0x3e05ed8b` (0.130789) |

+108 は下位 byte だけの食い違いではなく、値そのものが別。よって「部分幅ストアの merge 規則」だけでは説明がつかない。step 0 の出力に現れない状態 (xmm レジスタ・フラグ・step 間で持ち越す値) が step 1 の入力に入っている可能性がある。これは仮説で、未検証。

### 切り分けの結論

- 「PE data 未敷設が trap の原因」→ 解消済み (trap 0)。
- 「部分幅 store の lane 規則のみ」→ +108 の値が丸ごと異なるため、単独の原因とは言えない。未確定。
- 未確認: step 1 入力の xmm / フラグが `out_native.txt` と `out_wasm.txt` のどちらでも比較されていないこと。`ott_xmm0` の読み出しは末尾節で修正済み (訂正済み: 末尾節参照)。

### 次の入口 (更新)

1. `scen.txt` の step 1 入力 (`self` / `P` / `L` / `R` / xmm0〜15 / flags) を native 側の trace (`liftlib/work/kh_gain/diff/native_runner`) と突き合わせ、step 1 の入力が一致するかを先に確定する。入力が違うなら、比較対象は step 間の状態持ち越しの扱い。
2. 入力が一致する場合のみ、step 1 で `self+108` を書く命令を `rt_kilohearts-gain/after.0.restored.ll` の `!insn.addr` から特定する。
3. `ir_flatten` の `--table` (dispatch 表 164) 経由の呼び出しで、戻り値の float 扱い (`ott_xmm0`) を確認する。

## runner 修正と xmm0 欄の訂正 (2026-10-14 06:04〜06:25 UTC)

測定 commit: `4d131493` (`tools/icall/kh_route_run.sh` を変えた最後の commit)。`4d131493..HEAD` のコード差分 (`tools/icall`) は 0 行。素材は ws-1025 worktree の `work/` に展開 (`work-icall` / `work-liftlib` / `kh_pe/HeartCore.core_64`)。

- 訂正: 前節までの「xmm0 欄の不一致 (native `0x3e315071`・wasm `0`)」は lift の差ではなく runner の表示上の差だった。`kh_route_run.sh` が複製する `wasm_runner.mjs` は R 行の xmm0 を常に `0` で出力していた。commit `4d131493` で `M._ott_xmm0()` を読むよう修正 (native_runner の `xmm0_out[0]` と同じ意味)。
- 修正後の実測 (測定 commit `4d131493`・ws-1025 worktree・再現コマンド `bash tools/icall/kh_route_build.sh && bash tools/icall/kh_route_run.sh`):

| 項目 | 実測 |
|---|---|
| `kh_route_build.sh` | rc 0 / real 1m13s (`kh_route.wasm` 50,762,457 B) |
| `kh_route_run.sh` | rc 0 / real 0.33 s / scenarios 61 / steps 366 / wasm_trap 0 |
| 全バッファ bit 一致 steps | 61/366 (step 0 は全 61 シナリオ一致) |
| xmm0 一致 steps | 73/366 (step 1 は 11/61) |
| 不一致バッファ (step 数) | self 305・P 293・L 291・R 290 |
| rax 一致 | 173/366 だが参考値。rax は wasm / native で address space が異なるポインタを含むため判定に使わない |

- step 1 (シナリオ 0) の `self` 不一致は 9 bytes: offset 106・107・110・136〜138・152〜154。`self+104` は native `0x3c800000` (0.015625)・wasm `0x00000000` (0)。`self+108` は native `0x3f800000` (1.0)・wasm `0x3f000000` (0.5)。
- 0x3c800000 (0.015625) はイメージ内の `.rdata` 範囲 (0x13a1000〜) 以外にも複数箇所に現れ、`data_gen.py` の敷設対象 (`.rdata`/`.data`/`_RDATA`) で値が出るかは未確認。`.text` 側の即値・`.pdata`・`.rsrc` 由来の可能性を含めて未切り分け。
- step 0 で全バッファ一致しているため、step 1 で初めて現れる入力 (step 0 の出力で更新された状態、もしくは `ott_run` の引数 ABI) が疑わしい。`ms_ctx` は native 側で毎回 `memset` されており、状態の持ち越しは native に無い。wasm 側の持ち越しは未確認。

判定: 受入 1・2 は引き続き未達。受入 3 (再現 1 本) は build + run で実行まで通ることを確認済み。

## movups 欠落の修復と comis 入力の採取 (2026-10-14 17:23〜17:40 UTC)

測定 commit: `8d26ce7c` (`tools/icall/ir_fix_vstore.py`・`kh_route_build.sh`・`tests/test_icall.py` を変えた最後の commit)。`8d26ce7c..HEAD` のコード差分は本節の文言のみ (下記 `git diff`)。

素材: `plugins-kilohearts` → Installer zip → payload.dat → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B) を `tools/icall/work/kh_pe/` に配置。`work-icall` / `work-liftlib` は main checkout の `work/` を symlink で参照。

| 項目 | 実測 (commit `8d26ce7c`) |
|---|---|
| `kh_route_build.sh` | rc 0 / real 40.8 s / `kh_route.wasm` 50,774,295 B |
| `kh_route_run.sh` | rc 0 / real 0.195 s / scenarios 61 / steps 366 / wasm_trap 0 |
| bit 一致 | 61/366 (直前 HEAD と同値) |
| 不一致バッファ (step 数) | self 305・P 293・L 291・R 290 (直前 HEAD と同値) |
| `fix_vstore` | fixed 1 / **direct 63** / unresolved 20 (直前: fixed 1 / unresolved 83) |

### 1. 欠落していた store (修復済み・差分の原因の一部)

kh_gain 本体 `0x1804b03d1` の `movups [self+104], xmm` は、RetDec が `%50 = load [%49]` と `call void @__asm_movups(i128 %50, i128 %47)` に落とし、no-op helper のまま残っていた (`%49 = inttoptr (%0+104)`・`%0` = self)。`ir_fix_vstore.py` は宛先が alloca でないため unresolved とし、16 バイト store が wasm から消えていた。

`--direct` (既定 off・kh 経路のみ on) で、宛先 `%P` の load と helper 呼出しの 2 箇所しか使われないものを `store i128 %S, i128* %P` に置換する (63 件)。既定 off の出力は、kh 経路の入力 IR で旧版と完全一致 (`cmp` 0 差分)。OTT/FA 経路 (`ott_route.sh`・`fa_route_build.sh`) は既定 off のため変化しない。

修復後も bit 一致件数は変わらない (61/366)。この store だけでは step 1 の差分は説明できない。

### 2. 分岐条件の入力 (debug build で採取・リポジトリには含めない)

`0x1804b03d1` の直前の分岐は `ucomisd(a, 1e-15)` の CF で決まる (`a = |xmm0 − self[+112]|`、`CF=1` で store 経路)。debug 版 (`__icall_comis` に fprintf を入れた一時ビルド、scenario 0 のみ) で採取した値:

| step | comis: a (BLK+0xA0) | b (BLK+0xA8) | fl (BLK+0xB0) | comis 時の self+112 | native の直前 step 後の self+112 |
|---|---|---|---|---|---|
| 1 | 0 | 1e-15 | 1 (CF=1) | 1.0 | 1.0 (step 0 後) |
| 2 | 0 | 1e-15 | 1 | 0.5 | 0.5 (step 1 後) |
| 3 | 0 | 1e-15 | 1 | 0.5 | 0.5 (step 2 後) |
| 4 | 0 | 1e-15 | 1 | 2.5 | 2.5 (step 3 後) |
| 5 | 0 | 1e-15 | 1 | 3.0 | 3.0 (step 4 後) |

(step 0 では comis は呼ばれない。)`self+112` の入力値は native と一致する。一方、`a = 0` は xmm0 ローカル (`%xmm0.0.reload`) が 1.0 であることを意味する。`%xmm0.0.reload` の出所は IR 上 `%14 = load [ctx+12680]` (P のポインタ) → `movss [%14+4]` の経路が候補だが、**未検証**。native 側の `a` と xmm0 ローカルの値は未取得。

### 3. 未解決 (起票先: #1025 本体)

- step 1 の `self+104` 最終値は native `0x3c800000` (0.015625)・wasm `0`。`shufps(movq(xmm0), 2)` の lane 0 は定義上 0 なので、この値は修復した store ではなく、後続の別 store か別経路で書かれる。未特定。
- native 側の comis 入力 (`a`・xmm0 ローカル) が wasm と一致するかは未確認。native の trace が無いため (`native_runner` は ll_ms_call 内部を見られない)。
- 残 unresolved 20 件は `__asm_vmovdqa.25` 系 (i256)。fail-fast stub で、本 run の trap 0 から実行されていないと見てよい (間接確認)。

### 次の入口

1. wasm 側で `self+104`〜`self+119` への書込みを全て log する debug 版を作り、step 1 の最後の書込みを特定する (`!insn.addr` で IR に対応付ける)。
2. native 側は gdb (`ll_ms_call` の直後で `self+104` の watchpoint) で同じ書込みを取り、値と命令を照合する。gdb が無ければ native_runner に一時 trace を入れる。
3. 上 2 点が揃った後に、`xmm0.0.reload` の出所 (`ctx+12680` → P) の値を native と比較する。

### 判定

受入 1・2 は引き続き未達。受入 3 (再現 1 本) は build + run まで実行できることを再確認 (上表)。
