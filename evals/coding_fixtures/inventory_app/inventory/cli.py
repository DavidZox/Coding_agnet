"""命令列介面：python3 -m inventory.cli --file inv.json <add|remove|report> ..."""
import argparse
import sys

from . import storage


def build_parser():
    p = argparse.ArgumentParser(prog="inventory")
    p.add_argument("--file", default="inventory.json", help="庫存檔路徑")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="新增品項")
    a.add_argument("name")
    a.add_argument("price", type=float)
    a.add_argument("qty", type=int, nargs="?", default=1)
    r = sub.add_parser("remove", help="移除數量")
    r.add_argument("name")
    r.add_argument("qty", type=int, nargs="?", default=1)
    sub.add_parser("report", help="列出庫存")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    inv = storage.load(args.file)
    if args.cmd == "add":
        inv.add(args.name, args.price, args.qty)
    elif args.cmd == "remove":
        inv.remove(args.name, args.qty)
    elif args.cmd == "report":
        print(inv.report())
        return 0
    storage.save(inv, args.file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
