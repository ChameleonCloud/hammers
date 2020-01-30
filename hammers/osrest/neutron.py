import collections

from hammers.osrest.base import BaseAPI


API = BaseAPI('network')


def floatingip_delete(auth, floatingip):
    """Frees a floating IP by ID"""
    if isinstance(floatingip, collections.Mapping):
        floatingip = floatingip['id']

    response = API.delete(auth, '/v2.0/floatingips/{}'.format(floatingip))

    # 204 No Content is normal.
    return response


def floatingips(auth):
    """Get all floating IPs, returns a dictionary keyed by ID."""
    response = API.get(auth, '/v2.0/floatingips')

    return {fip['id']: fip for fip in response.json()['floatingips']}


def network(auth, net):
    """Gets a network by ID, or mapping containing an ``'id'`` key."""
    if isinstance(net, collections.Mapping):
        net = net['id']

    response = API.get(auth, '/v2.0/networks/{}'.format(net))

    return response.json()['network']


def networks(auth):
    """Get all networks. Returns dictionary keyed by ID."""
    response = API.get(auth,  '/v2.0/networks')

    return {net['id']: net for net in response.json()['networks']}


def port_delete(auth, port):
    """Deletes a port by ID, or mapping containing an ``'id'`` key."""
    if isinstance(port, collections.Mapping):
        port = port['id']

    response = API.delete(auth,  '/v2.0/ports/{}'.format(port))

    return response


def ports(auth):
    """Get all ports. Returns a dictionary keyed by port ID."""
    response = API.get(auth,  '/v2.0/ports')
    response.raise_for_status()
    data = response.json()
    return {n['id']: n for n in data['ports']}


def subnet(auth, subnet):
    """Get subnet info. Accepts ID or mapping containing an ``'id'`` key."""
    if isinstance(subnet, collections.Mapping):
        subnet = subnet['id']

    response = API.get(auth, '/v2.0/subnets/{}'.format(subnet))

    return response.json()['subnet']


def subnets(auth):
    """Get all subnets."""
    response = API.get(auth, '/v2.0/subnets')

    return {subnet['id']: subnet for subnet in response.json()['subnets']}


__all__ = [
    'neutron_port_delete',
    'neutron_ports',
]

neutron_port_delete = port_delete
neutron_ports = ports
