import datetime
import pytz
import sys
import argparse
import os
import itertools
from hammers import osapi, osrest
from django.utils import timezone
from hammers.osrest.nova import _addremove_host

# Set env variables
os.environ["OS_AUTH_URL"] = "http://10.20.111.241:35357/v3"

# Let's parse some CLI arguments
parser = argparse.ArgumentParser(description='Clean old Nova aggregates tied to expired Blazar leases.')
# The 'osapi' module has a helper to add rules to parse well-known arguments
# (like the OpenStack username/password)
osapi.add_arguments(parser)
# Invoke the parser on the CLI arguments, save as 'args'
args = parser.parse_args(sys.argv[1:])
# Pass args to Auth constructor; will fall back to finding values in well-known env vars
# (like OS_USERNAME/OS_PASSWORD)
auth = osapi.Auth.from_env_or_args(args=args)

# Get aggregates and leases
aggregates = osrest.nova.aggregates(auth)
leases = osrest.blazar.leases(auth)

# Get leases with past end dates
now=datetime.datetime.utcnow().replace(tzinfo=pytz.timezone('UTC'))

def is_terminated(lease):
    dt_fmt = '%Y-%m-%dT%H:%M:%S.%f'
    return now > datetime.datetime.strptime(lease['end_date'], dt_fmt).replace(tzinfo=pytz.timezone('UTC'))

# Match lease to aggregate
def aggregates_for_lease(lease):
    physical_reservation_ids = [r['id'] for r in lease['reservations'] if r['resource_type'] == 'physical:host']
    return [x for x in aggregates.values() if x['name'] in physical_reservation_ids]

def main():
 
    term_leases = [lease for lease in leases.values() if is_terminated(lease)]
    old_aggregates = [aggregates_for_lease(lease) for lease in term_leases if aggregates_for_lease(lease) != None]
    aggregate_list = list(itertools.chain(*old_aggregates))

    for x in aggregate_list:
        if x['hosts']:
            for host in x['hosts']:
                print("Deleting host {} from aggregate {}, then adding to freepool.".format(host, x['id']))
                _addremove_host(auth, "remove", x, host)
                _addremove_host(auth, "add", '1', host)

if __name__ == '__main__':
    main()
