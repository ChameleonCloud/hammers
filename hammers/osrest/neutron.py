import collections
import requests


def floatingip_delete(auth, floatingip):
    if isinstance(floatingip, collections.Mapping):
        floatingip = floatingip['id']

    response = requests.delete(
        url=auth.endpoint('network') + '/v2.0/floatingips/{}'.format(floatingip),
        headers={'X-Auth-Token': auth.token},
    )
    response.raise_for_status()
    return response # 204 No Content is normal.


def floatingips(auth):
    response = requests.get(
        url=auth.endpoint('network') + '/v2.0/floatingips',
        headers={'X-Auth-Token': auth.token},
    )
    response.raise_for_status()
    fips = response.json()['floatingips']
    return {fip['id']: fip for fip in fips}


def network(auth, net):
    if isinstance(net, collections.Mapping):
        net = net['id']
    response = requests.get(
        url=auth.endpoint('network') + '/v2.0/networks/{}'.format(net),
        headers={'X-Auth-Token': auth.token},
    )
    response.raise_for_status()
    return response.json()['network']


def networks(auth):
    response = requests.get(
        url=auth.endpoint('network') + '/v2.0/networks',
        headers={'X-Auth-Token': auth.token},
    )
    response.raise_for_status()
    nets = response.json()['networks']
    return {net['id']: net for net in nets}


def port_delete(auth, port):
    if isinstance(port, collections.Mapping):
        port = port['id']

    response = requests.delete(
        url=auth.endpoint('network') + '/v2.0/ports/{}'.format(port),
        headers={'X-Auth-Token': auth.token},
    )
    response.raise_for_status()
    return response


def ports(auth):
    response = requests.get(
        url=auth.endpoint('network') + '/v2.0/ports',
        headers={'X-Auth-Token': auth.token},
    )
    response.raise_for_status()
    data = response.json()
    return {n['id']: n for n in data['ports']}


def subnet(auth, subnet):
    if isinstance(subnet, collections.Mapping):
        subnet = subnet['id']
    response = requests.get(
        url=auth.endpoint('network') + '/v2.0/subnets/{}'.format(subnet),
        headers={'X-Auth-Token': auth.token},
    )
    response.raise_for_status()
    return response.json()['subnet']


def subnets(auth):
    response = requests.get(
        url=auth.endpoint('network') + '/v2.0/subnets',
        headers={'X-Auth-Token': auth.token},
    )
    response.raise_for_status()
    subnets = response.json()['subnets']
    return {subnet['id']: subnet for subnet in subnets}


__all__ = [
    'neutron_port_delete',
    'neutron_ports',
]

neutron_port_delete = port_delete
neutron_ports = ports
