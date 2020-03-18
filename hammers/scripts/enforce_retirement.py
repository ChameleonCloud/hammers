#!/usr/bin/python

import mysql.connector
import os
from hammers.slack import Slackbot
#from hammers.util import base_parser
import sys
sys.path.append('/root/fhalbach/hammers/hammers')
from hammers.util import base_parser

def correct_state(cursor,slk,dryrun=False):
    '''
    # Find retired nodes
    cursor.execute("SELECT uuid FROM ironic.nodes WHERE name LIKE '%retired';")
    retired_nodes = cursor.fetchall()

    # Find blazar hosts with incorrect state
    for node in retired_nodes:
        blazar_chk = "SELECT reservable FROM blazar.computehosts WHERE hypervisor_hostname = %s"
        cursor.execute(blazar_chk, [node[0]])
        if cursor.fetchall()[0][0] != 0:
    '''
    # Find retired nodes
    cursor.execute("SELECT n.uuid from ironic.nodes n join blazar.computehosts ch on n.uuid = ch.hypervisor_hostname WHERE n.name LIKE '%retired' AND ch.reservable != 0;")
    retired_nodes = cursor.fetchall()
    print(retired_nodes)
'''
            if not dryrun:
                blazar_fix = "UPDATE blazar.computehosts SET reservable = '0' WHERE hypervisor_hostname = %s"
                cursor.execute(blazar_fix, [node[0]])
                mess = ("Reverted state of node " + node[0] + " to non-reservable.")
            else:
                mess = ("State of retired node " + node[0] + " is reservable, run without '--dryrun' to retire.")

            print(mess)
            if slk:
                slk.message(mess)
'''
def main(argv=None):
    if argv is None:
        argv = sys.argv

    parser = base_parser('Retired node state enforcer.')
    parser.add_argument('--dryrun', help='dryrun mode', action='store_true')
    args = parser.parse_args(sys.argv[1:])
    slack = Slackbot(args.slack, script_name='enforce-retirement') if args.slack else None

    # Open MYSQL connection
    # Set MYSQL Login and host, create connection
    conn = mysql.connector.connect(
      host = os.environ.get(MYSQL_HOST),
      user = os.environ.get(MYSQL_USER),
      passwd = os.environ.get(MYSQL_PASSWORD),
    )
    
    mycursor = conn.cursor()

    # Find retired nodes and ensure they are non reservable in blazar
    correct_state(mycursor,slack,dryrun=args.dryrun)

    # Close mysql connection
    conn.commit()
    conn.close()
    mycursor.close()

if __name__== "__main__":
    main()

