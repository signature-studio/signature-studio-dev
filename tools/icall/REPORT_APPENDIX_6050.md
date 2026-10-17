# tools/icall 付録 — #6050 (ICALL-124): 0x1803dee20 の xmm0 不一致 1 件の原因と既定化

親: #4348 (ICALL-116/101)。測定基準は #4348 の `6af773cb4` (main 未取り込みの commit)。

## 1. 結論

- **原因: lift / route / 範囲のどれでもなく、harness 側 (`tools/ott/native/ott_native.c` の `k_HeapAlloc`) の順序バグ。**
  `OTT_KEEP_XMM0=1` の経路が `xmm0` を退避する前に `getenv()` を初めて呼んでいた。libc の `getenv` が `xmm0` を書き換え、退避値が環境変数名の断片 `"OTT_KEEP"` (`5045454b5f54544f`) になっていた。
- **修正 (2 commit)**: (a) 退避を `getenv` より前に移す (`dd4e2b602`)、(b) 既定を ON にする。`OTT_KEEP_XMM0=0` で従来 (退避無し) に戻せる (`af7718c92`)。
- 修正の効果: `0x1803dee20` は既定で 0/8 → **8/8**。`fa_sweep.sh 8 60` の bit 一致は 55 → **56** (悪化なし)。

## 2. 事前の再現 (測定 commit `6af773cb4`、`fa_cmp.py 1803dee20 --n 8`)

| 設定 | match | mismatch | 不一致の値 (n=0) |
|---|---|---|---|
| 既定 (env 未設定) | 0 | 8 | native `0000000000000000` / wasm `c000c5300342457c` |
| `OTT_KEEP_XMM0=1` | 7 | 1 | native `5045454b5f54544f` / wasm `c000c5300342457c` |

## 3. 修正後の実測 (測定 commit `af7718c92`)

| 設定 | `fa_cmp 1803dee20 --n 8` | `fa_sweep.sh 8 60` (131 関数) |
|---|---|---|
| 既定 (env 未設定) | match 8 / mismatch 0 | bit一致 56 / native crash 64 / wasm のみ err 10 / 値の不一致 1 |
| `OTT_KEEP_XMM0=0` | match 0 / mismatch 8 (従来どおり) | bit一致 55 / 値の不一致 2 (`6af773cb4` 既定と同一) |
| `OTT_KEEP_XMM0=1` (`dd4e2b602`) | match 8 / mismatch 0 | bit一致 56 / 値の不一致 1 |

sweep の比較 (同じ 131 関数):

| 版 | bit一致 | 値の不一致 | 備考 |
|---|---|---|---|
| `6af773cb4` 既定 | 55 | 2 | 基準 (env 未設定) |
| `6af773cb4` KEEP | 54 | 3 | `getenv` の順序で `0x1803dee20`・`0x180cb5ef0` が不一致 |
| `dd4e2b602` KEEP | 56 | 1 | 順序修正 |
| `af7718c92` 既定 | 56 | 1 | 既定化 (本 PR) |

残る不一致 `0x180da4030` (既定・KEEP とも 0/8、native `0000…` / wasm `c000c5300342457c`) は本 issue の範囲外。未解決。

## 4. 変更の範囲と差分

測定 commit: `af7718c92`。`git diff 6af773cb4 HEAD -- tools/icall tools/ott/native` の出力は PR 本文に載せる。

## 5. 検証環境

- 素材: `work-icall`・`plugins-freshair`・`fl-win64`・`toolchain-retdec`・`toolchain-emsdk` を `$ARTIFACTS_DIR` から展開 (worktree `ws-6050`)。
- `bash tools/icall/fa_route_build.sh` rc 0 (`fa_route.cjs` 88,639 B)。`bash tools/ott/native/build.sh` で `libottnative.so` を再ビルド。
- sweep: `bash tools/icall/diff/fa_sweep.sh 8 60` 約 74 秒 (131 関数を 1 関数 1 プロセス)。
- sweep 出力の `missing function` は 7 件 (`function_1803b5546`・`function_18040ca0d`・`function_180ca1651`・`function_180da6084`・`function_181066530` 等の wasm 側の未解決 call)。`6af773cb4` 基準でも 7 件で、本 issue の修正では増減しない。受入条件の「0 件のまま」は基準時点で満たしていない。残件は #4348 に移す。
