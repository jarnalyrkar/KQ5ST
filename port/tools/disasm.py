# Relocation-aware linear disassembly of hunks dumped by hunks.py.  disasm.py <hunkdir> <outdir>
# Relocated longwords are shown as H<hunk>_<offset>; listing lines are "H<hunk>_<offset>: <hex>  <insn>".
import sys, os, json, struct
from capstone import Cs, CS_ARCH_M68K, CS_MODE_M68K_000, CS_MODE_BIG_ENDIAN
hd, od = sys.argv[1], sys.argv[2]; os.makedirs(od, exist_ok=True)
hunks = json.load(open(os.path.join(hd, 'hunks.json')))
md = Cs(CS_ARCH_M68K, CS_MODE_M68K_000 | CS_MODE_BIG_ENDIAN)
for i, h in enumerate(hunks):
    if h['type'] != 'CODE' or not h['size']: continue
    d = open(os.path.join(hd, f'hunk{i:02d}.bin'), 'rb').read()
    rel = {}  # offset -> target label
    for tgt, offs in h['relocs'].items():
        for o in offs:
            v = struct.unpack('>I', d[o:o+4])[0]; rel[o] = f'H{int(tgt)}_{v:x}'
    out = []; pc = 0
    while pc < len(d):
        ins = next(md.disasm(d[pc:pc+10], pc), None)
        if ins is None:
            out.append(f'H{i}_{pc:x}: {d[pc:pc+2].hex()}  dc.w ${d[pc:pc+2].hex()}'); pc += 2; continue
        txt = f'{ins.mnemonic} {ins.op_str}'
        for o in range(pc, pc + ins.size - 3):
            if o in rel: txt += f'    ; -> {rel[o]}'
        out.append(f'H{i}_{pc:x}: {ins.bytes.hex():20} {txt}'); pc += ins.size
    open(os.path.join(od, f'hunk{i:02d}.s'), 'w').write('\n'.join(out) + '\n')
print('done')
