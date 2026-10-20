#!/usr/bin/env bash

ROOT="$(dirname "$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )")"

cd ${ROOT}
echo -e "\nTests: "
echo "$(wc -l tests/*.py)"
echo -e "\nScripts: "
echo "$(wc -l scripts/*)"
echo -e "\nTemplates: "
echo "$(wc -l tuil/templates/*)"
echo -e "\nCode: "
echo "$(wc -l tuil/*.py)"
echo -e "\nCombined: "
echo "$(cat tests/*.py scripts/* tuil/templates/* tuil/*.py | wc -l) total lines"
