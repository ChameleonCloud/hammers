# coding: utf-8
'''
Sometimes Nova doesn't seem to tell Ironic the instance went away on a node,
then the next time it deploys to the same node, Ironic fails.

.. code-block:: bash

    undead-instances {info, delete}

Running with ``info`` displays what it thinks is wrong, and with ``delete``
will clear the offending state from the nodes.
'''
from __future__ import absolute_import, print_function, unicode_literals

import sys
import os
import argparse
import json
from pprint import pprint

import requests

from hammers import osrest
from hammers.osapi import load_osrc, Auth
from hammers.slack import Slackbot
from hammers.util import error_message_factory

OS_ENV_PREFIX = 'OS_'
SUBCOMMAND = 'undead-instances'

_thats_crazy = error_message_factory(SUBCOMMAND)


def clear_node_instance_data(auth, node, validate=True):
    if validate:
        # attempting to clean clean nodes is *probably* a bug in the caller
        node_data = osrest.ironic_node(auth, node)
        instance_uuid = node_data['instance_uuid']
        if instance_uuid is None:
            raise RuntimeError('there is no instance set on node "{}"'.format(node))

        # check that the instance isn't available (MUST 404)
        try:
            instance = osrest.nova_instance(auth, instance_uuid)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                pass
            else:
                raise
        else:
            raise RuntimeError('node "{}" refers to instance "{}" that is status "{}"'
                               .format(node, instance_uuid, instance['status']))

    return osrest.ironic_node_update(auth, node, replace={
        '/instance_uuid': None,
        '/instance_info': {},
    })


def main(argv=None):
    if argv is None:
        argv = sys.argv

    parser = argparse.ArgumentParser(description='Kick Ironic nodes that '
        'refer to a deleted/nonexistant Nova instance')

    parser.add_argument('mode', choices=['info', 'delete'],
        help='Just display data on the bound nodes or delete them')
    parser.add_argument('--slack', type=str,
        help='JSON file with Slack webhook information to send a notification to')
    parser.add_argument('--osrc', type=str,
        help='Connection parameter file. Should include password. envars used '
        'if not provided by this file.')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('--force-sane', action='store_true',
        help='Disable sanity checking (i.e. things really are that bad)')
    parser.add_argument('--force-insane', action='store_true',
        help=argparse.SUPPRESS) # for testing

    args = parser.parse_args(argv[1:])

    slack = Slackbot(args.slack, script_name='undead-instances') if args.slack else None

    os_vars = {k: os.environ[k] for k in os.environ if k.startswith(OS_ENV_PREFIX)}
    if args.osrc:
        os_vars.update(load_osrc(args.osrc))
    missing_os_vars = set(Auth.required_os_vars) - set(os_vars)
    if missing_os_vars:
        print(
            'Missing required OS values in env/rcfile: {}'
            .format(', '.join(missing_os_vars)),
            file=sys.stderr
        )
        return -1

    auth = Auth(os_vars)

    nodes = osrest.ironic_nodes(auth)
    instances = osrest.nova_instances(auth)

    node_instance_map = {
        n['instance_uuid']: n
        for n
        in nodes.values()
        if n['instance_uuid'] is not None
    }

    node_instance_ids = set(node_instance_map)
    instance_ids = set(instances)

    unbound_instances = node_instance_ids - instance_ids

    if args.mode == 'info':
        # no-op
        if unbound_instances:
            print('ZOMBIE INSTANCES ON NODES')
        else:
            print('No zombies currently.')
        for inst_id in unbound_instances:
            node = node_instance_map[inst_id]

            assert inst_id not in instances, 'contradiction, this should be impossible'

            print('-----')
            print('Ironic Node\n'
                  '  ID:       {}'.format(node['uuid']))
            print('  Instance: {}'.format(node['instance_uuid']))
            print('  State:    {}'.format(node['provision_state']))

    elif args.mode == 'delete':
        if not args.force_sane or args.force_insane:
            # sanity check(s) to avoid doing something stupid
            if len(instance_ids) == 0 and len(unbound_instances) != 0:
                _thats_crazy('(in)sanity check: 0 running instances(?!)', slack)

            ubi_limit = 20 if not args.force_insane else -1
            if len(unbound_instances) > ubi_limit:
                _thats_crazy(
                    '(in)sanity check: it thinks there are {} unbound instances'
                        .format(len(unbound_instances)),
                    slack,
                )

        try:
            for inst_id in unbound_instances:
                node = node_instance_map[inst_id]
                node_id = node['uuid']
                if node['provision_state'] == 'available':
                    clear_node_instance_data(auth, node_id)
                else:
                    osrest.ironic_node_set_state(auth, node_id, 'deleted')

            message = 'Fixed Ironic nodes with nonexistant instances:\n{}'.format(
                '\n'.join(
                    ' • node `{}` → instance `{}`'.format(
                        node_instance_map[i]['uuid'],
                        node_instance_map[i]['instance_uuid'])
                    for i in unbound_instances
                )
            )

            print(message)

            if slack:
                slack.success(message)
        except:
            if slack:
                slack.exception()
            raise


if __name__ == '__main__':
    sys.exit(main(sys.argv))
