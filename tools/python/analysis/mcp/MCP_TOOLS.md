# MCPTools.pyc (FL 26.1.7 System/Tools/MCP) 48 tools — 分類と FL API 呼出面

A local-flapi **38** / B local-ilmcp **8** / U local-ui(Gopher 付随) **2** / X 対象外(外部通信) **0**

wasm 実行: 全 tool を wasm CPython(Worker)+モック FLEngine 上で実行 → 48/48 ok

| # | tool | 引数 | 分類 | FL API (推移閉包) | ilmcp |
|---|---|---|---|---|---|
| 1 | `get_session_context` | — | A | channels.channelCount, channels.getChannelName, channels.getChannelPan, channels.getChannelVolume, channels.getTargetFxTrack, mixer.getCurrentTempo, mixer.getRouteSendActive, mixer.getRouteToLevel, mixer.getTrackName, mixer.getTrackPan, mixer.getTrackVolume, mixer.trackCount, plugins.getPluginName, plugins.isValid | — |
| 2 | `get_browser_names` | name, fullRecursive | B | — | getBrowserNames |
| 3 | `show_or_hide_window` | window_name, state | A | ui.hideWindow, ui.showWindow | — |
| 4 | `get_highlight_names` | — | U | — | getHighlightNames |
| 5 | `show_highlight` | item, tutorialName, tutorialCaption | U | — | getHighlightNames, showHighlight |
| 6 | `play` | — | A | transport.start | — |
| 7 | `stop` | — | A | transport.stop | — |
| 8 | `get_tempo` | — | A | mixer.getCurrentTempo | — |
| 9 | `set_tempo` | bpm | A | mixer.setCurrentTempo | — |
| 10 | `list_channel_names` | — | A | channels.channelCount, channels.getChannelName, plugins.getPluginName | — |
| 11 | `select_channels` | target_channels, selected | A | channels.channelCount, channels.getChannelName, channels.isChannelSelected, channels.selectChannel, plugins.getPluginName, plugins.isValid | — |
| 12 | `rename_channels` | channel_mapping | A | channels.channelCount, channels.getChannelName, channels.isChannelSelected, channels.setChannelName, plugins.getPluginName, plugins.isValid | — |
| 13 | `add_channel` | plugin | B | — | addChannel |
| 14 | `remove_channels` | target_channels | B | channels.channelCount, channels.getChannelName, channels.isChannelSelected, plugins.getPluginName, plugins.isValid | removeChannel |
| 15 | `route_channels_to_mixer` | target_channels, mixer_track_target | A | channels.channelCount, channels.getChannelName, channels.isChannelSelected, channels.setTargetFxTrack, mixer.getTrackName, mixer.isTrackSelected, mixer.trackCount, plugins.getPluginName, plugins.isValid | — |
| 16 | `get_channel_volumes` | target_channels | A | channels.channelCount, channels.getChannelName, channels.getChannelVolume, channels.isChannelSelected, plugins.getPluginName, plugins.isValid | — |
| 17 | `set_channels_volume_db` | target_channels, volume_db | A | channels.channelCount, channels.getChannelName, channels.getChannelVolume, channels.isChannelSelected, channels.setChannelVolume, mixer.getTrackVolume, plugins.getPluginName, plugins.isValid | — |
| 18 | `set_channels_volume` | target_channels, volume | A | channels.channelCount, channels.getChannelName, channels.isChannelSelected, channels.setChannelVolume, plugins.getPluginName, plugins.isValid | — |
| 19 | `set_channels_pan` | target_channels, pan | A | channels.channelCount, channels.getChannelName, channels.isChannelSelected, channels.setChannelPan, plugins.getPluginName, plugins.isValid | — |
| 20 | `set_channels_colour` | target_channels, colour | A | channels.channelCount, channels.getChannelName, channels.isChannelSelected, channels.setChannelColor, plugins.getPluginName, plugins.isValid | — |
| 21 | `mute_channels` | target_channels, muted | A | channels.channelCount, channels.getChannelName, channels.isChannelSelected, channels.muteChannel, plugins.getPluginName, plugins.isValid | — |
| 22 | `solo_channels` | target_channels, value | A | channels.channelCount, channels.getChannelName, channels.isChannelSelected, channels.soloChannel, plugins.getPluginName, plugins.isValid | — |
| 23 | `set_step_sequencer_step` | target_channels, step_number, value | A | channels.channelCount, channels.getChannelName, channels.isChannelSelected, channels.setGridBit, plugins.getPluginName, plugins.isValid | — |
| 24 | `set_step_sequencer_pattern` | target_channels, pattern | A | channels.channelCount, channels.getChannelName, channels.isChannelSelected, channels.setGridBit, plugins.getPluginName, plugins.isValid | — |
| 25 | `set_mixer_tracks_pan` | target_tracks, pan | A | mixer.getTrackName, mixer.isTrackSelected, mixer.setTrackPan, mixer.trackCount | — |
| 26 | `get_mixer_tracks_volume` | target_tracks | A | mixer.getTrackName, mixer.getTrackVolume, mixer.isTrackSelected, mixer.trackCount | — |
| 27 | `set_mixer_tracks_volume_db` | target_tracks, volume_db | A | mixer.getTrackName, mixer.getTrackVolume, mixer.isTrackSelected, mixer.setTrackVolume, mixer.trackCount | — |
| 28 | `set_mixer_tracks_volume_percent` | target_tracks, percent | A | mixer.getTrackName, mixer.isTrackSelected, mixer.setTrackVolume, mixer.trackCount | — |
| 29 | `rename_mixer_tracks` | track_mapping | A | mixer.getTrackName, mixer.isTrackSelected, mixer.setTrackName, mixer.trackCount | — |
| 30 | `add_effect` | plugin, target_tracks, slot_number | B | mixer.getTrackName, mixer.isTrackSelected, mixer.trackCount | addEffect |
| 31 | `remove_effect` | target_tracks, slot_numbers | B | mixer.getTrackName, mixer.isTrackSelected, mixer.trackCount | addEffect |
| 32 | `set_mixer_tracks_colour` | target_tracks, colour | A | mixer.getTrackName, mixer.isTrackSelected, mixer.setTrackColor, mixer.trackCount | — |
| 33 | `mute_mixer_tracks` | target_tracks, muted | A | mixer.getTrackName, mixer.isTrackSelected, mixer.muteTrack, mixer.trackCount | — |
| 34 | `solo_mixer_tracks` | target_tracks, value | A | mixer.getTrackName, mixer.isTrackSelected, mixer.soloTrack, mixer.trackCount | — |
| 35 | `reset_mixer_tracks` | target_tracks | B | mixer.getRouteSendActive, mixer.getTrackName, mixer.isTrackSelected, mixer.setRouteTo, mixer.setRouteToLevel, mixer.setTrackColor, mixer.setTrackName, mixer.setTrackPan, mixer.setTrackVolume, mixer.trackCount | addEffect |
| 36 | `get_mixer_routing` | — | A | mixer.getRouteSendActive, mixer.getRouteToLevel, mixer.getTrackName, mixer.trackCount | — |
| 37 | `set_mixer_routing` | source_track, dest_track, active, level | A | mixer.getTrackName, mixer.isTrackSelected, mixer.setRouteTo, mixer.setRouteToLevel, mixer.trackCount | — |
| 38 | `reset_mixer_routing` | target_tracks | A | mixer.getRouteSendActive, mixer.getTrackName, mixer.isTrackSelected, mixer.setRouteTo, mixer.setRouteToLevel, mixer.trackCount | — |
| 39 | `open_piano_roll_for_channel` | target_channel | A | channels.channelCount, channels.deselectAll, channels.getChannelName, channels.isChannelSelected, channels.selectChannel, plugins.getPluginName, plugins.isValid, ui.getVisible, ui.hideWindow, ui.showWindow | — |
| 40 | `quantize_channel` | channel_number | A | channels.quickQuantize | — |
| 41 | `get_playlist_track_names` | — | A | playlist.getTrackName, playlist.trackCount | — |
| 42 | `rename_playlist_tracks` | track_mapping | A | playlist.setTrackName | — |
| 43 | `set_playlist_tracks_colour` | target_tracks, colour | A | playlist.setTrackColor | — |
| 44 | `get_plugin_parameter_list` | target, slot_number | A | channels.channelCount, channels.getChannelName, channels.isChannelSelected, mixer.getTrackName, mixer.isTrackSelected, mixer.trackCount, plugins.getParamCount, plugins.getParamName, plugins.getPluginName, plugins.isValid | — |
| 45 | `get_plugin_parameter_value` | target, param_identifier, slot_number | A | channels.channelCount, channels.getChannelName, channels.isChannelSelected, mixer.getTrackName, mixer.isTrackSelected, mixer.trackCount, plugins.getParamCount, plugins.getParamName, plugins.getParamValue, plugins.getParamValueString, plugins.getPluginName, plugins.isValid | — |
| 46 | `set_plugin_parameter_value` | target, param_identifier, value, slot_number | A | channels.channelCount, channels.getChannelName, channels.isChannelSelected, channels.showEditor, mixer.focusEditor, mixer.getTrackName, mixer.isTrackSelected, mixer.trackCount, plugins.getParamCount, plugins.getParamName, plugins.getPluginName, plugins.isValid, plugins.setParamValue | — |
| 47 | `save_piano_roll_script` | script_name, source | B | — | storePRScript |
| 48 | `run_piano_roll_script` | source | B | ui.showWindow | runPRScript |
