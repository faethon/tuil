Release Checklist
-----------------

1. Switch to the master branch and stash/commit any uncommited changes.
2. Bump the version number in [tuil/\_\_version\_\_.py](tuil/__version__.py).
3. Update the release notes in the [CHANGELOG.rst](CHANGELOG.rst).
4. Update the contributor list by running [``scripts/build_authors.py``](scripts/build_authors.py).
5. Re-generate the manpage by running [``scripts/build_manpage.py``](scripts/build_manpage.py).
6. Run tests with [``scripts/ci.sh``](scripts/ci.sh).
7. Commit all changes to the correct branch and tag the correct commit with its version.
8. Clean out any old build/release files by running [``scripts/pip_clean.sh``](scripts/pip_clean.sh).
9. Build the source tarball and binary wheel: ``$ python3 setup.py sdist bdist_wheel``
10. Smoke test the new release on Python 3.
11. Push the unpublished changes and the tag.
12. Upload the packages to PyPI: ``$ twine upload dist/*``
13. Verify that the upload was successful: ``$ pip install tuil --upgrade --force-reinstall``
14. Delete any old and unused branches that have been merged.
