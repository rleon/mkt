
# Copyright (c) 2013 python-gerrit Developers.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import paramiko
import json

class Client(object):

    def __init__(self, host, port=29418, user=None,
                 key=None, config="~/.ssh/config"):

        self.key = key
        self.host = host
        self.port = port
        self.user = user

        config = os.path.expanduser(config)
        if os.path.exists(config):
            ssh = paramiko.SSHConfig()
            ssh.parse(open(config))
            conf = ssh.lookup(host)

            self.host = conf['hostname']
            self.port = int(conf.get('port', self.port))
            self.user = conf.get('user', self.user)
            self.key = conf.get('identityfile', self.key)

    @property
    def client(self):
        if not hasattr(self, "_client"):
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self._client.load_system_host_keys()
            self._client.connect(self.host,
                                 port=self.port,
                                 username=self.user,
                                 key_filename=self.key)
        return self._client

class Items(list):
    key = None

    def add_flags(self, *flags):
        """Adds one or more flags to the query.

        For example:
            current-patch-set -> --current-patch-set
        """
        if not isinstance(flags, (list, tuple)):
            flags = [str(flags)]

        self.extend(["--%s" % f for f in flags])
        return self

    def add_items(self, key, value, not_key=False):

        if not isinstance(value, (list, tuple)):
            value = [str(value)]

        if not_key:
            self.extend(["NOT"])

        self.extend(["%s:%s" % (key, val) for val in value])
        return self

    def __repr__(self):
        subs_repr = [str(i) for i in self]

        base = '(%s)'
        key = self.key

        if not key:
            key, base = ' ', '%s'

        return base % key.join(subs_repr)


class OrFilter(Items):
    key = ' OR '


class AndFilter(Items):
    key = ' AND '

class Query(Client):

    def __init__(self, *args, **kwargs):
        super(Query, self).__init__(*args, **kwargs)
        self._filters = Items()

    def __iter__(self):
        return iter(self._execute())

    def _execute(self):
        """Executes the query and yields items."""

        query = [
            'gerrit', 'query',
            '--current-patch-set',
            str(self._filters),
            '--format=JSON']

        results = self.client.exec_command(' '.join(query))
        stdin, stdout, stderr = results

        for line in stdout:
            normalized = json.loads(line)

            # Do not return the last item
            # since it is the summary of
            # of the query
            if "rowCount" in normalized:
                return

            yield normalized

    def filter(self, *filters):
        """Adds generic filters to use in the query

        For example:

            - is:open
            - is:
        :param filters: List or tuple of projects
        to add to the filters.
        """
        self._filters.extend(filters)
        return self


class Review(Client):
    """Single review instance.

    This can be used to approve, block or modify
    a review.

    :params review: The commit sha or review,patch-set
    to review.
    """
    def __init__(self, review, *args, **kwargs):
        super(Review, self).__init__(*args, **kwargs)
        self._review = review
        self._status = None
        self._verified = None
        self._code_review = None

    def verify(self, value):
        """The verification score for this review."""
        self._verified = value

    def review(self, value):
        """The score for this review."""
        self._code_review = value

    def status(self, value):
        """Sets the status of this review

        Available options are:
            - restore
            - abandon
            - workinprogress
            - readyforreview
        """
        self._status = value

    def commit(self, message=None):
        """Executes the command

        :params message: The message
        to use as a comment for this
        action.
        """

        flags = Items()

        if self._status:
            flags.add_flags(self._status)

        if self._code_review is not None:
            flags.add_flags("code-review %s" % self._code_review)

        if self._verified is not None:
            flags.add_flags("verified %s" % self._verified)

        if message:
            flags.add_flags("message '%s'" % message)

        query = ['gerrit', 'review', str(flags), str(self._review)]

        results = self.client.exec_command(' '.join(query))
        stdin, stdout, stderr = results

        # NOTE(flaper87): Log error messages
        error = []
        for line in stderr:
            error.append(line)

        # True if success
        return not error
    def manage_reviewers(self, email, remove=False):
        if remove:
            cmd = '-r'
        else:
            cmd = '-a'
        set_cmd = ['gerrit', 'set-reviewers', cmd, email, self._review['id']]
        self.client.exec_command(' '.join(set_cmd))
