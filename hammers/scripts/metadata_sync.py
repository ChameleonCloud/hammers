# coding: utf-8
"""
Synchronizes the metadata contained in the G5K API to Blazar's "extra
capabilities". Keys not in Blazar are created, those not in G5K are deleted.

If using the soft removal option, you could follow up with a manual query
to clean up the empty strings:

.. code-block:: sql

    DELETE FROM blazar.computehost_extra_capabilities WHERE capability_value='';
"""
from __future__ import print_function
import argparse
import collections
from six.moves.urllib.parse import urlparse
import sys

import requests
import six

from hammers import osapi, osrest, query
from hammers.mysqlargs import MySqlArgs


GRID_ENDPOINTS = {
    'chi.uc.chameleoncloud.org': 'https://api.chameleoncloud.org/sites/uc/clusters/chameleon/nodes',
    'chi.tacc.chameleoncloud.org': 'https://api.chameleoncloud.org/sites/tacc/clusters/chameleon/nodes',
}
GRID_IGNORE_PREFIX = [
    'links',
]
BLAZAR_IGNORE_PREFIX = [
    'id',
    'created_at',
    'updated_at',
    'status',
    'trust_id',
    'su_factor',
    # Keys below are accessible via hypervisor_properties, not
    # resource_properties
    'vcpus',
    'cpu_info',
    'hypervisor_hostname',
    'hypervisor_type',
    'hypervisor_version',
    'service_name',
    'memory_mb',
    'local_gb',
]


def ignore_keys(keys, prefixes):
    for k in keys:
        if any(k.startswith(p) for p in prefixes):
            continue
        yield k


def nonstringiterable(arg):
    return (isinstance(arg, collections.Iterable)
            and not isinstance(arg, six.string_types))


def _flatten_to_dots(obj, prefix=None):
    if prefix is None:
        prefix = []

    if nonstringiterable(obj):
        if isinstance(obj, collections.Sequence): # list-like, integer keys
            items = enumerate(obj)
        elif isinstance(obj, collections.Mapping): # dict-like, string keys
            items = obj.items()
        else:
            raise RuntimeError('unhandlable type')

        for key, value in items:
            path = prefix + [key] # copy; do not append or it'll trash mut var
            if nonstringiterable(value):
                #yield from _flatten_to_dots(value, prefix=path) # Py 3
                for item in _flatten_to_dots(value, prefix=path):
                    yield item
            else:
                yield '.'.join(str(x) for x in path), value
    else:
        raise RuntimeError('unhandlable type')


def flatten_to_dots(obj):
    '''
    Flattens a nested dictionary/list into a dictionary with keys that
    describe the nested keys/indicies to get to the same value, separated
    by dots.

    for example:

    {
        'person': 'Nick',
        'games': ['Portal', 'Furi'],
        'books': [
            {'title': 'Kingkiller Chronicles', 'author': 'Patrick Rothfuss'},
            {'title': 'The Expanse', 'author': 'James SA Corey'},
        ],
    }

    becomes

    {
        'person': 'Nick',
        'games.0': 'Portal',
        'games.1': 'Furi',
        'books.0.title': 'Kingkiller Chronicles',
        'books.0.author': 'Patrick Rothfuss',
        'books.1.title': 'The Expanse',
        'books.1.author': 'James SA Corey',
    }
    '''
    return dict(_flatten_to_dots(obj))


def compare_host(grid_host, blazar_host):
    grid_host = flatten_to_dots(grid_host)
    grid_keys = set(ignore_keys(grid_host, GRID_IGNORE_PREFIX))
    blazar_keys = set(ignore_keys(blazar_host, BLAZAR_IGNORE_PREFIX))

    blazar_excess = blazar_keys - grid_keys
    blazar_missing = grid_keys - blazar_keys
    common = blazar_keys & grid_keys

    for key in blazar_excess:
        yield ('remove', (key,))
    for key in blazar_missing:
        yield ('add', (key, grid_host[key]))
    for key in common:
        if str(grid_host[key]) != blazar_host[key]:
            yield ('replace', (key, grid_host[key]))


def get_g5k_hosts(auth):
    auth_host = urlparse(auth.rc['OS_AUTH_URL']).hostname
    try:
        grid_endpoint = GRID_ENDPOINTS[auth_host]
    except KeyError:
        raise RuntimeError("Don't know the G5K endpoint for site at {}".format(auth_host))

    response = requests.get(grid_endpoint)
    data = response.json()
    grid_hosts = {h['uid']: h for h in data['items']}

    return grid_hosts


def get_blazar_hosts(auth):
    blazar_hosts_shortid = osrest.blazar.hosts(auth)

    # convert short-integer IDs to the UUIDs to pair with G5K
    blazar_hosts = {}
    for host in blazar_hosts_shortid.values():
        try:
            blazar_hosts[host['uid']] = host
        except KeyError:
            print("WARNING: UID missing for Blazar host {}, can't pair with G5K"
                  .format(host['id'], file=sys.stderr))

    return blazar_hosts


def main(argv):
    mysqlargs = MySqlArgs({
        'user': 'root',
        'password': '',
        'host': 'localhost',
        'port': 3306,
    })

    parser = argparse.ArgumentParser(description=__doc__)

    osapi.add_arguments(parser) # --osrc
    mysqlargs.inject(parser) # --user, --password, --host, --port
    parser.add_argument('action', choices=['info', 'update'],
        help='Info only prints out actions to be taken without doing '
             'anything. Update does them.')
    parser.add_argument('-s', '--soft-removal', action='store_true',
        help='Soft removal, sets value to empty-string. Relieves database '
             'access requirement.')
    parser.add_argument('-v', '--verbose', action='store_true')

    args = parser.parse_args(argv[1:])
    auth = osapi.Auth.from_env_or_args(args=args)
    mysqlargs.extract(args)
    dry_run = args.action == 'info'
    if not dry_run and not args.soft_removal:
        db = mysqlargs.connect()

    blazar_hosts = get_blazar_hosts(auth)
    grid_hosts = get_g5k_hosts(auth)

    blazar_uids = set(blazar_hosts)
    grid_uids = set(grid_hosts)

    uids_both = grid_uids & blazar_uids
    blazar_missing = grid_uids - blazar_uids
    grid_missing = blazar_uids - grid_uids

    if blazar_missing:
        print('Blazar missing node UIDs: {}'.format(blazar_missing))
    if grid_missing:
        print('Grid missing node UIDs: {}'.format(grid_missing))

    for uid in sorted(uids_both):
        gh = grid_hosts[uid]
        bh = blazar_hosts[uid]

        actions = compare_host(gh, bh)

        # collect updates instead of doing one-by-one to reduce number
        # of requests
        updates = {}
        removals = []
        for action, action_args in actions:
                # print(uid, action, action_args)
                # continue
            if action in {'add', 'replace'}:
                key, value = action_args
                updates[key] = str(value) # blazar likes strings

                if dry_run or args.verbose:
                    if action == 'add':
                        old_value = ''
                    else:
                        old_value = ' (old value: {})'.format(bh[key])
                    print('{} {}({}=\'{}\'){}'.format(
                          uid, action, key, value, old_value))
            elif action in {'remove'}:
                key, = action_args
                removals.append(key)

                if dry_run or args.verbose:
                    print('{} {}({}) (old value: {})'.format(
                          uid, action, key, bh[key]))
            else:
                raise RuntimeError('unknown action "{}"'.format(action))

        if args.soft_removal:
            while removals:
                key = removals.pop()
                updates[key] = ''

        if dry_run:
            continue

        if updates:
            osrest.blazar.host_update(auth, bh['id'], updates)
        if removals:
            for key in removals:
                modified = query.remove_extra_capability(db, bh['id'], key)
                if modified != 1:
                    raise RuntimeError('delete query removed {} rows, expected 1'.format(modified))

        db.db.commit()

if __name__ == '__main__':
    sys.exit(main(sys.argv))
