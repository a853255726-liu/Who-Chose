"""Prepare a versioned manual local plugin. Never registers it globally or trusts hooks."""
import base64
import json
import os
from pathlib import Path
import shutil
import sys
import zipfile
from .contracts import require, digest
from . import __version__


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def package_plugin(output, python=None, data_root=None):
    output = Path(output).absolute()
    require(not output.exists() and not output.is_symlink(), "OUTPUT_EXISTS", "Prepare into a new versioned directory")
    require(all(not p.is_symlink() and not (hasattr(p, "is_junction") and p.is_junction()) for p in output.parents), "LINKED_PATH", "Package destination must not traverse links")
    interpreter = Path(python or sys.executable).resolve(strict=True)
    source = Path(__file__).resolve().parents[1]
    plugin_source = source / "plugins" / "whochose"
    require(plugin_source.is_dir(), "PACKAGE_SOURCE_MISSING", "Prepare from the portable source bundle/project checkout")
    output.mkdir(parents=True)
    plugin = output / "whochose"
    shutil.copytree(plugin_source, plugin, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(Path(__file__).parent, plugin / "whochose", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    launcher = plugin / "scripts" / "launch.py"
    launcher.parent.mkdir(exist_ok=True)
    launcher.write_text('from pathlib import Path\nimport sys\nsys.path.insert(0,str(Path(__file__).resolve().parents[1]))\nfrom whochose.server import main\nmain()\n', encoding="utf-8")
    env = {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    if data_root:
        env["WHOCHOSE_DATA"] = str(Path(data_root).absolute())
    write_json(plugin / ".mcp.json", {"mcpServers": {"whochose": {
        "command": str(interpreter), "args": ["-B", str(launcher)], "env": env,
        "startup_timeout_sec": 30, "tool_timeout_sec": 60}}})
    hooks_path = plugin / "hooks" / "hooks.json"
    hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
    quote = lambda value: "'" + str(value).replace("'", "''") + "'"
    script = "$env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'; "
    if data_root:
        script += "$env:WHOCHOSE_DATA=" + quote(Path(data_root).absolute()) + "; "
    script += "& " + quote(interpreter) + " -B (Join-Path $env:PLUGIN_ROOT 'hooks/hook_runner.py'); exit $LASTEXITCODE"
    command_windows = "powershell.exe -NoLogo -NoProfile -NonInteractive -EncodedCommand " + base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    for groups in hooks["hooks"].values():
        for group in groups:
            for handler in group["hooks"]:
                handler["command"] = f'"{interpreter}" -B "${{PLUGIN_ROOT}}/hooks/hook_runner.py"'
                handler["commandWindows"] = command_windows
    write_json(hooks_path, hooks)
    marketplace = output / ".claude-plugin" / "marketplace.json"
    write_json(marketplace, {"name": "whochose-local", "plugins": [{"name": "whochose", "source": {"source": "local", "path": "./whochose"},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}, "category": "Developer Tools"}]})
    hashes = {p.relative_to(output).as_posix(): digest(p.read_bytes()) for p in sorted(output.rglob("*")) if p.is_file()}
    result = {"version": __version__, "plugin_root": str(plugin), "marketplace": str(marketplace), "python": str(interpreter),
        "data_root": str(Path(data_root).absolute()) if data_root else "user_level_default", "host_config_modified": False,
        "hooks_trusted": False, "machine_specific_paths": True, "files": hashes}
    write_json(output / "installation.json", result)
    return result


def source_archive(output):
    output = Path(output).absolute()
    require(not output.exists(), "OUTPUT_EXISTS", "Refusing to overwrite an archive")
    source = Path(__file__).resolve().parents[1]
    selected = []
    for name in ["pyproject.toml", "README.md", ".gitignore", "requirements-tested-windows.txt"]:
        selected.append(source / name)
    for folder in ["whochose", "plugins/whochose", "scripts", "tests"]:
        selected.extend(p for p in (source / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
    selected.extend(source / "docs" / name for name in ["PRODUCT_BASELINE.md", "INSTALL.md", "VALIDATION.md", "IMPLEMENTATION_LOG.md"])
    selected.extend(p for p in (source / "docs/evidence").rglob("*") if p.is_file())
    require(all(p.is_file() and not p.is_symlink() for p in selected), "PACKAGE_SOURCE_MISSING", "Release inputs are missing or linked")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(selected)):
            archive.write(path, "WhoChose/" + path.relative_to(source).as_posix())
    return {"path": str(output), "sha256": digest(output.read_bytes()), "file_count": len(set(selected)), "portable_source": True}
