# -*- coding: utf-8 -*-
"""daily 安全追加器（T#0043 根治：Edit 锚点误替换曾两次覆写历史条目）。

用法:
  python -X utf8 tools/daily_append.py <file> --entry-file <utf8文件>
  python -X utf8 tools/daily_append.py <file> --entry "one line"
  python -X utf8 tools/daily_append.py --selftest   （内置三场景自检）
  可选: --sep "> AI生成"   （CodeBuddy daily 格式：新条目须以该行引导）

行为:
  1. 追加 "- [UTC时间] <entry>" 到文件末尾（保留原换行风格 CRLF/LF 与 BOM 状态）
  2. 回读完整性断言：原有全部 "- [" 条目行逐条仍在 + 新条目在位
  3. 原子写（tmp + os.replace），断言失败自动回滚 exit 1
  4. 中文条目一律走 --entry-file（UTF-8），规避 PS5.1 命令行 GBK（T-028）
  5. --selftest：T-HARVEST 收割（2026-09-08，源自 .temp/test_daily_append_sandbox.py
     三场景：LF 连追 / CRLF+sep+中文 / 多行折叠），自测与 append_entry 同源实现
"""
import argparse
import os
import sys
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")


def _read(path):
    raw = open(path, "rb").read()
    return raw, raw.startswith(b"\xef\xbb\xbf"), raw.decode("utf-8-sig")


def append_entry(path, entry, sep=None, localz=False):
    """核心追加逻辑（main 与 selftest 共用同源实现）。返回 (rc, msg)。"""
    entry = " ".join(entry.split())
    if not entry:
        return 1, "FAIL: 空条目"

    raw, has_bom, text = _read(path)
    crlf = "\r\n" in text
    nl = "\r\n" if crlf else "\n"

    old_entries = [l for l in text.splitlines() if l.startswith("- [")]
    old_sep_count = text.count(sep) if sep else 0
    ts = (datetime.now() if localz else datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_line = "- [%s] %s" % (ts, entry)

    body = text.rstrip("\r\n")
    tail = new_line
    if sep:
        last_nonempty = ""
        for l in reversed(body.splitlines()):
            if l.strip():
                last_nonempty = l.strip()
                break
        if last_nonempty != sep.strip():
            tail = sep + nl + new_line
    new_text = body + nl + tail + nl

    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write((b"\xef\xbb\xbf" if has_bom else b"") + new_text.encode("utf-8"))
    os.replace(tmp, path)

    # 回读完整性断言
    _, _, back = _read(path)
    back_entries = [l for l in back.splitlines() if l.startswith("- [")]
    lost = [e for e in old_entries if e not in back_entries]
    sep_ok = (back.count(sep) >= old_sep_count) if sep else True
    if lost or back_entries[-1] != new_line or not sep_ok:
        with open(path, "wb") as f:
            f.write(raw)  # 回滚
        msgs = ["FAIL: 完整性断言失败, 已回滚"] + ["  丢失:" + l[:80] for l in lost]
        return 1, "\n".join(msgs)
    return 0, "PASS: 追加1条 (原%d条全在, 现%d条; crlf=%s bom=%s)" % (
        len(old_entries), len(back_entries), crlf, has_bom)


def run_selftest():
    """内置三场景自检（T-HARVEST 收割入库；临时目录自包含，测完即清）。"""
    import shutil
    import tempfile
    d = tempfile.mkdtemp(prefix="daily_append_selftest_")
    fails = 0
    try:
        # 场景1: LF 无 sep，连追两条，旧条目保全
        fa = os.path.join(d, "a.md")
        open(fa, "w", encoding="utf-8", newline="\n").write(
            "- [2026-09-08T00:00:00Z] 旧条目一\n- [2026-09-08T00:01:00Z] 旧条目二\n")
        rc1, _ = append_entry(fa, "selftest one")
        rc2, _ = append_entry(fa, "selftest two")
        back = open(fa, encoding="utf-8").read()
        ok1 = (rc1 == 0 and rc2 == 0 and back.count("- [") == 4
               and "旧条目一" in back and "旧条目二" in back and back.count("selftest") == 2)
        print(("PASS" if ok1 else "FAIL") + " 场景1 LF无sep连追两条")
        fails += 0 if ok1 else 1

        # 场景2: CRLF + sep 引导（CodeBuddy 式）+ 中文条目 + 换行/BOM 保持
        fb = os.path.join(d, "b.md")
        open(fb, "wb").write(("> AI生成\r\n- [2026-09-08T00:00:00Z] 中文旧条目甲\r\n\r\n"
                              "> AI生成\r\n- [2026-09-08T00:01:00Z] 中文旧条目乙\r\n\r\n> AI生成\r\n").encode("utf-8"))
        rc3, _ = append_entry(fb, "中文新条目丙：完整性断言验证", sep="> AI生成")
        back_raw = open(fb, "rb").read()
        back = back_raw.decode("utf-8-sig")
        ok2 = (rc3 == 0 and "中文旧条目甲" in back and "中文旧条目乙" in back
               and "中文新条目丙" in back and b"\r\n" in back_raw and back.count("> AI生成") == 3)
        print(("PASS" if ok2 else "FAIL") + " 场景2 CRLF+sep+中文")
        fails += 0 if ok2 else 1

        # 场景3: 多行 entry 折叠为单行
        fc = os.path.join(d, "c.md")
        open(fc, "w", encoding="utf-8", newline="\n").write("- [2026-09-08T00:00:00Z] 基线\n")
        rc4, _ = append_entry(fc, "第一行\n第二行")
        back = open(fc, encoding="utf-8").read()
        ok3 = rc4 == 0 and back.count("- [") == 2 and "第一行 第二行" in back
        print(("PASS" if ok3 else "FAIL") + " 场景3 多行折叠单行")
        fails += 0 if ok3 else 1
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("selftest: " + ("全部通过" if fails == 0 else "%d 项失败" % fails))
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?", help="目标 daily 文件")
    ap.add_argument("--entry")
    ap.add_argument("--entry-file")
    ap.add_argument("--sep", default=None, help="条目引导行（如 CodeBuddy daily 的 '> AI生成'）")
    ap.add_argument("--localz", action="store_true", help="时间戳用本地时间标Z（CodeBuddy daily 惯例）；默认真实UTC（TeleAgent daily 惯例）")
    ap.add_argument("--selftest", action="store_true", help="内置三场景自检，无需 file")
    a = ap.parse_args()

    if a.selftest:
        return run_selftest()
    if not a.file:
        ap.error("需要 <file>（或 --selftest）")

    if a.entry_file:
        entry = open(a.entry_file, encoding="utf-8-sig").read().strip()
    elif a.entry:
        entry = a.entry.strip()
    else:
        print("FAIL: 未提供条目（--entry / --entry-file）")
        return 1

    rc, msg = append_entry(a.file, entry, sep=a.sep, localz=a.localz)
    print(msg)
    return rc


if __name__ == "__main__":
    sys.exit(main())
