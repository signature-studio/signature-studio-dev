(module
  (import "env" "memory" (memory 1 1 shared))
  (func (export "inc") (param $n i32)
    (loop $l
      (drop (i32.atomic.rmw.add (i32.const 0) (i32.const 1)))
      (local.set $n (i32.sub (local.get $n) (i32.const 1)))
      (br_if $l (local.get $n))))
  (func (export "waitflag") (result i32)
    ;; addr 4 が 0 の間 wait (timeout 10s)
    (memory.atomic.wait32 (i32.const 4) (i32.const 0) (i64.const 10000000000))))
