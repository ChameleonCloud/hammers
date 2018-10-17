# coding: utf-8
'''
.. code-block:: bash
'''
import sys
import argparse
from pprint import pprint

from hammers import MySqlArgs, osapi, query
from hammers.slack import Slackbot
from hammers.osrest.blazar import lease_delete

def reaper(db, auth, whitelist=None, describe=False, quiet=False):
    """"""
    user_gpu_leases = {}

    for row in query.gpu_leases(db):
        user_id = row['user_id']
        node_id = row['node_id']

        if user_id not in user_gpu_leases.keys():
            user_gpu_leases[row['user_id']] = {}

        if node_id not in user_gpu_leases[user_id].keys():
            user_gpu_leases[user_id][node_id] = [
                (row['lease_id'], row['start_date'])]
        else:
            user_gpu_leases[user_id][node_id].append(
                (row['lease_id'], row['start_date']))

    leases_to_delete = []
    for user_id in user_gpu_leases.keys():
        for node in user_gpu_leases[user_id].keys():
            leases = user_gpu_leases[user_id][node_id]
            leases = list(sorted(leases, key=lambda x: x[1]))

            if len(leases) > 1:
                leases.extend(leases[1:])

    if not describe:
        for lease_id, _ in leases_to_delete:
            # lease_delete(auth, lease_id)
            pass # until tested
    else:
        pprint(user_gpu_leases)

    return len(leases_to_delete)


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

    parser.add_argument('-w', '--whitelist', type=str,
        help='File of project/tenant IDs/names to ignore, one per line. '
             'Ignores case and dashes.')
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

    whitelist = set()
    if args.whitelist:
        with open(args.whitelist) as f:
            whitelist = {}

    db = mysqlargs.connect()
    db.version = 'ocata'

    kwargs = {
        'db': db,
        'auth': auth,
        'whitelist': whitelist,
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
            message = ('')
        else:
            message = ('')


if __name__ == '__main__':
    sys.exit(main(sys.argv))
