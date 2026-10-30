# -*- coding: utf-8 -*-
import io
for f in ('valley_watch.ps1', 'valley_induce.ps1', 'a2gate.py', 'gpu_sampler.py',
          'ab_interleave.ps1', 'async_abab.ps1', 'deeppool_async_onoff.ps1',
            r'experiments\round2b_15k.py'):
    p = r'J:\ninfer-kvmem\scripts' + chr(92) + f
    t = io.open(p, 'rb').read().decode('utf-8')
    lines = t.splitlines()
    for i, seg in enumerate(lines):
        if '.temp' in seg and ('watch_dmon' in seg or 'state_journal' in seg
                               or 'induce_' in seg or 'abab_text' in seg
                               or 'gate_%s' in seg or 'gpu_samples' in seg
                               or 'reqlog_' in seg):
            k = seg.find('.temp')
            j = max(seg.find('watch_dmon', k), seg.find('state_journal', k),
                    seg.find('induce_', k), seg.find('abab_text', k),
                    seg.find('gate_%s', k), seg.find('gpu_samples', k),
                    seg.find('reqlog_', k))
            if j > k:
                mid = seg[k + 5:j]
                print(f, i + 1, 'bs =', mid.count(chr(92)), repr(mid[:40]))
