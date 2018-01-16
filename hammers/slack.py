# coding: utf-8
from __future__ import absolute_import, print_function, unicode_literals

import codecs
import json
import socket
import sys
import traceback

import requests

from hammers import __version__ as VERSION
from hammers import colors


class Slackbot(object):
    def __init__(self, settings_file, script_name=None):
        with codecs.open(settings_file, 'r', encoding='utf-8') as f:
            self.settings = json.load(f)

        if 'webhook' not in self.settings:
            raise ValueError('settings file must contain "webhook" key at minimum')

        host = socket.getfqdn()
        try:
            host = self.settings['hostname_names'][host]
        except KeyError:
            host = '({})'.format(host)
        self.host = host
        self.script_name = script_name

    def message(self, payload, color='#ccc'):
        '''Newer version of ``post()`` that omits the script name'''
        return self.post(self.script_name, payload, color=color)

    def post(self, script, payload, color='#ccc'):
        if color.startswith('xkcd:'):
            color = colors.XKCD_COLORS[color[5:]]

        payload = {
            'username': 'Box o\' Hammers',
            'icon_emoji': ':hammer:',
            'attachments': [{
                'fallback': '{} | {} | {}'.format(self.host, script, payload),
                'mrkdwn_in': ['text'],
                'color': color,
                'author_name': 'chameleoncloud/hammers@{}'.format(VERSION),
                'author_link': 'https://github.com/ChameleonCloud/hammers/',
                'title': '{} on {}'.format(script, self.host),
                'text': payload,
            }]
        }
        CH = 'channel'
        if CH in self.settings:
            # if nothing specified, uses webhook default (e.g. #notifications)
            payload[CH] = self.settings[CH]

        response = requests.post(self.settings['webhook'], json=payload)
        if response.status_code != requests.codes.OK:
            print('Non-OK ({}) response from Slack: {}'.format(
                response.status_code, response.content[:400]), file=sys.stderr)
        return response

    def __enter__(self):
        return self

    def __exit__(self, etype, value, tb):
        '''Context manager logs exceptions in Slack (doesn't suppress)'''
        if etype is not None:
            error_lines = traceback.format_exception(etype, value, tb)
            self.post(self.script_name, ''.join(error_lines), color='xkcd:red')
