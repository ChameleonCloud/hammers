from hammers.osrest.base import BaseAPI


FREEPOOL_AGGREGATE_ID = 1
RESET_STATES = ['error', 'active']
API = BaseAPI('compute')


def hypervisors(auth, details=False):
    path = '/os-hypervisors/detail' if details else '/os-hypervisors'
    response = API.get(auth, path)

    return {h['id']: h for h in response.json()['hypervisors']}


def instance(auth, id):
    response = API.get(auth, '/servers/{}'.format(id))

    return response.json()['server']


def instances(auth, **params):
    params['all_tenants'] = 1
    response = API.get(auth, '/servers', params=params)

    return {s['id']: s for s in response.json()['servers']}


def instances_details(auth, **params):
    params['all_tenants'] = 1
    response = API.get(auth, '/servers/detail', params=params)

    return {s['id']: s for s in response.json()['servers']}


def reset_state(auth, id, state='error'):
    if state not in RESET_STATES:
        raise ValueError('cannot reset state to \'{}\', not one of {}'.format(
            state, RESET_STATES))


def aggregates(auth):
    response = API.get(auth, '/os-aggregates')

    return {int(a['id']): a for a in response.json()['aggregates']}


def aggregate_details(auth, agg_id):
    response = API.get(auth, '/os-aggregates/{}'.format(agg_id))

    return response.json()['aggregate']


def aggregate_delete(auth, agg_id):
    if int(agg_id) == FREEPOOL_AGGREGATE_ID:
        raise RuntimeError(
            'nope. (this is the freepool aggregate...bad idea.)')

    response = API.delete(auth, '/os-aggregates/{}'.format(agg_id))

    return response


def _addremove_host(auth, mode, agg_id, host_id):
    if mode not in ['add_host', 'remove_host']:
        raise ValueError('invalid mode')

    response = API.post(auth, '/os-aggregates/{}/action'.format(agg_id),
                        json={mode: {'host': host_id}})

    return response.json()['aggregate']


def aggregate_add_host(auth, agg_id, host_id):
    return _addremove_host(auth, 'add_host', agg_id, host_id)


def aggregate_remove_host(auth, agg_id, host_id, verify=True):
    if verify:
        agg = aggregate_details(auth, agg_id)
        if host_id not in agg['hosts']:
            raise RuntimeError("host '{}' is not in aggregate '{}'".format(
                host_id, agg_id))
    return _addremove_host(auth, 'remove_host', agg_id, host_id)


def aggregate_move_host(auth, host_id, from_agg_id, to_agg_id):
    aggregate_remove_host(auth, from_agg_id, host_id)
    return aggregate_add_host(auth, to_agg_id, host_id)


def availabilityzones(auth):
    response = API.get(auth, '/os-availability-zone/detail')

    return response.json()['availabilityZoneInfo']


def availabilityzones(auth):
    response = API.get(auth, '/os-availability-zone/detail')

    return response.json()['availabilityZoneInfo']


__all__ = [
    'nova_hypervisors',
    'nova_instance',
    'nova_instances',
    'nova_instances_details',
    'nova_reset_state',
    'nova_aggregates',
    'nova_aggregate_details',
    'nova_aggregate_delete',
    'nova_aggregate_add_host',
    'nova_aggregate_remove_host',
    'nova_aggregate_move_host',
    'nova_availabilityzones',
]

nova_hypervisors = hypervisors
nova_instance = instance
nova_instances = instances
nova_instances_details = instances_details
nova_reset_state = reset_state
nova_aggregates = aggregates
nova_aggregate_details = aggregate_details
nova_aggregate_delete = aggregate_delete
nova_aggregate_add_host = aggregate_add_host
nova_aggregate_remove_host = aggregate_remove_host
nova_aggregate_move_host = aggregate_remove_host
nova_availabilityzones = availabilityzones
