"""把崩溃栈上的 RVA 解析成函数名。

输入：
  1) 重链接生成的 .map 文件（MSVC /MAP 格式）
  2) 一个文本文件，每行一个 exe RVA（十六进制，如 0x1cd0ee3）

用法：python tools/sym_resolve.py <map> <rva-list-file>
另：`--verify <exeA> <exeB>` 比较两个镜像除前 1 KiB 外是否逐字节相同（判断 map 是否对得上）。
"""
import bisect
import hashlib
import re
import struct
import sys

LINE = re.compile(r'^\s+[0-9a-fA-F]{4}:[0-9a-fA-F]{8}\s+(\S+)\s+([0-9a-fA-F]{16})\s+(\w+)\s+(\S+)')


def load_map(path):
    symbols = []
    base = None
    with open(path, 'r', encoding='utf-8', errors='replace') as handle:
        for line in handle:
            if base is None and 'Preferred load address is' in line:
                base = int(line.rsplit(' ', 1)[1], 16)
                continue
            match = LINE.match(line)
            if not match:
                continue
            name, va, kind, obj = match.group(1), int(match.group(2), 16), match.group(3), match.group(4)
            symbols.append((va, name, kind, obj))
    symbols.sort(key=lambda item: item[0])
    return base, symbols


def verify(path_a, path_b):
    chunk = 1 << 22
    digests = []
    for path in (path_a, path_b):
        digest = hashlib.sha256()
        with open(path, 'rb') as handle:
            handle.seek(0x400)
            while True:
                block = handle.read(chunk)
                if not block:
                    break
                digest.update(block)
        digests.append(digest.hexdigest())
    same = digests[0] == digests[1]
    print('image[0x400:] sha256 A = %s' % digests[0])
    print('image[0x400:] sha256 B = %s' % digests[1])
    print('IDENTICAL BEYOND 1 KiB: %s' % same)
    return same


def diff_chunks(path_a, path_b, chunk=1 << 20):
    """按 1 MiB 分块比对，打印不同的块范围（定位差异所在区域）。"""
    with open(path_a, 'rb') as handle_a, open(path_b, 'rb') as handle_b:
        index = 0
        bad = 0
        while True:
            block_a = handle_a.read(chunk)
            block_b = handle_b.read(chunk)
            if not block_a and not block_b:
                break
            if block_a != block_b:
                bad += 1
                if bad <= 40:
                    print('  differ: file offset 0x%08x .. 0x%08x' % (index * chunk, (index + 1) * chunk))
            index += 1
    print('chunks total %d, differing %d' % (index, bad))


def pe_sections(path):
    """[(name, virtual_address, virtual_size, raw_offset, raw_size)]"""
    with open(path, 'rb') as handle:
        head = handle.read(0x2000)
    pe_off = struct.unpack_from('<I', head, 0x3C)[0]
    coff = pe_off + 4
    count = struct.unpack_from('<H', head, coff + 2)[0]
    optional_size = struct.unpack_from('<H', head, coff + 16)[0]
    table = coff + 20 + optional_size
    out = []
    for index in range(count):
        entry = table + index * 40
        name = head[entry:entry + 8].rstrip(b'\0').decode('ascii', 'replace')
        virtual_size, virtual_address, raw_size, raw_offset = struct.unpack_from('<IIII', head, entry + 8)
        out.append((name, virtual_address, virtual_size, raw_offset, raw_size))
    return out


def section_of(sections, file_offset):
    for name, va, vsize, raw_offset, raw_size in sections:
        if raw_offset <= file_offset < raw_offset + raw_size:
            return '%s (rva 0x%x)' % (name, va + (file_offset - raw_offset))
    return '(headers/not mapped)'


def diff_range(path_a, path_b, start, end, grain=64):
    """按 grain 粒度找出差异块，并把文件偏移翻成节 + RVA。"""
    sections = pe_sections(path_a)
    ranges = []
    with open(path_a, 'rb') as handle_a, open(path_b, 'rb') as handle_b:
        handle_a.seek(start)
        handle_b.seek(start)
        offset = start
        while offset < end:
            block_a = handle_a.read(grain)
            block_b = handle_b.read(grain)
            if not block_a and not block_b:
                break
            if block_a != block_b:
                if ranges and ranges[-1][1] == offset:
                    ranges[-1][1] = offset + grain
                else:
                    ranges.append([offset, offset + grain])
            offset += grain
    print('%s' % path_a)
    print('vs %s' % path_b)
    print('%d differing %d-byte ranges in [0x%x, 0x%x):' % (len(ranges), grain, start, end))
    for begin, finish in ranges:
        print('  0x%08x .. 0x%08x  %s' % (begin, finish, section_of(sections, begin)))


def main():
    if sys.argv[1] == '--verify':
        verify(sys.argv[2], sys.argv[3])
        return
    if sys.argv[1] == '--diff':
        diff_chunks(sys.argv[2], sys.argv[3])
        return
    if sys.argv[1] == '--diff-range':
        diff_range(sys.argv[2], sys.argv[3], int(sys.argv[4], 16), int(sys.argv[5], 16),
                   int(sys.argv[6]) if len(sys.argv) > 6 else 64)
        return
    if sys.argv[1] == '--sections':
        for entry in pe_sections(sys.argv[2]):
            print('  %-8s va=0x%08x vsize=0x%08x raw=0x%08x rawsize=0x%08x' % entry)
        return
    map_path, list_path = sys.argv[1], sys.argv[2]
    base, symbols = load_map(map_path)
    print('map: %s | preferred base 0x%x | %d symbols' % (map_path, base, len(symbols)))
    addresses = []
    for line in open(list_path):
        line = line.strip()
        if line.startswith('RVA '):
            addresses.append(int(line.split()[1], 16))
        elif line.startswith('0x'):
            addresses.append(int(line, 16))
    vas = [item[0] for item in symbols]
    for rva in sorted(set(addresses)):
        va = base + rva
        index = bisect.bisect_right(vas, va) - 1
        if index < 0:
            print('0x%08x -> (before first symbol)' % rva)
            continue
        sym_va, name, kind, obj = symbols[index]
        print('0x%08x -> +0x%-6x %s   [%s %s]' % (rva, va - sym_va, name, kind, obj))


if __name__ == '__main__':
    main()
