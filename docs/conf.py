import os
import sys
from datetime import datetime

# Add project root and src to sys.path so Sphinx can find the `redisgraph` package
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

project = "Redis Graph Connection Manager"
author = "Zobayer Hasan"
current_year = datetime.now().year
# noinspection PyShadowingBuiltins
copyright = f"{current_year}, {author}"
# The full version, including alpha/beta/rc tags
release = "0.1.7"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "haiku"
