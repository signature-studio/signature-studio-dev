# REPORT 付録 (#5310 KH-149): Delay の void 宣言の関数の戻り値 (機械語で確認)

親 #4686 (KH-109)・上位 #4672 (KH-107)。#4686 が残した Delay の void 戻り値の emcc error 4 件 (issue 本文の行 2121・3968・4329・5001) を、呼出元の機械語で 1 件ずつ確認する。

## 結論

- 4 件の呼出し点は **全件、呼出し直後に戻り値のレジスタを読んでいる** (機械語で確認)。void 宣言は誤り。
- ただし issue 本文の行番号と呼出元は一部ずれていた (下の表)。emcc の行番号は測定条件 (FX) で変わる。
- 戻り値の型を C 本体で返す規則 (`ABI` / `DELAY_RULES`) は **本 PR では入れない**。4 件の callee 本体の戻り値型を確定し、Gain/Haas/Gate の `.o` 不変を確かめてから入れる (子 issue に分割)。
- 1 件 (`FUN_180fd27a8`) は本体が `return;` で、呼出元の `ax` 読みと矛盾する。本体の戻り値の決定が未了。

## 測定条件

- 測定 commit: `e5261de58` (`origin/main` 取り込み後・コード変更は本 PR の `void_ret_check.sh` のみ)。
- 素材: `plugins-kilohearts` → Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B、sha256 先頭 16 桁 `d55ce8b4c0ad7ebe` 一致)。
- `[GHIDRA]` 12.1.4 (zip sha256 先頭 16 桁 `ddac49f903da9d5b` 一致)・JDK 21 (temurin-21)・`[EMSDK]` 6.0.12。
- 作業ディレクトリは repo 外 (`$RUNNER_TEMP/kh149`)。`work/winpkg/` は gitignore。
- `gtype_census.sh` 既定 FX (`bitcast,intload,stackpair,assoc,concat,gtype`)。decompile 151/151 OK・所要 57.9 s・load 0.94 (4 vCPU)。
- 同じ census の delay emcc error 行は **315** (`REPORT_APPENDIX_5664.md` の既定 FX の値と一致)。Gain/Haas/Gate の `.o` は 1435 / 3217 / 3756 B (REPORT の基準と一致)。
- 基準 FX (`bitcast,intload,stackpair,assoc,concat,gtype,lanes`) では error 行 283。行番号は FX で動くため、以下の行番号は既定 FX の生成 C に対するもの。

## 4 件の呼出し点 (emcc error ↔ 機械語)

| issue の行 | 既定 FX の生成 C の行 | 呼出元 (生成 C の関数) | 呼出先 (生成 C の宣言) | 呼出し番地 | 呼出し直後に読むレジスタ (機械語) | 戻り値を使うか |
|---|---|---|---|---|---|---|
| 2121 | 2122 | `FUN_1802ed790` | `FUN_180fc4590` (`void`) | `1802ed7c1` | `cvtsd2ss xmm0,xmm0` (xmm0) | 使う |
| 3968 | 3968 | `FUN_180fc6d70` | `FUN_180fdc880` (`void`) | `180fc7004` | `movsd xmm2,xmm0`・`mulsd xmm2,xmm0` (xmm0) | 使う |
| 4329 | 4329 | `FUN_180fcdbfc` | `FUN_180fd27a8` (`void`) | `180fcdc2d` | `movzx ecx,ax` (ax) | 使う |
| 5001 | 5001 | `FUN_180fd2a60` | `FUN_180fe24b8` (`void`) | `180fd2a64` | `test rax,rax` (rax) | 使う |

- 4329 は issue 本文の `FUN_180fd27a8` で合っている。ただし `#4686` の停止報告の `FUN_180fbde90` 側 (同じ行の `sVar1 = FUN_180fbde90();`) は別件で、本 issue の 4 件には含めない。
- 2121 → 2122、3968・5001 は issue と同じ行。

## 戻り値の本体 (生成 C の `return`)

| callee | 生成 C の宣言 | 本体の return (生成 C) | 判定 |
|---|---|---|---|
| `FUN_180fc4590` | `void` | `return (ulonglong)((uint)fVar3 \| 0x400000);`・`return CONCAT44(uVar4,f2u(fVar2));` | 本体は値を返す。宣言が誤り |
| `FUN_180fdc880` | `void` | `return uStackX_8;` | 本体は値を返す。宣言が誤り |
| `FUN_180fd27a8` | `void` | `EnterCriticalSection(...)` の後 `return;` | **本体は値を返さない**。呼出元の `ax` 読みと矛盾 (未確定) |
| `FUN_180fe24b8` | `void(void)` | `return uVar2 >> bVar1 \| uVar2 << 0x40 - bVar1;` | 本体は値を返す。宣言が誤り |

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `FUN_180fd27a8` の戻り値 (本体 `return;` と呼出元 `ax` の矛盾)。呼出元 9 件の全件精査 | 4329 の規則を決められない | #5310 (Refs・子 issue に切り出し) |
| 3 件 (`FUN_180fc4590`・`FUN_180fdc880`・`FUN_180fe24b8`) の戻り値型を `ABI`/`DELAY_RULES` に入れ、emcc error 0 件と Gain/Haas/Gate `.o` 不変を確かめる | 2122・3968・5001 が未解消 | #5310 (Refs・子 issue) |
| Delay の数値検証 (戻り値の型を変えた後の bit-exact) | emcc 通過だけでは値は言えない | #3073 [KH-41] |

## 再現

```
bash tools/targets/kilohearts/ghidra_route/void_ret_check.sh <HeartCore.core_64>
```

出力は 4 呼出し点の call と直後 6 命令。判定は上の表。

HeartCore.core_64 の実出力は **未取得** (素材 `plugins-kilohearts` が取得されておらず、この run では展開できなかった)。表の番地・レジスタは、取得後に上のコマンドの出力と照合して確定する。

照合ロジックの確認 (テスト用 ELF・`gcc -O0` で作った 2 関数・objdump 表記 `call   1030` = `0x` なし)。修正後の照合で一致する:

```
== 1102 call 1030
    1102:	call   1030 <__cxa_finalize@plt>
    1107:	call   1070 <deregister_tm_clones>
    110c:	mov    BYTE PTR [rip+0x2efd],0x1        # 4010 <__TMC_END__>
    1113:	pop    rbp
    1114:	ret
    1115:	nop    DWORD PTR [rax]
    1118:	ret
```
