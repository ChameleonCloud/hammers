# coding: utf-8
"""
Synchronizes the metadata contained in the G5K API to Blazar's "extra
capabilities". Keys not in Blazar are created, those not in G5K are deleted.
"""

from collections.abc import Mapping, Iterable, Sequence
import sys

import requests
import six

from hammers import osapi, osrest
from hammers.util import base_parser

# FIXME: this should be looked up from sites.json from the G5k API
GRID_ENDPOINTS = {
    'CHI@UC': 'https://api.chameleoncloud.org/sites/uc/clusters/chameleon/nodes',
    'CHI@TACC': 'https://api.chameleoncloud.org/sites/tacc/clusters/chameleon/nodes',
    'CHI@NU': 'https://api.chameleoncloud.org/sites/nu/clusters/chameleon/nodes',
}
GRID_IGNORE_PREFIX = [
    'links',
    'version',
]
BLAZAR_IGNORE_PREFIX = [
    'id',
    'created_at',
    'updated_at',
    'status',
    'trust_id',
    'su_factor',
    'availability_zone',
    'reservable',
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
    return (isinstance(arg, Iterable)
            and not isinstance(arg, six.string_types))


def _flatten_to_dots(obj, prefix=None):
    if prefix is None:
        prefix = []

    if nonstringiterable(obj):
        if isinstance(obj, Sequence): # list-like, integer keys
            items = enumerate(obj)
        elif isinstance(obj, Mapping): # dict-like, string keys
            items = list(obj.items())
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
    region = auth.rc['OS_REGION_NAME']
    try:
        grid_endpoint = GRID_ENDPOINTS[region]
    except KeyError:
        raise RuntimeError(
            "Don't know the G5K endpoint for site {}".format(region))

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
            print(
                "WARNING: UID missing for Blazar host {}, can't pair with G5K"
                .format(host['id'], file=sys.stderr))

    return blazar_hosts


def main(argv=None):
    if argv is None:
        argv = sys.argv

    parser = base_parser(__doc__)

    parser.add_argument('action', choices=['info', 'update'],
        nargs='?', default='info',
        help='Info only prints out actions to be taken without doing '
             'anything. Update does them.')
    parser.add_argument('-v', '--verbose', action='store_true')

    args = parser.parse_args(argv[1:])
    auth = osapi.Auth.from_env_or_args(args=args)
    dry_run = args.action == 'info'
    any_updates = False

    blazar_hosts = get_blazar_hosts(auth)
    grid_hosts = get_g5k_hosts(auth)

    blazar_uids = set(blazar_hosts)
    grid_uids = set(grid_hosts)

    uids_both = grid_uids & blazar_uids
    blazar_missing = grid_uids - blazar_uids
    grid_missing = blazar_uids - grid_uids

    if blazar_missing:
        print('Blazar missing node UIDs: {}'.format(blazar_missing))
        any_updates = True
    if grid_missing:
        print('Grid missing node UIDs: {}'.format(grid_missing))
        any_updates = True

    for uid in sorted(uids_both):
        gh = grid_hosts[uid]
        bh = blazar_hosts[uid]

        actions = compare_host(gh, bh)

        # collect updates instead of doing one-by-one to reduce number
        # of requests
        updates = {}
        for action, action_args in actions:
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
                updates[key] = None

                if dry_run or args.verbose:
                    print('{} {}({}) (old value: {})'.format(
                          uid, action, key, bh[key]))
            else:
                raise RuntimeError('unknown action "{}"'.format(action))

        if updates:
            any_updates = True

            if dry_run:
                continue

            try:
                osrest.blazar.host_update(auth, bh['id'], updates)
            except Exception as e:
                print(e)
                print("UPDATE SKIPPED DUE TO ERROR")
                print("\tNODE ID: {}\n\tUpdate Detail: {}".format(
                    bh['id'], str(updates)))

    if any_updates:
        return 1
    else:
        print("Blazar and G5K repo are synced.")
        return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv))
