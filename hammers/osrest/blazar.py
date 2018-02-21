import requests


def host(auth, host_id):
    """Retrieves host by ID."""
    response = requests.get(
        url=auth.endpoint('reservation') + '/os-hosts/{}'.format(host_id),
        headers={'X-Auth-Token': auth.token}
    )
    response.raise_for_status()
    bhost = response.json()['host']
    return bhost


def hosts(auth):
    """Retrieves all hosts, returning a dictionary keyed by ID."""
    response = requests.get(
        url=auth.endpoint('reservation') + '/os-hosts',
        headers={'X-Auth-Token': auth.token}
    )
    response.raise_for_status()
    bhosts = response.json()['hosts']
    bhosts = {h['id']: h for h in bhosts}
    return bhosts


def host_update(auth, host_id, values_payload):
    """Updates host data"""
    response = requests.put(
        url=auth.endpoint('reservation') + '/os-hosts/{}'.format(host_id),
        headers={'X-Auth-Token': auth.token},
        json=values_payload#{'values': values_payload}, # disagreement with API spec?
    )
    response.raise_for_status()
    bhost = response.json()['host']
    return bhost


def leases(auth):
    """Retrieves all leases, returning a dictionary keyed by ID"""
    response = requests.get(
        url=auth.endpoint('reservation') + '/leases',
        headers={'X-Auth-Token': auth.token},
    )
    response.raise_for_status()
    leases = response.json()['leases']
    leases = {l['id']: l for l in leases}
    return leases


def lease(auth, lease_id):
    """Retrieves a lease by ID"""
    response = requests.get(
        url=auth.endpoint('reservation') + '/leases/{}'.format(lease_id),
        headers={'X-Auth-Token': auth.token},
    )
    response.raise_for_status()
    return response.json()['lease']


def lease_delete(auth, lease_id):
    """Deletes a lease by ID"""
    response = requests.delete(
        url=auth.endpoint('reservation') + '/leases/{}'.format(lease_id),
        headers={'X-Auth-Token': auth.token},
    )
    response.raise_for_status()
    return response


__all__ = [
    'blazar_host',
    'blazar_hosts',
    'blazar_host_update',
    'blazar_leases',
    'blazar_lease',
    'blazar_lease_delete',
]

blazar_host = host
blazar_hosts = hosts
blazar_host_update = host_update
blazar_leases = leases
blazar_lease = lease
blazar_lease_delete = lease_delete
