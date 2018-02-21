"""
Keystone API shims. Requires v3 API. See `Keystone HTTP API
<https://developer.openstack.org/api-ref/identity/v3/>`_
"""

import requests


def project(auth, id):
    """Retrieve project by ID"""
    response = requests.get(
        url=auth.endpoint('identityv3') + '/projects/{}'.format(id),
        headers={'X-Auth-Token': auth.token},
    )
    response.raise_for_status()
    project = response.json()['project']
    return project


def projects(auth, **params):
    """
    Retrieve multiple projects, optionally filtered by `params`. Keyed by ID.

    Example params: ``name``, ``enabled``, or stuff from
    https://developer.openstack.org/api-ref/identity/v3/?expanded=list-projects-detail#list-projects
    """
    response = requests.get(
        url=auth.endpoint('identityv3') + '/projects'.format(id),
        headers={'X-Auth-Token': auth.token},
        params=params,
    )
    response.raise_for_status()
    projects = response.json()['projects']
    projects = {p['id']: p for p in projects}
    return projects


def project_lookup(auth, name_or_id):
    """Tries to find a single project by name or ID. Raises an error if
    none or multiple projects found."""
    try:
        return keystone_project(auth, name_or_id)
    except requests.HTTPError:
        pass # failed lookup assuming it was an id, must be a name?

    projects = keystone_projects(auth, name=name_or_id)
    if len(projects) < 1:
        raise RuntimeError('no projects found')
    elif len(projects) > 1:
        raise RuntimeError('multiple projects matched provided name')

    id, project = projects.popitem()
    return project


def user(auth, id):
    """Retrieves information about a user by ID"""
    response = requests.get(
        url=auth.endpoint('identityv3') + '/users/{}'.format(id),
        headers={'X-Auth-Token': auth.token},
    )
    response.raise_for_status()
    user = response.json()['user']
    return user


def users(auth, enabled=None, name=None):
    """Retrieves multiple users, optionally filtered."""
    params = {}
    if name is not None:
        params['name'] = name
    if enabled is not None:
        params['enabled'] = enabled

    response = requests.get(
        url=auth.endpoint('identityv3') + '/users',
        headers={'X-Auth-Token': auth.token},
        params=params,
    )
    response.raise_for_status()
    users = response.json()['users']
    users = {u['id']: u for u in users}
    return users


def user_lookup(auth, name_or_id):
    """Tries to find a single user by name or ID. Raises an error if none
    or multiple users are found."""
    try:
        return keystone_user(auth, name_or_id)
    except requests.HTTPError:
        pass # failed lookup assuming it was an id, must be a name?

    users = keystone_users(auth, name=name_or_id)
    if len(users) < 1:
        raise RuntimeError('no users found')
    elif len(users) > 1:
        raise RuntimeError('multiple users matched provided name')

    id, user = users.popitem()
    return user


__all__ = [
    'keystone_project',
    'keystone_projects',
    'keystone_project_lookup',
    'keystone_user',
    'keystone_users',
    'keystone_user_lookup',
]

keystone_project = project
keystone_projects = projects
keystone_project_lookup = project_lookup
keystone_user = user
keystone_users = users
keystone_user_lookup = user_lookup
