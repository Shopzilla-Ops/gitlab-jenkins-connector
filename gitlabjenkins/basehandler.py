# * Copyright 2014 Shopzilla.com
# *
# * Licensed under the Apache License, Version 2.0 (the "License");
# * you may not use this file except in compliance with the License.
# * You may obtain a copy of the License at
# *
# * http://www.apache.org/licenses/LICENSE-2.0
# *
# * Unless required by applicable law or agreed to in writing, software
# * distributed under the License is distributed on an "AS IS" BASIS,
# * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# * See the License for the specific language governing permissions and
# * limitations under the License.
# *
# * http://tech.shopzilla.com
# *

from szgitlab import GitLab
from jenkins import Jenkins
import json
import tornado.httpclient
import tornado.web
import yaml


class BaseHandler(tornado.web.RequestHandler):
    '''Request handler modified to abstract away gitlab web/service calls'''
    method_index = 2  # /handler/<method>

    def __init__(self, application, request, **kwargs):
        '''Setup gitlab and jenkins connectors'''
        super(BaseHandler, self).__init__(application, request, **kwargs)
        with open('/etc/gitlabjenkins/settings.yaml') as _file:
            settings = yaml.load(_file)
        gitlab_server = settings.get('gitlab_server', '').rstrip('/')
        gitlab_private_token = settings.get('gitlab_private_token')
        if not gitlab_server or not gitlab_private_token:
            raise Exception('gitlab_server or gitlab_private_token not '
                            'defined in /etc/gitlabjenkins/settings.yaml')
        self.gl = GitLab(gitlab_server, gitlab_private_token)
        self.httpclient = tornado.httpclient.AsyncHTTPClient()
        self.jenkins = Jenkins()

    def _dispatch(self, m):
        '''Route requests to methods based on http verb and hook uri'''
        if self.request.uri.endswith('/'):
            func = getattr(self, 'index', None)
            return func()
        path = self.request.uri.split('?')[0]
        try:
            method = path.split('/')[self.method_index].split(".")[0]
            if not method.startswith('_'):
                func = getattr(self, "_" + m + "_" + method, None)
                if func:
                    return func()
                else:
                    raise tornado.web.HTTPError(404)
            else:
                raise tornado.web.HTTPError(404)
        except:
            return self._index()

    def get(self):
        """Returns self._dispatch()"""
        return self._dispatch("get")

    def post(self):
        """Returns self._dispatch()"""
        return self._dispatch("post")

    def parse_body(self):
        try:
            r = json.loads(self.request.body)
        except:
            r = {}
        return r
