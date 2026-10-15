# tools/plugins/f2 REPORT_APPENDIX_4950 — PLG-F3-44 (#4950): RaiseException 0xeedfade の例外クラス

- 親: #3374 (受入 2 の移送元)。根拠: `REPORT_APPENDIX_3295.md` §3 (例外オブジェクト `rcx=0x50141c90`、`[rcx]=0x42d2b8` の VMT)。
- 測定 commit: `727af2eaf` (`vmt_class_name.py` の PPTypeInfo・ptr 幅の修正。元の追加は `b1d43ec83`)。
- 入力: 素材 `fl-win64` の `extracted/block19148_PE.bin` (展開手順は `docs/WORKFLOW.md` の fl-win64 節)。sha256 先頭 16 桁 `4524c1bd81b153b3`。
- 道具: `tools/plugins/f2/vmt_class_name.py` (pefile のみ。unicorn 不要)。venv は `work/` 配下に作る。

## 0. 結論

1. **受入 1 達成**: 例外のクラスは **`EOutOfMemory`** (VMT `0x42d2b8`)。
   - 根拠: PE 内で ClassType ポインタ `0x42d2b8` を持つ tkClass の RTTI が `0x42d2e8` に 1 件だけあり、その名前が `EOutOfMemory`。
   - 対照: VMT `0x42d2b9` (1 バイトずらし) は該当 0 件。
2. **継承元 (ParentInfo) を読んだ**: `EHeapException` (TypeInfo `0x42d1b0`)。ParentInfo は PPTypeInfo (`0x42d1a8`) で、一段間接参照して親の TypeInfo を得た。
   - 旧版 (b1d43ec83) は ClassType・ParentInfo を 4 バイトで読んでおり、PE32+ の 8 バイトの値を誤って切っていた (ParentInfo=0x0 は誤読)。修正は `727af2eaf`。
3. 本 run は VMT の読みのみ。`unicorn_trace.py` の `0x8525f0` 実行は行っていない (受入条件の対象外)。
4. 受入 2 (`RaiseException` を harness でどう扱うか) は本件の範囲外で、#3374 側に残る。

## 1. 再現

```
uv venv work/f4950venv && VIRTUAL_ENV=work/f4950venv uv pip install pefile
work/f4950venv/bin/python tools/plugins/f2/vmt_class_name.py "$FL_WIN64_DIR/extracted/block19148_PE.bin" 42d2b8
work/f4950venv/bin/python tools/plugins/f2/vmt_class_name.py "$FL_WIN64_DIR/extracted/block19148_PE.bin" 42d2b9
```

出力 (実測、測定 commit `727af2eaf`):
```
TypeInfo at 0x42d2e8: kind=tkClass name='EOutOfMemory' ClassType=0x42d2b8
ParentInfo(PPTypeInfo)=0x42d1a8 parent_TypeInfo=0x42d1b0 parent_name='EHeapException'
VMT 0x42d2b9 を ClassType に持つ tkClass の TypeInfo は見つからなかった
```

## 2. 鮮度

- 本付録と `vmt_class_name.py` のみを追加・修正。`REPORT_APPENDIX_3295.md` は変更しない。
