import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.lang.Register;
import java.io.*;
import java.util.*;

/* 範囲限定 Ghidra: -noanalysis で import 後, DSP closure (clo_fa_union_vas.txt: "VA size") のみ逆アセンブルして
 * 命令数 / XMM・YMM 操作命令数 / call 数を実測する (全体解析 25,063 関数を回さない)。 */
public class FaScoped extends GhidraScript {
    @Override
    public void run() throws Exception {
        String path = getScriptArgs().length > 0 ? getScriptArgs()[0] : "clo_fa_union_vas.txt";
        BufferedReader br = new BufferedReader(new FileReader(path));
        String line; long insns = 0, simd = 0, calls = 0, bytes = 0; int fns = 0;
        Listing l = currentProgram.getListing();
        while ((line = br.readLine()) != null) {
            String[] t = line.trim().split("\\s+"); if (t.length < 2) continue;
            Address a = toAddr(Long.decode(t[0])); long sz = Long.parseLong(t[1]);
            disassemble(a);
            Address end = a.add(sz - 1);
            InstructionIterator it = l.getInstructions(new AddressSet(a, end), true);
            while (it.hasNext()) {
                Instruction i = it.next(); insns++;
                if (i.getMnemonicString().equals("CALL")) calls++;
                boolean s = false;
                for (int k = 0; k < i.getNumOperands() && !s; k++)
                    for (Object o : i.getOpObjects(k))
                        if (o instanceof Register && (((Register) o).getName().startsWith("XMM") || ((Register) o).getName().startsWith("YMM"))) { s = true; break; }
                if (s) simd++;
            }
            fns++; bytes += sz;
        }
        println("SCOPED_FUNCS=" + fns); println("SCOPED_BYTES=" + bytes); println("SCOPED_INSNS=" + insns);
        println("SCOPED_XMM_OPERAND_INSNS=" + simd); println("SCOPED_CALLS=" + calls);
    }
}
