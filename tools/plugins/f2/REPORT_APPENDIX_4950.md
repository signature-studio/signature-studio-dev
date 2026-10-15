# tools/plugins/f2 REPORT_APPENDIX_4950 — PLG-F3-44 (#4950): RaiseException 0xeedfade の例外クラス

- 親: #3374 (受入 2 の移送元)。根拠: `REPORT_APPENDIX_3295.md` §3 (例外オブジェクト `rcx=0x50141c90`、`[rcx]=0x42d2b8` の VMT)。
- 測定 commit: 本 PR の commit (コードは `vmt_class_name.py` の追加のみ)。
- 入力: `$RUNNER_TEMP/fl-win64/extracted/block19148_PE.bin` (`tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64 extracted/block19148_PE.bin`)。sha256 先頭 16 桁 `4524c1bd81b153b3`。
- 道具: `tools/plugins/f2/vmt_class_name.py` (pefile のみ。unicorn 不要)。

## 0. 結論

1. **受入 1 達成**: 例外のクラスは **`EOutOfMemory`** (VMT `0x42d2b8`)。
   - 根拠: PE 内で ClassType dword `0x42d2b8` を持つ tkClass の RTTI が `0x42d2e8` に 1 件だけあり、その名前が `EOutOfMemory` (`python tools/plugins/f2/vmt_class_name.py <PE> 42d2b8`)。
   - 対照: VMT `0x42d2b9` (1 バイトずらし) は該当 0 件。
2. **未検証**: `ParentInfo` (継承元) は 0 と読んだ。Delphi の TypeInfo 配置の確認が未了のため、継承関係は記録しない。
3. 本 run は VMT の読みのみ。`unicorn_trace.py` の `0x8525f0` 実行は行っていない (受入条件の対象外)。
4. 受入 2 (`RaiseException` を harness でどう扱うか) は本件の範囲外で、#3374 側に残る。

## 1. 再現

```
uv venv $RUNNER_TEMP/f4950venv && VIRTUAL_ENV=$RUNNER_TEMP/f4950venv uv pip install pefile
$RUNNER_TEMP/f4950venv/bin/python tools/plugins/f2/vmt_class_name.py $RUNNER_TEMP/fl-win64/extracted/block19148_PE.bin 42d2b8
```

出力 (実測):
```
TypeInfo at 0x42d2e8: kind=tkClass name='EOutOfMemory' ClassType=0x42d2b8
ParentInfo=0x0 parent_name=None
```

## 2. 鮮度

- 本付録と `vmt_class_name.py` のみを追加。`REPORT_APPENDIX_3295.md` は変更しない。
