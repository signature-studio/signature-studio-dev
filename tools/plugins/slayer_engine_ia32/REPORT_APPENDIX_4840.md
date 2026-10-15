# REPORT_APPENDIX_4840 — `0x10009bc4` の ST(0) 全行不一致の原因 (PLG-G2-65)

既知類型との関係: `ott_x87.h` の制限 (4) (スタックの over/underflow を模型化しない) の範囲。 同じ類型は #4146 (PLG-G2-49)・#4185 (PLG-G2-51)。 `docs/DEFECTS.md` の既存 ID へは当てていない。 新しい類型は作らない。

- 親: #4080 (親 #4066)。 本付録は #4840 の測定。 #4080 の付録 `REPORT_APPENDIX_4080.md` は repo に無い。 #4080 の子 (`0x10009bc4` の突合) の入口状態の根拠として本付録を使う。
- 測定 commit: `c44bcf4de` (コードを変えた最後の commit)。 素材: fl-win64 の `block22434_PE.bin`・toolchain-emsdk (emcc 6.0.12)。 seed 2989。
- 起動・GUI に関わらない (製品 KPI は対象外)。

## 1. 結論

- **issue 本文の前提の訂正**: `0x10009bc4` は cdecl の double 引数を取らない。 本体は `[ebp+8]` を読まず、先頭の `fistp qword` で呼出し時の **x87 ST(0)** を整数化する (`0x10009bc4`〜`0x10009bea`)。 入力は引数でなく ST(0) である。
- **空スタックの読みが原因**: 既存の harness (`x87_fn_diff.py`) は `fninit` のあと空スタックで呼ぶ。 その入口では ST(0) が空で、native (実 x87) は default NaN (-qNaN `ffc00000`) を返し、wasm の模型は 0 を返す。 4,000 行すべてが `nan-num` になる原因はこれ。
- **分類**: 模型の限界 (`ott_x87.h` の制限 (4)・underflow) で、lowering の誤りではない。 double を ST(0) に積んだ入口では差が 0 (§2)。 これが lowering の正しさを示すのは、同じ経路で測ったこの関数の 4,000 行に限る。
- **入力を ST(0) に積むと一致**: 呼出し前に double を 1 個積むと (`X87_PUSH64=1`)、native と wasm は 4,000 行すべて eax・ST(0)・x87 深さ・bit が一致する。 特殊値 (NaN・±inf・非正規・±0・int32 境界) を含む 4,000 行も 4,000 / 4,000 で一致。
- **TARGETS の判定 (入れない)**: 下記 §3 の理由で既定ゲート (`TARGETS`) には入れない。 測定は `X87_PUSH64=1` の経路で行う。

## 2. 測定

| 試験 | 入口状態 | 結果 (native vs wasm) | 判定 |
|---|---|---|---|
| `X87_PROBE=1`・`fn_10009bc4` (既存 harness) | 空スタック | 4,000 / 4,000 行 `nan-num` (native `ffc00000`・wasm `00000000`)。 eax 一致 | 空スタックの underflow (模型の限界) |
| `X87_PUSH64=1` (double を ST(0) に積む) | double を積む | 4,000 / 4,000 行 bit 一致。 eax 種類 1,751 (非自明性) | PASS |
| `X87_PUSH64=1 --special` (NaN・inf・非正規・±0・int32 境界) | double を積む (特殊値) | 4,000 / 4,000 行 bit 一致 | PASS |
| 既定ゲート `python3 x87_fn_diff.py` | 既存 TARGETS | PASS (5 本・構造は従来どおり) | 変わらず |
| `--nega` (1 bit 反転) | 既存 | 15,495 → 15,494 (検出) | ネガコン OK |
| `--nega-lower` (lowering の取り違え) | 既存 | float32 不一致を検出 | ネガコン OK |

- `X87_PROBE=1` の出力の `fn_10009bc4` 行は、空スタックの基準線として残す (`PROBE` に 1 本追加)。 FAIL になるのはこの基準線だけで、既存のゲートではない。
- 戻り値 eax の分布 (double 入力): 1,751 種類 (通常乱数)。 OBJ 窓と stack 窓は書かない関数なので、非自明性は eax の種類数で判定する (`x87_fn_diff.py` の `PUSH64` 分岐)。

## 3. TARGETS の判定 (入れない)

| 理由 | 内容 |
|---|---|
| 既定の入口状態が模型の範囲外 | 既定ゲートは空スタックで呼ぶ。 `0x10009bc4` の実際の入口は ST(0) に値がある。 空の入口で通すと、underflow を模型に入れた値を比べることになる |
| 出力が eax だけ | OBJ 窓・stack 窓を書かないため、既定ゲートの「窓が変わった行」の判定が通らない。 通すには判定器を関数ごとに変える必要がある |
| 呼出し元の深さが未確認 | 50 箇所の呼出し元のうち、確認したのは `0x100013fb` の 1 件だけ (直前の `fmul` が ST(0) に残す)。 残り 49 件の呼出し時の x87 深さは未測定 |

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 呼出し元 50 箇所の、呼出し時の x87 深さ (ST(0) に値があるか) | `0x10009bc4` を TARGETS に入れる判断の根拠が 1 件のみ | #4064 (親・OPEN。 入口状態の再判断) |
| 空スタック入口の扱い (default NaN か 0 か) | 既存の入口状態の決定 (#4146 CLOSED) と同じ論点 | #4064 (PM が再判断) |
| eax 専用の関数を既定ゲートで通す判定器の設計 | `0x10009bc4` を既定ゲートに入れる場合に必要 | #4064 |

## 5. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64   # 素材 [WIN64] (docs/REFERENCES.md)
python3 tools/plugins/slayer_engine_ia32/lift_text.py                 # work/lift_text/ott_lifted.c を作る
X87_PROBE=1 python3 tools/plugins/slayer_engine_ia32/x87_fn_diff.py     # 空スタックの基準線 (fn_10009bc4 は FAIL する)
X87_PUSH64=1 python3 tools/plugins/slayer_engine_ia32/x87_fn_diff.py    # double を ST(0) に積む (PASS)
X87_PUSH64=1 python3 tools/plugins/slayer_engine_ia32/x87_fn_diff.py --special   # 特殊値 (PASS)
python3 tools/plugins/slayer_engine_ia32/x87_fn_diff.py                  # 既定ゲート (PASS・変わらず)
```

測定 commit `c44bcf4de` の値。 `lift_text.py` は 22 秒・rc 0。 `x87_fn_diff.py` の build は native 0.05 s・wasm emcc 9.2 s・run は 0.08〜0.3 s。
