import argparse
import json
import sys
from .contracts import ContractError, TOOLS
from .service import Service
from . import __version__


def main(argv=None):
    parser = argparse.ArgumentParser(prog="whochose")
    parser.add_argument("--data-root")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    call = sub.add_parser("call", help="Explicit manual fallback for the same seven business tools")
    call.add_argument("tool", choices=TOOLS)
    call.add_argument("--input", required=True, help="UTF-8 JSON file, or - for stdin")
    verify = sub.add_parser("verify", help="Explicitly run a local command and record its actual exit status/code versions")
    verify.add_argument("--task", required=True)
    verify.add_argument("--purpose", required=True)
    verify.add_argument("run_command", nargs=argparse.REMAINDER)
    for name in ("report", "export"):
        export = sub.add_parser(name)
        export.add_argument("--task", required=True)
        export.add_argument("--format", choices=["html", "md"], default="html" if name == "report" else "md")
        export.add_argument("--output")
    package = sub.add_parser("package", help="Prepare a manual local plugin; does not install or trust it")
    package.add_argument("--output", required=True)
    package.add_argument("--python")
    package.add_argument("--runtime-data")
    args = parser.parse_args(argv)
    try:
        if args.command == "package":
            from .packaging import package_plugin
            print(json.dumps(package_plugin(args.output, args.python, args.runtime_data), ensure_ascii=False, indent=2))
            return 0
        service = Service(args.data_root)
        if args.command == "doctor":
            import importlib.metadata
            import sqlite3
            result = {"version": __version__, "python": sys.version.split()[0], "mcp_sdk": importlib.metadata.version("mcp"),
                      "data_root": str(service.store.root), "sqlite": sqlite3.sqlite_version,
                      "automatic_hook_coverage": "incomplete_until_host_verified", "tools": list(TOOLS)}
        elif args.command in {"report", "export"}:
            from .export import write_report
            result = write_report(service.store, args.task, args.format, args.output)
        elif args.command == "verify":
            from .implementation import record_run
            command = args.run_command[1:] if args.run_command[:1] == ["--"] else args.run_command
            result = record_run(service.store, args.task, command, args.purpose)
        else:
            from pathlib import Path
            payload = json.loads(sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8-sig"))
            result = getattr(service, args.tool)(**payload)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ContractError, ValueError, OSError) as exc:
        print(json.dumps({"ok": False, "error": {"code": getattr(exc, "code", "INPUT_OR_IO_ERROR"), "message": str(exc)}}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
