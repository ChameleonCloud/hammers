# coding: utf-8
from __future__ import absolute_import, print_function, unicode_literals

import contextlib
import functools


def error_message_factory(subcommand):
    return functools.partial(error_with_message, subcommand)


def error_with_message(subcommand, reason, slack=None):
    if slack:
        slack.post(subcommand, reason, color='xkcd:red')
    raise RuntimeError(reason)


def drop_prefix(s, start):
    l = len(start)
    if s[:l] != start:
        raise ValueError('string does not start with expected value')
    return s[l:]


# 3.7+ has https://bugs.python.org/issue10049
@contextlib.contextmanager
def nullcontext(*args, **kwargs):
    "With ``with``, wiff (do nothing)"
    yield


if __name__ == '__main__':
    assert drop_prefix('x:1234', 'x:') == '1234'
    assert drop_prefix('abcde', 'abc') == 'de'
    try:
        drop_prefix('1234', 'a')
    except ValueError:
        pass
    else:
        assert False
