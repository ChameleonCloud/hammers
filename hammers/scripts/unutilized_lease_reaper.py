# coding: utf-8
'''
.. code-block:: bash

    unutilized-leases {info, delete}

Deletes leases that do not launch any instances after a period of time
specified by the admin.

* ``info`` to just display leases or actuall delete them with ``delete``
'''
from collections import defaultdict
from datetime import datetime, timedelta
from pprint import pprint
from pytz import timezone
import sys

from hammers import osapi
from hammers.slack import Slackbot
from hammers.notifications import _email
from hammers.osrest import blazar, ironic, keystone
from hammers.util import base_parser

DEFAULT_WARN_HOURS = 6
DEFAULT_GRACE_HOURS = 9
EXCLUDED_PROJECT_IDS = [
    # Chameleon (TACC)
    'f6c7696906c04b3c89fc3bda9a1b8be0',
    # Chameleon (UC)
    '4140e5f9f65545dbb9f0bdc90ef68d23',
    # Maintenance
    '4ffe61cf850d4b45aef86b46411d33e1']


def parse_time(time, alt_format=False):

    if alt_format:
        dt_fmt = '%Y-%m-%d %H:%M:%S'
    else:
        time = time.split('+')[0].split('.')[0]
        dt_fmt = '%Y-%m-%dT%H:%M:%S'

    return datetime.strptime(time, dt_fmt).replace(tzinfo=timezone('UTC'))


def inviolation_filter(hour):
    now = datetime.utcnow().replace(tzinfo=timezone('UTC'))
    threshold = now - timedelta(minutes=hour*60)

    def inviolation(lease):
        start_event = [
            x for x in lease['events']
            if x['event_type'] == 'start_lease'].pop()
        start_time = parse_time(start_event['updated_at'], alt_format=True)

        if lease['project_id'] in EXCLUDED_PROJECT_IDS:
            return False

        if len(lease['nodes']) == 0:
            return False

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
    allocations = [
        x for x in blazar.host_allocations(auth)
        if x['resource_id'] in nodes_by_host.keys()]
    allocs_by_lease = defaultdict(list)

    for alloc in allocations:
        for reservation in alloc['reservations']:
            allocs_by_lease[reservation['lease_id']].append(
                nodes_by_host[alloc['resource_id']])

    for lease in leases:
        lease['nodes'] = allocs_by_lease[lease['id']]

    return leases


def send_notification(auth, lease, sender, warn_period, termination_period,
                      subject, email_body):
    user = keystone.user(auth, lease['user_id'])
    html = _email.render_template(
        email_body,
        vars=dict(username = user['name'],
                  lease_name=lease['name'],
                  lease_id=lease['id'],
                  warn_period=warn_period,
                  termination_period=termination_period))
    _email.send(_email.get_host(), user['email'], sender, subject, html)


def find_leases_in_violation(auth, warn_period, grace_period):
    leases = leases_with_node_details(auth)
    leases_to_warn = list(filter(inviolation_filter(warn_period), leases))
    leases_to_remove = list(filter(inviolation_filter(grace_period), leases))

    return leases_to_warn, leases_to_remove


def main(argv=None):
    if argv is None:
        argv = sys.argv

    parser = base_parser('Unutilized Lease Reaper')
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

    if args.slack:
        slack = Slackbot(args.slack, script_name='unutilized-leases-reaper')
    else:
        slack = None

    try:
        sender = args.sender
        warn_period = args.warn_hours
        grace_period = args.grace_hours
        warn, terminate = find_leases_in_violation(
            auth, warn_period, grace_period)

        if (len(warn) + len(terminate) > 0):
            if args.action == 'delete':
                for lease in warn:
                    if lease not in terminate:
                        send_notification(
                            auth, lease, sender, warn_period, grace_period,
                            "Your lease {} is idle and may be terminated."
                            .format(lease['name']),
                            _email.IDLE_LEASE_WARNING_EMAIL_BODY)

                for lease in terminate:
                    blazar.lease_delete(auth, lease['id'])
                    send_notification(
                        auth, lease, sender, warn_period, grace_period,
                        "Your lease {} has been terminated.".format(
                            lease['name']),
                        _email.IDLE_LEASE_TERMINATION_EMAIL_BODY)

                message = (
                    'Warned deletion of *{} idle leases* '
                    'Commanded deletion of *{} idle leases* '
                    '(Unutilized lease violation)'
                    .format(len(warn), len(terminate))
                )

                print(message)

                if slack:
                    slack.message(message)
            else:
                pprint(dict(
                    warn=[
                        dict(
                            lease_id=l['id'],
                            nodes=[n['uuid'] for n in l['nodes']])
                        for l in warn],
                    terminate=[
                        dict(
                            lease_id=l['id'],
                            nodes=[n['uuid'] for n in l['nodes']])
                        for l in terminate]))
        else:
            print('No leases to warn or delete.')
    except Exception:
        if slack:
            slack.exception()
        raise


if __name__ == '__main__':
    sys.exit(main(sys.argv))
