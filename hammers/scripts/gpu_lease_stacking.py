# coding: utf-8
'''
.. code-block:: bash

    gpu-lease-stacking {info, delete}

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


LEASES_ALLOWED = 1


class GPUUser:
    """Class for user with advanced reservation on gpu nodes."""

    def __init__(self, user_id, name, email):
        """Constructor."""
        self.user_id = user_id
        self.name = name
        self.email = email
        self.nodes = {}
        self.leases_to_delete = []

    def add_lease(self, node_id, lease_id, start_date, end_date, **kwargs):
        """Add lease to node list."""
        if node_id not in self.nodes:
            self.nodes[node_id] = []

        self.nodes[node_id].append((lease_id, start_date, end_date))

    def delete_stacked_leases(self, auth):
        """Delete leases in leases_to_delete."""
        for lease_id, _, _ in self.leases_to_delete:
            lease_delete(auth, lease_id)

    def sort_leases_by_date(self):
        """Sort leases by date for each node."""
        for node_id, leases in self.nodes.items():
            self.nodes[node_id] = list(sorted(
                set(leases), key=lambda x: x[1]))

    def in_violation(self):
        """Return boolean value for whether user has stacked gpu leases."""
        return len(self.leases_to_delete) > 1

    def check_leases_for_stacking(self):
        """Check for lease stacking and add lease to delete list."""
        self.sort_leases_by_date()

        for node_id, leases in self.nodes.items():
            stacked_leases = self.find_stacked_leases(leases)
            self.leases_to_delete.extend(stacked_leases[LEASES_ALLOWED:])

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

            stacked_previous = (start_date - last_end_date).days < 1
            stacked_next = (next_start_date - end_date).days < 1

            if stacked_previous or stacked_next:
                stacked.append(leases[i])

        return stacked

    def send_delete_notification(self, sender):
        """Send email notifying user of leases deleted."""
        email_body = _email.STACKED_LEASE_DELETED_EMAIL_BODY
        html = _email.render_template(
            email_body,
            vars={'lease_list': [x[0] for x in self.leases_to_delete]})
        subject = "Your GPU lease(s) was deleted."
        _email.send(
            _email.get_host(),
            self.email,
            sender,
            subject,
            html.encode("utf8"))

    def print_info(self):
        """Return dict of info for console output."""
        return {
            'user_name': self.name,
            'user_email': self.email,
            'leases': self.leases_to_delete
        }


def gpu_stack_reaper(db, auth, sender, describe=False, quiet=False):
    """Delete stacked leases on gpu nodes."""
    gpu_users = {}

    for row in query.get_gpu_advanced_reservations(db):
        user_id = row['user_id']

        if user_id not in gpu_users.keys():
            gpu_users[user_id] = GPUUser(
                user_id=user_id,
                name=row['user_name'],
                email=json.loads(row['user_extra'])['email'])

        gpu_users[user_id].add_lease(**row)

    # Check for lease Stacking
    for gpu_user in gpu_users.values():
        gpu_user.check_leases_for_stacking()

    # Filter out users who are not stacking leases
    users_in_violation = [
        v for (k, v) in gpu_users.items() if v.in_violation()]

    lease_delete_count = 0
    if not describe:
        for user in users_in_violation:
            lease_delete_count += len(user.leases_to_delete)
            user.delete_stacked_leases()
            user.send_delete_notification(sender)
    else:
        for user in users_in_violation:
            pprint(user.print_info())

    return lease_delete_count

def main(argv=None):
    if argv is None:
        argv = sys.argv

    parser = argparse.ArgumentParser(description='GPU Lease Stacking Reaper')
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
        slack = Slackbot(args.slack, script_name='gpu_lease_stacking')
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
            remove_count = gpu_stack_reaper(**kwargs)
    else:
        remove_count = gpu_stack_reaper(**kwargs)

    if slack and (args.action == 'delete') and (
            (not args.quiet) or remove_count):

        if remove_count > 0:
            message = (
                'Commanded deletion of *{} leases* (GPU stacking restriction violated)'
                .format(remove_count)
            )
            color = '#000000'
        else:
            message = ('No leases on gpu nodes to delete.')
            color = '#cccccc'
        slack.post('gpu-lease-stacking', message, color=color)

if __name__ == '__main__':
    sys.exit(main(sys.argv))
