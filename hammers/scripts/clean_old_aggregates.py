import datetime
import pytz
import sys
import argparse
import os
import itertools
from hammers import osapi, osrest
from hammers.osrest.nova import aggregate_move_host
from hammers.osrest.nova import aggregate_delete

# Append "/v3" to OS_AUTH_URL, if necesary
auth_url = os.environ["OS_AUTH_URL"]
if not re.search("\/v3$", auth_url):
  os.environ["OS_AUTH_URL"]=auth_url+"/v3"

parser = argparse.ArgumentParser(description='Clean old Nova aggregates tied to expired Blazar leases.')
osapi.add_arguments(parser)
args = parser.parse_args(sys.argv[1:])
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

def main(argv=None):

    term_leases = [lease for lease in leases.values() if is_terminated(lease)]

    old_aggregates = [aggregates_for_lease(lease) for lease in term_leases if aggregates_for_lease(lease) != None]

    aggregate_list = list(itertools.chain(*old_aggregates))

    for x in aggregate_list:
        if x['hosts']:
            for host in x['hosts']:
                print("Deleting host {} from aggregate {} and returning to freepool".format(host, x['id']))
                aggregate_move_host(auth, host, x['id'], 1)
            print("Deleting aggregate {}".format(host, x['id']))
            aggregate_delete(auth, x['id'])

if __name__ == '__main__':
    sys.exit(main(sys.argv))

