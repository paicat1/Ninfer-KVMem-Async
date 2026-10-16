"""从"抛出点返回地址"反查它引用的字符串字面量。

思路：`throw std::logic_error("...")` 在 MSVC 下先 `lea rdx, [rip+disp]` 取字面量地址，
再构造异常对象、再 `call _CxxThrowException`。给定抛出点附近的返回地址，往前扫
`48 8D 15 xx xx xx xx`（lea rdx,[rip+disp32]）并解析目标 RVA，再到磁盘上的 exe 里
把那个 C 字符串读出来 —— 就是这条不变式的原文。

用法：python tools/find_throw_string.py <exe> <rva-of-throw-site> [lookback-bytes]
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sym_resolve import pe_sections  # noqa: E402


class Image:
    def __init__(self, path):
        self.path = path
        self.sections = pe_sections(path)
        self.handle = open(path, 'rb')

    def read_rva(self, rva, length):
        for name, va, vsize, raw_offset, raw_size in self.sections:
            span = min(vsize, raw_size)
            if va <= rva < va + span:
                self.handle.seek(raw_offset + (rva - va))
                return self.handle.read(min(length, va + span - rva))
        return b''

    def string_at(self, rva, limit=200):
        raw = self.read_rva(rva, limit)
        end = raw.find(b'\0')
        if end < 0:
            return None
        text = raw[:end]
        try:
            decoded = text.decode('ascii')
        except UnicodeDecodeError:
            return None
        if len(decoded) < 8 or not decoded.isprintable():
            return None
        return decoded


def main():
    image = Image(sys.argv[1])
    throw_rva = int(sys.argv[2], 16)
    lookback = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x180
    start = throw_rva - lookback
    blob = image.read_rva(start, lookback)
    print('exe=%s  throw site RVA 0x%x  scanning [0x%x, 0x%x)  %d bytes'
          % (os.path.basename(image.path), throw_rva, start, throw_rva, len(blob)))
    for offset in range(0, len(blob) - 7):
        if blob[offset] != 0x48 or blob[offset + 1] != 0x8D:
            continue
        modrm = blob[offset + 2]
        # lea r64, [rip+disp32] : mod=00, rm=101
        if (modrm & 0xC7) != 0x05:
            continue
        reg = (modrm >> 3) & 0x07
        disp = struct.unpack_from('<i', blob, offset + 3)[0]
        target = start + offset + 7 + disp
        text = image.string_at(target)
        if text is None:
            continue
        print('  @rva 0x%08x  lea %s, [rip%+d] -> rva 0x%08x  "%s"'
              % (start + offset, ['rax', 'rcx', 'rdx', 'rbx', 'rsp', 'rbp', 'rsi', 'rdi'][reg],
                 disp, target, text))


if __name__ == '__main__':
    main()
