"""Minimal Windows minidump reader (no third-party deps).

用途：从 ninfer-serve.exe 的崩溃转储里取出「崩溃线程的调用栈返回地址」，并把每个地址
归位到「模块 + RVA」，便于用同一份二进制重链接得到的 .map 文件做符号化。

不是通用工具：只实现定位崩溃现场所需的最小流集合。
  - Stream 3  ThreadListStream
  - Stream 4  ModuleListStream
  - Stream 5  MemoryListStream
  - Stream 6  ExceptionStream
  - Stream 9  Memory64ListStream
"""
import struct
import sys
import os

ST_THREADS = 3
ST_MODULES = 4
ST_MEMORY = 5
ST_EXCEPTION = 6
ST_MEMORY64 = 9

MAX_FRAMES = 96
STACK_WINDOW = 0x20000  # 128 KiB of stack from Rsp


class Dump:
    def __init__(self, path):
        with open(path, 'rb') as handle:
            self.buf = handle.read()
        signature, version, count, dir_rva = struct.unpack_from('<IIII', self.buf, 0)
        if signature != 0x504D444D:
            raise ValueError('not a minidump (MDMP) file')
        self.streams = {}
        for index in range(count):
            stype, size, rva = struct.unpack_from('<III', self.buf, dir_rva + index * 12)
            self.streams.setdefault(stype, (size, rva))

    def modules(self):
        size, rva = self.streams[ST_MODULES]
        (count,) = struct.unpack_from('<I', self.buf, rva)
        out = []
        for index in range(count):
            base = rva + 4 + index * 108
            base_of_image, size_of_image = struct.unpack_from('<QI', self.buf, base)
            name_rva = struct.unpack_from('<I', self.buf, base + 20)[0]
            (length,) = struct.unpack_from('<I', self.buf, name_rva)
            name = self.buf[name_rva + 4:name_rva + 4 + length].decode('utf-16-le', 'replace')
            out.append((base_of_image, size_of_image, name))
        return out

    def threads(self):
        size, rva = self.streams[ST_THREADS]
        (count,) = struct.unpack_from('<I', self.buf, rva)
        out = []
        for index in range(count):
            base = rva + 4 + index * 48
            thread_id = struct.unpack_from('<I', self.buf, base)[0]
            stack_start = struct.unpack_from('<Q', self.buf, base + 24)[0]
            ctx_size, ctx_rva = struct.unpack_from('<II', self.buf, base + 40)
            out.append({'id': thread_id, 'stack_start': stack_start,
                        'ctx_rva': ctx_rva, 'ctx_size': ctx_size})
        return out

    def exception(self):
        size, rva = self.streams[ST_EXCEPTION]
        thread_id = struct.unpack_from('<I', self.buf, rva)[0]
        code, flags, address = struct.unpack_from('<IIQ', self.buf, rva + 8)
        params = struct.unpack_from('<15Q', self.buf, rva + 8 + 16 + 16)
        ctx_size, ctx_rva = struct.unpack_from('<II', self.buf, rva + 160)
        return {'thread_id': thread_id, 'code': code, 'flags': flags, 'address': address,
                'params': params, 'ctx_rva': ctx_rva, 'ctx_size': ctx_size}

    def memory_ranges(self):
        """Returns [(start, size, rva_of_data)] across either memory stream."""
        out = []
        if ST_MEMORY in self.streams:
            size, rva = self.streams[ST_MEMORY]
            (count,) = struct.unpack_from('<I', self.buf, rva)
            for index in range(count):
                start, data_size, data_rva = struct.unpack_from('<QII', self.buf, rva + 4 + index * 16)
                out.append((start, data_size, data_rva))
        if ST_MEMORY64 in self.streams:
            size, rva = self.streams[ST_MEMORY64]
            count, base_rva = struct.unpack_from('<QQ', self.buf, rva)
            cursor = base_rva
            for index in range(count):
                start, data_size = struct.unpack_from('<QQ', self.buf, rva + 16 + index * 16)
                out.append((start, data_size, cursor))
                cursor += data_size
        return out

    def read_memory(self, address, length):
        """Best-effort contiguous read from the dump's memory ranges."""
        chunks = []
        remaining = length
        cursor = address
        ranges = self.memory_ranges()
        while remaining > 0:
            hit = None
            for start, size, data_rva in ranges:
                if start <= cursor < start + size:
                    hit = (start, size, data_rva)
                    break
            if hit is None:
                break
            start, size, data_rva = hit
            take = min(remaining, start + size - cursor)
            offset = data_rva + (cursor - start)
            chunks.append(self.buf[offset:offset + take])
            cursor += take
            remaining -= take
        return b''.join(chunks)


def pe_text_range(path):
    """(.text virtual address, .text virtual size) of an image, or None."""
    if not os.path.exists(path):
        return None
    with open(path, 'rb') as handle:
        head = handle.read(0x2000)
    if head[:2] != b'MZ':
        return None
    pe_off = struct.unpack_from('<I', head, 0x3C)[0]
    if head[pe_off:pe_off + 4] != b'PE\0\0':
        return None
    coff = pe_off + 4
    section_count = struct.unpack_from('<H', head, coff + 2)[0]
    optional_size = struct.unpack_from('<H', head, coff + 16)[0]
    optional = coff + 20
    image_base = struct.unpack_from('<Q', head, optional + 24)[0]
    sections = optional + optional_size
    for index in range(section_count):
        entry = sections + index * 40
        name = head[entry:entry + 8].rstrip(b'\0')
        virtual_size, virtual_address = struct.unpack_from('<II', head, entry + 8)
        if name == b'.text':
            # 返回 RVA 而不是首选 VA：模块是 ASLR 载入的，比较必须用载入基址 + RVA。
            return virtual_address, virtual_size
    return None


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.environ['LOCALAPPDATA'], 'CrashDumps', 'ninfer-serve.exe.16892.dmp')
    dump = Dump(path)
    print('dump: %s (%.1f MiB)' % (path, len(dump.buf) / 1048576.0))
    print('streams: %s' % sorted(dump.streams))

    modules = dump.modules()
    print('\nmodules (%d):' % len(modules))
    for base, size, name in modules:
        if 'ninfer' in name.lower() or 'ucrtbase' in name.lower() or 'cudart' in name.lower():
            print('  %016x +%08x  %s' % (base, size, name))

    exc = dump.exception()
    print('\nexception: code=0x%08x flags=0x%08x address=0x%016x thread=0x%x' %
          (exc['code'], exc['flags'], exc['address'], exc['thread_id']))
    print('  params[0]=0x%x (fastfail code)' % exc['params'][0])

    context = dump.buf[exc['ctx_rva']:exc['ctx_rva'] + exc['ctx_size']]
    rip = struct.unpack_from('<Q', context, 0xF8)[0]
    rsp = struct.unpack_from('<Q', context, 0x98)[0]
    rbp = struct.unpack_from('<Q', context, 0xA0)[0]
    print('  rip=0x%016x rsp=0x%016x rbp=0x%016x' % (rip, rsp, rbp))

    # exe identity
    exe_entry = None
    for base, size, name in modules:
        if name.lower().endswith('ninfer-serve.exe'):
            exe_entry = (base, size, name)
            break
    exe_text = None
    if exe_entry:
        exe_text = pe_text_range(exe_entry[2])
        print('\nexe: base=0x%016x size=0x%x path=%s' % exe_entry)
        if exe_text:
            print('  .text va=0x%016x size=0x%x' % exe_text)

    stack = dump.read_memory(rsp, STACK_WINDOW)
    print('\nstack window from rsp: %d bytes read' % len(stack))

    def locate(value):
        for base, size, name in modules:
            if base <= value < base + size:
                return name, value - base
        return None, None

    want_rvas = len(sys.argv) > 2 and sys.argv[2] == 'rvas'
    chain_mode = len(sys.argv) > 2 and sys.argv[2] == 'chain'
    print('\ncandidate return addresses (module + RVA), scan of first 8 KiB:')
    limit = len(stack) if (want_rvas or chain_mode) else min(len(stack), 0x2000)
    for offset in range(0, limit - 8, 8):
        value = struct.unpack_from('<Q', stack, offset)[0]
        if not (0x10000 <= value < 0x800000000000):
            continue
        name, rva = locate(value)
        if name is None:
            continue
        short = os.path.basename(name)
        tag = ''
        in_exe_text = False
        if exe_text and exe_entry and exe_entry[0] <= value < exe_entry[0] + exe_entry[1]:
            if exe_entry[0] + exe_text[0] <= value < exe_entry[0] + exe_text[0] + exe_text[1]:
                tag = '  <== EXE .text'
                in_exe_text = True
        if want_rvas:
            if in_exe_text:
                print('RVA 0x%x' % (value - exe_entry[0]))
            continue
        if chain_mode:
            print('OFF 0x%06x  %s+0x%x' % (offset, short, rva))
            continue
        print('  [rsp+0x%04x] 0x%016x  %s+0x%x%s' % (offset, value, short, rva, tag))


if __name__ == '__main__':
    main()
