#!/bin/sh
set -eu
pip install '.[test]'
pip install .
coverage run -m pytest
pylint --rcfile .pylintrc -E tuil/
coverage report
