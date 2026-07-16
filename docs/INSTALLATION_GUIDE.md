# SIRAJ 0.1.0-rc.1 Installation

This release candidate supports Windows only and requires Python 3.13. The
tested interpreter is Python 3.13.14. Python 3.11 and 3.12, Linux, and macOS
are not supported for this release.

Install either the wheel or source distribution in a clean Windows virtual
environment. Validate with `siraj version`, `siraj health`, and
`siraj release-verify`. SQLite is the only supported persistence backend;
renderer behavior is dry-run only. Live AI-provider use remains opt-in.
