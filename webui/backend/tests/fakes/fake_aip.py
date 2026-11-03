"""Stand-in for vendor/dfs-aip/aip.py used by the backend tests."""
import os
import sys

args = sys.argv[1:]
i = args.index("--cache")
args = args[:i] + args[i + 2:]

log = os.environ.get("FAKE_AIP_LOG")
if log:
    with open(log, "a") as f:
        f.write(" ".join(args) + "\n")

if args[:2] == ["toc", "fetch"]:
    sys.exit(int(os.environ.get("FAKE_AIP_TOC_FAIL", "0")))
if args[:2] == ["toc", "list"]:
    print(f"vfr {os.environ.get('FAKE_AIRAC', '2026-11-12')}")
    sys.exit(0)
if args[0] == "pdf":
    if os.environ.get("FAKE_AIP_PDF_FAIL"):
        print("boom", file=sys.stderr)
        sys.exit(1)
    out = args[args.index("--output") + 1]
    with open(out, "wb") as f:
        f.write(b"%PDF-fake raw " + os.environ.get("FAKE_AIRAC", "").encode())
    print("page-1")
    print("page-2")
    sys.exit(0)
sys.exit(2)
