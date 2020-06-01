import datetime
import pytz
import sys
import os
import itertools
import re
import requests
import traceback
import dateutil.parser
#from datetime import datetime
from urllib.error import HTTPError
from hammers.slack import Slackbot
from hammers import osapi, osrest
#from hammers.osrest.nova import aggregate_delete, _addremove_host
#from hammers.osrest.ironic import nodes
#from hammers.osrest.blazar import hosts,host_allocations,lease
from hammers.util import base_parser
from hammers import MySqlArgs, query

# Append "/v3" to OS_AUTH_URL, if necesary
auth_url = os.environ["OS_AUTH_URL"]
if not re.search("\/v3$", auth_url):
  os.environ["OS_AUTH_URL"]=auth_url+"/v3"

parser = base_parser(
    'Clean old Nova aggregates tied to expired Blazar leases.')
mysqlargs = MySqlArgs({
    'user': 'root',
    'password': '',
    'host': 'localhost',
    'port': '3306',
    })
mysqlargs.inject(parser)
args = parser.parse_args(sys.argv[1:])
auth = osapi.Auth.from_env_or_args(args=args)
mysqlargs.extract(args)
conn = mysqlargs.connect()

#Get aggregates, leases, host_allocations
aggregates = osrest.nova.aggregates(auth)
host_allocs = osrest.blazar.host_allocations(auth)
leases = osrest.blazar.leases(auth)
dt_fmt = '%Y-%m-%dT%H:%M:%S.%f'

def is_terminated(lease):

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

def orphan_find(allaggs):

    # Find all hosts currently in aggregates
    hosts_from_aggs = []
    for agg in allaggs.values():
        for host in agg['hosts']:
            hosts_from_aggs.append(host)

    # Make list of ironic hosts not in any aggregate
    ironic_hosts = osrest.ironic.nodes(auth, details=False).keys()
    orphans = []
    for host in ironic_hosts:
        if host not in hosts_from_aggs:
            host_id = [h['id'] for h in osrest.blazar.hosts(auth).values() if h['uid'] == host][0]
            orphans.append(host_id)
    return(orphans)

def has_active_allocation(orph):

    matching_allocs = [alloc for alloc in host_allocs if alloc['resource_id'] == orph]
    if not matching_allocs:
        return False
    res = matching_allocs[0]['reservations'][0]['id']
    return(res)

def del_expired_alloc(db, old_alloc):

    ha_id = old_alloc['id']
    l_id = old_alloc['lid']
    hh = old_alloc['hypervisor_hostname']

    msg=("Deleting host_allocation for host {} matching expired lease {}. ".format(hh,l_id) + "\n")
    count = query.blazar_old_host_alloc_delete(db, ha_id)
    return(msg)

def main(argv=None):
    
    slack = Slackbot(args.slack, script_name='clean-old-aggregates') if args.slack else None

    try:
        term_leases = [lease for lease in leases.values() if is_terminated(lease)]
        old_aggregates = [aggs for aggs in (aggregates_for_lease(lease) for lease in term_leases) if aggs != None]
        aggregate_list = list(itertools.chain(*old_aggregates))
        errors, reports = clear_aggregates(aggregate_list)
        orphan_list = orphan_find(aggregates)
        reports = []
        
        if orphan_list:
            for orphan in orphan_list:
                destiny = has_active_allocation(orphan)
                host = osrest.blazar.host(auth, orphan)
                if destiny is None:
                    reports.append("Error identifying allocation for orphan host {}.".format(orphan) + "\n")
                elif destiny is False:
                    reports.append("Returning orphan host {} to freepool.".format(orphan) + "\n")
                    osrest.nova.aggregate_add_host(auth, 1, host['hypervisor_hostname'])
                else:
                    destination_agg = [aggr['id'] for aggr in aggregates.values() if aggr['name'] == destiny][0]
                    reports.append("Moving orphan host {} to destined aggregate {}.".format(orphan, destination_agg) + "\n")
                    osrest.nova.aggregate_add_host(auth, destination_agg, host['hypervisor_hostname'])
        

        old_allocations = query.blazar_find_old_host_alloc(conn)
        for alloc in old_allocations:
            reports.append(del_expired_alloc(conn, alloc))
        conn.db.commit()

        if reports:
            str_report = ''.join(reports)
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
