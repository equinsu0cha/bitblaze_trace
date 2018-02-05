#!/usr/bin/env python

import struct
import os

from capstone import *

md = Cs(CS_ARCH_X86, CS_MODE_32)

def read_format(_format, trace_file):
    size = struct.calcsize(_format)
    buf = trace_file.read(size)
    result = struct.unpack(_format, buf)
    return result, size

class OpType(object):
    op_type = {30: ('TNone', 'TRegister', 'TMemLoc', 'TImmediate', 'TJump', 'TFloatRegister', 'TMemAddress')}
    def __init__(self):
        pass

class BitblazeReg(object):
    reg_name = {30: {# 8 bits lower, upper
        116: 'eax', 117: 'ecx', 118: 'edx', 119: 'ebx', 120: 'eax', 121: 'ecx', 122: 'edx', 123: 'ebx',
                     # 16bits
                     124: 'eax', 125: 'ecx', 126: 'edx', 127: 'ebx', 128:'esp', 129: 'ebp', 130: 'esi', 131: 'edi',
                     # 32bits
                     132: 'eax', 133: 'ecx', 134: 'edx', 135: 'ebx', 136:'esp', 137: 'ebp', 138: 'esi', 139: 'edi'
                    }
               }

class ProcRecord30(object):
# typedef struct _process_record {
#     char name[32]; 
#     uint32_t pid; 
#     int  n_mods; 
# } ProcRecord; 
    def __init__(self, trace_file):
        result, size = read_format('<32sII', trace_file)
        self.name, self.pid, self.n_mods = result
        self.size = size
        self.mods = []
        for mod_id in range(self.n_mods):
            mod = ModRecord30(trace_file)
            self.mods.append(mod)
            self.size += mod.size

    def __repr__(self):
        repr_string = '''
        Name: {}
        PID: {}
        n_mods: {}
        '''.format(self.name, self.pid, self.n_mods)
        return repr_string

class ModRecord30(object):
# typedef struct _module_record {
#     char name[32]; 
#     uint32_t base; 
#     uint32_t size; 
# } ModuleRecord; 
    def __init__(self, trace_file):
        result, size = read_format('<32sII', trace_file)
        self.name, self.base, self.mod_size = result
        self.size = size

class EntryHeader30(object):
# typedef struct {
#     uint32_t addr; 
#     char rawbytes[15]; 
#     ZL: 1 byte padding here (found in temu_trace.ml)
#     OperandVal operand[5];
#     OperandVal memregs[3][3];
#     OperandVal esp; 
#     uint32_t eflags; 
#     uint32_t cc_op; 
#     uint32_t df; 
#     uint32_t hflags; 
#     uint32_t ldt; 
#     uint32_t gdt;
#     uint32_t tr; 
#     uint32_t idt; 
# } EntryHeader; 
    def __init__(self, trace_file):
        result, size = read_format('<I16s', trace_file)
        self.addr, self.rawbytes = result
        self.size = size
        (address, size, mnemonic, op_str) = md.disasm_lite(self.rawbytes, self.addr).next()
        # truncate the rawbytes to just the current instruction
        self.rawbytes = self.rawbytes[:size]
        self.asm = '{} {}'.format(mnemonic, op_str)
        self.tainted = False
        self.ops = []
        for _ in range(5):
            op = OpVal30(trace_file)
            if (op.tainted):
                self.tainted = True
            self.ops.append(op)
            self.size += op.size
        self.memregs = []
        for x in range(3):
            self.memregs.append([])
            for _ in range(3):
                op = OpVal30(trace_file)
                self.memregs[x].append(op)
                self.size += op.size
        self.esp = OpVal30(trace_file)
        self.size += op.size
        result, size = read_format('<IIIIIIII', trace_file)
        self.eflags, self.cc_op, self.df, self.hflags, self.ldt, self.gdt, self.tr, self.idt = result
        self.size += size

    def __repr__(self):
        repr_string = '{} : {} : {}'.format(self.tainted, hex(self.addr), self.asm)
        return repr_string

class OpVal30(object):
# typedef struct {
#     enum OpType type; 
#     uint32_t addr;
#     uint32_t value; 
#     uint64_t tainted;
#     uint32_t origin[4]; 
#     uint32_t offset[4]; 
#     uint32_t source_id[4]; 
#     char new_id[4]; 
# } OperandVal; 
    def __init__(self, trace_file):
        result, size = read_format('<IIIQ', trace_file)
        self.type, self.addr, self.value, self.tainted = result
        self.type_str = OpType.op_type[30][self.type]
        self.size = size
        result, size = read_format('<4I', trace_file)
        self.origin = result
        self.size += size
        result, size = read_format('<4I', trace_file)
        self.offset = result
        self.size += size
        result, size = read_format('<4I', trace_file)
        self.source_id = result
        self.size += size
        result, size = read_format('<4B', trace_file)
        self.new_id = result
        self.size += size

    def __repr__(self):
        repr_string = '''
        Type: {}
        Addr: {}
        Value: {}
        Tainted: {}
        Origin: {}
        Offset: {}
        SourceID: {}
        NewID: {}
        '''.format(self.type, hex(self.addr), hex(self.value), self.tainted, self.origin, self.offset, self.source_id, self.new_id)
        return repr_string

class BitblazeTrace(object):
    def __init__(self, path):
        # initialize the supported versions
        self._read_header = {30: self._read_header_30}
        self._read_procs = {30: self._read_procs_30}
        self._read_instruction = {30: self._read_instruction_30}

        self.trace_file = open(path, 'rb')

        # get total size
        self.trace_file.seek(0, os.SEEK_END)
        self.trace_size = self.trace_file.tell()
        self.trace_file.seek(0)

        # get magicnumber and version
        buf = self.trace_file.read(8)
        self.magic_number, self.version = struct.unpack("II", buf)
        self._read_header[self.version]()
        self._read_procs[self.version]()

        #self._read_procs[version]()

    def _read_header_30(self):
        buf = self.trace_file.read(4)
        self.n_procs = struct.unpack("I", buf)[0]

    def _read_procs_30(self):
        self.procs = []
        for proc_id in range(self.n_procs):
            self.procs.append(ProcRecord30(self.trace_file))

    def _read_instruction_30(self):
        if (self.trace_file.tell() == self.trace_size):
            return None
        eh = EntryHeader30(self.trace_file)
        return eh

    def ReadInstruction(self):
        return self._read_instruction[self.version]()

