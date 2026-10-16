# REPORT_APPENDIX_5862 — Delay の型不一致 4 件 (1335・1340・2667・2759) の種類と規則 (KH-177)

issue #5862 の受入条件の測定正本。親 #4672 の一部。

## 測定条件 (実測・n=1)

- 基点 commit: `origin/main` (27706c23a)。census は `FX=bitcast,intload,stackpair,assoc,concat,gtype` で `gtype_census.sh` を使う。
- 素材: `plugins-kilohearts` → Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B、REPORT と一致)。
- Ghidra 12.1.4 (sha256 `ddac49f9…d2db` 一致)、JDK 21。emcc 6.0.12。すべて repo 外 (`$RUNNER_TEMP/kh`)。
- 測定時の負荷: load average 1.16〜1.19 (4 vCPU)。census の所要 35 s 前後。

## 4 件の型不一致 (基点で確認)

| 行 | 種類 | 呼出先 (宣言) | 機械語で確認した戻り値の読み手 | 既存の規則 | 判定・本 PR |
|---|---|---|---|---|---|
| 1335 | void 代入 | `FUN_180f878e0` (`void`) | 呼出元 `18004cf20` が call 直後に `rax` を読む | なし | 新規。**本 PR では未投入** (子 issue へ) |
| 1340 | void 代入 | `FUN_180f878e0` (`void`) | 同上 | なし | 同上 |
| 2667 | void 代入 | `FUN_180fcf904` (`void`) | 呼出元 `180fbbfb8` が call 直後に `ax` を読む (`movzx ecx,ax`) | 引数側のみ。宣言は未投入 | 新規。**本 PR で投入** |
| 2759 | void 代入 | `FUN_180fcf904` (`void`) | 呼出元 `180fbc1f4` が call 直後に `ax` を読む (`movsx ecx,ax`) | 同上 | 同上 |

## 規則の内容

- `FUN_180fcf904`: 宣言 `void` → `short` (`patches.py` の `ABI['delay']`)。本体の `return;` を `return FUN_180fbdfcc(...)` に直す (本体は `FUN_180fbdfcc` の `ax` を素通しする・機械語 `180fcf904` で確認)。
- `FUN_180f878e0`: **投入しない**。宣言を `ulonglong` にすると、本体の `return;` 4 箇所 (`-Wreturn-mismatch`) が新たな error になる。本体の値付けは意味の補正に当たるため、既存の #4686 (KH-109・同じ関数の戻り値・OPEN) の範囲に残す。

## 測定結果 (census・`gtype_census.sh`)

| 条件 | delay emcc error | 1335 | 1340 | 2667 | 2759 | Gain .o | Haas .o | Gate .o |
|---|---|---|---|---|---|---|---|---|
| 基点 (`origin/main`・規則なし) | 309 | 残 | 残 | 残 | 残 | 1,435 | 3,217 | 3,756 |
| 宣言 `FUN_180f878e0` も投入 | 307 | 残 (`-Wreturn-mismatch` に置換) | 同左 | 消 | 消 | 1,435 | 3,217 | 3,756 |
| **本 PR (`FUN_180fcf904` のみ)** | **306** | **残** | **残** | **消** | **消** | 1,435 | 3,217 | 3,756 |

- Gain/Haas/Gate の `.o` は、旧規則 (`origin/main` の ghidra_route) との `cmp` で 3 本とも一致。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `FUN_180f878e0` (rax・8 byte) の宣言と本体の値付け (`return;` 4 箇所) | 1335・1340 が残る (delay emcc error 2 件) | #4686 [KH-109] (既存・OPEN) |
| 4329・5001 (void 代入) | delay の emcc error の一部 | #5310 [KH-149] |
