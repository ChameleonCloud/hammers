# coding: utf-8
'''
Basic Usage:

.. code-block:: bash

    dirty-ports {info, clean}

There was/is an issue where a non-empty value in an Ironic node's port's
``internal_info`` field would cause a new instance to fail deployment on the
node. This notifies (``info``) or ``clean``\ s up if there is info on said
ports on nodes that are in the "available" state.
'''


import sys
import os
import argparse
import collections
# import datetime
# from pprint import pprint

from MySQLdb import ProgrammingError

from hammers import MySqlArgs, osapi, osrest, query
from hammers.slack import Slackbot

OS_ENV_PREFIX = 'OS_'

def ports_by_node(ports, assert_single=False):
    node_ports = collections.defaultdict(list)
    for port_id, port in ports.items():
        node_ports[port['node_uuid']].append(port)
    node_ports.default_factory = None

    if assert_single:
        for node_id, ports in node_ports.items():
            if len(ports) != 1:
                raise ValueError('node {} has more than one port.'.format(node_id))

    return node_ports


def identify_dirty_ports(auth, assert_single):
    '''
    Return list of port data that's shady

    Brief race condition hazard if maybe ironic was going to clean it up
    but we mark it as dirty then try to fix it later?
    '''
    iports = ports_by_node(osrest.ironic.ports(auth), assert_single)
    nodes = osrest.ironic.nodes(auth)

    bad_ports = []

    for nid in nodes:
        if nodes[nid]['provision_state'] != 'available':
            continue

        if nid not in iports:
            continue
        port = iports[nid][0]
        if not port['internal_info']:
            continue

        bad_ports.append(port)

    return bad_ports


def clean_ports(db, ports):
    for port in ports:
        updated_rows = query.clear_ironic_port_internalinfo(db, port['uuid'])
        assert updated_rows == 1
    db.db.commit()


def main(argv=None):
    if argv is None:
        argv = sys.argv

    parser = argparse.ArgumentParser(description='Floating IP and port reclaimer.')
    mysqlargs = MySqlArgs({
        'user': 'root',
        'password': '',
        'host': 'localhost',
        'port': 3306,
    })
    mysqlargs.inject(parser)
    osapi.add_arguments(parser)

    parser.add_argument('-q', '--quiet', action='store_true',
        help='Quiet mode. No output to Slack if there was nothing to do.')
    parser.add_argument('--slack', type=str,
        help='JSON file with Slack webhook information to send a notification to')
    parser.add_argument('--multiport', action='store_true',
        help='Enable if Ironic nodes may have multiple ports associated.')
    parser.add_argument('action', choices=['info', 'clean'],
        help='Just display info or actually fix them?')

    args = parser.parse_args(argv[1:])
    mysqlargs.extract(args)

    auth = osapi.Auth.from_env_or_args(args=args)
    slack = Slackbot(args.slack, script_name='dirty-ports') if args.slack else None
    assert_single = False if args.multiport else True
    take_action = args.action == 'clean'

    db = mysqlargs.connect()

    try:
        bad_ports = identify_dirty_ports(auth, assert_single)

        if bad_ports:
            str_ports = '\n'.join(
                ' • port `{uuid}` on node `{node_uuid}`'.format(**p)
                for p
                in bad_ports
            )

            if take_action:
                clean_ports(db, bad_ports)
                message = "Cleaned {} ports with `internal_info` data on `available` nodes:\n{}".format(
                    len(bad_ports),
                    str_ports
                )
                print(message)

                if slack:
                    slack.success(message)
            else:
                print("(read-only mode, not cleaning ports):\n{}".format(str_ports))
            
    except:
        if slack:
            slack.exception()
        raise


if __name__ == '__main__':
    sys.exit(main(sys.argv))
