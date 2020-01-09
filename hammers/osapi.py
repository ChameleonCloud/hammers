# coding: utf-8
"""
Tools to convert credentials into authentication and authorization in raw
Python, as opposed to the Python APIs provided by ``keystoneauth1`` or the
like. They were largely created out of frustration with the apparent
moving target and inconsistencies of the OS client APIs, which was also
exacerbated by the Blazar client being fairly nacent.

.. admonition:: Compare and contrast

    :py:mod:`ccmanage.auth` which *does* use the Python APIs.
"""


import datetime
import getpass
import logging
import os
import re

from dateutil.parser import parse as dateparse
from dateutil.tz import tzutc
import requests


OS_ENV_PREFIX = 'OS_'


def add_arguments(parser):
    """
    Inject an arg into the user's parser. Intented to pair with
    :py:meth:`Auth.from_env_or_args`: after argparse parses the
    args, feed that the args namespace.
    """
    parser.add_argument('--osrc', type=str,
        help='OpenStack parameters file that overrides envvars.')


def load_osrc(fn, get_pass=False):
    '''Parse a Bash RC file dumped out by the dashboard to a dict.
    Used to load the file specified by :py:func:`add_arguments`.'''
    envval = re.compile(r'''
        \s* # maybe whitespace
        (?P<key>[A-Za-z0-9_\-$]+)  # variable name
        =
        ([\'\"]?)                  # optional quote
        (?P<value>.*)              # variable content
        \2                         # matching quote
        ''', flags=re.VERBOSE)
    rc = {}
    with open(fn, 'r') as f:
        for line in f:
            match = envval.search(line)
            if not match:
                continue
            match = match.groupdict()
            rc[match['key']] = match['value']

    try:
        password = rc['OS_PASSWORD']
    except KeyError:
        pass
    else:
        if password == '$OS_PASSWORD_INPUT':
            rc.pop('OS_PASSWORD')

    if get_pass:
        rc['OS_PASSWORD'] = getpass.getpass('Enter your password: ')

    return rc


class Auth(object):
    """
    The Auth object consumes credentials and provides tokens and endpoints.
    Create either directly by providing a mapping with the keys in
    ``required_os_vars`` or via the :py:meth:`Auth.from_env_or_args` method.
    """

    _L = logging.getLogger(__name__ + '.Auth')

    required_os_vars = {
        'OS_USERNAME',
        'OS_PASSWORD',
        'OS_PROJECT_NAME',
        'OS_AUTH_URL',
    }

    @classmethod
    # def from_env_or_args(cls, *, args=None, env=True):
    # <py2 kwargs compat>
    def from_env_or_args(cls, **kwargs):
        """
        Loads the RC values from the file in the provided *args* namespace,
        falling back to the environment vars if *env* is true.
        :py:func:`add_arguments` is a helper function that will add the "osrc"
        argument to an argparse parser.

        Returns an Auth object that's ready for use.
        """
        args = kwargs.get('args', None)
        env = kwargs.get('env', True)
    # </py2 kwargs compat>
        os_vars = {}
        if env:
            os_vars = {k: os.environ[k] for k in os.environ if k.startswith(OS_ENV_PREFIX)}
        if args and args.osrc:
            os_vars.update(load_osrc(args.osrc))
        return cls(os_vars)

    def __init__(self, rc):
        self.rc = rc
        missing_vars = self.required_os_vars - set(rc)
        if 'OS_PROJECT_DOMAIN_NAME' not in self.rc and 'OS_PROJECT_DOMAIN_ID' not in self.rc:
            missing_vars.add('OS_PROJECT_DOMAIN_NAME/ID')
        if missing_vars:
            raise RuntimeError('Missing required OS values: {}'.format(missing_vars))
        self.auth_url = self.rc['OS_AUTH_URL']

        if self.auth_url[-2:] != 'v3':
            self.auth_url += '/v3'

        self.region = self.rc.get('OS_REGION_NAME', None)
        self.authenticate()

    def authenticate(self):
        """
        Authenticate with Keystone to get a token and endpoint listing
        """
        if 'OS_PROJECT_DOMAIN_ID' in self.rc:
            domain_info = {"id": self.rc['OS_PROJECT_DOMAIN_ID']}
        else:
            domain_info = {"name": self.rc['OS_PROJECT_DOMAIN_NAME']}
        
        response = requests.post(self.auth_url + '/auth/tokens', json={
            "auth": {
                "identity": {
                    "methods": [
                        "password"
                    ],
                    "password": {
                        "user": {
                            "domain": {
                                "id": "default"
                            },
                            "name": self.rc['OS_USERNAME'],
                            "password": self.rc['OS_PASSWORD']
                        }
                    }
                },
                "scope": {
                    "project": {
                        "name": self.rc['OS_PROJECT_NAME'],
                        "domain": domain_info
                    }
                }
            }
        })

        if response.status_code != 201:
            raise RuntimeError(
                'HTTP {}: {}'
                .format(response.status_code, response.content[:400])
            )

        json = response.json()
        self._token = response.headers['x-subject-token']
        self.service_catalog = json['token']['catalog']
        self.expiry = dateparse(json['token']['expires_at'])

        self._L.debug('New token "{}" expires in {:.2f} minutes'.format(
            self._token,
            (self.expiry - datetime.datetime.now(tz=tzutc())).total_seconds() / 60
        ))

    @property
    def token(self):
        """
        Read-only property that returns an active token, reauthenticating if
        it has expired. Most services accept this in the HTTP request header
        under the key ``X-Auth-Token``.
        """
        if (self.expiry - datetime.datetime.now(tz=tzutc())).total_seconds() < 60:
            self.authenticate()

        return self._token

    def endpoint(self, type):
        """
        Find the endpoint for a given service *type*. Examples include ``compute`` for Nova,
        ``reservation`` for Blazar, or ``image`` for Glance.
        """
        # add filter service['endpoints'] is not empty, because kvm site contains artifacts from older version.
        services = [
            service
            for service
            in self.service_catalog
            if service['type'] == type and len(service['endpoints']) > 0
        ]
        if len(services) < 1:
            raise RuntimeError("didn't find any services matching type '{}'".format(type))
        elif len(services) > 1:
            raise RuntimeError("found multiple services matching type '{}'".format(type))
        service = services[0]
        endpoint = [
            e for e in service['endpoints']
            if e['interface'] == 'public' and e['region'] == self.region
        ][0]

        if not endpoint:
            raise RuntimeError("didn't find endpoint for service")

        return endpoint['url']


class Authv2(object):
    #TODO: used for KVM only; remove this class after KVM upgrading
    """
    The Authv2 object consumes credentials and provides tokens and endpoints.
    Create either directly by providing a mapping with the keys in
    ``required_os_vars`` or via the :py:meth:`Authv2.from_env_or_args` method.
    """

    _L = logging.getLogger(__name__ + '.Auth')

    required_os_vars = {
        'OS_USERNAME',
        'OS_PASSWORD',
        'OS_TENANT_NAME',
        'OS_AUTH_URL',
    }

    @classmethod
    def from_env_or_args(cls, **kwargs):
        """
        Loads the RC values from the file in the provided *args* namespace,
        falling back to the environment vars if *env* is true.
        :py:func:`add_arguments` is a helper function that will add the "osrc"
        argument to an argparse parser.

        Returns an Auth object that's ready for use.
        """
        args = kwargs.get('args', None)
        env = kwargs.get('env', True)
        os_vars = {}
        if env:
            os_vars = {k: os.environ[k] for k in os.environ if k.startswith(OS_ENV_PREFIX)}
        if args and args.osrc:
            os_vars.update(load_osrc(args.osrc))
        return cls(os_vars)

    def __init__(self, rc):
        self.rc = rc
        missing_vars = self.required_os_vars - set(rc)
        if missing_vars:
            raise RuntimeError('Missing required OS values: {}'.format(missing_vars))
        self._find_keystone2_root()
        self.region = self.rc.get('OS_REGION_NAME', None)
        self.authenticate()
        
    def _find_keystone2_root(self):
        '''Sometimes the OS_AUTH_URL is missing the v2.0 suffix for some
        reason. Hopefully asking the root endpoint will always tell us
        where it really is.
        '''
        response = requests.get(self.rc['OS_AUTH_URL'])
        data = response.json()

        if 'version' in data:
            data['versions'] = {'values': [data['version']]}
        for version in data['versions']['values']:
            if version['id'] != 'v2.0':
                continue
            for link in version['links']:
                if link.get('rel') == 'self':
                    self._keystone2_root = link['href']
                    return
            else:
                raise RuntimeError('could not find self-link among v2 data: {}'.format(data))
        else:
            raise RuntimeError('could not find Keystone v2 root')

    def authenticate(self):
        """
        Authenticate with Keystone to get a token and endpoint listing
        """
        response = requests.post(self._keystone2_root + '/tokens', json={
        'auth': {
            'passwordCredentials': {
                'username': self.rc['OS_USERNAME'],
                'password': self.rc['OS_PASSWORD'],
            },
            'tenantName': self.rc['OS_TENANT_NAME']
        }})
        if response.status_code != 200:
            raise RuntimeError(
                'HTTP {}: {}'
                .format(response.status_code, response.content[:400])
            )

        jresponse = response.json()
        try:
            self.access = jresponse['access']
        except KeyError:
            raise RuntimeError(
                'expected "access" key not present in response '
                '(found keys: {})'.format(list(jresponse))
            )

        self._token = self.access['token']['id']
        self.expiry = dateparse(self.access['token']['expires'])

        self._L.debug('New token "{}" expires in {:.2f} minutes'.format(
            self._token,
            (self.expiry - datetime.datetime.now(tz=tzutc())).total_seconds() / 60
        ))


