#!/usr/bin/env python

"""
Internal tool used to automatically generate an up-to-date version of the tuil
man page. Currently this script should be manually run after each version bump.
In the future, it would be nice to have this functionality built into setup.py.

Usage:
    $ python scripts/build_manpage.py
"""

import os
import sys
from argparse import SUPPRESS
from datetime import datetime, timezone

_filepath = os.path.dirname(os.path.relpath(__file__))
ROOT = os.path.abspath(os.path.join(_filepath, '..'))
sys.path.insert(0, ROOT)

import tuil
from tuil import config, docs


def main():
    parser = config.build_parser()

    data = {
        'version': tuil.__version__,
        'release_date': datetime.now(timezone.utc).strftime('%B %d, %Y'),
        'synopsis': parser.format_usage().splitlines()[0][7:],
        'description': docs.SUMMARY.strip(),
        'license': tuil.__license__,
        'copyright': tuil.__copyright__,
    }

    options = []
    for action in parser._actions:
        if action.help == SUPPRESS:
            continue
        if action.option_strings:
            flag = ', '.join(action.option_strings)
        else:
            flag = action.metavar or action.dest.upper()
        if action.option_strings and action.nargs != 0:
            flag += ' ' + (action.metavar or action.dest.upper())
        flag = ', '.join(r'\fB' + item + r'\fR' for item in flag.split(', '))
        options.extend(('.TP', flag, action.help or '', ''))
    data['options'] = '\n'.join(options).rstrip()

    data = {key: value.replace('-', r'\-') for key, value in data.items()}
    template_path = os.path.join(ROOT, 'scripts', 'tuil.1.template')
    with open(template_path) as fp:
        template = fp.read()

    print('Writing to %s/tuil.1' % ROOT)
    with open(os.path.join(ROOT, 'tuil.1'), 'w') as fp:
        fp.write(template.format(**data))


if __name__ == '__main__':
    main()
