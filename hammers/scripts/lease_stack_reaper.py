# coding: utf-8
'''
.. code-block:: bash

    lease-stack-reaper {info, delete}

Reclaims nodes from leases that violate terms of use.

* ``info`` to just display leases or actuall delete them with ``delete``
'''
from collections import defaultdict
import sys
from pprint import pprint
from datetime import datetime
from pytz import timezone

from hammers import osapi
from hammers.slack import Slackbot
from hammers.osrest import blazar, keystone
from hammers.notifications import _email
from hammers.util import base_parser, parse_datestr


LEASES_ALLOWED = 1
MIN_ALLOWED_STACK_INTERVAL_DAYS = 2
MAX_GPU_DAYS_PER_USER = 32
EXCLUDED_PROJECT_IDS = [
    '975c0a94b784483a885f4503f70af655',
    '4ffe61cf850d4b45aef86b46411d33e1',
    'd9faac3973a847f1b718fa765fe312e2',
    'a40a60192c1b42ad9dcb40666663b0e3',  ## LSS Institute
    '0c47c44bb7074b8084eda658151c7d7b',  ## SCC21 CHI-210867
    'a99991eefc974f6f84986257012acf00',  ## SCC21 CHI-210868
    '22521dca92d042f3b98c30bf02c50491',  ## SCC21 CHI-210869
    '5e979a2c26844f2aa62f1342205cd79b',  ## SCC21 CHI-210870
    'b23da57cc66f4ea9add421e635a293a2',  ## SCC21 CHI-210878
]
EXCLUDED_NODE_TYPES = [
    'compute_skylake'
]


class User:
    """Class for user with advanced reservation on gpu nodes."""

    def __init__(self, user_id, name, email):
        """Constructor."""
        self.user_id = user_id
        self.name = name
        self.email = email
        self.nodes = defaultdict(list)

    def add_lease(self, node_type, lease):
        """Add lease to node list."""
        self.nodes[node_type].append(lease)

    def sort_leases_by_date(self):
        """Sort leases by date for each node."""
        for node_type, leases in self.nodes.items():
            self.nodes[node_type] = list(
                sorted(leases, key=lambda x: x['start_date']))

    def leases_in_violation(self):
        """Check for lease stacking and add lease to delete list."""
        self.sort_leases_by_date()
        leases_to_delete = set()

        for node_type, leases in self.nodes.items():
            if node_type in EXCLUDED_NODE_TYPES:
                continue

            if 'gpu_' in node_type:
                gpu_day_violation = self.find_gpu_days_limit_leases(leases)
                pprint(self.print_info(
                    gpu_day_violation,
                    "These leases are in violation of gpu days limit"
                ))
                leases_to_delete.update(gpu_day_violation)

            stacked_leases = self.find_stacked_leases(leases)
            stacked_leases_to_delete = stacked_leases[LEASES_ALLOWED:]
            pprint(self.print_info(
                stacked_leases_to_delete,
                "These leases are stacked on each other"
            ))
            leases_to_delete.update(stacked_leases_to_delete)

        return leases_to_delete

    def find_gpu_days_limit_leases(self, leases):
        """Return list of lease ids in violation of gpu days limit."""
        user_gpu_days = 0
        in_violation = set()

        for lease in leases:

            lease_days = (lease['end_date'] - lease['start_date']).days
            node_count = len(lease['nodes'])
            user_gpu_days += lease_days * node_count

            if user_gpu_days > MAX_GPU_DAYS_PER_USER:
                in_violation.append(lease['id'])

        return in_violation

    def find_stacked_leases(self, leases):
        """Return list of only the leases stacked on each other."""
        stacked = []

        for i in range(len(leases)):

            start_date = leases[i]['start_date']
            end_date = leases[i]['end_date']

            if i > 0:
                last_end_date = leases[i - 1]['end_date']
            else:
                last_end_date = datetime.min.replace(tzinfo=timezone('UTC'))

            if i < len(leases) - 1:
                next_start_date = leases[i + 1]['start_date']
            else:
                next_start_date = datetime.max.replace(tzinfo=timezone('UTC'))

            stacked_previous = (
                (start_date - last_end_date).days
                < MIN_ALLOWED_STACK_INTERVAL_DAYS)
            stacked_next = (
                (next_start_date - end_date).days
                < MIN_ALLOWED_STACK_INTERVAL_DAYS)

            if stacked_previous or stacked_next:
                stacked.append(leases[i])

        return [
            x['id'] for x in stacked
            if (x['end_date'] - x['start_date']).days > 1]

    def print_info(self, lease_ids, reason):
        """Return dict of info for console output."""
        return {
            'user_name': self.name,
            'user_email': self.email,
            'leases': lease_ids,
            'reason': reason
        }


def send_delete_notification(gpu_user, lease_ids, sender):
    """Send email notifying user of leases deleted."""
    email_body = _email.STACKED_LEASE_DELETED_EMAIL_BODY
    html = _email.render_template(
        email_body,
        vars={
            'username': gpu_user.name,
            'lease_list': lease_ids})
    subject = "Your Chameleon lease(s) was deleted."
    _email.send(
        _email.get_host(),
        gpu_user.email,
        sender,
        subject,
        html)


def collect_user_leases(auth):
    users = {}
    users_by_id = keystone.users(auth)
    hosts_by_id = blazar.hosts(auth)
    allocs_by_lease = defaultdict(list)

    for alloc in blazar.host_allocations(auth):
        for r in alloc['reservations']:
            allocs_by_lease[r['lease_id']].append(alloc['resource_id'])


    now = datetime.utcnow().replace(tzinfo=timezone('UTC'))

    for lease_id, lease in blazar.leases(auth).items():
        user_id = lease['user_id']
        lease['nodes'] = allocs_by_lease[lease_id]
        lease['start_date'] = parse_datestr(lease['start_date'])
        lease['end_date'] = parse_datestr(lease['end_date'])
        terminated = lease['status'].lower() == 'terminated'

        if lease['project_id'] in EXCLUDED_PROJECT_IDS:
            continue

        if lease['start_date'] < now or terminated:
            continue

        if user_id not in users:
            users[user_id] = User(user_id=user_id,
                                  name=users_by_id[user_id]['name'],
                                  email=users_by_id[user_id]['email'])

        node_types = set(
            [hosts_by_id[h]['node_type'] for h in allocs_by_lease[lease_id]])

        if len(node_types) == 1:
            users[user_id].add_lease(node_types.pop(), lease)

    return users


def main(argv=None):
    if argv is None:
        argv = sys.argv

    parser = base_parser('Lease Stack Reaper')
    parser.add_argument(
        '-q', '--quiet', action='store_true',
        help='Quiet mode. No output if there was nothing to do.')
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
    sender = args.sender

    if args.slack:
        slack = Slackbot(args.slack, script_name='lease_stack_reaper')
    else:
        slack = None

    try:
        users = collect_user_leases(auth)
        lease_delete_count = 0

        for user in list(users.values()):
            leases_in_violation = user.leases_in_violation()

            if leases_in_violation and args.action == 'delete':
                print(
                    f"deleting the leases {leases_in_violation} "
                    "that are violating lease stacking restriction"
                )
                lease_delete_count += len(leases_in_violation)
                [blazar.lease_delete(auth, l) for l in leases_in_violation]
                send_delete_notification(user, leases_in_violation, sender)

        if lease_delete_count > 0:
            if slack:
                slack.message((
                    'Commanded deletion of *{} leases* '
                    '(Lease stacking restriction violated)'
                    .format(lease_delete_count)
                ))
    except:
        if slack:
            slack.exception()
        raise


if __name__ == '__main__':
    sys.exit(main(sys.argv))
