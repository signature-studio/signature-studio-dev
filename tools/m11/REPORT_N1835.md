# REPORT N1835 — argrecover_verify の stack 引数位置 (pos ≥ 4) 検算の実測 (#1835, 親 #1660)

既知類型との関係: 該当なし (検算の追加。sigfix 分類の定義は `m11_argrecover.py` 既存)。
親: #1660 (PR #1868 で pos ≥ 4 を扱えるようにした)。関連: `REPORT_N1532.md` §6 の「pos≥4 の 15 件は独立検算できない」。

## 1. 結論

- `m11_argrecover_verify.py` は pos ≥ 4 の stack 引数を検算できるようになった。`fixes 33: match 33 / mismatch 0` (stack 15 件を含む)。
- 従来は `ALIAS[f['pos']]` が pos 0〜3 しか持たず `KeyError: 4` で停止していた。`REPORT_N1532.md` §6 の「pos≥4 の 15 件は独立検算できない」は、この変更で解消した。
- **再測定は本 run では未実施**。測定 commit の入力 `tools/m11/work/boot_final.ll` (work-m11) と `fixes.json` が本 run の素材に無いため。下表の値は PR #1868 作成時の run の実測 (測定 commit `48150074`) を引用している。
- 検算の既知の限界 (§4): join 点 (分岐先ラベル) を越えて後ろ向きに走査する。register 経路・stack 経路とも同じ。

## 2. 測定条件と結果 (PR #1868 作成時 run の実測)

| 項目 | 値 |
|---|---|
| 測定 commit | `48150074` (コード変更の最後の commit。PR head `4815007` と同一) |
| 実行コマンド | `bash tools/m11/m11_sigfix_stats.sh` (`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`) |
| 入力 | `tools/m11/work/boot_final.ll` (work-m11)・PE `extracted/block00031_PE.bin` (fl-win64) |
| rc | 0 |
| 所要時間 | real 3.5 s (load 0.15) |
| 終端行 | `[stats] zeropad sites 1049 / args 2064; const recovered 24 (base 0)` |
| verifier | `[verify] fixes 33: match 33 / mismatch 0` |
| 修正前 (`d24cbe51` 相当の verifier) | 同じ入力で `KeyError: 4` (`m11_argrecover_verify.py` line 31) rc 1 |
| ネガティブコントロール | `m11_argrecover_verify.py work/sigfix_stats/fixes.json --pe $PE --corrupt 3` → `match 30 / mismatch 3` (値を +1 した 3 件が FAIL) |

## 3. 本 run の確認

- 測定 commit から HEAD までのコード差分: `git diff 48150074 HEAD -- tools/m11` の出力は 0 行 (本 REPORT の追加を除き、本 PR の commit は tools/m11 のコードを変えていない)。
- 本 run の素材: `fl-win64.tar.zst` のみ。`work-m11` (`boot_final.ll`・`fixes.json` の生成元) は無く、`m11_sigfix_stats.sh` は再実行できなかった。
- `oc_artifacts:` 行を PR 本文に追加した (`fl-win64 toolchain-retdec toolchain-emsdk work-m11`)。次回の再測定はこの素材で行う。

## 4. 検算の限界 (join 点)

- `m11_argrecover.py` の `stack_imm_of` は `fn.targets` (分岐先ラベル) で止まる。verifier (`m11_argrecover_verify.py`) は止まらない。
- 対象は stack 経路 (pos ≥ 4) だけではなく、register 経路 (pos < 4) も同じ。verifier は分岐を跨いだ後ろ向き走査を許す。
- 影響: 分岐の合流点で旧値が変わる場合、verifier が同じ値を返す保証はない。今回の 33 件 (match 33) は実測で一致したが、join 点越えの件数は未集計。
- 本 PR では code を変えない (測定 commit `48150074` の値を保つため)。停止条件の追加は、入力が揃う再測定の時点で別 commit にする。この制限は PR 本文の未解決表に載せる (起票先は PR 本文を参照)。

## 5. 再現手順 (入力が揃う場合)

1. `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk work-m11` を付けた run で素材を展開する (`tools/m11/work/` が生成される)。
2. `bash tools/m11/m11_sigfix_stats.sh` を実行する。rc 0 と終端行 (`zeropad sites 1049 / args 2064; const recovered 24`) を確認する。
3. `python3 m11_argrecover_verify.py work/sigfix_stats/fixes.json --pe $FL_WIN64_DIR/extracted/block00031_PE.bin` で `match 33 / mismatch 0`。
4. ネガティブコントロール `--corrupt 3` で `match 30 / mismatch 3`。
