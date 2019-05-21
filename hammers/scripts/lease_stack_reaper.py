# coding: utf-8
'''
.. code-block:: bash

    lease-stack-reaper {info, delete}

Reclaims GPU nodes from leases that violate terms of use.

* ``info`` to just display leases or actuall delete them with ``delete``
'''
import argparse
import json
import sys
from pprint import pprint
from datetime import datetime

from hammers import MySqlArgs, osapi, query
from hammers.slack import Slackbot
from hammers.osrest.blazar import lease_delete
from hammers.notifications import _email
from hammers.util import prometheus_exporter


LEASES_ALLOWED = 1
MIN_ALLOWED_STACK_INTERVAL_DAYS = 2
MAX_GPU_DAYS_PER_USER = 32
EXCLUDED_PROJECT_IDS = [
    '975c0a94b784483a885f4503f70af655',
    '4ffe61cf850d4b45aef86b46411d33e1',
    'd9faac3973a847f1b718fa765fe312e2 ',
    'a40a60192c1b42ad9dcb40666663b0e3'] ##LSS Institute


class User:
    """Class for user with advanced reservation on gpu nodes."""

    def __init__(self, user_id, name, email):
        """Constructor."""
        self.user_id = user_id
        self.name = name
        self.email = email
        self.nodes = {}

    def add_lease(self, node_type, lease_id, start_date, end_date, **kwargs):
        """Add lease to node list."""
        if node_type not in self.nodes:
            self.nodes[node_type] = set()

        self.nodes[node_type].add((lease_id, start_date, end_date))

    def sort_leases_by_date(self):
        """Sort leases by date for each node."""
        for node_type, leases in self.nodes.items():
            self.nodes[node_type] = list(sorted(leases, key=lambda x: x[1]))

    def leases_in_violation(self, db):
        """Check for lease stacking and add lease to delete list."""
        self.sort_leases_by_date()
        leases_to_delete = set()

        for node_type, leases in self.nodes.items():
            if 'gpu_' in node_type:
                gpu_day_violation = self.find_gpu_days_limit_leases(
                    db, leases)
                leases_to_delete.update(gpu_day_violation)

            stacked_leases = self.find_stacked_leases(leases)
            leases_to_delete.update(stacked_leases[LEASES_ALLOWED:])

        return leases_to_delete

    def find_gpu_days_limit_leases(self, db, leases):
        """Return list of leases in violation of gpu days limit."""
        user_gpu_days = 0
        in_violation = []

        for i in range(len(leases)):

            lease_id, start_date, end_date = leases[i]

            lease_days = (end_date - start_date).days
            node_count = len(list(query.get_nodes_by_lease(db, lease_id)))
            user_gpu_days += lease_days * node_count

            if user_gpu_days > MAX_GPU_DAYS_PER_USER:
                in_violation.append(leases[i])

        return in_violation

    def find_stacked_leases(self, leases):
        """Return list of only the leases stacked on each other."""
        stacked = []

        for i in range(len(leases)):

            _, start_date, end_date = leases[i]

            if i > 0:
                last_end_date = leases[i - 1][2]
            else:
                last_end_date = datetime.min

            if i < len(leases) - 1:
                next_start_date = leases[i + 1][1]
            else:
                next_start_date = datetime.max

            stacked_previous = (
                (start_date - last_end_date).days
                < MIN_ALLOWED_STACK_INTERVAL_DAYS)
            stacked_next = (
                (next_start_date - end_date).days
                < MIN_ALLOWED_STACK_INTERVAL_DAYS)

            if stacked_previous or stacked_next:
                stacked.append(leases[i])

        return [x for x in stacked if (x[2] - x[1]).days > 1]

    def print_info(self, leases):
        """Return dict of info for console output."""
        return {
            'user_name': self.name,
            'user_email': self.email,
            'leases': leases}


def send_delete_notification(gpu_user, leases, sender):
    """Send email notifying user of leases deleted."""
    email_body = _email.STACKED_LEASE_DELETED_EMAIL_BODY
    html = _email.render_template(
        email_body,
        vars={
            'username': gpu_user.name,
            'lease_list': [x[0] for x in leases]})
    subject = "Your GPU lease(s) was deleted."
    _email.send(
        _email.get_host(),
        gpu_user.email,
        sender,
        subject,
        html.encode("utf8"))


def lease_stack_reaper(db, auth, sender, describe=False, quiet=False):
    """Delete stacked leases on gpu nodes."""
    users = {}

    for row in query.get_advanced_reservations_by_node_type(db):
        user_id = row['user_id']

        if row['project_id'] in EXCLUDED_PROJECT_IDS:
            continue

        if user_id not in users.keys():
            users[user_id] = User(
                user_id=user_id,
                name=row['user_name'],
                email=json.loads(row['user_extra'])['email'])

        users[user_id].add_lease(**row)

    lease_delete_count = 0
    for user in users.values():
        leases_in_violation = user.leases_in_violation(db)

        if leases_in_violation:
            if not describe:
                lease_delete_count += len(leases_in_violation)
                [lease_delete(auth, x[0]) for x in leases_in_violation]
                send_delete_notification(user, leases_in_violation, sender)
            else:
                pprint(user.print_info(leases_in_violation))

    return lease_delete_count


@prometheus_exporter(__file__)
def main(argv=None):
    if argv is None:
        argv = sys.argv

    parser = argparse.ArgumentParser(description='Lease Stack Reaper')
    mysqlargs = MySqlArgs({
        'user': 'root',
        'password': '',
        'host': 'localhost',
        'port': 3306,
    })
    mysqlargs.inject(parser)
    osapi.add_arguments(parser)

    parser.add_argument(
        '-q', '--quiet', action='store_true',
        help='Quiet mode. No output if there was nothing to do.')
    parser.add_argument(
        '--slack', type=str,
        help='JSON file with Slack webhook information')
    parser.add_argument(
        'action', choices=['info', 'delete'],
        help='Just display info or actually delete them?')
    parser.add_argument(
        '--sender',
        type=str,
        help='Email address of sender.',
        default='noreply@chameleoncloud.org')

    args = parser.parse_args(argv[1:])
    mysqlargs.extract(args)
    auth = osapi.Auth.from_env_or_args(args=args)

    if args.slack:
        slack = Slackbot(args.slack, script_name='lease_stack_reaper')
    else:
        slack = None

    db = mysqlargs.connect()
    db.version = 'ocata'

    kwargs = {
        'db': db,
        'auth': auth,
        'describe': args.action == 'info',
        'quiet': args.quiet,
        'sender': args.sender
    }

    if slack:
        with slack:
            remove_count = lease_stack_reaper(**kwargs)
    else:
        remove_count = lease_stack_reaper(**kwargs)

    if slack and (args.action == 'delete') and (
            (not args.quiet) or remove_count):

        if remove_count > 0:
            message = (
                'Commanded deletion of *{} leases* '
                '(Lease stacking restriction violated)'
                .format(remove_count)
            )
            color = '#000000'
        else:
            message = ('No leases to delete.')
            color = '#cccccc'
        slack.post('lease-stack-reaper', message, color=color)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
