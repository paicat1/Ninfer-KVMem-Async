"""最小 x64 栈回溯器：读崩溃转储 + 各模块 .pdata/unwind info，输出真实调用链。

为什么需要它：栈扫描会把 EH 状态数据误当返回地址；本脚本按 Windows x64 ABI 逐帧展开
（UNWIND_INFO + unwind codes），得到可信的帧序列，再用 .map 把 exe 帧解析成函数名。
"""
import bisect
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dump_stack import Dump  # noqa: E402
from sym_resolve import load_map, pe_sections  # noqa: E402

UWOP_PUSH_NONVOL = 0
UWOP_ALLOC_LARGE = 1
UWOP_ALLOC_SMALL = 2
UWOP_SET_FPREG = 3
UWOP_SAVE_NONVOL = 4
UWOP_SAVE_NONVOL_FAR = 5
UWOP_SAVE_XMM128 = 8
UWOP_SAVE_XMM128_FAR = 9
UWOP_PUSH_MACHFRAME = 10

EXTRA_SLOTS = {UWOP_ALLOC_LARGE: None, UWOP_SAVE_NONVOL_FAR: 2, UWOP_SAVE_XMM128_FAR: 2}


class Image:
    def __init__(self, path, base, size):
        self.path = path
        self.base = base
        self.size = size
        self.sections = pe_sections(path) if os.path.exists(path) else []
        self.handle = open(path, 'rb') if os.path.exists(path) else None
        self.pdata = self._load_pdata() if self.handle is not None else []
        self.ends = [entry[1] for entry in self.pdata]
        self.cache = {}

    def _read_file(self, offset, length):
        self.handle.seek(offset)
        return self.handle.read(length)

    def _read_rva(self, rva, length):
        for name, va, vsize, raw_offset, raw_size in self.sections:
            span = min(vsize, raw_size)
            if va <= rva < va + span:
                self.handle.seek(raw_offset + (rva - va))
                return self.handle.read(min(length, va + span - rva))
        return b''

    def _load_pdata(self):
        head = self._read_file(0, 0x1000)  # 头部不在任何节里，直接按文件偏移读
        if len(head) < 0x100:
            return []
        pe_off = struct.unpack_from('<I', head, 0x3C)[0]
        optional = pe_off + 24
        magic = struct.unpack_from('<H', head, optional)[0]
        if magic != 0x20B:
            return []
        dir_count = struct.unpack_from('<I', head, optional + 108)[0]
        if dir_count < 4:
            return []
        dir_rva, dir_size = struct.unpack_from('<II', head, optional + 112 + 3 * 8)
        if dir_rva == 0 or dir_size == 0:
            return []
        blob = self._read_rva(dir_rva, dir_size)
        entries = []
        for offset in range(0, len(blob) - 11, 12):
            begin, end, info = struct.unpack_from('<III', blob, offset)
            if begin == 0 or end == 0 or info == 0:
                continue
            entries.append((begin, end, info))
        entries.sort(key=lambda item: item[0])
        return entries

    def runtime_function(self, rva):
        index = bisect.bisect_right(self.ends, rva) if self.ends else 0
        while index < len(self.pdata):
            begin, end, info = self.pdata[index]
            if begin <= rva < end:
                return (begin, end, info)
            if begin > rva:
                return None
            index += 1
        return None

    def unwind_info(self, rva):
        if rva in self.cache:
            return self.cache[rva]
        raw = self._read_rva(rva, 16)
        if len(raw) < 4:
            self.cache[rva] = None
            return None
        version_flags, prolog, code_count, frame = struct.unpack_from('<BBBB', raw, 0)
        codes_raw = self._read_rva(rva + 4, code_count * 2)
        codes = []
        for index in range(code_count):
            if (index + 1) * 2 > len(codes_raw):
                break
            offset, op = struct.unpack_from('<BB', codes_raw, index * 2)
            codes.append((offset, op & 0x0F, op >> 4))
        chain_rva = None
        if (version_flags >> 3) & 0x4:  # UNW_FLAG_CHAININFO
            chain_raw = self._read_rva(rva + 4 + code_count * 2 + ((code_count & 1) * 2), 12)
            if len(chain_raw) == 12:
                chain_rva = struct.unpack_from('<III', chain_raw, 0)[2]
        info = {
            'flags': version_flags >> 3,
            'frame_register': frame & 0x0F,
            'frame_offset': (frame >> 4) * 16,
            'codes': codes,
            'chain': chain_rva,
        }
        self.cache[rva] = info
        return info


def build_images(dump):
    images = []
    for base, size, name in dump.modules():
        try:
            images.append(Image(name, base, size))
        except Exception:
            continue
    images.sort(key=lambda item: item.base)
    bases = [image.base for image in images]
    return images, bases


def find_image(images, bases, address):
    index = bisect.bisect_right(bases, address) - 1
    if index < 0:
        return None
    image = images[index]
    if address < image.base + image.size:
        return image
    return None


def unwind_one(images, bases, rip, rsp, rbp, dump):
    """返回 (next_rip, next_rsp, next_rbp) 或 None。"""
    image = find_image(images, bases, rip)
    if image is None:
        return None
    rva = rip - image.base
    entry = image.runtime_function(rva)
    codes = []
    frame_register = 0
    frame_offset = 0
    if entry is not None:
        info = image.unwind_info(entry[2])
        if info is not None:
            codes = info['codes']
            frame_register = info['frame_register']
            frame_offset = info['frame_offset']
    # 逐条 unwind code 还原 prolog 前的 RSP（数组按 prolog 倒序给出）
    if frame_register != 0:
        rsp = rbp - frame_offset
    index = 0
    while index < len(codes):
        offset, op, info_bits = codes[index]
        slots = 1
        if op == UWOP_ALLOC_LARGE:
            slots = 1 + (1 if info_bits == 0 else 2)
        elif op in EXTRA_SLOTS and EXTRA_SLOTS[op]:
            slots = 1 + EXTRA_SLOTS[op]
        if op == UWOP_PUSH_NONVOL:
            rsp += 8
        elif op == UWOP_ALLOC_LARGE:
            if info_bits == 0:
                size = codes[index + 1][0] * 8 if index + 1 < len(codes) else 0
                rsp += size
            else:
                if index + 2 < len(codes):
                    low, high = codes[index + 1], codes[index + 2]
                    rsp += low[0] | (high[0] << 8) | (low[1] << 16) | (high[1] << 24)
        elif op == UWOP_ALLOC_SMALL:
            rsp += info_bits * 8 + 8
        elif op == UWOP_SET_FPREG:
            pass
        elif op == UWOP_PUSH_MACHFRAME:
            rsp += 0x38 if info_bits else 0x30
        index += slots
    raw = dump.read_memory(rsp, 8)
    if len(raw) < 8:
        return None
    next_rip = struct.unpack('<Q', raw)[0]
    return next_rip, rsp + 8, rbp


def main():
    dump_path = sys.argv[1]
    map_path = sys.argv[2]
    dump = Dump(dump_path)
    base_map, symbols = load_map(map_path)
    vas = [item[0] for item in symbols]

    def symbol(address):
        index = bisect.bisect_right(vas, address) - 1
        if index < 0:
            return None
        sym_va, name, kind, obj = symbols[index]
        return name, address - sym_va

    exc = dump.exception()
    context = dump.buf[exc['ctx_rva']:exc['ctx_rva'] + exc['ctx_size']]
    rip = struct.unpack_from('<Q', context, 0xF8)[0]
    rsp = struct.unpack_from('<Q', context, 0x98)[0]
    rbp = struct.unpack_from('<Q', context, 0xA0)[0]

    images, bases = build_images(dump)
    print('images: %d (with .pdata: %d)' % (len(images), sum(1 for i in images if i.pdata)))
    print('start rip=0x%016x rsp=0x%016x rbp=0x%016x' % (rip, rsp, rbp))
    print('--- chain ---')
    for step in range(80):
        image = find_image(images, bases, rip)
        label = '?'
        if image is not None:
            rva = rip - image.base
            short = os.path.basename(image.path)
            entry = image.runtime_function(rva)
            func_rva = entry[0] if entry else rva
            label = '%s+0x%x' % (short, rva)
            if short.lower() == 'ninfer-serve.exe':
                resolved = symbol(base_map + func_rva)
                if resolved:
                    label += '  %s+0x%x' % (resolved[0], rva - func_rva)
        print('%2d  %016x  %s' % (step, rip, label))
        if rip == 0:
            break
        moved = unwind_one(images, bases, rip, rsp, rbp, dump)
        if moved is None:
            print('   (cannot unwind further)')
            break
        rip, rsp, rbp = moved


if __name__ == '__main__':
    main()
