from hammers.osrest.base import BaseAPI


API = BaseAPI('reservation')


def host(auth, host_id):
    """Retrieves host by ID."""
    response = API.get(auth, '/os-hosts/{}'.format(host_id))

    return response.json()['host']


def hosts(auth):
    """Retrieves all hosts, returning a dictionary keyed by ID."""
    response = API.get(auth, '/os-hosts')

    return {h['id']: h for h in response.json()['hosts']}


def host_update(auth, host_id, values_payload):
    """Updates host data"""
    response = API.put(auth, '/os-hosts/{}'.format(host_id), values_payload)

    return response.json()['host']


def leases(auth):
    """Retrieves all leases, returning a dictionary keyed by ID"""
    response = API.get(auth, '/leases')

    return {l['id']: l for l in response.json()['leases']}


def lease(auth, lease_id):
    """Retrieves a lease by ID"""
    response = API.get(auth, '/leases/{}'.format(lease_id))

    return response.json()['lease']


def lease_delete(auth, lease_id):
    """Deletes a lease by ID"""
    response = API.delete(auth, '/leases/{}'.format(lease_id))

    return response


def host_allocations(auth):
    """Retrieve host allocations"""
    response = API.get(auth, '/os-hosts/allocations')

    return response.json()['allocations']


__all__ = [
    'blazar_host',
    'blazar_hosts',
    'blazar_host_update',
    'blazar_leases',
    'blazar_lease',
    'blazar_lease_delete',
    'blazar_host_allocations'
]

blazar_host = host
blazar_hosts = hosts
blazar_host_update = host_update
blazar_leases = leases
blazar_lease = lease
blazar_lease_delete = lease_delete
blazar_host_allocations = host_allocations
