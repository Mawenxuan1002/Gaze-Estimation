from pathlib import Path

from Cython.Build import cythonize
from setuptools import Extension, setup

PACKAGE_DIR = Path(__file__).parent / "gaze_tracker"
SOURCES = sorted(
    path for path in PACKAGE_DIR.glob("*.py")
    if path.name not in {"__init__.py", "__main__.py"}
)

extensions = [
    Extension(f"gaze_tracker.{path.stem}", [str(path)])
    for path in SOURCES
]

setup(
    name="gaze-tracker-compiled",
    ext_modules=cythonize(
        extensions,
        compiler_directives={"language_level": "3"},
        annotate=False,
    ),
)
