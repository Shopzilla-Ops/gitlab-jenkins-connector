#!/usr/bin/env python

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

import tornado.gen
import tornado.httpclient
from gitlabjenkins import BaseHandler
from gitlabjenkins import GitLab
import gitlab
import logging
import yaml
import sys


class WebHookHandler(BaseHandler):

    @tornado.gen.coroutine
    def post(self):
        data = self.parse_body()
        if data['after'] == '0000000000000000000000000000000000000000':
            job_name = self.jenkins.get_job_name(data)
            yield self.jenkins.delete_job(job_name)
            return
        tree = data['repository']['homepage'] + '/raw/' + data['after'] + '/'
        triggers = ['jenkins.xml']
        for filename in triggers:
            try:
                response = yield self.httpclient.fetch(tree + filename)
                break  # Go to else clause
            except tornado.httpclient.HTTPError as e:
                if str(e) != 'HTTP 404: Not Found':
                    logger.error('Error: ' + str(e))
                continue
        else:
            logger.info('No trigger files found')
            return
        if filename == 'jenkins.xml':
            raw_config_xml = response.body
        (job_name, config_xml) = self.jenkins.process_config_xml(
            self.gl, data, raw_config_xml)
        yield self.jenkins.create_or_update_job(job_name, config_xml)
        yield self.jenkins.trigger_build(job_name)


class SystemHookHandler(BaseHandler):
    def _dispatch(self, m):
        self.body = self.parse_body()
        func = getattr(self, self.body.get('event_name'), None)
        if func:
            return func()
        else:
            logger.error('Undefined event ' + self.body.get('event_name'))
            raise tornado.web.HTTPError(404)

    # other seen events: user_add_to_team, user_remove_from_team
    def project_create(self):
        project_id = self.body.get('project_id')
        self.gl.register_webhook(project_id)

    def user_remove_from_team(self):
        pass

    def user_add_to_team(self):
        pass

    def project_destroy(self):
        pass


if __name__ == '__main__':
    logger = logging.getLogger()
    with open('/etc/gitlabjenkins/settings.yaml') as _file:
        settings = yaml.load(_file)
    log_file = settings.get('log_file')
    log_max_bytes = settings.get('log_max_bytes')
    log_max_files = settings.get('log_max_files')
    if not all([log_file, log_max_bytes, log_max_files]):
        raise Exception('log_file, log_max_bytes, or log_max_files not '
                        'defined in /etc/gitlabjenkins/settings.yaml')
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s')
    logfh = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=log_max_bytes,
        backupCount=log_max_files
    )
    logfh.setFormatter(formatter)
    logger = logging.getLogger('')
    logger.setLevel(logging.INFO)
    logger.addHandler(logfh)
    logging.getLogger('requests').setLevel(logging.ERROR)
    logger.info('Starting gitlabjenkins service')
    gitlab_server = settings.get('gitlab_server', '').rstrip('/')
    gitlab_private_token = settings.get('gitlab_private_token')
    gitlabjenkins_port = settings.get('gitlabjenkins_server_port')
    if not gitlab_server or not gitlab_private_token or not gitlabjenkins_port:
        raise Exception('gitlab_server, gitlab_private_token, '
                        'or gitlabjenkins_port not defined in '
                        '/etc/gitlabjenkins/settings.yaml')
    gl = GitLab(gitlab_server, gitlab_private_token)
    try:
        gl.auth()
    except gitlab.GitlabAuthenticationError:
        logger.error('Invalid authentication token')
        sys.exit(1)
    gl.register_server()
    gl.register_webhook()
    application = tornado.web.Application([
        (r'/webhook', WebHookHandler),
        (r'/systemhook', SystemHookHandler),
    ])
    application.listen(gitlabjenkins_port)
    tornado.ioloop.IOLoop.instance().start()
