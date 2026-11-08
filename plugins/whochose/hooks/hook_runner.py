"""Works in the bundled plugin and with a separately installed development package."""
from pathlib import Path
import sys

plugin_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(plugin_root))
from whochose.hooks import main

raise SystemExit(main())
