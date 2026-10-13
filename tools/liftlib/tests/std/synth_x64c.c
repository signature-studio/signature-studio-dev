/* x64c lift (tools/ott) 形のビルド (単一 emcc 呼出・GLOBAL_BASE / initial-memory / MODULARIZE) を模した合成 C カーネル */
extern float synth_helper(float, float);
float synth_run(float *in, float *out, int n) {
  float acc = 0.0f;
  for (int i = 0; i < n; i++) {
    float d = synth_helper(in[i], 0.75f) / 3.0f;
    out[i] = d;
    acc = acc * 0.5f + d;
  }
  return acc;
}
