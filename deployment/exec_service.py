"""Load only this service's generated settings and replace the entrypoint process."""

import json
import os
import sys
from pathlib import Path

settings = json.loads(Path("/settings/settings.json").read_text())
os.environ.update(settings)
os.execvp(sys.argv[1], sys.argv[1:])
