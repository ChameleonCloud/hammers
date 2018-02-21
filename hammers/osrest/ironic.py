"""
Shims for Ironic. See `Ironic HTTP API Docs
<https://developer.openstack.org/api-ref/baremetal/>`_.

"""
import requests


_API_VERSION = '1.20'


def node(auth, node):
    """Get node by ID or the ``uuid`` key out of a dictionary."""
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
    """Set provision state of `node` to `state`.

    .. seealso:: `Ironic's State Machine <https://docs.openstack.org/ironic/pike/contributor/states.html>`_
    """
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
    """
    Add/remove/replace properties on the node.

    :param mapping add:     properties to add
    :param iterable remove: properties to delete
    :param mapping replace: properties to replace by key
    """
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
    """Retrieves all nodes, with more info if `details` is true."""
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
    """Retrieves all Ironic ports, returns a dictionary keyed by the port ID"""
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
