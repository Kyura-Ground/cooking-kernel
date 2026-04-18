# Contributing to cooking-kernel

First off, thanks for taking the time to contribute! 🎉

The following is a set of guidelines for contributing to **cooking-kernel**. These are mostly guidelines, not rules. Use your best judgment, and feel free to propose changes to this document in a pull request.

## How Can I Contribute?

### Reporting Bugs

* **Check the existing issues** to see if the bug has already been reported.
* **Use the Bug Report template** if available, or provide as much detail as possible (logs, CI environment, kernel version).

### Suggesting Enhancements

* **Open an issue** with the "enhancement" tag.
* Explain why this enhancement would be useful and how it should work.

### Pull Requests

1. **Fork the repository** and create your branch from `main`.
2. **Run ShellCheck** on your scripts before committing.
3. **Ensure the CI passes** on your fork.
4. **Keep your PR small and focused** on a single change.
5. **Update the README.md** if you are adding new configuration options.

## Scripting Standards

* Use `set -euo pipefail` in all scripts.
* Follow the existing logging style: `info`, `success`, `error`.
* Use `shellcheck` to validate your code.
* Prefer modularity (separate functions for separate tasks).

## License

By contributing, you agree that your contributions will be licensed under its MIT License.
