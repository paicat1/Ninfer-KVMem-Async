"""检查转储内存区间构成，并判断给定地址是否在转储内。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dump_stack import Dump  # noqa: E402

path = sys.argv[1]
dump = Dump(path)
ranges = dump.memory_ranges()
print('ranges=%d total=%.1f MiB' % (len(ranges), sum(s for _, s, _ in ranges) / 1048576.0))
for start, size, _ in sorted(ranges, key=lambda item: -item[1])[:12]:
    print('  0x%016x  %8.2f MiB' % (start, size / 1048576.0))
for text in sys.argv[2:]:
    target = int(text, 16)
    hit = [(start, size) for start, size, _ in ranges if start <= target < start + size]
    print('contains 0x%x: %s' % (target, hit if hit else 'NO'))
