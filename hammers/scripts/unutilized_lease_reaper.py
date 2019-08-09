# coding: utf-8
'''
.. code-block:: bash

    unutilized-leases {info, delete}

Deletes leases that do not launch any instances after a period of time
specified by the admin.

* ``info`` to just display leases or actuall delete them with ``delete``
'''
import argparse
from collections import defaultdict
from datetime import datetime, timedelta
from pprint import pprint
from pytz import timezone
import sys

from hammers import osapi
from hammers.slack import Slackbot
from hammers.notifications import _email
from hammers.osrest import blazar, ironic, keystone

DEFAULT_WARN_HOURS = 6
DEFAULT_GRACE_HOURS = 9


def parse_time(time):
    time = time.split('+')[0].split('.')[0]
    dt_fmt = '%Y-%m-%dT%H:%M:%S'
    return datetime.strptime(time, dt_fmt).replace(tzinfo=timezone('UTC'))


def inviolation_filter(hour):
    now = datetime.utcnow().replace(tzinfo=timezone('UTC'))
    threshold = now - timedelta(minutes=hour*60)

    def inviolation(lease):
        start_time = parse_time(lease['start_date'])

        if start_time > threshold:
            return False

        active_nodes = any([
            x['provision_state'] == 'active'
            for x in lease['nodes']])
        provision_state_change = any([
            parse_time(x['provision_updated_at']) > start_time
            for x in lease['nodes']])

        return not active_nodes and not provision_state_change
    return inviolation


def leases_with_node_details(auth):
    leases = [
        l for l in blazar.leases(auth).values()
        if l['status'] == 'ACTIVE']
    hosts_by_node_uuid = {
        v['hypervisor_hostname']: v['id']
        for k, v in blazar.hosts(auth).items()}
    nodes_by_host = {
        hosts_by_node_uuid[k]: v for k, v
        in ironic.nodes(auth, details=True).items()}
    allocations = blazar.host_allocations(auth)
    allocs_by_lease = defaultdict(list)

    for alloc in allocations:
        for reservation in alloc['reservations']:
            allocs_by_lease[reservation['lease_id']].append(
                nodes_by_host[alloc['resource_id']])

    for lease in leases:
        lease['nodes'] = allocs_by_lease[lease['id']]

    return leases


def send_notification(lease, sender, subject, email_body):
    user = keystone.user(lease['user_id'])
    html = _email.render_template(
        email_body,
        vars=dict(lease_name=lease['name'],
                  lease_id=lease['id']))
    _email.send(_email.get_host(), user['email'], sender, subject,
                html.encode('utf8'))


def reaper(auth, sender, warn_period, termination_period, delete=False):
    leases = leases_with_node_details(auth)
    leases_to_warn = filter(inviolation_filter(warn_period), leases)
    leases_to_remove = filter(inviolation_filter(termination_period), leases)

    if delete:
        for lease in leases_to_warn:
            send_notification(
                lease, sender, warn_period, termination_period,
                "Your lease {} is idle and may be terminated.",
                _email.IDLE_LEASE_WARNING_EMAIL_BODY)
        for lease in leases_to_remove:
            blazar.lease_delete(lease['id'])
            send_notification(
                lease, sender, warn_period, termination_period,
                "Your lease {} has been terminated.",
                _email.IDLE_LEASE_TERMINATION_EMAIL_BODY)

    return leases_to_warn, leases_to_remove


def main(argv=None):
    if argv is None:
        argv = sys.argv

    parser = argparse.ArgumentParser(description='Unutilized Lease Reaper')
    osapi.add_arguments(parser)
    parser.add_argument(
        '--slack', type=str,
        help='JSON file with Slack webhook information')
    parser.add_argument(
        '-w', '--warn-hours', type=int,
        help='Number of hours after which to warn user.',
        default=DEFAULT_WARN_HOURS)
    parser.add_argument(
        '-r', '--grace-hours', type=int,
        help='Number of hours after which to remove lease.',
        default=DEFAULT_GRACE_HOURS)
    parser.add_argument(
        'action', choices=['info', 'delete'],
        help='Just display info or actually delete them?')
    parser.add_argument(
        '--sender',
        type=str,
        help='Email address of sender.',
        default='noreply@chameleoncloud.org')

    args = parser.parse_args(argv[1:])
    auth = osapi.Auth.from_env_or_args(args=args)

    assert args.grace_hours > args.warn_hours, (
        "Grace hours must be greater than warning period.")

    if args.slack and (args.action == 'delete'):
        slack = Slackbot(args.slack, script_name='unutilized_leases_reaper')

        with slack:
            warn, terminate = reaper(auth, args.sender, args.warn_hours,
                                     args.grace_hours, delete=True)

            if (len(warn) + len(terminate) > 0):

                message = (
                    'Warned deletion of *{} idle leases* '
                    'Commanded deletion of *{} idle leases* '
                    '(Unutilized lease violation)'
                    .format(len(warn), len(terminate))
                )
                color = '#000000'
            else:
                message = ('No leases to warn or delete.')
                color = '#cccccc'
            slack.post('unutilized-lease-reaper', message, color=color)

    elif (args.action == 'info'):
        warn, terminate = reaper(auth, args.sender, args.warn_hours,
                                 args.grace_hours, delete=False)
        print("Count: {} Warn; {} Terminate".format(
            len(warn), len(terminate)))
        pprint(dict(
            warn=[
                dict(lease_id=l['id'], nodes=[n['uuid'] for n in l['nodes']])
                for l in warn],
            terminate=[
                dict(lease_id=l['id'], nodes=[n['uuid'] for n in l['nodes']])
                for l in terminate]))


if __name__ == '__main__':
    sys.exit(main(sys.argv))
