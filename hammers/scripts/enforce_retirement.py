#!/usr/bin/python

import os
import sys
from hammers import MySqlArgs, query
from hammers.slack import Slackbot
from hammers.util import base_parser

def correct_state(db,slk,dryrun=False):

    # Find retired nodes
    retired_nodes = query.find_reservable_retired_nodes(db)
    node_list = []
    for node in retired_nodes:
        node_list.append(node['uuid'])
        if not dryrun:
            blazar_fix = query.blazar_set_non_reservable(db, node['uuid'])
    
    if not dryrun:
        mess = ("Reverted state of node(s) " + str(', '.join(node_list))  + " to non-reservable.")
        db.db.commit
    else:
        mess = ("State of retired node(s) " + str(', '.join(node_list)) +  " is reservable, run without '--dryrun' to retire.")

    if node_list:
        print(mess)
        if slk:
            slk.message(mess)

def main(argv=None):
    if argv is None:
        argv = sys.argv

    parser = base_parser('Retired node state enforcer.')
    mysqlargs = MySqlArgs({
        'user': 'root',
        'password': '',
        'host': 'localhost',
        'port': 3306,
    })
    mysqlargs.inject(parser)
    parser.add_argument('--dryrun', help='dryrun mode', action='store_true')
    args = parser.parse_args(argv[1:])
    mysqlargs.extract(args)
    conn = mysqlargs.connect()
    slack = Slackbot(args.slack, script_name='enforce-retirement') if args.slack else None

    # Find retired nodes and ensure they are non reservable in blazar
    correct_state(conn, slack, dryrun=args.dryrun)

if __name__== "__main__":
    main()
