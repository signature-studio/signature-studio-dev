# FL 26.1.7 組込 Python API 面 (FLEngine rodata 抽出; mac x86_64/arm64 一致、win は ペア一致で照合)

| module | 関数数 | stubs(旧)に無い新規 | win ペア一致 | MCP 使用 |
|---|---|---|---|---|
| playlist | 42 | 1 (selectTool) | 42/42 | 4 |
| channels | 54 | 6 (fillEachNSteps, getSwing, rerollLoopStarterLoop, rerollLoopStarterSample, rerollLoopStarterSteps, setSwing) | 53/54 | 18 |
| mixer | 75 | 8 (getPluginMixLevel, getPluginMuteState, getRouteToLevel, getTrackCount, setCurrentTempo, setPluginMixLevel, setPluginMuteState, setRouteToLevel) | 73/75 | 18 |
| patterns | 31 | 6 (clearPattern, duplicatePatternData, incrementPatternLength, movePattern, setLoopStarterRootNote, setPatternLength) | 31/31 | 0 |
| transport | 20 | 0 () | 20/20 | 2 |
| general | 30 | 6 (getProjectAuthor, getProjectGenre, getProjectTitle, setDenominator, setNumerator, setRecPPQ) | 29/30 | 0 |
| ui | 72 | 1 (showPicker) | 44/45 | 3 |
| device | 37 | 3 (flrMidiCC, flrMidiNote, releaseCC) | 33/37 | 0 |
| arrangement | 12 | 3 (selectionClear, selectionIsActive, selectionSet) | 12/12 | 0 |
| launchMapPages | 12 | 0 () | 12/12 | 0 |
| screen | 28 | 0 () | 27/28 | 0 |
| plugins | 13 | 0 () | 12/13 | 7 |
| ilmcp | 9 | 9 (showHighlight, forwardTutorialEvent, storePRScript, runPRScript, addChannel, removeChannel, getBrowserNames, getHighlightNames…) | 0/0 | 8 |
| **合計** | **435** | | | |
