# flengine 付録 (#3832): pe_image_parity.py の DIR64 末尾 slot 境界

親: [CI-180] (#3832)。`tools/liftlib/dir64_boundary_gate.sh` [1] (列挙) の FAIL 是正。

## 1. 修正内容

`tools/gui/flengine/pe_image_parity.py` の旧境界 (`r < lo + len - 8`、section 末尾の 8B slot を落とす) を、
`dataimage.py` / `m6_data_gen.py` / `test_unit.py` と同じ現行規則 (`r <= lo + len - 8`) に揃えた。

- L97 (ネガコン N1 の対象 slot 選択): `base = lo - lb` を切り出し、`base <= r <= base + len(sd) - 8`。
  左辺を変数に切ったのは、grep 系の列挙が `lo - lb <= r` 形を拾えず、AST 系と突合できなかったため
  (修正前の L97 は grep=None・ast=OLD)。
- L119 (INFO の data 系 DIR64 スロット数): `lo <= r <= lo + vs - 8`。

## 2. 出力の before / after (既定実行 `--pe block00031_PE.bin`)

修正前後の差分は INFO 1 行のみ。P1/P2/N1/N2/N3 は両方 PASS (全行同一)。

```
< [parity] INFO runtime 方式 ...: data 系 DIR64 スロット 10283 / lva 方式の補正 10284
> [parity] INFO runtime 方式 ...: data 系 DIR64 スロット 10284 / lva 方式の補正 10284
```

差分の理由: L119 の旧境界が section 末尾の DIR64 slot 1 件 (RVA 0x11e5000) を数え落としていた。
修正後は data 系 DIR64 スロット数が lva 方式の補正数 (10284) と一致する。
補正件数 (`.data` 10,284 件 = m11 `m11_data_gen.py` 出力) は before/after とも不変。
