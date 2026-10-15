# REPORT_APPENDIX_4066 — x87 断片 10 本の入口判定 (#4066 PLG-G2-42)

既知類型との関係: 該当なし (`docs/DEFECTS.md` の既存 ID には当たらない)。

- 親 issue: #3715 (PLG-G2-31 の前提)。 本付録が判定の正本。
- 測定 commit: `5ba8578ed` (`feat(x87): classify x87 leaf entry candidates ...`。 規則のコードを含む最後の commit)。
- 起動・GUI に関わらない (製品 KPI は対象外)。 入力は fl-win64 の `block22434_PE.bin` のみ (静的解析。 実行はしていない)。
- 依頼文の前提の訂正: 本文は「`add esp, 0x2c` で始まる」としたが、10 本の先頭は `83 ec 08` (`sub esp,8`) 等で、`add esp,0x2c` で始まるものは無い。 後半 6 本の末尾が `add esp,0x2c; ret` である。 判定は先頭命令でなく参照関係で行った。

## 1. 判定結果

判定規則 (`x87_fn_diff.py --classify`): PE の code section 全体の直接 `call` (E8) と `jmp` (E9) の rel32 と、間接ジャンプテーブル `ff 24 85 disp32` のエントリを走査する。

| 入口 | 判定 | 根拠 |
|---|---|---|
| `0x100052d0` | callee (独立入口) | direct call 4 件 (`0x10006ae9`・`0x10006d87`・`0x10006f09`・`0x10007068`) |
| `0x10005550` | callee (独立入口) | direct call 1 件 (`0x10006600`) |
| `0x10009bc4` | callee (独立入口) | direct call 53 件 |
| `0x1000bf1e` | callee (独立入口) | direct call 3 件 (`0x1000bd7b`・`0x1000bd89`・`0x1000befb`) |
| `0x1000c084`・`0x1000c08f`・`0x1000c09a`・`0x1000c0a0`・`0x1000c0a6`・`0x1000c0ac` | switch-arm (断片) | direct 参照 0 件。 `ff 24 85` (`0x1000c07d`) のジャンプテーブル (`0x10024e3e`) の case 先 |

- 断片 6 本は、`0x1000c07d` の `jmp [eax*4+0x10024e3e]` の case 先で、各 case は `x87 命令; add esp,0x2c; ret` の末尾になっている。 別関数の末尾に入る断片という #3715 の見立てと一致する。
- **親関数の入口は未確定**。 `0x1000bf60` を親と推定したが、逆アセンブルで誤りと分かった。 `0x1000bf60` は `0x1000c0bf` から call される別の関数 (`fld TBYTE [esp+0x10]` で始まる)。 テーブルを引く `0x1000c07d` を含む関数の入口は、機械的な規則では決まらなかった。 規則からはこの推定を外した。
- 独立入口 4 本の `TARGETS` 投入 (受入条件 2 の前半) は未実施。 引数の形 (thiscall か stdcall か・a0〜a2 の意味) を各関数で確定してから harness に入れる必要がある。

## 2. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64
tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64 --wildcards '*block22434_PE.bin'
python3 tools/plugins/slayer_engine_ia32/x87_fn_diff.py --classify
```

実測 (commit `5ba8578ed`、本 run の worktree `ws-4066`): 上の 10 行が出力され、rc=0。 `python3 -m py_compile` も通った。

## 3. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 独立入口 4 本 (`100052d0`・`10005550`・`10009bc4`・`1000bf1e`) の `TARGETS` 投入と native/wasm 突合 | 受入条件 2 の前半が未達 | [PLG-G2-43] 子 issue (親 #4066) |
| 断片 6 本の親関数の入口の確定と、親の入口での試験 | 受入条件 2 の後半が未達。 断片の単独呼出しは試験対象にならない | [PLG-G2-43] 子 issue (親 #4066) |
