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
import logging
import urllib
import yaml


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class Jenkins(object):
    '''Provides a connector to the jenkins api'''

    def __init__(self):
        '''Import settings'''
        with open('/etc/gitlabjenkins/settings.yaml') as _file:
            settings = yaml.load(_file)
        self.jenkins_server = settings.get('jenkins_server',
                                           '').rstrip('/')
        if not self.jenkins_server:
            raise Exception('jenkins_server not defined in '
                            '/etc/gitlabjenkins/settings.yaml')

    def get_job_name(self, data):
        '''Get job name from data dict'''
        group = data['repository']['url'].split(':')[1].split('/')[0]
        project = data['repository']['url'].split(':')[1].split(
            '/')[1].split('.')[0]
        branch = data['ref'].split('/')[-1]
        name = '{%s}-%s' % (group, project)
        if branch and branch != 'master':
            name = name + '-{%s}' % branch
        return name

    @tornado.gen.coroutine
    def fetch(self, url):
        '''Fetch a page asynchronously'''
        http_client = tornado.httpclient.AsyncHTTPClient()
        try:
            response = yield http_client.fetch(url)
            raise tornado.gen.Return(response)
        except tornado.httpclient.HTTPError as e:
            logger.error('Error: ' + str(e) + ' on ' + urllib.unquote(url))
            raise tornado.gen.Return(None)

    @tornado.gen.coroutine
    def authorized_post(self, url, data):
        '''Send POST with added jenkins authentication parameters'''
        http_client = tornado.httpclient.AsyncHTTPClient()
        request = tornado.httpclient.HTTPRequest(
            url,
            method='POST',
            body=data,
            headers={'content-type': 'text/xml'}
        )
        try:
            logger.debug('Posting to ' + urllib.unquote(url))
            response = yield http_client.fetch(request)
            logger.debug('Post to ' + urllib.unquote(url) + ' completed.')
            raise tornado.gen.Return(response)
        except tornado.httpclient.HTTPError as e:
            logger.error('Error doing authorized post: ' + str(e))
            return

    @tornado.gen.coroutine
    def fetch_config_xml(self, job_name):
        '''Get jenkins config.xml file for a job'''
        url = '{}/job/{}/config.xml'.format(self.jenkins_server,
                                            urllib.quote(job_name))
        response = yield self.fetch(url)
        if response is None:
            raise tornado.gen.Return(None)
        config_xml = response.body
        raise tornado.gen.Return(config_xml)

    def process_config_xml(self, gitlab, data, config_xml):
        '''Replace jenkins.xml variables with data from GitLab'''
        job_name = self.get_job_name(data)
        user = gitlab.User(id=data['user_id'])
        repo = data['repository']['url'].replace(':', '/').replace(
            'git@', 'http://')
        ref, branch = data['ref'].split('/')[1:3]
        vars = {
            'USER_EMAIL': user.email,
            'GIT_REPOSITORY': repo,
            'GIT_BRANCH': branch,
            'GIT_URL': data['repository']['homepage'],
            'PROJECT_NAME': job_name
        }
        for k, v in vars.iteritems():
            config_xml = config_xml.replace(k, v)
        return (job_name, config_xml)

    @tornado.gen.coroutine
    def trigger_build(self, job_name):
        '''Trigger a jenkins build for the job associated with a repo'''
        url = '{}/job/{}/build'.format(self.jenkins_server,
                                       urllib.quote(job_name))
        logger.info('Triggering a build of %s', job_name)
        yield self.authorized_post(url, '')
        return

    @tornado.gen.coroutine
    def create_job(self, job_name, config_xml):
        '''Create a jenkins build job for a repo'''
        url = '{}/createItem?name={}'.format(self.jenkins_server,
                                             urllib.quote(job_name))
        yield self.authorized_post(url, config_xml)
        return

    @tornado.gen.coroutine
    def delete_job(self, job_name):
        '''Delete a jenkins build job for a repo'''
        url = '{}/job/{}/doDelete'.format(self.jenkins_server,
                                          urllib.quote(job_name))
        logger.info('Deleting Job ' + urllib.unquote(url))
        yield self.authorized_post(url, '')
        return

    @tornado.gen.coroutine
    def update_job(self, job_name, config_xml):
        '''Update settings for a jenkins build job for a repo'''
        url = '{}/job/{}/config.xml'.format(self.jenkins_server,
                                            urllib.quote(job_name))
        yield self.authorized_post(url, config_xml)
        return

    @tornado.gen.coroutine
    def create_or_update_job(self, job_name, config_xml):
        '''Update a jenkins job for a repo or build one if none exists'''
        current_config = yield self.fetch_config_xml(job_name)
        if current_config is None:
            logger.info('Creating ' + job_name)
            yield self.create_job(job_name, config_xml)
        # there may be a whitespace problem with this
        if current_config != config_xml:
            logger.info('Updating ' + job_name)
            yield self.update_job(job_name, config_xml)
