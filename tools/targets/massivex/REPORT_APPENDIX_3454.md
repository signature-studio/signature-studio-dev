# Massive X REPORT 付録 (#3454 MX-35 分割移動・§11.5)

本体 `REPORT.md` の 250 行上限のため、§11.5 (dsp unsup 基準の更新と NC3 の相対判定) を分割移動した (内容は無変更)。

### 11.5 dsp unsup 基準の更新と NC3 の相対判定 (#3454・2026-10-15 実測)

- 測定 commit = **`458405518`** (NC3 修正 = コミット A)。同 commit の detached worktree (`$RUNNER_TEMP` 配下・検証後 remove) で `dsp/e2e.sh` → `dsp/negctl.sh` の順に foreground 実行。
- 素材: `plugins-massivex` → `Native Instruments Massive X v1.7.1.exe` (1,870,391,792 B) → `parse_setup_headers.py` → `extract_massivex.py <exe> <work> key`。`Massive X.vst3` md5 = `622993e76565f49c094063a2b717d6ca` (dsp/REPORT §0 と一致)。installer 内 checksum 0/125 は §11.1 と同じ。

| コマンド (exit) | 所要 | load start → end | 結果 |
|---|--:|---|---|
| `dsp/e2e.sh` (0) | 23 s | 0.17 0.21 0.10 → 0.51 0.29 0.13 | insns 258,087 / unsup_sites **38,485** / 264 種 / e8e9_targets 594,978 |
| `dsp/negctl.sh` (0) | 9 s (date 差・1 s 粒度) | 0.47 0.28 0.13 → 0.51 0.30 0.14 | NC1 / NC2 / NC3 すべて FAIL<期待> |

```
   NC1 insns=3118 (base 258087)  unsup=5 (base 38485)  -> FAIL<期待>
   NC2 insns=4575 (base 258087) unsup=561 (base 38485) -> FAIL<期待>
   NC3 insns=31 (base 258087) unsup=0 (base 38485) -> FAIL<期待>
```

- 群別 (e2e 出力): AVX 37,630 / AES·SHA-NI 224 / x87 73 / その他 558 (合計 38,485)。同 commit を ws-3454 で再実行 (22 s・exit 0) し、総数 (38,485 / 264 種) と群別内訳が初回と一致 (初回の種別表は未保存)。
- 旧値 48,612 は x64c の `ac58a8749`・`fe2dc9ed9` より前の値 (両 commit は HEAD の祖先)。
- 差分証跡: `git diff 458405518 HEAD -- tools/targets/massivex/dsp ':!*.md'` = **0 行** (コミット B は .md のみ)。
- 未解決 (起票先: #3487 [MX-36]): e2e の群分けは vaes 系 224 を AVX に、pshufb / palignr / pclmulqdq を「その他」に入れる (表示のみ・合計不変)。原因は unsup key が `mnemonic:mnemonic` 形式なことと判定順。
