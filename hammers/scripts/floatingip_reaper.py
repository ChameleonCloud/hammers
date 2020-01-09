# coding: utf-8
'''
.. code-block:: bash

    floatingip-reaper --grace-days <grace-days>

Reclaims idle floating IPs.

Required arguments, in order:

* A floaing ip needs to be idle for ``grace-days`` days.

Optional arguments:

* ``--dryrun`` present for dryrun mode; print out instead of actually reclaiming floating ips from projects

NOTE: Only used for OpenStack database Rocky version!
'''


import sys
import argparse

from hammers import MySqlArgs, osapi, osrest, query
from hammers.slack import Slackbot

def reaper(db, auth, grace_days, whitelist, dryrun=False):
    to_delete = {}
    # iterate through all idle floating ips
    for obj in query.idle_not_reserved_floating_ips(db, grace_days):
        project_id = obj['project_id']
        floating_ip_id = obj['floating_ip_id']
        
        # collect floating ips that don't belong to whitelist project
        if project_id not in whitelist:
            if project_id not in to_delete:
                to_delete[project_id] = []
            to_delete[project_id].append(floating_ip_id)
            
    for proj, ipids in to_delete.items():
        print('Reclaim {} floating ips from project {}'.format(str(len(ipids)), proj))
        for ipid in ipids:
            print(ipid)
            if not dryrun: osrest.neutron.floatingip_delete(auth, ipid)
            
    return to_delete

def main(argv=None):
    if argv is None:
        argv = sys.argv

    parser = argparse.ArgumentParser(description='floating IP reaper')
    mysqlargs = MySqlArgs({
        'user': 'root',
        'password': '',
        'host': 'localhost',
        'port': 3306,
    })
    mysqlargs.inject(parser)
    osapi.add_arguments(parser)

    parser.add_argument('-w', '--whitelist', type=str, help='File of project/tenant IDs to ignore, one per line.')
    parser.add_argument('--slack', type=str, help='JSON file with Slack webhook information to send a notification to')
    parser.add_argument('--grace-days', type=int, required=True, help='Number of days since last used to consider to be idle')
    parser.add_argument('--dryrun', help='dryrun mode', action='store_true')

    args = parser.parse_args(argv[1:])
    mysqlargs.extract(args)
    auth = osapi.Auth.from_env_or_args(args=args)

    slack = Slackbot(args.slack, script_name='floatingip-reaper') if args.slack else None

    whitelist = set()
    if args.whitelist:
        with open(args.whitelist) as f:
            whitelist = {line.rstrip('\n') for line in f}

    db = mysqlargs.connect()
    db.version = query.ROCKY

    try:
        result = reaper(db=db, auth=auth, grace_days=args.grace_days, whitelist=whitelist, dryrun=args.dryrun)
        if result and not args.dryrun:
            message_lines = []
            for proj, ips in result.items():
                message_lines.append('Reclaimed *{} floating ips* from project {} ({:.0f} day grace-period)'.format(str(len(ips)), proj, args.grace_days))
            message = '\n'.join(message_lines)
            print(message)
            
            if slack:
                slack.message(message)
    except:
        if slack:
            slack.exception()
        raise


if __name__ == '__main__':
    sys.exit(main(sys.argv))
