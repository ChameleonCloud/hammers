# coding: utf-8
'''
.. code-block:: bash

    node-doctor <node_name>

'''
from datetime import datetime, timedelta
import re
import sys

from hammers import osrest, osapi
from hammers.util import base_parser, now_utc, parse_datestr

MAINTENANCE_LEASE_REGEX = "^[a-zA-Z0-9\-]+-maintenance$"
NODE_AILMENTS_MESSAGES = {
    "error_state": ("""
        ERROR: node in an error state
        Indicates node has an error state."""),
    "stuck_deleting": ("""
        ERROR: node is stuck in "deleting" state.
        This indicates that the node failed to tear down when its instance was
        deleted; this can happen when network connectivity between Ironic and
        Neutron (or other services) is disrupted during an instance deletion.

        The only known remediation currently is to directly update the DB:

        mysql ironic -e "update nodes
            set provision_state='available',
                target_provision_state=null,
                provision_updated_at=current_timestamp()
            where uuid='$node_uuid';"
        """),
    "maintenance_state_error": ("""
        ERROR: node in maintenance state
        Indicates node is in a maintenance state but does not have
        a corresponding maintenance lease."""),
    "not_in_freepool": ("""
        ERROR: node not in freepool
        Indicates that node is not current reserved and is not in free
        pool. This can occur when a lease fails to terminate properly
        and the node remains in an orphaned aggregate."""),
    "undead_instance": ("""
        ERROR: undead instance
        Indicates that the node has an instance associated with it that no
        longer exists in Nova."""),
    "resource_provider_allocated": ("""
        ERROR: allocations exist
        This indicates that for some reason an allocation was made
        against the resource provider, but was not cleaned up.
        Suggestion: delete the allocation.

        openstack resource provider allocation delete $allocation"""),
    "resource_provider_reserved": ("""
        ERROR ($node): inventory already reserved
        This indicates that for some reason there is a reservation for the
        resource provider's inventory. Suggestion: reset the inventory.

        openstack resource provider inventory set $provider \\
            --resource CUSTOM_BAREMETAL:total=1 \\
            --resource CUSTOM_BAREMETAL:max_unit=1 \\
            --resource CUSTOM_BAREMETAL:reserved=0""")
}


def available_nodes(nodes):
    return [
        nid for nid, node in nodes.items()
        if not node['maintenance'] and node['provision_state'] == "available"]


def node_in_error_state(nodes):
    for nid, node in nodes.items():
        if node['provision_state'] == 'error':
            nodes[nid]['ailments'].append("error_state")


def node_stuck_deleting(nodes):
    expected_time_in_deleting = timedelta(minutes=2)
    threshold = now_utc() - expected_time_in_deleting

    for nid, node in nodes.items():
        provision_updated_at = (
            parse_datestr(node["provision_updated_at"], fmt="ironic"))
        if (node["provision_state"] == "deleting" and
                provision_updated_at < threshold and
                node["last_error"] is not None):
            nodes[nid]["ailments"].append("stuck_deleting")


def node_maintenance_state_error(auth, nodes):
    pattern = re.compile(MAINTENANCE_LEASE_REGEX)
    maintenance_leases = {
        l['name']: l for l_id, l in osrest.blazar.leases(auth).items()
        if re.match(pattern, l['name'])}

    for nid, node in nodes.items():
        if (node['maintenance'] and
                node['name'] not in maintenance_leases):
            nodes[nid]['ailments'].append("maintenance_state_error")


def node_not_in_freepool(auth, nodes):
    freepool = osrest.nova.aggregate_details(auth, '1')
    hosts = osrest.blazar.hosts(auth)
    unallocated_nodes = [
        hosts[x['resource_id']]['hypervisor_hostname'] for x
        in osrest.blazar.host_allocations(auth) if not x['reservations']]

    for node_id in available_nodes(nodes):
        if node_id in unallocated_nodes and node_id not in freepool['hosts']:
            nodes[node_id]['ailments'].append("not_in_freepool")


def node_undead_instance(auth, nodes):
    node_instance_map = {
        n['instance_uuid']: n for n in nodes.values()
        if n['instance_uuid'] is not None}

    node_instance_ids = set(node_instance_map)
    instance_ids = set(osrest.nova_instances(auth))
    unbound_instances = node_instance_ids - instance_ids

    for instance_id in unbound_instances:
        node_id = node_instance_map[instance_id]['uuid']
        nodes[node_id]['ailments'].append("undead_instance")


def resource_provider_failure(auth, nodes):
    provider_by_node = {p['name']: p['uuid'] for p
                        in osrest.placement.resource_providers(auth)}

    for node_id in available_nodes(nodes):
        in_use = osrest.placement.resource_provider(
            auth, provider_by_node.get(node_id), 'usages')
        reserved = osrest.placement.resource_provider(
            auth, provider_by_node.get(node_id), 'inventories',
            resource_class='CUSTOM_BAREMETAL')

        if in_use:
            allocations = osrest.placement.resource_provider(
                auth, node_id, 'allocations')
            if allocations['allocations']:
                nodes[node_id]['ailments'].append(
                    "resource_provider_allocated")
        elif reserved:
            nodes[node_id]["ailments"].append("resource_provider_reserved")


def main(argv=None):
    if argv is None:
        argv = sys.argv

    parser = base_parser('Diagnose node(s) for error states.')
    parser.add_argument('--nodes', nargs="+", type=str, default=[])

    args = parser.parse_args(sys.argv[1:])
    auth = osapi.Auth.from_env_or_args(args=args)

    nodes = {
        nid: dict(n, **{"ailments": []}) for nid, n
        in osrest.ironic_nodes(auth, details=True).items()
        if n['name'] in args.nodes or not args.nodes}

    node_in_error_state(nodes)
    node_stuck_deleting(nodes)
    node_maintenance_state_error(auth, nodes)
    node_not_in_freepool(auth, nodes)
    node_undead_instance(auth, nodes)
    resource_provider_failure(auth, nodes)

    for node_id, node in nodes.items():
        print("Checking Node {name} (uuid: {uuid})".format(
            name=node['name'], uuid=node_id))

        if node.get("ailments"):
            for ailment in node.get("ailments"):
                print("\t{node_name}: {msg}".format(
                    node_name=node.get("name"),
                    msg=NODE_AILMENTS_MESSAGES[ailment]))
        else:
            print("\tNODE PASSED ALL TESTS. EVERYTHING SHOULD BE FINE.")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
