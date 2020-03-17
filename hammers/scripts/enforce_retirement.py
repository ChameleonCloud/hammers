#!/usr/bin/python

import mysql.connector
import os
from time import sleep
import sys
from hammers.slack import Slackbot
from hammers.util import base_parser

def mysql_conn(host, user, passwd):

    # Set MYSQL Login and host, create connection
    mydb = mysql.connector.connect(
      host = os.environ.get(host),
      user = os.environ.get(user),
      passwd = os.environ.get(passwd),
    )
    return mydb

def correct_state(cursor,slk,dryrun=False):

    # Find retired nodes
    cursor.execute("SELECT uuid FROM ironic.nodes WHERE name LIKE '%retired';")
    retired_nodes = cursor.fetchall()

    # Find blazar hosts with incorrect state
    for node in retired_nodes:
        blazar_chk = "SELECT reservable FROM blazar.computehosts WHERE hypervisor_hostname = %s"
        cursor.execute(blazar_chk, [node[0]])
        if cursor.fetchall()[0][0] != 0:
            if not dryrun:
                blazar_fix = "UPDATE blazar.computehosts SET reservable = '0' WHERE hypervisor_hostname = %s"
                cursor.execute(blazar_fix, [node[0]])
                mess = ("Reverted state of node " + node[0] + " to non-reservable.")
            else:
                mess = ("State of retired node " + node[0] + " is reservable, run without '--dryrun' to retire.")

            print(mess)
            if slk:
                slk.message(slack_message)

def main(argv=None):
    if argv is None:
        argv = sys.argv

    parser = base_parser('Retired node state enforcer.')
    parser.add_argument('--dryrun', help='dryrun mode', action='store_true')
    args = parser.parse_args(sys.argv[1:])
    slack = Slackbot(args.slack, script_name='enforce-retirement') if args.slack else None

    # Open MYSQL connection
    conn = mysql_conn('MYSQL_HOST','MYSQL_USER','MYSQL_PASSWD')
    mycursor = conn.cursor()

    # Find retired nodes and ensure they are non reservable in blazar
    correct_state(mycursor,slack,dryrun=args.dryrun)

    # Close mysql connection
    conn.commit()
    conn.close()
    mycursor.close()

if __name__== "__main__":
    main()

