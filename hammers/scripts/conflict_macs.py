# coding: utf-8
'''
.. code-block:: bash

    conflict-macs \
        {info, delete} \
        ( --ignore-from-ironic-config <path to ironic.conf> |
          --ignore-subnet <subnet UUID> )

The Ironic subnet must be provided---directly via ID or determined from a
config---otherwise the script would think that they are in conflict.
'''


from collections import Counter
import configparser
import json
import os
from pprint import pprint
import sys

import requests

from hammers import osrest
from hammers.osapi import load_osrc, Auth
from hammers.slack import Slackbot
from hammers.util import nullcontext, base_parser

OS_ENV_PREFIX = 'OS_'
SUBCOMMAND = 'conflict-macs'


def main(argv=None):
    if argv is None:
        argv = sys.argv

    parser = base_parser('Remove orphan ports in Neutron referring to an '
                         'inactive Ironic instance')
    parser.add_argument('mode', choices=['info', 'delete'],
        help='Just display data on the conflict ports or delete them')
    parser.add_argument('--ignore-subnet', type=str,
        help='Ignore Neutron ports in this subnet (UUID). Must provide either '
             'this or --ignore-from-ironic-conf. This overrides the conf.')
    parser.add_argument('-c', '--ignore-from-ironic-conf', type=str,
        help='Ignore Neutron ports in the subnet(s) under the '
             '"provisioning_network" network in the "neutron" section of '
             'this configuration file.')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('--force-sane', action='store_true',
        help='Disable sanity checking (i.e. things really are that bad)')

    args = parser.parse_args(argv[1:])

    # Validate args

    slack = Slackbot(args.slack, SUBCOMMAND) if args.slack else None
    auth = Auth.from_env_or_args(args=args)

    if args.ignore_subnet:
        ignore_subnets = [args.ignore_subnet]
    elif args.ignore_from_ironic_conf:
        ironic_config = configparser.ConfigParser()
        ironic_config.read(args.ignore_from_ironic_conf)
        net_id = ironic_config['neutron']['provisioning_network']
        network = osrest.neutron.network(auth, net_id)
        ignore_subnets = network['subnets']
    else:
        print('Must provide --ignore-subnet or --ignore-from-ironic-conf',
              file=sys.stderr)
        return -1

    # Do actual work
    try:
        conflict_macs = find_conflicts(auth, ignore_subnets)

        if args.mode == 'info':
            show_info(conflict_macs)
        elif args.mode == 'delete':
            if (not args.force_sane) and len(conflict_macs) > 10:
                raise RuntimeError('(in)sanity check: thinks there are {} conflicting MACs'.format(len(conflict_macs)))

            for mac in conflict_macs.values():
                osrest.neutron_port_delete(auth, mac['neutron_port_id'])

            if slack:
                message = 'Fixed Ironic/Neutron MAC conflicts\n{}'.format(
                    '\n'.join(
                        ' • Neutron Port `{neutron_port_id}` → `{mac}` ← Ironic Node `{ironic_node_id}` (Port `{ironic_port}`)'
                        .format(**m) for m in conflict_macs.values()
                    )
                )
                slack.success(message)
        else:
            print('unknown command', file=sys.stderr)
            return -1
    except:
        if slack:
            slack.exception()
        raise


def find_conflicts(auth, ignore_subnets):
    nodes = osrest.ironic_nodes(auth)
    ports = osrest.ironic_ports(auth)
    neut_ports = osrest.neutron_ports(auth)

    # they aren't being ironic
    serious_neut_ports = {
        pid: port
        for pid, port
        in neut_ports.items()
        if not any(
            ip['subnet_id'] in ignore_subnets
            for ip
            in port['fixed_ips']
        )
    }

    # mac --> uuid mappings
    node_mac_map = {port['address']: port['node_uuid'] for port in ports.values()}
    port_mac_map = {port['address']: pid for pid, port in ports.items()}
    neut_mac_map = {port['mac_address']: pid for pid, port in serious_neut_ports.items()}

    neut_macs = set(neut_mac_map)

    # there would be fewer in the neut_mac_map if there were collisions on
    # the mac address
    if len(neut_mac_map) != len(serious_neut_ports):
        macs = (port['mac_address'] for port in serious_neut_ports.values())
        mac_collisions = [
            (mac, count)
            for mac, count
            in Counter(macs).items()
            if count > 1
        ]
        message_lines = []
        for mac_collision, count in mac_collisions:
            bad_ports = (
                pid
                for pid, port
                in serious_neut_ports.items()
                if port['mac_address'] == mac_collision
            )
            message_lines.append('- mac {}, ports: {}'.format(
                mac_collision,
                ', '.join(bad_ports)
            ))
            neut_macs.remove(mac_collision)
        message = ('conflict of mac addresses among neutron ports, ignoring '
                   'some mac addresses:\n{}'
                   .format('\n'.join(message_lines)))
        print(message, file=sys.stderr)

    inactive_nodes = {
        nid: node
        for nid, node
        in nodes.items()
        if node['instance_uuid'] is None
    }
    inactive_ports = {
        pid: port
        for pid, port
        in ports.items()
        if port['node_uuid'] in inactive_nodes
    }
    inactive_macs = {port['address'] for port in inactive_ports.values()}

    conflict_macs = neut_macs & inactive_macs

    conflict_macs_info = {}
    for mac in conflict_macs:
        node = nodes[node_mac_map[mac]]
        neut_port = neut_ports[neut_mac_map[mac]]

        conflict_macs_info[mac] = {
            'mac': mac,
            'ironic_node_id': node['uuid'],
            'ironic_node_instance': node['instance_uuid'],
            'ironic_port': port_mac_map[mac],
            'neutron_port_id': neut_port['id'],
            'neutron_port': neut_port,
        }

    return conflict_macs_info


def show_info(conflict_macs):
    # no-op
    if conflict_macs:
        print('CONFLICTS')
    else:
        print('No conflicts currently.')
    for mac in conflict_macs.values():
        print('-----')
        print('MAC Address:          {}'.format(mac['mac']))
        print('Ironic Node ID:       {}'.format(mac['ironic_node_id']))
        print('Ironic Node Instance: {}'.format(mac['ironic_node_instance']))
        print('Neutron Port ID:      {}'.format(mac['neutron_port_id']))
        print('Neutron Port Details:')
        pprint(mac['neutron_port_id'])


if __name__ == '__main__':
    sys.exit(main(sys.argv))
