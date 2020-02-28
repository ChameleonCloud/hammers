import requests


class BaseAPI:

    def __init__(self, service, extra_headers=None):

        self.service = service
        self.extra_headers = extra_headers

    def headers(self, token, content_type=None):
        headers = {'X-Auth-Token': token}

        if self.extra_headers:
            headers.update(self.extra_headers)
        if content_type:
            headers.update({'Content-Type': content_type})

        return headers

    def get(self, auth, path, params=None):
        response = requests.get(url=auth.endpoint(self.service) + path,
                                params=params,
                                headers=self.headers(auth.token))
        response.raise_for_status()
        return response

    def post(self, auth, path, json):
        response = requests.post(url=auth.endpoint(self.service) + path,
                                 headers=self.headers(auth.token), json=json)
        response.raise_for_status()
        return response

    def put(self, auth, path, json):
        response = requests.put(url=auth.endpoint(self.service) + path,
                                headers=self.headers(auth.token), json=json)
        response.raise_for_status()
        return response

    def delete(self, auth, path):
        response = requests.delete(url=auth.endpoint(self.service) + path,
                                   headers=self.headers(auth.token))
        response.raise_for_status()
        return response

    def patch(self, auth, path, content_type, json):
        response = requests.patch(url=auth.endpoint(self.service) + path,
                                  headers=self.headers(auth.token,
                                                       content_type),
                                  json=json)
        response.raise_for_status()
        return response
