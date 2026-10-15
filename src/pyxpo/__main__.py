"""`python -m pyxpo` runs the CLI (native build scripts of ejected projects call it this way)."""
import sys

from .cli import main

sys.exit(main())
