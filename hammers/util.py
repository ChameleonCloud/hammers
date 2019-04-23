# coding: utf-8
from __future__ import absolute_import, print_function, unicode_literals

import contextlib
import functools
from prometheus_client import Gauge, CollectorRegistry, pushadd_to_gateway
from subprocess import Popen, PIPE, check_output
from time import time


def push_last_success_time(hammer_filename):
    """Pushes last time hammer succeeded to prometheus pushgateway."""
    metric_name = 'cron_last_success'
    job_name = 'hammer_{}'.format(
        hammer_filename.split('/')[-1].replace('.py', ''))

    registry = CollectorRegistry()
    last_success = Gauge(
        metric_name, 'Unixtime hammer last succeeded', registry=registry)
    last_success.set_to_current_time()

    pushadd_to_gateway('0.0.0.0:9091', job=job_name, registry=registry)


def prometheus_exporter(hammer_filename):
    """
    Wrapper function for hammers to export boolean value for if hammer ran
    successful to prometheus monitoring.
    """
    def wrap(f):
        def with_pushgateway(*args, **kwargs):
            try:
                _f = f(*args, **kwargs)
                push_last_success_time(hammer_filename)
                return _f
            except Exception:
                return f(*args, **kwargs)
        return with_pushgateway
    return wrap


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
