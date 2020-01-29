from hammers.osrest.base import BaseAPI


API = BaseAPI('placement')


def resource_providers(auth):
    response = API.get(auth, '/resource_providers')

    return response.json()['resource_providers']


def resource_provider(auth, resource_provider_id, category,
                      resource_class=None):
    path = '/resource_providers/{}/{}'.format(resource_provider_id, category)

    if resource_class:
        path += '/' + resource_class

    response = API.get(auth, path)

    return response.json()
