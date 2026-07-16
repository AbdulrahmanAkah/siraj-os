"""Setuptools release-build customisation for SIRAJ.

The repository retains legacy test modules directly under ``src`` for
backward-compatible local development.  They are not runtime modules and
must not be copied into published distributions.
"""

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py


class build_py(_build_py):
    """Exclude legacy root-package test modules from built artifacts."""

    def find_package_modules(self, package: str, package_dir: str):
        modules = super().find_package_modules(package, package_dir)
        if package == "src":
            return [
                module
                for module in modules
                if not module[1].startswith("test_")
            ]
        return modules


setup(cmdclass={"build_py": build_py})
