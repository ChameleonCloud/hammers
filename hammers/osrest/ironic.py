import requests


_API_VERSION = '1.20'


def node(auth, node):
    if isinstance(node, dict):
        node = node['uuid']

    response = requests.get(
        url=auth.endpoint('baremetal') + '/v1/nodes/{}'.format(node),
        headers={
            'X-Auth-Token': auth.token,
            'X-OpenStack-Ironic-API-Version': _API_VERSION,
        },
    )
    response.raise_for_status()
    data = response.json()
    return data


def node_set_state(auth, node, state):
    if isinstance(node, dict):
        node = node['uuid']

    response = requests.put(
        url=auth.endpoint('baremetal') + '/v1/nodes/{}/states/provision'.format(node),
        json={'target': state},
        headers={
            'X-Auth-Token': auth.token,
            'X-OpenStack-Ironic-API-Version': _API_VERSION,
        },
    )
    response.raise_for_status()
    return response


# def ironic_node_update(auth, node, *, add=None, remove=None, replace=None):
# <python 2 compat>
def node_update(auth, node, **kwargs):
    add = kwargs.get('add')
    remove = kwargs.get('remove')
    replace = kwargs.get('replace')
# </python 2 compat>
    patch = []
    if replace is not None:
        for key, value in replace.items():
            patch.append({'op': 'replace', 'path': key, 'value': value})

    if isinstance(node, dict):
        node = node['uuid']

    response = requests.patch(
        url=auth.endpoint('baremetal') + '/v1/nodes/{}'.format(node),
        headers={
            'X-Auth-Token': auth.token,
            'X-OpenStack-Ironic-API-Version': _API_VERSION,
        },
        json=patch,
    )
    response.raise_for_status()
    data = response.json()
    return data


def nodes(auth, details=False):
    path = '/v1/nodes' if not details else '/v1/nodes/detail'
    response = requests.get(
        url=auth.endpoint('baremetal') + path,
        headers={
            'X-Auth-Token': auth.token,
            'X-OpenStack-Ironic-API-Version': _API_VERSION,
        },
    )
    response.raise_for_status()
    data = response.json()

    return {n['uuid']: n for n in data['nodes']}


def ports(auth):
    response = requests.get(
        url=auth.endpoint('baremetal') + '/v1/ports/detail',
        headers={
            'X-Auth-Token': auth.token,
            'X-OpenStack-Ironic-API-Version': _API_VERSION,
        },
    )
    response.raise_for_status()
    data = response.json()

    return {n['uuid']: n for n in data['ports']}


__all__ = [
    'ironic_node',
    'ironic_node_set_state',
    'ironic_node_update',
    'ironic_nodes',
    'ironic_ports',
]

ironic_node = node
ironic_node_set_state = node_set_state
ironic_node_update = node_update
ironic_nodes = nodes
ironic_ports = ports
