import sys, struct
path=sys.argv[1]
TEXT_VM=0x100006c80
TEXT_OFF=27776
TEXT_SIZE=0x200b0ec
with open(path,'rb') as f:
    f.seek(TEXT_OFF); code=f.read(TEXT_SIZE)
selrefs={}
for line in open(sys.argv[2]):
    if not line.strip(): continue
    a,n=line.strip().split(' ',1)
    selrefs[int(a,16)]=n
def sign_extend(v,bits):
    if v & (1<<(bits-1)): v -= 1<<bits
    return v
def dec_adrp(insn, pc):
    if (insn & 0x9F000000) != 0x90000000: return None
    rd=insn & 0x1f
    immlo=(insn>>29)&3; immhi=(insn>>5)&0x7ffff
    imm=sign_extend((immhi<<2)|immlo,21)<<12
    return rd, (pc & ~0xfff)+imm
def dec_add_imm(insn):
    if (insn & 0x7F000000) != 0x11000000: return None
    sf=(insn>>31)&1; op=(insn>>30)&1
    if op or not sf: return None
    rd=insn&0x1f; rn=(insn>>5)&0x1f; imm=(insn>>10)&0xfff; sh=(insn>>22)&3
    if sh==1: imm <<= 12
    elif sh!=0: return None
    return rd,rn,imm
def dec_ldr_imm(insn):
    if (insn & 0xFFC00000) != 0xF9400000: return None
    rt=insn&0x1f; rn=(insn>>5)&0x1f; imm=((insn>>10)&0xfff)*8
    return rt,rn,imm
for i in range(0,len(code)-4,4):
    insn=struct.unpack_from('<I',code,i)[0]
    pc=TEXT_VM+i
    a=dec_adrp(insn,pc)
    if not a: continue
    rd,page=a
    regs={rd:page}
    for j in range(1,10):
        if i+4*j>=len(code): break
        ins2=struct.unpack_from('<I',code,i+4*j)[0]
        pc2=TEXT_VM+i+4*j
        add=dec_add_imm(ins2)
        if add:
            rdst,rn,imm=add
            if rn in regs: regs[rdst]=regs[rn]+imm
        ldr=dec_ldr_imm(ins2)
        if ldr:
            rt,rn,imm=ldr
            if rn in regs:
                addr=regs[rn]+imm
                if addr in selrefs:
                    print(f'{selrefs[addr]:30s} selref={addr:#x} adrp={pc:#x} use={pc2:#x} rt=x{rt} base=x{rn} off={imm:#x}')
