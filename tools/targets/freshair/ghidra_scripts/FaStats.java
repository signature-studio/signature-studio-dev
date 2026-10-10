import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.mem.*;
import ghidra.program.model.lang.Register;

public class FaStats extends GhidraScript {
    @Override
    public void run() throws Exception {
        Program p = currentProgram;
        FunctionManager fm = p.getFunctionManager();
        int n = 0, named = 0, big = 0; long bytes = 0;
        for (Function f : fm.getFunctions(true)) {
            n++;
            if (!f.isThunk()) { if (!f.getName().startsWith("FUN_")) named++; long sz = f.getBody().getNumAddresses(); bytes += sz; if (sz > 4096) big++; }
        }
        long insns = 0, simd = 0;
        for (Instruction i : p.getListing().getInstructions(true)) {
            insns++;
            String m = i.getMnemonicString();
            boolean s = false;
            for (int k = 0; k < i.getNumOperands() && !s; k++) {
                for (Object o : i.getOpObjects(k)) { if (o instanceof Register && ((Register) o).getName().startsWith("XMM")) { s = true; break; } if (o instanceof Register && ((Register) o).getName().startsWith("YMM")) { s = true; break; } }
            }
            if (s || m.startsWith("V") && m.length() > 3) simd++;
        }
        println("FN_DEFINED=" + n); println("FN_NAMED=" + named); println("FN_BIG_GT4K=" + big); println("FN_BYTES=" + bytes);
        println("INSNS=" + insns); println("SIMD_INSNS(xmm/ymm operand)=" + simd);
        for (MemoryBlock b : p.getMemory().getBlocks()) println("BLK " + b.getName() + " size=" + b.getSize());
    }
}
