// cross_thread ケースの Worker: 共有カウンタの予算 (useBudget=true) または無予算で Memory を作れるだけ作る。
import { MemoryBudget, createBudgetedMemory } from "/gen/memory_budget.js";
onmessage = (e) => {
  const { counter, cap, useBudget } = e.data;
  const budget = new MemoryBudget(cap, counter);
  const keep = [];
  let denied = null, err = null;
  try {
    for (let i = 0; i < 500; i++) {
      if (useBudget) {
        const l = budget.tryAcquire(`w${i}`);
        if (!l) { denied = i; break; }
        keep.push({ l, m: new WebAssembly.Memory({ initial: 1, maximum: 65536 }) });
      } else {
        keep.push(new WebAssembly.Memory({ initial: 1, maximum: 65536 }));
      }
    }
  } catch (ex) { err = { name: ex?.name, message: String(ex?.message ?? ex).slice(0, 120) }; }
  void createBudgetedMemory;
  postMessage({ created: keep.length, deniedAt: denied, err, inUse: budget.inUse });
};
