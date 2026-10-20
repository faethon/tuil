# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import sys

import pytest

from tuil.clipboard import copy
from tuil.exceptions import ProgramError


try:
    from unittest import mock
except ImportError:
    import mock


def test_copy_nix():

    with mock.patch('subprocess.Popen') as Popen, \
            mock.patch('subprocess.call', return_value=0) as call:

        # Mock out the subprocess calls
        p = mock.Mock()
        p.communicate = mock.Mock()
        Popen.return_value = p

        copy('test', 'xsel -b -i')
        assert Popen.call_args[0][0] == ['xsel', '-b', '-i']
        p.communicate.assert_called_with(input='test'.encode('utf-8'))

        copy('test ❤')
        assert Popen.call_args[0][0] == ['xclip', '-selection', 'clipboard']
        p.communicate.assert_called_with(input='test ❤'.encode('utf-8'))

def test_copy_darwin():
    with mock.patch('subprocess.Popen') as Popen, \
            mock.patch('subprocess.call', return_value=0) as call:

        sys.platform = 'darwin'

        p = mock.Mock()
        p.communicate = mock.Mock()
        Popen.return_value = p

        copy('test')
        assert Popen.call_args[0][0] == ['pbcopy', 'w']
        p.communicate.assert_called_with(input='test'.encode('utf-8'))
