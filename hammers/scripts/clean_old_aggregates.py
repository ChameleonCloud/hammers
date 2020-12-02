from datetime import datetime
import pytz
import sys
import os
import itertools
import re
from hammers.slack import Slackbot
from hammers import osapi, osrest
from hammers.osrest.nova import aggregate_delete, _addremove_host
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

aggregates = osrest.nova.aggregates(auth)
host_allocs = osrest.blazar.host_allocations(auth)
leases = osrest.blazar.leases(auth)
dt_fmt = '%Y-%m-%dT%H:%M:%S.%f'


def is_terminated(lease):
    # Get leases with past end dates
    tzinfo = pytz.timezone('UTC')
    now = datetime.utcnow().replace(tzinfo=tzinfo)
    lease_end = (
        datetime.strptime(lease['end_date'], dt_fmt).replace(tzinfo=tzinfo))
    return now > lease_end


def aggregates_for_lease(lease):
    physical_reservation_ids = [
        r['id'] for r in lease['reservations']
        if r['resource_type'] == 'physical:host'
    ]
    return [
        x for x in aggregates.values()
        if x['name'] in physical_reservation_ids
    ]


def clear_aggregates(agg_list):
    report = []
    errors = []

    for x in agg_list:
        if x['hosts']:
            for host in x['hosts']:
                try:
                    _addremove_host(auth, 'remove_host', x['id'], host)
                    _addremove_host(auth, 'add_host', 1, host)
                    report.append((
                        f"Deleted host {host} from aggregate {x['id']} and "
                        "returned to freepool."))
                except Exception as exc:
                    report.append((
                        f"Unexpected error moving host {host} from aggregate "
                        f"{x['id']} to freepool."))
                    errors.append(exc)
            try:
                aggregate_delete(auth, x['id'])
                report.append(f"Deleted aggregate {x['id']}.")
            except Exception as exc:
                report.append(f"Unexpected error deleting aggregate {x['id']}.")
                errors.append(exc)

    return errors, report


def orphan_find(allaggs):
    # Find all hosts currently in aggregates
    hosts_from_aggs = []
    for agg in allaggs.values():
        for host in agg['hosts']:
            hosts_from_aggs.append(host)

    # Make list of ironic hosts not in any aggregate
    ironic_nodes = osrest.ironic.nodes(auth, details=False).keys()
    blazar_hosts = osrest.blazar.hosts(auth).values()
    orphans = []
    for node_uuid in ironic_nodes:
        if node_uuid not in hosts_from_aggs:
            host_id = next(iter(
                [h['id'] for h in blazar_hosts if h.get('uid') == node_uuid]
            ), None)
            if not host_id:
                raise ValueError(
                    f"Node {node_uuid} not associated to any Blazar host!")
            orphans.append(host_id)
    return orphans


def has_active_allocation(orph):
    matching_allocs = [
        alloc for alloc in host_allocs
        if alloc['resource_id'] == orph
    ]
    if not matching_allocs:
        return False
    res = matching_allocs[0]['reservations'][0]['id']
    return res


def del_expired_alloc(db, old_alloc):
    ha_id = old_alloc['id']
    l_id = old_alloc['lid']
    query.blazar_old_host_alloc_delete(db, ha_id)
    return ha_id, l_id


def main(argv=None):
    script = 'clean-old-aggregates'
    slack = Slackbot(args.slack, script_name=script) if args.slack else None

    try:
        term_leases = [lease for lease in leases.values() if is_terminated(lease)]
        old_aggregates = [aggs for aggs in (aggregates_for_lease(lease) for lease in term_leases) if aggs != None]
        aggregate_list = list(itertools.chain(*old_aggregates))
        errors, reports = clear_aggregates(aggregate_list)
        orphan_list = orphan_find(aggregates)

        for orphan in orphan_list:
            destiny = has_active_allocation(orphan)
            host = osrest.blazar.host(auth, orphan)
            if destiny is None:
                reports.append("Error identifying allocation for orphan host {}.".format(orphan))
            elif destiny is False:
                reports.append("Returning orphan host {} to freepool.".format(orphan) + "\n")
                osrest.nova.aggregate_add_host(auth, 1, host['hypervisor_hostname'])
            else:
                destination_agg = [aggr['id'] for aggr in aggregates.values() if aggr['name'] == destiny][0]
                reports.append("Moving orphan host {} to destined aggregate {}.".format(orphan, destination_agg))
                osrest.nova.aggregate_add_host(auth, destination_agg, host['hypervisor_hostname'])

        old_allocations = query.blazar_find_old_host_alloc(conn)
        for alloc in old_allocations:
            hostname, lease_id = del_expired_alloc(conn, alloc)
            reports.append("Deleted host_allocation for host {} matching expired lease {}.".format(hostname, lease_id))
        conn.db.commit()

        if reports:
            str_report = '\n'.join(reports)
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
