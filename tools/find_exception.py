"""在崩溃转储里找"正在抛出的异常对象"，直接读出它的 what() 消息。

原理：MSVC 的 std::logic_error / runtime_error / bad_alloc 等对象首字段是 vtable 指针
（符号 ??_7logic_error@std@@6B@ 等，可从 .map 取到 RVA）。对象 +8 处是消息指针。
转储只含私有内存，消息字符串通常在 exe 的 .rdata（文件映像）里 —— 于是把该指针
换算成 RVA，回到磁盘上的 exe 文件里把字符串读出来。
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dump_stack import Dump  # noqa: E402
from sym_resolve import pe_sections  # noqa: E402

# 从 map 取到的 RVA（section 2 = .rdata）
VTABLES = {
    0x1D82C98: 'std::bad_alloc',
    0x1D82FB8: 'std::logic_error',
    0x1D82FD0: 'std::invalid_argument',
    0x1D82FE8: 'std::runtime_error',
    0x1DA64E0: 'std::out_of_range',
    0x1DB6878: 'std::length_error',
}


class ImageReader:
    """按 RVA 从磁盘上的 exe 读字节（文件映像部分）。"""

    def __init__(self, path):
        self.path = path
        self.sections = pe_sections(path)
        self.handle = open(path, 'rb')

    def read_rva(self, rva, length):
        for name, va, vsize, raw_offset, raw_size in self.sections:
            if va <= rva < va + min(vsize, raw_size):
                self.handle.seek(raw_offset + (rva - va))
                return self.handle.read(min(length, va + min(vsize, raw_size) - rva))
        return b''

    def cstring_rva(self, rva, limit=240):
        raw = self.read_rva(rva, limit)
        end = raw.find(b'\0')
        return (raw[:end] if end >= 0 else raw).decode('utf-8', 'replace')


def main():
    path = sys.argv[1]
    exe_path = sys.argv[2]
    dump = Dump(path)
    modules = dump.modules()
    exe_base = None
    for base, size, name in modules:
        if name.lower().endswith('ninfer-serve.exe'):
            exe_base = base
            break
    image = ImageReader(exe_path)
    print('exe base 0x%x  image=%s' % (exe_base, exe_path))

    targets = {}
    for rva, label in VTABLES.items():
        targets[struct.pack('<Q', exe_base + rva)] = label

    ranges = dump.memory_ranges()
    print('memory ranges: %d, total %.1f MiB' % (len(ranges), sum(s for _, s, _ in ranges) / 1048576.0))

    hits = 0
    for start, size, data_rva in ranges:
        blob = dump.buf[data_rva:data_rva + size]
        for pattern, label in targets.items():
            cursor = 0
            while True:
                found = blob.find(pattern, cursor)
                if found < 0:
                    break
                cursor = found + 1
                address = start + found
                data1 = struct.unpack_from('<Q', blob, found + 8)[0] if found + 16 <= len(blob) else 0
                data2 = struct.unpack_from('<Q', blob, found + 16)[0] if found + 24 <= len(blob) else 0
                message = ''
                where = 'not-in-image'
                if exe_base <= data1 < exe_base + 0x4E92E000:
                    rva = data1 - exe_base
                    message = image.cstring_rva(rva)
                    where = 'exe+0x%x' % rva
                hits += 1
                print('  %s @ 0x%016x  _Data1=0x%x (%s)  _Data2=0x%x  what="%s"'
                      % (label, address, data1, where, data2, message))
                if hits > 200:
                    print('  ... (truncated)')
                    return
    print('total hits: %d' % hits)


if __name__ == '__main__':
    main()
