# coding: utf-8
'''
.. code-block:: bash

    orphan-resource-providers {info, update}

Occasionally, compute nodes are recreated in the Nova database with new UUIDs,
but resource providers in the Placement API database are not updated and still
refer to the old UUIDs. This causes failures to post allocations and results in
errors when launching instances. This detects the issue (``info``) and fixes it
(``update``) by updating the ``uuid`` field of resource providers.
'''


import sys
import argparse

from hammers import MySqlArgs, osapi, query
from hammers.slack import Slackbot


def resource_providers_fixer(db, describe=False, quiet=False):
    if describe:
        for row in query.count_orphan_resource_providers(db):
            count = row['COUNT(*)']
        print('Found %d orphaned resource providers' % count)
        return count
    else:
        count = query.update_orphan_resource_providers(db)
        db.db.commit()
        print('Updated %d orphaned resource providers' % count)
        return count


def main(argv=None):
    if argv is None:
        argv = sys.argv

    parser = argparse.ArgumentParser(description='Fixes issues with orphaned resource providers.')
    mysqlargs = MySqlArgs({
        'user': 'root',
        'password': '',
        'host': 'localhost',
        'port': 3306,
    })
    mysqlargs.inject(parser)

    parser.add_argument('-q', '--quiet', action='store_true',
        help='Quiet mode. No output if there was nothing to do.')
    parser.add_argument('--slack', type=str,
        help='JSON file with Slack webhook information to send a notification to')
    parser.add_argument('action', choices=['info', 'update'],
                        help='Just display info or actually update them?')

    args = parser.parse_args(argv[1:])
    mysqlargs.extract(args)

    slack = Slackbot(args.slack, script_name='orphan-resource-providers') if args.slack else None

    try:
        db = mysqlargs.connect()

        update_count = resource_providers_fixer(db=db, describe=args.action == 'info', quiet=args.quiet)

        if args.action == 'update':
            if update_count > 0:
                message = (
                    'Commanded update of *{} resource providers*'
                    .format(update_count)
                )
                
                print(message)
                
                slack.message(message)
            elif not args.quiet:
                print('No resource providers to delete')
    except:
        if slack:
            slack.exception()
        raise


if __name__ == '__main__':
    sys.exit(main(sys.argv))
