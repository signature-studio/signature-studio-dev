# tools/shim — M4 Win32 shim core (wasm)

## 結論

FLEngine が wasm で動くための最小 Win32 shim (timer / file / thread・sync / heap)、53 export API を emcc 6 でビルド可能にした M4 成果物。**`bash tools/shim/test.sh` で node 上の単体テストが exit 0 で完結する** (MT=pthread が本番経路、ST=シングルスレッドは smoke)。

## 使い方

```
bash tools/shim/test.sh        # ビルド + node 単体テスト + fail-fast 確認 (exit 0 成功)
```

- 中間生成物はすべて `build/` 配下 (gitignored)。
- API と §3 対応は `inventory.md` 参照。emcc に渡す export 一覧は `exports.txt` (test.sh が `_main` を追加して `build/run_exports.txt` に生成)。
- 定型ビルドフラグは `flags.sh` (`tools/m1/flags.sh` の流儀)。本番リンク時は `src/*.c` をそのまま emcc リンクに含める (静的)。lifter 生成コードからの未対応 import 到達時は `shim_unimplemented()` が stderr に関数名を出して即 abort する。

## M5 以降に向けて

- `strategy.md` M4 検証条件 2 (M3 wasm 成果物からの shim 呼出連結) は M3 成果物と本 shim の結合時に行う。
- import 面 diff (FLEngine 実 import ↔ exports.txt) を M5 で機械照合し、不足面を追加する。
