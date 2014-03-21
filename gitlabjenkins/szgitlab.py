# * Copyright 2012 Shopzilla.com
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

import gitlab
import logging
import yaml


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class GitLab(gitlab.Gitlab):
    '''Provides a connector to the gitlab api'''

    def __init__(self, server, token):
        '''Import settings'''
        super(GitLab, self).__init__(server, token)
        with open('/etc/gitlabjenkins/settings.yaml') as _file:
            settings = yaml.load(_file)
        self.gitlabjenkins_server = settings.get('gitlabjenkins_server_url',
                                                 '').rstrip('/')
        self.gitlabjenkins_port = settings.get('gitlabjenkins_server_port')
        if not self.gitlabjenkins_server or not self.gitlabjenkins_port:
            raise Exception('gitlabjenkins_server or gitlabjenkins_port not '
                            'defined in /etc/gitlabjenkins/settings.yaml')

    def register_server(self):
        '''Sets up a gitlab system hook to contact this service'''
        logger.info("Validating system hook configuration")
        server_hook = '{}:{}/systemhook'.format(self.gitlabjenkins_server,
                                                self.gitlabjenkins_port)
        configured_hooks = [h.url for h in self.Hook()]
        if server_hook not in configured_hooks:
            logger.info("System hook was not configured, adding")
            system_hook = self.Hook({"url": server_hook})
            system_hook.save()
        logger.info("Done")
        return

    def register_webhook(self, project_id=None, page_limit=1000):
        '''Sets up a gitlab web hooks to this service on new repo creation'''
        projects = []
        webhook = '{}:{}/webhook'.format(self.gitlabjenkins_server,
                                         self.gitlabjenkins_port)
        if project_id is None:
            logger.info("Registering Webhook on existing repositories")
            for page_num in range(1, page_limit):
                some_projects = self.Project(page=page_num, per_page=100)
                if not some_projects:
                    break
                projects.extend(some_projects)
        else:
            try:
                p = self.Project(id=project_id)
            except gitlab.GitlabGetError:
                logger.error("Invalid project id (%d)" % project_id)
                return
            projects.append(p)
        for project in projects:
            logger.info("Ensuring webhook on " + project.name)
            configured_webhooks = [h.url for h in project.Hook()]
            if webhook not in configured_webhooks:
                logger.info("Adding webhook to " + project.name)
                hook = project.Hook({"url": webhook})
                hook.save()
        logger.info("Done")
