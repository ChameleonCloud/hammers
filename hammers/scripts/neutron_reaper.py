# coding: utf-8
'''
.. code-block:: bash

    neutron-reaper {info, delete} \
                   {ip, port} \
                   <grace-days>

Reclaims idle floating IPs and cleans up stale ports.

Required arguments, in order:

* ``info`` to just display what would be cleaned up, or actually clean it up with ``delete``.
* Consider floating ``ip``'s or ``port``'s
* A project needs to be idle for ``grace-days`` days.
'''
#TODO: Used for KVM site only. After upgrading KVM site to OpenStack Rocky version, remove this script and use floatingip-reaper.
from __future__ import absolute_import, print_function, unicode_literals

import sys
import os
import argparse
import collections
import datetime
from pprint import pprint

from hammers import MySqlArgs, osapi, osrest, query
from hammers.slack import Slackbot

OS_ENV_PREFIX = 'OS_'

RESOURCE_QUERY = {
    'ip': query.owned_compute_ip_single,
    'port': query.owned_compute_port_single,
}

RESOURCE_DELETE_COMMAND = {
    'ip': osrest.neutron.floatingip_delete,
    'port': osrest.neutron.port_delete,
}

assert set(RESOURCE_QUERY) == set(RESOURCE_DELETE_COMMAND)

def days_past(dt):
    if isinstance(dt, str):
        dt = datetime.datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
    return (datetime.datetime.utcnow() - dt).total_seconds() / (60*60*24)


def check_lease_past_end_date(db, not_down):
    """
    Check if a lease has ended for node associated with an active floating ip
    address and remove ip address from not_down list.
    """
    ip_ids = tuple([str(x['id']) for x in not_down])

    for lease in query.floating_ips_to_leases(db, ip_ids):

        if lease.pop('end_date') < datetime.datetime.utcnow():

            for idx, ip in enumerate(not_down):
                if lease.get('ip_id') == str(ip['id']):
                    del not_down[idx]


def find_reapable_resources(db, auth, type_, idle_days, whitelist):
    future_projects = set()
    db_names = ['nova']

    project_last_seen = {}
    for db_name in db_names:
        for row in query.latest_instance_interaction(db, db_name):
            # Projects that have active instances are not considered as idled projects
            if row['active']: continue
            proj_id = row['id']
            if (proj_id in whitelist
                    or row['name'] in whitelist
                    or proj_id in future_projects):
                # skip
                continue
            try:
                already_last_seen = project_last_seen[proj_id]
            except KeyError:
                # new ID
                project_last_seen[proj_id] = row['latest_interaction']
            else:
                # existing ID, keep the max date
                project_last_seen[proj_id] = max(row['latest_interaction'], already_last_seen)

    too_idle_project_ids = [
        proj_id
        for proj_id, last_seen
        in project_last_seen.items()
        if days_past(last_seen) > idle_days
    ]

    resource_query = RESOURCE_QUERY[type_]

    to_delete = []
    not_down = [] # should be empty, otherwise fail.
    for proj_id in too_idle_project_ids:
        # TODO replace SQL query by looking at floating IP data from
        # the HTTP endpoint
        for resource in resource_query(db, proj_id):
            to_delete.append(resource['id'])
            if (resource['status'] != 'DOWN'):
                not_down.append(resource)

    if not_down:
        raise RuntimeError('error: not all resources selected are in "DOWN" state'
            '.\n\n{}'.format(not_down))

    return to_delete


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

    parser.add_argument('-w', '--whitelist', type=str,
        help='File of project/tenant IDs/names to ignore, one per line. '
             'Ignores case and dashes.')
    parser.add_argument('--slack', type=str,
        help='JSON file with Slack webhook information to send a notification to')

    parser.add_argument('action', choices=['info', 'delete'],
        help='Just display info or actually delete them?')
    parser.add_argument('type', choices=list(RESOURCE_QUERY),
        help='Grab floating IPs or ports?')
    parser.add_argument('idle_days', type=float,
        help='Number of days since last active instance in project was '
        'deleted to consider it idle.')

    args = parser.parse_args(argv[1:])
    mysqlargs.extract(args)
    auth = osapi.Authv2.from_env_or_args(args=args)

    slack = Slackbot(args.slack, script_name='neutron-reaper') if args.slack else None

    whitelist = set()
    if args.whitelist:
        with open(args.whitelist) as f:
            whitelist = {line for line in f}

    db = mysqlargs.connect()
    db.version = query.ROCKY

    try:
        to_delete = find_reapable_resources(db=db, auth=auth, type_=args.type, idle_days=args.idle_days, whitelist=whitelist)

        thing = '{}{}'.format(
            {'ip': 'floating IP', 'port': 'port'}[args.type],
            ('' if len(to_delete) == 1 else 's'),
        )

        if to_delete:
            if args.action == 'delete':
                for resource_id in to_delete:
                    RESOURCE_DELETE_COMMAND[args.type](auth, resource_id)
                message = (
                    'Commanded deletion of *{} {}* ({:.0f} day grace-period)'
                    .format(len(to_delete), thing, args.idle_days)
                )

                print(message)

                if slack:
                    slack.message(message)
            else:
                print((
                    'Found *{} {}* to delete ({:.0f} day grace-period):\n{}'
                    .format(len(to_delete), thing, args.idle_days, to_delete)
                ))
        else:
            print('No {} to delete ({:.0f} day grace-period)'.format(thing, args.idle_days))
        
    except:
        if slack:
            slack.exception()
        raise


if __name__ == '__main__':
    sys.exit(main(sys.argv))
