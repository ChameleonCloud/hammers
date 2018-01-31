# coding: utf-8
from __future__ import absolute_import, print_function, unicode_literals

try:
    import configparser # 3.x
except ImportError:
    from backports import configparser # 2.x 3rd party
try:
    from urllib.parse import urlparse # 3.x
except ImportError:
    from urlparse import urlparse # 2.x


from . import MyCnf, MySqlShim

__all__ = ['MySqlArgs']


class MySqlArgs(object):
    def __init__(self, defaults, mycnfpaths=None):
        mycnf = MyCnf(mycnfpaths)

        for client_key in ['user', 'password', 'host', 'port']:
            try:
                new_value = mycnf['client'][client_key]
            except KeyError:
                continue
            defaults[client_key] = new_value

        self.defaults = defaults

    def inject(self, parser):
        parser.add_argument('-u', '--db-user', type=str,
            default=self.defaults['user'],
            help='Database user (defaulting to "%(default)s")',
        )
        parser.add_argument('-p', '--password', type=str,
            default=self.defaults['password'],
            help='Database password (default empty or as configured with .my.cnf)',
        )
        parser.add_argument('-H', '--host', type=str,
            default=self.defaults['host'],
            help='Database host (defaulting to "%(default)s")',
        )
        parser.add_argument('-P', '--port', type=int,
            default=int(self.defaults['port']),
            help='Database port, ignored for local connections as the UNIX socket '
                 'is used. (defaulting to "%(default)s")',
        )
        parser.add_argument('--service-conf', type=str,
            help='Configuration file to scrape connection details from. '
                 'Overrides other settings if provided. Looks for section '
                 '"database" with key "connection"'
        )

    def extract(self, args):
        if args.service_conf:
            cp = configparser.ConfigParser()
            with open(args.service_conf, mode='r') as f:
                cp.read_file(f)

            parts = urlparse(cp['database']['connection'])
            self.connect_kwargs = {
                'user': parts.username,
                'passwd': parts.password,
                'host': parts.hostname,
                'port': parts.port or 3306,
            }
        else:
            pwd = args.password
            # remove quotes if they got pulled into the argument
            if pwd and len(pwd) > 1 and pwd[0] == pwd[-1] and pwd[0] in '\'\"':
                pwd = pwd[1:-1]

            self.connect_kwargs = {
                'user': args.db_user,
                'passwd': pwd,
                'host': args.host,
                'port': args.port,
            }

    def connect(self):
        return MySqlShim(**self.connect_kwargs)
