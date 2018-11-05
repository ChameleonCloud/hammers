# coding: utf-8
'''
.. code-block:: bash

    gpu-lease-stacking {info, delete}

Reclaims GPU nodes from leases that violate terms of use.

* ``info`` to just display leases or actuall delete them with ``delete``
'''
import sys
import argparse
from pprint import pprint
from datetime import datetime

from hammers import MySqlArgs, osapi, query
from hammers.slack import Slackbot
from hammers.osrest.blazar import lease_delete
from hammers.notifications import email


LEASES_ALLOWED = 1


class GPUUser:
    def __init__(self, user_id, name, email):
        self.user_id = user_id
        self.name = name
        self.email = email
        self.nodes = {}
        self.leases_to_delete = []

    def add_lease(self, node_id, lease_id, start_date, end_date, **kwargs):

        if node_id not in self.nodes:
            self.nodes[node_id] = []

        self.nodes[node_id].append(lease_id, start_date, end_date)

    def delete_stacked_leases(self, auth):
        """ """
        for lease_id, _, _ in self.leases_to_delete:
            lease_delete(auth, lease_id)

    def sort_leases_by_date(self):

        for node_id, leases in self.nodes.keys():
            self.nodes[node_id] = list(sorted(
                set(leases), key=lambda x: x[1]))

    def in_violation(self):
        return len(self.leases_to_delete) > 1

    def check_leases_for_stacks(self):

        self.sort_leases_by_date()

        for node_id, leases in self.nodes.items():
            add_stacked_leases

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

        email_body = email.get_email_template_by_name(
            'stacked_leases_deleted_email_body')
        html = email.render_template(
            email_body, lease_list=",".join(self.leases_to_delete))
        subject = ""
        email.send(
            email.get_host(),
            self.email,
            sender,
            subject,
            html.encode("utf8"))


def gpu_stack_reaper(db, auth, describe=False, quiet=False):
    """Delete stacked leases on gpu nodes."""
    gpu_users = {}

    for row in query.gpu_leases(db):
        user_id = row['user_id']

        if user_id not in gpu_users.keys():
            gpu_users[user_id] = GPUUser(
                user_id=user_id,
                name=row['user_name'],
                email=row['user_name'])

        gpu_user[user_id].add_lease(row)

    # Filter out users who are not stacking leases
    users_in_violation = [x for x in gpu_users if x.in_violation()]

    lease_delete_count = 0
    if not describe:
        for user in users_in_violation:
            lease_delete_count += len(user.leases_to_delete)
            user.delete_stacked_leases()
            user.send_email()
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

    parser.add_argument('-q', '--quiet', action='store_true',
        help='Quiet mode. No output if there was nothing to do.')
    parser.add_argument('--slack', type=str,
        help='JSON file with Slack webhook information to send a notification to')
    parser.add_argument('action', choices=['info', 'delete'],
        help='Just display info or actually delete them?')

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
        'quiet': args.quiet
    }

    if slack:
        with slack:
            remove_count = reaper(**kwargs)
    else:
        remove_count = reaper(**kwargs)

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

if __name__ == '__main__':
    sys.exit(main(sys.argv))
