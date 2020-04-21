# coding: utf-8
import argparse
import contextlib
from datetime import datetime, timezone
import functools
from subprocess import Popen, PIPE, check_output
from time import time


def base_parser(description=None):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--slack', type=str, help=(
        'JSON file with Slack webhook information to send a notification to'))
    parser.add_argument('--osrc', type=str, help=(
        'OpenStack parameters file that overrides envvars.'))

    return parser


def error_message_factory(subcommand):
    return functools.partial(error_with_message, subcommand)


def error_with_message(subcommand, reason, slack=None):
    """Raises a :py:exc:`RuntimeError` with `reason`, but if `slack` is not
    :py:not before sending
    a message to Slack"""
    if slack:
        slack.post(subcommand, reason, color='xkcd:red')
    raise RuntimeError(reason)


def drop_prefix(s, start):
    """Remove prefix `start` from sting `s`. Raises a :py:exc:`ValueError`
    if `s` didn't start with `start`."""
    l = len(start)
    if s[:l] != start:
        raise ValueError('string does not start with expected value')
    return s[l:]


DATE_FORMATS = {
    "cli": "%Y-%m-%d %H:%M:%S",
    "nova": "%Y-%m-%d %H:%M:%S",
    "ironic": "%Y-%m-%dT%H:%M:%S",
    "blazar_event": "%Y-%m-%d %H:%M:%S",
    "blazar_lease": "%Y-%m-%dT%H:%M:%S.%f",
}

def parse_datestr(datestr, fmt=None):
    if fmt:
        formats = [fmt]
    else:
        formats = DATE_FORMATS.keys()

    # HACK(jca): Chop of timezone for sanity, assume UTC
    datestr = datestr.split('+')[0]

    for f in formats:
        try:
            dateobj = datetime.strptime(datestr, DATE_FORMATS[f])
            dateobj = dateobj.replace(tzinfo=timezone("UTC"))
            return dateobj
        except ValueError:
            continue
    return None


# 3.7+ has https://bugs.python.org/issue10049
@contextlib.contextmanager
def nullcontext(*args, **kwargs):
    """With ``with``, wiff (do nothing). `Added to stdlib in 3.7
    <https://bugs.python.org/issue10049>`_ as :py:func:`contextlib.nullcontext`"""
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
