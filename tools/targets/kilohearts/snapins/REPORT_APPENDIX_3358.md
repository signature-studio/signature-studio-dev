# REPORT_APPENDIX_3358 — #3358 (KH-54) vmovaps store 形の復元検証 (生出力・差分)

`REPORT.md` §16 の詳細。要約と判定は REPORT.md §16 が正本。

## 測定条件

- 測定 commit: `40000edd8` (コードを変えた最後の commit。以降の変更は REPORT のみ)。
- コマンド: `cd tools/targets/kilohearts && python3 snapins/scripts/vmovaps_store_check.py 20000 1`
- 実行: rc=0 / real 4.48 s / 実行後 load 0.27 0.28 0.12 (nproc=4)。
- 再実行 (同じ commit・生出力を下に載せた回): rc=0 / 実行後 load 0.01 0.15 0.10。

## 生出力 (rc=0)

```
[kh_passes storelow] {'patched': 1, 'unfixed': [], 'vmovaps256': 1}
== 本検証 (pass 復元 32B store vs ホスト AVX2) n=20000 seed=1
  復元 IR: store 1 件 (call なし)
  vmovaps_store calls=20000 bytes=640000 mismatch=0
== 本検証 (接尾辞なし @__asm_vmovaps) 復元 IR: store 1 件 (call なし) / vmovaps_store calls=20000 bytes=640000 mismatch=0
== ネガコン (a) pass を外す (呼出が残り abort スタブで FAIL)
  rc=-6 -> FAIL (期待どおり)
== ネガコン (b) 復元 store を no-op に改変 (不一致 > 0 で FAIL)
  vmovaps_store calls=20000 bytes=640000 mismatch=20000
  rc=1 -> FAIL (期待どおり)
== 判定: 本検証 PASS / ネガコン(a) FAIL / ネガコン(b) FAIL -> PASS
rc=0
```

## 検証の内容

- 入力: RetDec 形 `call void @__asm_vmovaps.2(i256 %old, i256 %val)` (+ 接尾辞なし版) を `kh_passes.pass_storelow` に通す。
- 復元 IR: `store i256 %val, ptr %pd, align 1` 1 件・`call` 無し (`vmovaps256: 1`)。
- 突合: 32B 全 bit を `_mm256_loadu/storeu` (ホスト AVX2) の結果と比較。dst の初期値は src と必ず異なる (store が消えたら FAIL)。
- ネガコン: (a) pass 無し → 呼出が abort スタブへ落ち rc=-6。(b) 復元 store を no-op に改変 → mismatch 20,000 / 20,000。

## 差分 (測定 commit 以前 → 測定 commit)

- `git diff 4a8c4e0a5 40000edd8 -- tools/targets/kilohearts/snapins`: `scripts/vmovaps_store_check.py` のみ (+8 行・接尾辞なし case の追加)。
- 測定 commit → HEAD の lift/harness/scripts の差分: 測定後は REPORT のみ (`git diff 40000edd8 HEAD -- tools/targets/kilohearts/snapins/lift tools/targets/kilohearts/snapins/harness tools/targets/kilohearts/snapins/scripts` = 0 行)。

## 未解決の詳細

- `align 1` の扱い (元 VEX の 32B 整列要求との差) は REPORT.md §16 の m1 を参照。
- RetDec 実 IR での再実行は素材 `toolchain-retdec` が無いため未実施 (#3259 で snap-in 側を確認)。
