# #3259 — 既存 snap-in の生成物ハッシュ不変 (起点 B vs 比較先 H)

- 起点 B = `80fb2fd00` (`3d51fd7a3^`・#779 の直前)、比較先 H = `origin/main` (#779 変更 + #3256 含む)
- 手順: PM 指示 (2026-10-15 05:30Z) どおり、snap-in を 1 本ずつ `lift/build.py <name> --path s0 --tag <B|H> --trials 200 --seed 1` で build。
- 測定項目: emcc 前生成物 (`final.ll`・`simd.c`・`globals.c`・`stubs.c`・`sigs.json`) と wasm (`mod.wasm`) の sha256 (64 桁)、RESULT 行、所要秒、load。
- 判定: B と H の sha256 が一致すれば「生成物不変」。

| name | side | rc | sec | load | final.ll | simd.c | globals.c | stubs.c | sigs.json | mod.wasm | RESULT |
|---|---|--:|--:|--:|---|---|---|---|---|---|---|
| clipper | B | 0 | 14 | 0.72 | 71f799d4fc133bc9bf6515c1536b3e1714a31602c96d20c788d7a56bfb98be20 | a5963158b8371eb4f8f669cea534207a91a9ae41fa7511195abe5942baa43494 | 9bcb1ae91182d734788f62a411230104e346a4ec37ddcfb833a25539dda005ff | 768e1e744e8c32423c2e588077c1b748a1f9b16141eb4e100316b3e0f001f90c | e985df024b211fe1199fbdfd522e6a8ff97286d928c6eebd0e5bfae93088b21d | 5baf337e58e66cce046944882ef10ec85f23799039eb92cc352449ff67058a48 | RESULT trials 200/200 bit-exact; calls 1100/1100; by fn 180884790:86/86 180884b30:901/901 180884b10:113/113 |
| clipper | H | 0 | 13 | 0.78 | 71f799d4fc133bc9bf6515c1536b3e1714a31602c96d20c788d7a56bfb98be20 | a5963158b8371eb4f8f669cea534207a91a9ae41fa7511195abe5942baa43494 | 9bcb1ae91182d734788f62a411230104e346a4ec37ddcfb833a25539dda005ff | 768e1e744e8c32423c2e588077c1b748a1f9b16141eb4e100316b3e0f001f90c | e985df024b211fe1199fbdfd522e6a8ff97286d928c6eebd0e5bfae93088b21d | 5baf337e58e66cce046944882ef10ec85f23799039eb92cc352449ff67058a48 | RESULT trials 200/200 bit-exact; calls 1100/1100; by fn 180884790:86/86 180884b30:901/901 180884b10:113/113 |
| delay | B | 1 | 108 | 1.13 | 1770cb4d5895a5611310067e125101126c356d7a8c1183a96b012a459bfc043b | dfb73a0cc0232d95795e414c5e8b2da1c5416a92dfc3ff7623faf732ad15ce4e | ea4ac497ff5c788b5db9ecf7418103c3815e2b6ce0a2dc006914df89b223ccdc | 8357c0d77f18982959ed0c120e13ef068203b10e63310191d6a2bb12696322ba | 34445e5ccab0529994c0e7273e1115ff32e7c9621ac28fe5e064ce460a396c8f | MISSING | noresult |
| delay | H | 1 | 92 | 1.18 | 1770cb4d5895a5611310067e125101126c356d7a8c1183a96b012a459bfc043b | dfb73a0cc0232d95795e414c5e8b2da1c5416a92dfc3ff7623faf732ad15ce4e | ea4ac497ff5c788b5db9ecf7418103c3815e2b6ce0a2dc006914df89b223ccdc | 8357c0d77f18982959ed0c120e13ef068203b10e63310191d6a2bb12696322ba | 34445e5ccab0529994c0e7273e1115ff32e7c9621ac28fe5e064ce460a396c8f | MISSING | noresult [build] emcc RSS cap 超過: delay peak=11001MB (cap=11000MB) |
| disperser | B | 0 | 18 | 1.01 | 64bb9093c20665f9d3fd1e132fc654f0aaad9fe4f9ecd17afb4d0cbcfb247d9e | dfd728d7b5a78dca2156353fd7b63bceb8c814b0bc22587cf84af0e8b2b16e5a | 2374313b67bb0d88ec6558f3a0922185f384b6d9200e41b2a86f2599680280ff | 182c0005cbe6e2ad94c06d2072516637b99c6f545c765ebdcc2c8337af95b202 | 684974289582170b574b39240d1df863f84338263f89b9082b96d3fbe7424443 | 75d11d44d19a941d1e29a91bb45de08b60f61bb07e2bf3ee28f178c7fe698b5f | RESULT trials 200/200 bit-exact; calls 999/999; by fn 180316480:999/999 |
| disperser | H | 0 | 18 | 1.00 | 64bb9093c20665f9d3fd1e132fc654f0aaad9fe4f9ecd17afb4d0cbcfb247d9e | dfd728d7b5a78dca2156353fd7b63bceb8c814b0bc22587cf84af0e8b2b16e5a | 2374313b67bb0d88ec6558f3a0922185f384b6d9200e41b2a86f2599680280ff | 182c0005cbe6e2ad94c06d2072516637b99c6f545c765ebdcc2c8337af95b202 | 684974289582170b574b39240d1df863f84338263f89b9082b96d3fbe7424443 | 75d11d44d19a941d1e29a91bb45de08b60f61bb07e2bf3ee28f178c7fe698b5f | RESULT trials 200/200 bit-exact; calls 999/999; by fn 180316480:999/999 |
| formant | B | 0 | 18 | 1.00 | 015d190c7df5f62435bef5fff6cf797f32cb31a45e374f9dca53109c98ece912 | b6ce722f63c34ee5330ceed4196603742f7af1b567208a72e074fe29b9012190 | f8f7bc87647a00be6ba230a244efa2550a92997a105c668e68f1cbd9b27c36e3 | 6e229f89e667619c4e84f5048b4e3cc0af8dc8eab63863256dba9d9e665146d4 | 3328ce08d7cf46af99c37df5e380e97244fbc8dba6e2b445a241d4df1472bbe1 | 594924d87f432d3d56da8b3d76ac36d26df8a4cdc7576809677b073e6f07b362 | RESULT trials 200/200 bit-exact; calls 999/999; by fn 18085a730:999/999 |
| formant | H | 0 | 18 | 1.00 | 015d190c7df5f62435bef5fff6cf797f32cb31a45e374f9dca53109c98ece912 | b6ce722f63c34ee5330ceed4196603742f7af1b567208a72e074fe29b9012190 | f8f7bc87647a00be6ba230a244efa2550a92997a105c668e68f1cbd9b27c36e3 | 6e229f89e667619c4e84f5048b4e3cc0af8dc8eab63863256dba9d9e665146d4 | 3328ce08d7cf46af99c37df5e380e97244fbc8dba6e2b445a241d4df1472bbe1 | 594924d87f432d3d56da8b3d76ac36d26df8a4cdc7576809677b073e6f07b362 | RESULT trials 200/200 bit-exact; calls 999/999; by fn 18085a730:999/999 |
| gain | B | 0 | 13 | 0.36 | d7980101e7f942c92ffd96f34de494b538dc0a276b34b2b431ebf7fdb953bb6b | 751a8b41842fd75a0faab443ce0f92a9a6f9ef2bce47b33c834aeae1a9132506 | 59ae076c50cb1a25e676c228951055e83d9ce8e9f453870ba33418488966c55d | 968f1f09bf792109dc4237741e6234f7632ab4d12a85eccbbc2ba029df078aa7 | 4e3d4c8b777e68df9fdccc143355e3774be549e93484fe201608d7c1fdcaf9f0 | a8447893097d33b21f95c5ee52efa09bccdb94213fef8f991cec4d9c0dff16ed | RESULT trials 200/200 bit-exact; calls 999/999; by fn 1804b0380:999/999 |
| gain | H | 0 | 13 | 0.46 | d7980101e7f942c92ffd96f34de494b538dc0a276b34b2b431ebf7fdb953bb6b | 751a8b41842fd75a0faab443ce0f92a9a6f9ef2bce47b33c834aeae1a9132506 | 59ae076c50cb1a25e676c228951055e83d9ce8e9f453870ba33418488966c55d | 968f1f09bf792109dc4237741e6234f7632ab4d12a85eccbbc2ba029df078aa7 | 4e3d4c8b777e68df9fdccc143355e3774be549e93484fe201608d7c1fdcaf9f0 | a8447893097d33b21f95c5ee52efa09bccdb94213fef8f991cec4d9c0dff16ed | RESULT trials 200/200 bit-exact; calls 999/999; by fn 1804b0380:999/999 |
| gate | B | 0 | 13 | 0.76 | 12b9052ee76418cbb22162e0ef90d33011d4e8a22352d15912c8bd5487da059a | d39f293c9df5d3127078def7b4bada6ac38501e61962658dad940c0350de4250 | 92ee34f5640af636afa3a0643b17632dbe986f926be43c62f6f3b9b6ef103b63 | fd1852b074d31999140900e9759f80e5a01caeea04c2f1d12637821a17c09ed9 | 32a09f2532dd07929bbd624a60d4c1e38495fb8b7acbdbe3961893023adfb597 | 52170df7cfc8ffeadf89ee683ae378cf2b448dcbe3325ec016980c397abb74a6 | RESULT trials 200/200 bit-exact; calls 999/999; by fn 1804c2f50:999/999 |
| gate | H | 0 | 13 | 0.80 | 12b9052ee76418cbb22162e0ef90d33011d4e8a22352d15912c8bd5487da059a | d39f293c9df5d3127078def7b4bada6ac38501e61962658dad940c0350de4250 | 92ee34f5640af636afa3a0643b17632dbe986f926be43c62f6f3b9b6ef103b63 | fd1852b074d31999140900e9759f80e5a01caeea04c2f1d12637821a17c09ed9 | 32a09f2532dd07929bbd624a60d4c1e38495fb8b7acbdbe3961893023adfb597 | 52170df7cfc8ffeadf89ee683ae378cf2b448dcbe3325ec016980c397abb74a6 | RESULT trials 200/200 bit-exact; calls 999/999; by fn 1804c2f50:999/999 |
| haas | B | 0 | 13 | 0.58 | e6f2064a0c1acbc11e54c03f4ccee6f35553747c181c20d0991f6b1e72a80bc6 | e4e83e8539fc5c8c93976aff180ea51ec9f7ec64f71640f7bb43beeb05e32063 | d58ab6c87260a765a19ea0aee85ad6158a8d5adf8e13f69bb52c110f374796e3 | 768e1e744e8c32423c2e588077c1b748a1f9b16141eb4e100316b3e0f001f90c | ed1e1808ea0537d3b74c9fdcd739d571fcd8e821a69653789d5a225de73d2504 | 20f92a664ccc9a4fc0a0d0e9600b13e4ea62d3db89c961ca6766999a1cfe1959 | RESULT trials 200/200 bit-exact; calls 1100/1100; by fn 1804d0280:663/663 1804cff90:116/116 1804d0720:104/104 1804d0180:94/94 1804cff00:123/123 |
| haas | H | 0 | 13 | 0.67 | e6f2064a0c1acbc11e54c03f4ccee6f35553747c181c20d0991f6b1e72a80bc6 | e4e83e8539fc5c8c93976aff180ea51ec9f7ec64f71640f7bb43beeb05e32063 | d58ab6c87260a765a19ea0aee85ad6158a8d5adf8e13f69bb52c110f374796e3 | 768e1e744e8c32423c2e588077c1b748a1f9b16141eb4e100316b3e0f001f90c | ed1e1808ea0537d3b74c9fdcd739d571fcd8e821a69653789d5a225de73d2504 | 20f92a664ccc9a4fc0a0d0e9600b13e4ea62d3db89c961ca6766999a1cfe1959 | RESULT trials 200/200 bit-exact; calls 1100/1100; by fn 1804d0280:663/663 1804cff90:116/116 1804d0720:104/104 1804d0180:94/94 1804cff00:123/123 |
| khbase | B | 1 | 95 | 1.10 | d99661bc0721b5a810f79d8d96ae684d34f78e81d1b53c13c3f632729762ba87 | d46c088b128a2dc41d7168ccae2280e14414c3917ac5ce7009997691de5967ac | 5497f41acc90e12c90126a207fd0280704a9b386d1e54e29caff732249f2eca4 | 622f95d46d14ed7804faa22b0015a6308403b403a13201c4981709173f6e3110 | 9073f379b0a1d164d941a5cc2648262e019bdc3760aafd93504eda73a937b1a5 | MISSING | noresult |
| khbase | H | 1 | 89 | 1.09 | d99661bc0721b5a810f79d8d96ae684d34f78e81d1b53c13c3f632729762ba87 | d46c088b128a2dc41d7168ccae2280e14414c3917ac5ce7009997691de5967ac | 5497f41acc90e12c90126a207fd0280704a9b386d1e54e29caff732249f2eca4 | 622f95d46d14ed7804faa22b0015a6308403b403a13201c4981709173f6e3110 | 9073f379b0a1d164d941a5cc2648262e019bdc3760aafd93504eda73a937b1a5 | MISSING | noresult [build] emcc RSS cap 超過: khbase peak=11262MB (cap=11000MB) |
| limiter | B | 1 | 100 | 1.10 | bf91a6fa40dae3661f3bec362de8cee4530f453073a89bfb00410678b5082754 | c4bc45ecd6e52807737fb4e72853d6a0f656e7793eae3c67f0cea9172bc75963 | 57adf22c7752c35095b5bac0df18f1e4a73926aa8f749e9cd3bd4622753f37c8 | c958c4c494f59eae33ba530e17fb391d89a312f793c32851973b84a5de85980c | 37d500353d819f2f4d659fa6dc03992224c93b4ef3a7f28f47755fe705f14e1d | MISSING | noresult |
| limiter | H | 1 | 89 | 1.12 | bf91a6fa40dae3661f3bec362de8cee4530f453073a89bfb00410678b5082754 | c4bc45ecd6e52807737fb4e72853d6a0f656e7793eae3c67f0cea9172bc75963 | 57adf22c7752c35095b5bac0df18f1e4a73926aa8f749e9cd3bd4622753f37c8 | c958c4c494f59eae33ba530e17fb391d89a312f793c32851973b84a5de85980c | 37d500353d819f2f4d659fa6dc03992224c93b4ef3a7f28f47755fe705f14e1d | MISSING | noresult [build] emcc RSS cap 超過: limiter peak=11332MB (cap=11000MB) |
| matrix | B | 0 | 2 | 0.41 | cfd50da599fa348227584e5110526a2169f310a06b4fdc8b8c774801431952a6 | f9f794437cfa0dbe2e650863afd5bd7fd1030ab6c6128b0d978c02309430e5ed | a24f55ada1a0ff3f0f157d4d6b25fcfd225709cf1301ac3eb8dc5c7fc9ae105b | 768e1e744e8c32423c2e588077c1b748a1f9b16141eb4e100316b3e0f001f90c | 0091eb1d12cf05937f742130c053545b59abc43e03eb61ba7ec67d2dc9f1b5e4 | 1a069a24ec30895f2e6dedf7c18ddd501e180a4465f7c0d2181b265c270e6fba | RESULT trials 200/200 bit-exact; calls 1149/1149; by fn 1804f4180:100/100 1804f41a0:999/999 1804f4190:50/50 |
| matrix | H | 0 | 2 | 0.41 | cfd50da599fa348227584e5110526a2169f310a06b4fdc8b8c774801431952a6 | f9f794437cfa0dbe2e650863afd5bd7fd1030ab6c6128b0d978c02309430e5ed | a24f55ada1a0ff3f0f157d4d6b25fcfd225709cf1301ac3eb8dc5c7fc9ae105b | 768e1e744e8c32423c2e588077c1b748a1f9b16141eb4e100316b3e0f001f90c | 0091eb1d12cf05937f742130c053545b59abc43e03eb61ba7ec67d2dc9f1b5e4 | 1a069a24ec30895f2e6dedf7c18ddd501e180a4465f7c0d2181b265c270e6fba | RESULT trials 200/200 bit-exact; calls 1149/1149; by fn 1804f4180:100/100 1804f41a0:999/999 1804f4190:50/50 |
| phaser | B | 1 | 85 | 1.07 | 1c951a9b7deef5ca75924f8c0a796b0830319c70af336aa294677654f23aac9d | 9630d6f64627b1a44e83509e1f502e14d067bb5dca459f54d5b38a54eea1c9c3 | e3f484c31bb9ab2dc3b21a8fc4f7155b77b354611ecaaeff1cf129991d168b64 | 060a938c1c1e5ebd458bf49f3b3e185bc1b9f87dad8d63401a9c8bea26796280 | aeab68eb06133b497ba312ab906854df171a31633c507ecf042cc45f2b92f4a4 | MISSING | noresult |
| phaser | H | 1 | 75 | 1.19 | 1c951a9b7deef5ca75924f8c0a796b0830319c70af336aa294677654f23aac9d | 9630d6f64627b1a44e83509e1f502e14d067bb5dca459f54d5b38a54eea1c9c3 | e3f484c31bb9ab2dc3b21a8fc4f7155b77b354611ecaaeff1cf129991d168b64 | 060a938c1c1e5ebd458bf49f3b3e185bc1b9f87dad8d63401a9c8bea26796280 | aeab68eb06133b497ba312ab906854df171a31633c507ecf042cc45f2b92f4a4 | MISSING | noresult [build] emcc RSS cap 超過: phaser peak=11124MB (cap=11000MB) |
| quickeq | B | 0 | 18 | 0.62 | 4a7fc89f055a17cd1a4910c756d0a6a4ebd01f45f1254853580d4ef12c2b5a2f | 8862cfb75acb6ebb984039ce1923691e5134678e7f53660f384d91451f491927 | 505c02b609e0d592931a45ca395ae002dcb1aa44553a8d85f5358866f48840be | a85721e6c6f569bf48c50ebaf90758605cf5c6beaec3cb4b610ccd13614fa105 | 1a4169eee1245bc594dc247e897145e4d442260671034b7cfa8ad46d6d452b0f | 55d6d50f933b450da7e6d3a6b9c11496a7bf519552502b45d87f9eee59ea11bd | RESULT trials 200/200 bit-exact; calls 999/999; by fn 18035fb10:999/999 |
| quickeq | H | 0 | 18 | 0.81 | 4a7fc89f055a17cd1a4910c756d0a6a4ebd01f45f1254853580d4ef12c2b5a2f | 8862cfb75acb6ebb984039ce1923691e5134678e7f53660f384d91451f491927 | 505c02b609e0d592931a45ca395ae002dcb1aa44553a8d85f5358866f48840be | a85721e6c6f569bf48c50ebaf90758605cf5c6beaec3cb4b610ccd13614fa105 | 1a4169eee1245bc594dc247e897145e4d442260671034b7cfa8ad46d6d452b0f | 55d6d50f933b450da7e6d3a6b9c11496a7bf519552502b45d87f9eee59ea11bd | RESULT trials 200/200 bit-exact; calls 999/999; by fn 18035fb10:999/999 |
| resonator | B | 0 | 13 | 0.85 | 3bf6e141c889c0e74dde2e56a3e94b2f90f0a7b46e14b181553eaa964d3c523c | 1529959970333c5577c4ea1ace5533019a77ab6f6d5a9d51f50adaf16eab33fe | 5a344ca0daf25d07082c7c20622aa0e34e11c8e1d5e5f2e8c3c2757b35d14448 | 1b4a93f50efddf0238fbe4cbad12072688cd9ce5ef3a62ae14ef71a6fd1f91cc | 1c785fdf73152a3b678746864a9dae7a5e4e59fa504b45076f30f17efe950533 | 862aa2472ae58ab030004a6c2d6b52e73b73457592704368f0faf1a6a4b01980 | RESULT trials 80/200 bit-exact; calls 549/999; by fn 180743390:549/999 |
| resonator | H | 0 | 14 | 0.87 | 3bf6e141c889c0e74dde2e56a3e94b2f90f0a7b46e14b181553eaa964d3c523c | 1529959970333c5577c4ea1ace5533019a77ab6f6d5a9d51f50adaf16eab33fe | 5a344ca0daf25d07082c7c20622aa0e34e11c8e1d5e5f2e8c3c2757b35d14448 | 1b4a93f50efddf0238fbe4cbad12072688cd9ce5ef3a62ae14ef71a6fd1f91cc | 1c785fdf73152a3b678746864a9dae7a5e4e59fa504b45076f30f17efe950533 | 862aa2472ae58ab030004a6c2d6b52e73b73457592704368f0faf1a6a4b01980 | RESULT trials 80/200 bit-exact; calls 549/999; by fn 180743390:549/999 |
| stereo | B | 0 | 17 | 0.91 | 1ef7c99c85ee87b0dcbe61338f6745c9249e562ebeec83772238970e1cba2101 | df0d8ebc2626bceecdba3942ca24b4fdacb75ae83b2eb12a1f1154f32bd4ee24 | 7293bc9debbd4d5e01c86b34283da521fa7d7b8626d4b6d1e96846a9ff744fc6 | defd1b6880356e90b2833b3bf7427c9581d96ab5c3e2c5062fe6f5d34719b6b7 | 257b20dfb273b94e35264b85d3186360ac7dcf7894330155d436be552fc0867b | a1a94a621976d331902e90384baddcaa40c8e0837dc3dbb90c79a1652bba25e4 | RESULT trials 12/200 bit-exact; calls 552/999; by fn 18080d4d0:552/999 |
| stereo | H | 0 | 17 | 1.01 | 1ef7c99c85ee87b0dcbe61338f6745c9249e562ebeec83772238970e1cba2101 | df0d8ebc2626bceecdba3942ca24b4fdacb75ae83b2eb12a1f1154f32bd4ee24 | 7293bc9debbd4d5e01c86b34283da521fa7d7b8626d4b6d1e96846a9ff744fc6 | defd1b6880356e90b2833b3bf7427c9581d96ab5c3e2c5062fe6f5d34719b6b7 | 257b20dfb273b94e35264b85d3186360ac7dcf7894330155d436be552fc0867b | a1a94a621976d331902e90384baddcaa40c8e0837dc3dbb90c79a1652bba25e4 | RESULT trials 12/200 bit-exact; calls 552/999; by fn 18080d4d0:552/999 |

## 結論

- **測定 commit**: B = `80fb2fd00` (`3d51fd7a3^`)、H = `3769b0f76` (origin/main 時点)。H と HEAD の間は本付録の追加だけ (下の差分を参照)。
- **emcc 前の 5 項目 (final.ll・simd.c・globals.c・stubs.c・sigs.json)**: 14 本すべてで B と H の sha256 が一致。
- **wasm (mod.wasm)**: 10 本 (matrix・gain・haas・clipper・gate・quickeq・resonator・stereo・disperser・formant) で一致。RESULT も B・H で同一。
- **wasm は未測定の 4 本**: phaser・delay・limiter・khbase。emcc の RSS cap (11000MB) 超過で wasm が出ない。#3756 の完了後に再測定する。
- resonator (80/200)・stereo (12/200) は RESULT が 200/200 ではない。B と H で同じ値なので本件の変更による差ではない。既存の未解決 (従来値) として扱う。

## cap 超過 4 本の実測 (emcc 前生成物)

| name | final.ll (B=H) bytes | globals.c bytes | defines | emcc 段 |
|---|--:|--:|--:|---|
| phaser | 1,461,839 | 960,709,664 | 160 | H: cap 超過 peak=11124MB |
| delay | 2,775,052 | 1,263,683,900 | 282 | H: cap 超過 peak=11001MB |
| limiter | 1,817,263 | 1,255,439,321 | 216 | H: cap 超過 peak=11332MB |
| khbase | 2,152,241 | 1,257,571,498 | 232 | H: cap 超過 peak=11262MB |

## B 側の失敗モードについて

- B 側 (80fb2fd00) のログでは、4 本とも emcc の `globals.c` 段で **SIGKILL (-9)** で落ちた。cap の表示は出ていない。B に cap 機構が無いためと推定する (未確認)。
- 4 本の結果は「B も H も emcc で wasm が出ない」と読む。B 側の wasm が出ないことは、比較の対象外 (一致を主張しない)。

## 測定の所要と負荷

- 1 本あたり B・H それぞれ 2〜18 秒 (wasm が出る 10 本)、cap 超過の 4 本は 75〜108 秒。
- load (1 分平均) は 0.36〜1.19。RSS は cap 超過の 4 本でのみ 11GB 付近。

## 差分 (測定 commit から HEAD まで)

`git diff 3769b0f76 HEAD -- tools/targets/kilohearts/snapins` は本付録 (REPORT_APPENDIX_3259.md) のみ。コードの変更は 0。

## HEAD 再測定 (main 取り込み後・測定 commit 4410b3adf)

main 側に H (`3769b0f76`) より後の変更 (#3756 `c19086fdb`・#3358 `4a8c4e0a5`) が入ったため、競合解消後の HEAD で 14 本を再 build した。PR 自身はコードを変えていない (`git diff origin/main HEAD -- tools/targets/kilohearts ':!*.md'` は空)。`native_ref` は `build.py` が作らないため、`harness/native_ref.c` と `harness/scenarios.c` を `cc -O1 -Wall -o work/native_ref ... -lm` で作ってから実行した。全 14 本 rc=0。

| name | sec | final.ll | simd.c | globals.c | stubs.c | sigs.json | mod.wasm | RESULT |
|---|--:|---|---|---|---|---|---|---|
| clipper | 14 | = B | = B | = B | = B | = B | = B | 200/200 bit-exact, calls 1100/1100 |
| gain | 13 | = B | = B | = B | = B | = B | = B | 200/200, calls 999/999 |
| haas | 14 | = B | = B | = B | = B | = B | = B | 200/200, calls 1100/1100 |
| gate | 14 | = B | = B | = B | = B | = B | = B | 200/200, calls 999/999 |
| quickeq | 15 | = B | = B | ≠ B | = B | = B | = B | 200/200, calls 999/999 |
| resonator | 14 | = B | = B | = B | = B | = B | = B | 200/200, calls 999/999 |
| stereo | 14 | = B | = B | ≠ B | = B | = B | = B | 200/200, calls 999/999 |
| disperser | 14 | = B | = B | ≠ B | = B | = B | = B | 200/200, calls 999/999 |
| formant | 14 | = B | = B | ≠ B | = B | = B | = B | 200/200, calls 999/999 |
| matrix | 2 | = B | = B | = B | = B | = B | = B | 200/200, calls 1149/1149 |
| phaser | 16 | = B | = B | ≠ B | = B | = B | = B | 200/200, calls 1100/1100 |
| delay | 21 | = B | = B | ≠ B | = B | = B | = B | 200/200, calls 1299/1299 |
| limiter | 16 | = B | = B | ≠ B | = B | = B | = B | 200/200, calls 1100/1100 |
| khbase | 18 | = B | = B | ≠ B | = B | = B | = B | 200/200, calls 10500/10500 |

- **B との比較** (B = `80fb2fd00` の sha256 は上の旧表): `final.ll`・`simd.c`・`stubs.c`・`sigs.json`・`mod.wasm` は 14 本すべて一致。`globals.c` は 8 本で不一致 (quickeq・stereo・disperser・formant・phaser・delay・limiter・khbase)。
- **`globals.c` の不一致**: main 側の #3756 (`c19086fdb`・`gen_globals.py` の BSS 0 埋め膨張の修正) が原因。B・H の時点では 0 埋めが宣言長を超えていた。この PR の差分ではない。`globals.c` を含む生成物の変化は、この修正の意図した効果である。
- **cap 超過の 4 本 (phaser・delay・limiter・khbase)**: #3756 の修正後は emcc RSS cap 内に収まり、wasm が出た。旧表の「未測定」は HEAD では解消。
- **resonator・stereo**: RESULT は HEAD で 200/200 (旧 H は 80/200・12/200)。差の原因は**未切り分け** (本 PR はコードを変えていない。main 側の変更との対応は未確認)。wasm・final.ll は B・H と一致しているため、差は oracle 側の出力と読めるが、確認は未実施。
- 測定ログ: `work/<name>/H/` (gitignore 対象・commit しない)。
