import datetime
import pytz
import sys
import argparse
import os
import itertools
import re
from urllib2 import HTTPError
from hammers.slack import Slackbot
from hammers import osapi, osrest
from hammers.osrest.nova import aggregate_move_host
from hammers.osrest.nova import aggregate_delete
from hammers.osrest.nova import aggregate_remove_host


# Append "/v3" to OS_AUTH_URL, if necesary
auth_url = os.environ["OS_AUTH_URL"]
if not re.search("\/v3$", auth_url):
  os.environ["OS_AUTH_URL"]=auth_url+"/v3"

parser = argparse.ArgumentParser(description='Clean old Nova aggregates tied to expired Blazar leases.')
osapi.add_arguments(parser)
parser.add_argument('--slack', type=str,
        help='JSON file with Slack webhook information to send a notification to')
args = parser.parse_args(sys.argv[1:])
auth = osapi.Auth.from_env_or_args(args=args)

# Get aggregates and leases
aggregates = osrest.nova.aggregates(auth)
leases = osrest.blazar.leases(auth)

def is_terminated(lease):
    dt_fmt = '%Y-%m-%dT%H:%M:%S.%f'

    # Get leases with past end dates
    now=datetime.datetime.utcnow().replace(tzinfo=pytz.timezone('UTC'))

    return now > datetime.datetime.strptime(lease['end_date'], dt_fmt).replace(tzinfo=pytz.timezone('UTC'))

# Match lease to aggregate
def aggregates_for_lease(lease):
    physical_reservation_ids = [r['id'] for r in lease['reservations'] if r['resource_type'] == 'physical:host']
    return [x for x in aggregates.values() if x['name'] in physical_reservation_ids]

def clear_aggregates(agg_list):

    report = []

    for x in agg_list:
        if x['hosts']:   
            for host in x['hosts']:
                try:                
                    report.append("Deleting host {} from aggregate {} and returning to freepool. ".format(host, x['id']) + "\n")
                    aggregate_move_host(auth, host, x['id'], 1) 
                except:
                    report.append("Host {} present in aggregate {} and freepool. Removed from aggregate. ".format(host, x['id']) + "\n")
                    pass

            try:
                report.append("Deleting aggregate {}. ".format(host, x['id']) + "\n")
                aggregate_delete(auth, x['id'])
            except:
                report.append("Unexpected error deleting aggregate {}. ".format(x['id']) + "\n")
                pass

    str_report = ''.join(report)

    if report != []:
      return str_report
    else:
      return None


def main(argv=None):

    term_leases = [lease for lease in leases.values() if is_terminated(lease)]

    old_aggregates = [aggregates_for_lease(lease) for lease in term_leases if aggregates_for_lease(lease) != None]

    aggregate_list = list(itertools.chain(*old_aggregates))

    agg_report = clear_aggregates(aggregate_list)
    
    print(agg_report)

    if args.slack:
        slack = Slackbot(args.slack, script_name='clean-old-aggregates')
    else:
        slack = None

    if slack:
        if agg_report:
            slack.post('clean-old-aggregates', agg_report, color='#FF0000')
        else:
            slack.post('clean-old-aggregates', 'Aggregates are clean', color='#CCCCCC')

if __name__ == '__main__':
    sys.exit(main(sys.argv))

