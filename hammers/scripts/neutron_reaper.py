# coding: utf-8
'''
.. code-block:: bash

    neutron-reaper {info, delete} \
                   {ip, port} \
                   <grace-days> \
                   [ --dbversion ocata ]

Reclaims idle floating IPs and cleans up stale ports.

Required arguments, in order:

* ``info`` to just display what would be cleaned up, or actually clean it up with ``delete``.
* Consider floating ``ip``'s or ``port``'s
* A project needs to be idle for ``grace-days`` days.

Optional arguments:

* ``--dbversion ocata`` needed for the Ocata release as the database schema
  changed slightly.
'''
from __future__ import absolute_import, print_function, unicode_literals

import sys
import os
import argparse
import collections
import datetime
from pprint import pprint

from MySQLdb import ProgrammingError

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


def normalize_project_name(s, kvm=False):
    if kvm:
        return s
    else:
        return s.lower().replace('-', '').strip()


def days_past(dt):
    if isinstance(dt, str):
        dt = datetime.datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
    return (datetime.datetime.utcnow() - dt).total_seconds() / (60*60*24)


def check_failed_lease_takedown(db, not_down):
    '''
    Checks if a lease failed to disassociate a floating
    ip address when the lease expired, and removes
    ip address from not_down list.
    '''
    ip_ids = tuple([str(x['id']) for x in not_down])

    for lease in query.floating_ips_to_leases(db, ip_ids):

        if (lease.pop('action') == 'START' and
            lease.pop('end_date') < datetime.datetime.utcnow()):
            
            for idx, ip in enumerate(not_down):
                if lease.get('ip_id') == str(ip['id']):
                    del not_down[idx]


def reaper(db, auth, type_, idle_days, whitelist, kvm=False, describe=False, quiet=False):
    future_projects = set()
    db_names = ['nova']
    if not kvm:
        future_projects = {
            normalize_project_name(row['project_id'])
            for row
            in query.future_reservations(db)
        }
        db_names.append('nova_cell0')

    project_last_seen = {}
    for db_name in db_names:
        for row in query.latest_instance_interaction(db, kvm, db_name):
            # Projects that have active instances are not considered as idled projects
            if row['active']: continue
            proj_id = normalize_project_name(row['id'], kvm)
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
    # too_idle_project_ids = [proj['id'] for proj in too_idle_projects]
    #pprint(too_idle_project_ids)

    resource_query = RESOURCE_QUERY[type_]
    command = RESOURCE_DELETE_COMMAND[type_]

    n_things_to_remove = 0
    if not describe:
        to_delete = []
        not_down = [] # should be empty, otherwise fail.
        for proj_id in too_idle_project_ids:
            # TODO replace SQL query by looking at floating IP data from
            # the HTTP endpoint
            for resource in resource_query(db, proj_id):
                to_delete.append(resource['id'])
                if (resource['status'] != 'DOWN'):
                    not_down.append(resource)

        # Check if ips were not properly removed from lease
        # that expired.
        if not_down and not kvm and type_=='ip':
            check_failed_lease_takedown(db, not_down)
            
        if not_down:
            raise RuntimeError('error: not all {}s selected are in "DOWN" state'
                '.\n\n{}'.format(type_, not_down))
        for resource_id in to_delete:
            command(auth, resource_id)
            n_things_to_remove += 1

    else:
        projects = collections.defaultdict(dict)
        for proj_id in too_idle_project_ids:
            for resource in resource_query(db, proj_id):
                assert proj_id == resource.pop('project_id')
                projects[proj_id][resource.pop('id')] = resource
                n_things_to_remove += 1
        if (not quiet) or n_things_to_remove:
            print('Format: {project_id: {resource_id: {INFO} ...}, ...}\n')
            pprint(dict(projects))
            # print(json.dumps(dict(projects), indent=4))

    return n_things_to_remove


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
    parser.add_argument('-q', '--quiet', action='store_true',
        help='Quiet mode. No output if there was nothing to do.')
    parser.add_argument('--slack', type=str,
        help='JSON file with Slack webhook information to send a notification to')
    parser.add_argument('-d', '--dbversion', type=str,
        help='Version of the database. Schemas differ, pick the appropriate one.',
        choices=[query.LIBERTY, query.OCATA], default=query.LIBERTY)
    parser.add_argument('--kvm', help='Run at KVM site', action='store_true')

    parser.add_argument('action', choices=['info', 'delete'],
        help='Just display info or actually delete them?')
    parser.add_argument('type', choices=list(RESOURCE_QUERY),
        help='Grab floating IPs or ports?')
    parser.add_argument('idle_days', type=float,
        help='Number of days since last active instance in project was '
        'deleted to consider it idle.')

    args = parser.parse_args(argv[1:])
    mysqlargs.extract(args)
    auth = osapi.Auth.from_env_or_args(args=args)

    if args.action == 'delete' and args.type == 'port' and args.dbversion == 'ocata':
        print('Checking ports on Ocata isn\'t validated, refusing to '
              'automatically delete.', file=sys.stderr)
        sys.exit(1)

    if args.slack:
        slack = Slackbot(args.slack, script_name='neutron-reaper')
    else:
        slack = None

    whitelist = set()
    if args.whitelist:
        with open(args.whitelist) as f:
            whitelist = {normalize_project_name(line, args.kvm) for line in f}

    db = mysqlargs.connect()
    db.version = args.dbversion

    kwargs = {
        'db': db,
        'auth': auth,
        'type_': args.type,
        'idle_days': args.idle_days,
        'whitelist': whitelist,
        'kvm': args.kvm,
        'describe': args.action == 'info',
        'quiet': args.quiet,
    }
    if slack:
        with slack: # log exceptions
            remove_count = reaper(**kwargs)
    else:
        remove_count = reaper(**kwargs)

    if slack and (args.action == 'delete') and ((not args.quiet) or remove_count):
        thing = '{}{}'.format(
            {'ip': 'floating IP', 'port': 'port'}[args.type],
            ('' if remove_count == 1 else 's'),
        )

        if remove_count > 0:
            message = (
                'Commanded deletion of *{} {}* ({:.0f} day grace-period)'
                .format(remove_count, thing, args.idle_days)
            )
            color = '#000000'
        else:
            message = (
                'No {} to delete ({:.0f} day grace-period)'
                .format(thing, args.idle_days)
            )
            color = '#cccccc'

        slack.post('neutron-reaper', message, color=color)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
