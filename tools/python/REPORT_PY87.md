# tools/python REPORT: PY-87 general 状態読出しゲッター 4 件の PE 確定と C provider 実装 (#2738, 親 #941, 子 #2830・#2831・#2832)

> 正本: `tools/python/REPORT_PY27.md` (保留 150 件の出自)。本付録は PY-87 の実測のみ。

## 結論

- #1138 (PY-27) で保留した未実装 150 件のうち **4 件** (`general.getChangedFlag` / `getUseMetronome` / `getPrecount` / `getRecPPQ`) を PE で確定し、mock と C provider に実装した。mock と C の差分は 0 (`tests/general_diff.mjs` 9 呼出し)。
- **値は未確定**。4 関数はいずれも「engine の状態 1 つを読んで Python の値に変換して返す」だけで、初期値は mock と C で揃えた仮置き (`changed 0` / `useMetronome false` / `precount false` / `recPPQ 96`)。実機値は未実測。`recPPQ 96` は仮置きで、実機の既定値とは確認していない。
- 残り **146 件** は 3 件の子 issue に分けた: general 25 (#2830, PY-94) / ui 69 (#2831, PY-95) / screen 28 + arrangement 12 + launchMapPages 12 = 52 (#2832, PY-96)。

## 手段

- ハンドラ探索: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_handler_probe.py <名前...>` (`block00031_PE.bin` のみ。展開は `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst --wildcards '*block00031_PE.bin'`)。PyMethodDef のエントリ VA と関数先頭 VA (`fn`) を得る。
- 逆アセンブル: 同じ probe の先頭 40 命令 (`HEAD=40`)。RIP 相対の絶対アドレス = 次命令 + disp で求めた。
- 戻り型: 公開 stub (IL-Group FL-Studio-API-Stubs 由来、`analysis/flapi/flapi_table.json` の `sig.returns`)。

## 確定した 4 関数 (PE 根拠)

| 関数 | PyMethodDef entry | fn (VA) | 読む状態 (状態ポインタ slot) | 変換 | stub の戻り型 |
|---|---|---|---|---|---|
| `general.getChangedFlag` | 0x151aae0 | 0xd69800 | dword (slot 0x15e0bd0) | `call [slot 0x15e4280]` | int |
| `general.getUseMetronome` | 0x151ab00 | 0xd69820 | byte (slot 0x15e1498) | `call [slot 0x15e4280]` | bool |
| `general.getPrecount` | 0x151ab20 | 0xd69840 | byte (slot 0x15e0c08) | `call [slot 0x15e4280]` | bool |
| `general.getRecPPQ` | 0x151aa60 | 0xd69330 | dword (slot 0x15e01c8) | `call [slot 0x15e4280]` | int |

- 4 関数とも `flags=4` (METH_NOARGS)。先頭で `sub rsp` → 状態を読む → 変換呼出し → `ret` のみで、副作用・分岐は無い。
- 変換呼出しの間接スロットは 4 件とも絶対アドレス `0x15e4280` に一致する。同じスロットは `transport.isPlaying` (bool, fn 0xd68430) にも現れる。
- **bool と int は PE から区別できない**: 変換は `rcx` (値 1 個) だけを渡し、型の情報を渡さない。型は stub の `returns` に従う。FLEngine 側の変換関数の同定 (`0x15e4280` の先の関数) は未了。

## 保留 (本 run で未解析・子 issue へ)

- 本 run で逆アセンブルしたのは上の 4 件のみ。残り 146 件は未解析で、各 handler の VA の所在は `pe_handler_probe.py` で引ける (子 issue #2830・#2831・#2832 に名前を列挙)。
- 参考の一次観察 (結論ではない): `general.getRecPPB` (fn 0xd69310) は `call 0xd68d90` の戻り値から `+0xb20` の dword を読む。`general.safeToEdit` (0xd6a2c0) は object の仮想関数 `[rax+0x98]` の戻り値を bool として返す。どちらも状態の所在の同定が要る。

## 検証

測定 commit: `f2e03058` (コードを変えた最後の commit。main (`b2b052ce`) を取り込んだ merge。衝突は `tools/python/tests/provider_check.mjs` の定数表と件数だけ)。測定は同 commit のクリーンな作業ツリーで、`provider/build.sh` を再実行してから行った。
環境: runner 4 core、測定開始時の load average 1.45 (`uptime`)。`FL_WIN64_DIR` は [WIN64] の展開先 (runner の一時領域)。素材 `toolchain-emsdk` は取得されていなかったため、[EMSDK] を `emsdk install 6.0.12` で取得し、docs の規定位置に symlink した。

| コマンド | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` | exit 0・ハンドラ 81 | 0.75 秒 |
| `node tests/provider_check.mjs` | PASS (435 / 実装 81 / 未実装 354 / MCP 静的 60) | 0.30 秒 |
| `node tests/general_diff.mjs` | calls 9、diffs 0、PASS | 0.04 秒 |
| `node tests/ui_diff.mjs` | calls 17、diffs 0、範囲外既知差分 3、PASS | 0.04 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback 往復 true | 1.30 秒 |

件数の変化: main の取り込みで `channels.getChannelType` が公開 stub 確定 (REPORT_PY41_1514) として加わったため、本 PR 単独の測定 (実装 80 / 未実装 355) から実装 81 / 未実装 354 に変わった。上の表は取り込み後の値。

前提の生成物 (測定前に作成・gitignore): `bash fetch_inputs.sh`・`bash build_cpython_wasm.sh` (2 分 12 秒)・`FLPY_SKIP_TABLE=1 bash build_flpy.sh`。

コード差分 (測定 commit から HEAD まで、`tools/python` の .md 以外):

```
$ git diff f2e03058 HEAD -- tools/python ':!*.md'
(空)
```

## 未解決

- 4 関数の値 (`changed` / `useMetronome` / `precount` / `recPPQ`) は仮置き。実機の値は未実測。mock の値をそのまま正として扱わないこと。
- bool / int の変換関数 (`0x15e4280` の先) は未同定。stub の `returns` を正とした。
- 残り 146 件: 子 issue #2830 (general 25)・#2831 (ui 69)・#2832 (screen 28 + arrangement 12 + launchMapPages 12)。
