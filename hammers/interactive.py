from __future__ import absolute_import, print_function, unicode_literals

import json
import pathlib

from . import osapi


CC_LOCAL = pathlib.Path.home() / '.config' / 'chameleoncloud.json'


def auth(rc_file, retries=3, password=None):
    for i in range(retries):
        try:
            with CC_LOCAL.open() as f:
                settings = json.load(f)
            password = settings['password']
        except (OSError, KeyError):
            pass

        rc = osapi.load_osrc(rc_file, get_pass=(not password))
        if password:
            rc['OS_PASSWORD'] = password

        # abort if blank pass entered
        if rc['OS_PASSWORD'] == '':
            print('Aborting.', file=sys.stderr)
            return

        try:
            auth = osapi.Auth(rc)
        except RuntimeError:
            print('Auth failed.', file=sys.stderr)
        else:
            return auth
