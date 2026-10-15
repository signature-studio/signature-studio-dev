# REPORT_APPENDIX_4110 — FLDENV/FRSTOR 後のタグ語 (TW) の復元規則 (PLG-G2-48)

既知類型との関係: 該当なし (`docs/DEFECTS.md` の既存 ID には当たらない)。 親: #3688 (REPORT_APPENDIX_3688 §3・§7)。

- 測定 commit (コードを変えた最後の commit): `922ead531`。 検証 HEAD: 同じ (`git diff 922ead531 HEAD -- tools/ott tools/plugins/slayer_engine_ia32` は 0 行)。
- 比較基準: `ead1c1399` (origin/main) を `git worktree` で展開して同じ試験を実行 (§3)。
- 起動・GUI に関わらない (製品 KPI は対象外)。 入力は生成した試行のみ (fl-win64 は回帰試験の入力だけ)。
- 素材: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` (`tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst`・313 本の `_PE.bin`)。

## 1. 結論

- TW の規則: FLDENV/FRSTOR は TW の **空/非空だけ** を残し、非空の種類 (valid/zero/special) は、次の FNSTENV/FNSAVE で **レジスタの値から分類し直す**。 読んだ TW の 2 bit をそのまま保持する旧方針は、実機と一致しなかった。
- env 差分試験: 旧 99,982/100,000 (slot mismatch 18) → **100,000/100,000 (slot mismatch 0)**。 受入条件 2 を満たす。
- 受入条件 1 (TW 規則の確定と `ott_x87.h` への反映) を満たす。 ただし規則は実機の 3 シード・10 万件の観測からの経験的規則であり、理論的な証明ではない (§4 の残りの制限)。

## 2. 変更 (`tools/ott/rt/ott_x87.h`)

- `x87_tw()`: 物理レジスタの TW 2 bit を `ott_tag == empty ? 11 : x87_cls(値)` で作る (旧: `ott_tag` をそのまま使う)。
- `x87_load_env()`: TW の 2 bit が 11 なら empty (3)、それ以外は 0 (valid 扱い) として `ott_tag` に入れる。 種類は次の格納時に値から決まる。
- コメントを規則に合わせて更新。

## 3. 実測 (測定 commit `922ead531`・基準 `ead1c1399`)

| 試験 (コマンド) | n | seed | 基準 `ead1c1399` | HEAD `922ead531` |
|---|---:|---:|---:|---:|
| env (`x87_diff.py --env`) | 100,000 | 1 | 99,982 (99.98%)・slot 18 | **100,000 (100.00%)・slot 0** |
| env | 100,000 | 2 | (未測定) | 100,000 (100.00%)・slot 0 |
| env | 100,000 | 3 | (未測定) | 100,000 (100.00%)・slot 0 |
| ネガコン (`--nega-env`) | 100,000 | 1 | (未測定) | 0 (0.00%)・slot 100,000 (検出する) |
| 主 (`--n`) | 100,000 | 1 | 93,984 (93.98%)・FSW 166・slot 1,560 | 93,984 (93.98%)・FSW 166・slot 1,560 (不変) |
| `--rc-arith 0` | 20,000 | 1 | (未測定) | 18,791 (93.95%)・FSW 28・slot 348 (REPORT_APPENDIX_3688 §4 と一致) |
| `--nega-c1` | 20,000 | 1 | (未測定) | 18,112 (90.56%)・FSW 738・slot 315 (一致) |
| `--skip fldpi,fldlg2,fldl2e` | 20,000 | 1 | (未測定) | 19,230 (96.15%)・FSW 46・slot 172 (一致) |

- 主試験の 93,984 は REPORT_APPENDIX_3688 §4 の 93,985 と 1 件違う。 基準 `ead1c1399` でも 93,984 なので、本変更の影響ではない (3688 の測定時点との差)。
- env 試行の所要 (HEAD・`time` の real): env 22.96 s・ネガコン 22.87 s。 load1 開始時 0.98。

## 4. x64 回帰

`x64_regress_1099.py ws-4110-base 8` (基準 `ead1c1399` を展開): `[x64-regress] same 8/8` (ott_lifted.c・lift_meta.json)。 `ott_x87.h` は ia32 の生成 C だけが include するため、x64 の出力は変わらない。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| TW 規則は 3 シード (10 万件ずつ) の観測による経験則。 他の op 列・例外状態での反例は未検出 | 試行外の状況で TW が違う可能性 | 本 PR の残り (追加の試行列で検証) |
| FIP/FCS/FOO/FOS (環境の 12..27 B) は未モデル (0 で格納) | 環境を読み戻して実行アドレスを見る処理は一致しない | ADR D28 の制限への追記 (PM 判断待ち。 REPORT_APPENDIX_3688 §7 の通り) |
| x87 を含む関数の native と wasm の差分は未確認 | lowered の実 wasm での一致は未確認 | #2989 (PLG-G2-25) |
