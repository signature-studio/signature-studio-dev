/* LL とは別 TU の helper (RetDec chain の __asm_* と同じ構造: LTO で初めて inline される) */
float synth_helper(float x, float y) { return x * y + 0.1f * x; }
