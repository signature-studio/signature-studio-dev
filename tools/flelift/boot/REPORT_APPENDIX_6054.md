# FLE-51 (#6054): 0x4080a2 の rsi と 0x6b91e8 残骸の影響 (部分達成)

> 親: #4426 (受入 1 の子)。前提: `REPORT_APPENDIX_4004.md` §6-b (残骸の読出し 17 件・読出し元は未特定)。
> 測定 commit: `11771b9ad` (コードを変えた最後の commit。既定経路のコードはこの commit で固定)。
> 既定経路の測定 (§3・§4) はこの commit の `fle6_measure.sh`・`rsi_4080a2_probe.sh` で採った。
> zero 変種 (§5) は `rsi_zero_variant.sh` を含む `2e7f70d6c` (同 PR の別 commit・このスクリプトを追加した commit) で採った。
> 差分: §8 (`git diff 11771b9ad HEAD -- tools/flelift`)。

## 1. 結論

- **既定経路 (FLE_IPP 未指定・mode 3) では 0x6b91e8 は実行されない**。ippsZero_8u の呼出しは 0x67264d の 1 件だけ (len 0)。0x6b91e8 の未適用は既定経路では起きない。
- **残骸そのものは既定経路に存在する**。0x4080a2 の呼出しで rsi = `dst` (`0x12d777d0`) の一致を 3 回確認 (`nz40` = 19〜20)。戻り後 (0x4080af) も残骸 (`nz40` = 15) が残る。
- **残骸を消す対照 (zero) は GetMem を 3680 → 3681 に変える** (base 3 run・zero 2 run で各々一定)。残骸の有無で guest の動作が変わった可能性があるが、配置の変化 (下記 §5) と区別できていない。出力の hash は run ごとに揺れるため、hash の差からは影響の大きさを言えない。
- 受入 (「既定経路の出力に影響するか」) は**未達**。影響の判定には、残骸を読んで分岐する箇所の特定 (2 の未確認) が要る。

## 2. 未確認 (次の一手)

- 残骸を読んで GetMem 数が変わる経路 (zero 変種で `GetMem` が +1 になる理由)。読出し元の関数を特定し、分岐条件まで追う。
- zero 変種の出力差が、非決定位置 (base 同士の差 2,635 B) を超えるかの判定。byte 単位の差は heap 配置のずれで 1,700 万 B 規模になり、単純な差分では判定できない。

## 3. 測定 (既定経路・mode 3)

環境: 4 vCPU・`fl-win64` と `toolchain-emsdk` (6.0.12) を `$RUNNER_TEMP` に展開。`fle6_measure.sh` (`FLE_BOOT_RUNS=default`・`FLE_EXTRA_ROOTS=` 空)。

| 項目 | 値 |
|---|---|
| 所要 (`time`) | 3 分 29 秒 (lift 80 s・clang-plain 111 s・boot 11 s) |
| rc | 0 |
| units_run / stopped_at | 895 / 895 (`boot_threw=exit`) |
| GetMem / FreeMem | 3680 / 1499 |
| IPP | mode 3・`ptr_15F34A0=0x7f10001c` ok |
| `ippsZero_8u` 呼出し | 0x67264d の 1 件 (len 0) のみ |

## 4. 0x4080a2 の rsi と dst (`rsi_4080a2_probe.sh`)

範囲フィルタ (`[0x12d777d0, +0x28)`) で出力し、総数は `tot` で数えた (件数上限で打ち切らない)。

| route | 0x4080a2 で rsi=dst | 0x6b91e6 (ippsZero 直前) | 結果 |
|---|---|---|---|
| 既定 (mode 3) | 3 件 (tot 249〜251) | 0 件 | units 895・exit |
| `FLE_IPP=0` | 4 件 (tot 249〜252) | 1 件: `dst=12d777d0 len=28 nz40=20` | units 209・unlifted |

- `FLE_IPP=0` の 0x6b91e6 は、前回記録 (`REPORT_APPENDIX_4004.md` §2) の dst `0x12d777d0`・len `0x28`・非 0 20 バイトと一致。
- 既定の 0x4080a2 の `rsi` は全 run で `0x12d777d0`。残骸の 40 バイトのうち非 0 は 19〜20。

注: 4004 の既定 `0x12d677d0` と今回の `0x12d777d0` は 0x100000 ずれる (4004 §6-b と同じ)。

## 5. 残骸を消す対照 (`rsi_zero_variant.sh`)

既定経路 (mode 3) で、0x4080a2 の入口で rsi が dst 範囲なら 40 バイトをゼロにする変種 (zero) を作り、既定 (base) と比べる。

| 変種 | run | GetMem | outmem.full (先頭 16 文字) | dst 40 B (先頭 8 バイト) |
|---|---|---|---|---|
| base | d1 | 3680 | `e60181baa5439065` | `38c35a00 b0040200` |
| base | d2 | 3680 | `4708aa0e8de9e442` | `38c35a00 b0040200` |
| base | s (rsizero_base) | 3680 | `97df89d400f2a15d` | (未採取) |
| base | r1 (再実行) | 3680 | `2cd796291f86a4c9` | (未採取) |
| base | r2 (再実行) | 3680 | `e2c97d22b98287a1` | (未採取) |
| zero | d1 | 3681 | `5aa503ef0787784f` | `00000000 b0040200` |
| zero | d2 | 3681 | `77c08c4e2265168b` | `00000000 b0040200` |

- `d1`・`d2` は `FLE_OUTMEM_DUMP` 付きの run (線形メモリ dump あり)。`s`・`r1`・`r2` は dump なしの run で、hash だけ採った。
- `outmem.full` は base だけで 5 通りに揺れる (非決定)。zero の値は base の揺れの範囲外に見えるが、zero は stack/heap 配置も変えるので、値の差だけでは判定しない。

- base 同士の差: 2,635 B (非決定位置)。`outmem_compare.py` の判定は base 同士でも FAIL (`image_writable` 不一致)。
- zero と base の差: 約 1,700 万 B。大半は C スタック・heap の配置が 0x10 ずれたことによる (`stack.base` 0x11dd2150 → 0x11dd2160)。
- dst の残骸 (`0x12d777d0`〜) は zero で 0 になり、base は残る (base 2 run で同値)。

## 6. 影響の判定 (受入 1)

残骸を消す (zero) と GetMem が 3680 → 3681 になった。残骸が後続の動作に効いている根拠の一つだが、因果は未確認 (配置のずれとの区別がない)。出力 (`image_writable`) の変化の有無は、非決定位置を除いた比較でも判定できなかった (base 同士で既に揺れる)。**受入 1 は未達**。

## 7. 再現

```sh
FL_WIN64_DIR=<fl-win64 展開先> SS_EMSDK_ENV=<emsdk_env.sh> FLE_BOOT_WORK=<work> \
  FLE_BOOT_RUNS=default FLE_EXTRA_ROOTS= bash tools/flelift/boot/fle6_measure.sh
bash tools/flelift/boot/rsi_4080a2_probe.sh                  # 既定 (mode 3)
FLE_IPP=0 bash tools/flelift/boot/rsi_4080a2_probe.sh        # ネガコン
bash tools/flelift/boot/rsi_zero_variant.sh                  # base / zero の対照
```

素材: `oc_artifacts: fl-win64 toolchain-emsdk`。

## 8. 測定 commit 以降の差分

`git diff 11771b9ad HEAD -- tools/flelift` の結果 (新規 2 件のみ・既存の既定経路のコードは変更なし):

```
A	tools/flelift/boot/REPORT_APPENDIX_6054.md
A	tools/flelift/boot/rsi_zero_variant.sh
```

`fle6_measure.sh`・`fle_boot.mjs`・`rt/`・`x64c.py`・`rsi_4080a2_probe.sh` は差分 0。

## 9. 読出し元の特定 (既定経路・mode 3・FLE_RWATCH)

測定 commit: `fe48dca85` (origin/main。このPR で変えたのは本ファイルだけ)。
条件: `FLE_BOOT_RUNS=default FLE_EXTRA_ROOTS= FLE_EXTRA_CCF="-DFLE_RWATCH -DFLE_RWATCH_LO=0x12d777e8ull -DFLE_RWATCH_HI=0x12d777f8ull" bash tools/flelift/boot/fle6_measure.sh`。
ビルドだけ読出し監視を入れ、経路 (mode 3) は §3 と同じ。

- 結果: rc 0・units 895・stopped_at 895・exit・GetMem 3680・FreeMem 1499・IPP mode 3 ok (§3 と一致)。
- 所要: 3 分 51 秒 (fle6_measure.sh 全体)。boot のみ 10 秒。
- 残骸範囲 [0x12d777e8, 0x12d777f8) (= dst+0x18〜+0x27) に重なる読出しは 42 件。

| 読出し元 (lift 生成 C の行 → guest VA) | 関数 | 読出し | 件数 |
|---|---|---|---|
| fle_lifted_s7.c:47128 (0x475bae) | f_475ba0 | `movzx r8, byte [rcx]` (8 bit) | 12 |
| fle_lifted_s7.c:42093 (0x44f601) | f_44f5d0 | `movzx rdx, word [rcx]` (16 bit) | 4 |
| fle_lifted_s4.c:36673 (0x439512) | f_4394e0 | `movzx r8, word [rdx]` (16 bit) | 4 |
| fle_lifted_s6.c:38313 (0x43c4f5) | f_43c4c0 | `cmp word [rax+rcx*2], 0x2e` (16 bit) | 1 |
| fle_lifted_s3.c:31030 (0x409ca7) | f_409c80 | `mov r9, [rcx+rax-8]` (64 bit) | 1 |
| fle_lifted_s6.c:33493 (0x412d68) | f_412d60 | `mov rax, [rbx]` (64 bit) | 1 |
| `fle_cpu.h:92` (読出しヘルパ・16 バイト読出し) | 呼出し元は未特定 | 16 バイト (n=16) | 19 |

- `fle_cpu.h:92` の 19 件は 16 バイト読出し (16 バイト単位の copy)。読出しヘルパの行が出るため、呼出し元の関数は特定していない。`rsp_val` は 0x4080a7 (0x4080a2 の `call` の戻り番地) と 0x4130a2 が出る。
- `rsp_val` は読出し時の `[rsp]` であり、読出し元の戻り番地ではない (§6-b と同じ注意)。

### 判定の状況

- 残骸の読出し元は 6 関数 + 16 バイト copy (呼出し元未特定) に絞れた。
- f_44f5d0 は読んだ文字を bitmap (`bt`) の添字に使い、f_43c4c0 は `'.'` (0x2e) と比べて分岐する。残骸の値が分岐条件に入るのはこの 2 箇所 (計 5 件)。
- この分岐の結果が出力 (`image_writable`) に届くかは未確認。出力の書込みまで追う必要がある。
- zero 変種の GetMem 3680 → 3681 (§5) の因果も未確認のまま。

**受入 1 は未達** (部分達成)。
