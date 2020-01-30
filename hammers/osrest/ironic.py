"""
Shims for Ironic. See `Ironic HTTP API Docs
<https://developer.openstack.org/api-ref/baremetal/>`_.

"""
from hammers.osrest.base import BaseAPI


_API_VERSION = '1.20'
API = BaseAPI('baremetal', {'X-OpenStack-Ironic-API-Version': _API_VERSION})


def node(auth, node):
    """Get node by ID or the ``uuid`` key out of a dictionary."""
    if isinstance(node, dict):
        node = node['uuid']

    response = API.get(auth, '/v1/nodes/{}'.format(node))

    return response.json()


def node_set_state(auth, node, state):
    """Set provision state of `node` to `state`.

    .. seealso:: `Ironic's State Machine
            <https://docs.openstack.org/ironic/pike/contributor/states.html>`_
    """
    if isinstance(node, dict):
        node = node['uuid']

    response = API.put(auth, '/v1/nodes/{}/states/provision'.format(node),
                       {'target': state})

    return response


def node_update(auth, node, **kwargs):
    """
    Add/remove/replace properties on the node.

    :param mapping replace: properties to replace by key
    """
    replace = kwargs.get('replace')
    patch = [
        {'op': 'replace', 'path': k, 'value': v} for k, v in replace.items()]

    if isinstance(node, dict):
        node = node['uuid']

    response = API.patch(auth, '/v1/nodes/{}'.format(node), json=patch)

    return response.json()


def nodes(auth, details=False):
    """Retrieves all nodes, with more info if `details` is true."""
    response = API.get(auth, '/v1/nodes/detail' if details else '/v1/nodes')

    return {n['uuid']: n for n in response.json()['nodes']}


def ports(auth):
    """Retrieves all Ironic ports, returns a dictionary keyed by the port ID"""
    response = API.get(auth, '/v1/ports/detail')

    return {n['uuid']: n for n in response.json()['ports']}


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
