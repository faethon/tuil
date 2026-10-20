Release Checklist
-----------------

1. Switch to the master branch and stash/commit any uncommited changes.
2. Bump the version in [version.py](version.py) and [tuil/\_\_version\_\_.py](tuil/__version__.py).
3. Update the release notes in the [CHANGELOG.rst](CHANGELOG.rst).
4. Review and update [AUTHORS.rst](AUTHORS.rst) manually if needed.
5. Re-generate the manpage by running [``scripts/build_manpage.py``](scripts/build_manpage.py).
6. Run tests with [``scripts/ci.sh``](scripts/ci.sh).
7. Commit all changes to the correct branch and tag the correct commit with its version.
8. Clean out any old build/release files by running [``scripts/pip_clean.sh``](scripts/pip_clean.sh).
9. Build the source tarball and binary wheel: ``$ uv build``
10. Smoke test the new release with ``uv tool install --force dist/*.whl``.
11. Push the unpublished changes and the tag.
12. Create a GitHub release and attach the packages:
    ``$ gh release create vX.Y.Z dist/* --title vX.Y.Z --notes-file CHANGELOG.rst``
13. Optionally upload the packages to PyPI: ``$ uv publish``
14. Delete any old and unused branches that have been merged.
