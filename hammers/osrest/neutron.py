import requests


def port_delete(auth, port):
    if isinstance(port, dict):
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


__all__ = [
    'neutron_port_delete',
    'neutron_ports',
]

neutron_port_delete = port_delete
neutron_ports = ports
