; 合成 lift 出力 (stdbuild_e2e.sh 用; plugin バイナリ不要)。function_1000(in, out, n): out[i] = helper(in[i], .75) / 3, out[n] = 累積和
declare float @synth_helper(float, float)

define i64 @function_1000(i64 %arg1, i64 %arg2, i64 %arg3) {
entry:
  %n = trunc i64 %arg3 to i32
  %pin = inttoptr i64 %arg1 to ptr
  %pout = inttoptr i64 %arg2 to ptr
  %c = icmp sgt i32 %n, 0
  br i1 %c, label %loop, label %done
loop:
  %i = phi i32 [ 0, %entry ], [ %i1, %loop ]
  %acc = phi float [ 0.000000e+00, %entry ], [ %acc1, %loop ]
  %gi = getelementptr float, ptr %pin, i32 %i
  %x = load float, ptr %gi, align 4
  %h = call float @synth_helper(float %x, float 7.500000e-01)
  %d = fdiv float %h, 3.000000e+00
  %go = getelementptr float, ptr %pout, i32 %i
  store float %d, ptr %go, align 4
  %m = fmul float %acc, 5.000000e-01
  %acc1 = fadd float %m, %d
  %i1 = add i32 %i, 1
  %more = icmp slt i32 %i1, %n
  br i1 %more, label %loop, label %done
done:
  %accf = phi float [ 0.000000e+00, %entry ], [ %acc1, %loop ]
  %gn = getelementptr float, ptr %pout, i32 %n
  store float %accf, ptr %gn, align 4
  %bits = bitcast float %accf to i32
  %r = zext i32 %bits to i64
  ret i64 %r
}
