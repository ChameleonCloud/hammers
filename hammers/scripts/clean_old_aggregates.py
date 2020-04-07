import datetime
import pytz
import sys
import os
import itertools
import re
import requests
import traceback
from urllib.error import HTTPError
from hammers.slack import Slackbot
from hammers import osapi, osrest
from hammers.osrest.nova import aggregate_delete
from hammers.osrest.nova import _addremove_host
from hammers.osrest.ironic import nodes
from hammers.util import base_parser

# Append "/v3" to OS_AUTH_URL, if necesary
auth_url = os.environ["OS_AUTH_URL"]
if not re.search("\/v3$", auth_url):
  os.environ["OS_AUTH_URL"]=auth_url+"/v3"

parser = base_parser(
    'Clean old Nova aggregates tied to expired Blazar leases.')
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
    errors = []

    for x in agg_list:
        if x['hosts']:
            for host in x['hosts']:
                try:
                    _addremove_host(auth, 'remove_host', x['id'], host)
                    _addremove_host(auth, 'add_host', 1, host)
                    report.append("Deleted host {} from aggregate {} and returned to freepool. ".format(host, x['id']) + "\n")
                except Exception as exc:
                    report.append("Unexpected error moving host {} from aggregate {} to freepool. ".format(host, x['id']) + "\n")
                    errors.append(exc)
            try:
                aggregate_delete(auth, x['id'])
                report.append("Deleted aggregate {}. ".format(x['id']) + "\n")
            except Exception as exc:
                report.append("Unexpected error deleting aggregate {}. ".format(x['id']) + "\n")
                errors.append(exc)

    return errors, report

def orphan_helper(aggregates)

    nodes(auth, details=False)

def main(argv=None):
    slack = Slackbot(args.slack, script_name='clean-old-aggregates') if args.slack else None

    try:
        term_leases = [lease for lease in leases.values() if is_terminated(lease)]
        old_aggregates = [aggs for aggs in (aggregates_for_lease(lease) for lease in term_leases) if aggs != None]
        aggregate_list = list(itertools.chain(*old_aggregates))
        errors, report = clear_aggregates(aggregate_list)

        if report:
            str_report = ''.join(report)

            print(str_report)

            if slack:
                if errors:
                    slack.error(str_report)
                else:
                    slack.message(str_report)
    except:
        if slack:
            slack.exception()
        raise


if __name__ == '__main__':
    sys.exit(main(sys.argv))
