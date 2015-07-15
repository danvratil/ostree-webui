#!/bin/env python
# -*- coding: utf-8 -*-

#
# Copyright (C) 2015  Daniel Vrátil <dvratil@redhat.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA
#

import web, web.template
from web.contrib.template import render_mako

import subprocess
import ConfigParser
import urlparse
import StringIO

from utils import *


web.config.debug = True

app = web.application(fvars = globals(), autoreload = True)
app.add_mapping('/', 'App')

defaultConfig = {
    'title': 'OSTree Browser',
    'logo': 'xyz',
}

config = ConfigParser.ConfigParser(defaults = defaultConfig, allow_no_value = True)
config.read('ostreebrowser.cfg')


t_globals = {
    'datestr': web.datestr,
}

render = render_mako(
        directories = ['templates'],
        input_encoding = 'utf-8',
        output_encoding = 'utf-8')

class Page:
    def __init__(self, dummy = None):
        self.title = config.get('General', 'title')
        self.logo = config.get('General', 'logo')
        self.breadcrumbs = []

        self.ref = None
        self.action = None
        self.rev = None
        self.path = None


class Breadcrumb:
    def __init__(self, url, title):
        self.url = url
        self.title = title


class App:
    def GET(self):
        query = urlparse.parse_qs(web.ctx.query[1:])

        page = Page()
        page.breadcrumbs.append(Breadcrumb('/', 'repo'))

        if 'ref' in query:
            page.ref = query['ref'][0]
        if 'a' in query:
            page.action = query['a'][0]
        if 'rev' in query:
            page.rev = query['rev'][0]
        if 'path' in query:
            page.path = query['path'][0]

        if not page.ref:
            return self._listRefs(page);
        else:
            page.breadcrumbs.append(Breadcrumb('?ref=%s' % page.ref, page.ref))

            if not page.action or page.action == 'summary':
                return self._refSummary(page)
            else:
                if page.action == 'log':
                    return self._refLog(page)
                elif page.action == 'browse':
                    return self._refBrowse(page)
                elif page.action == 'commit' and page.rev:
                    return self._refCommit(page)

        return self._listRefs(page)

    def _ostree(self, args):
        p = subprocess.Popen(['ostree'] + args + ['--repo=%s' % config.get('General', 'repo')],
                             stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        print("Executed: %s" % (['ostree'] + args + ['--repo=%s' % config.get('General', 'repo')]))
        out, err = p.communicate()
        return out.decode('UTF-8').strip(), err.decode('UTF-8').strip()

    def _listRefs(self, page):
        refs, err = self._ostree(['refs'])
        page.refs = refs.split('\n')
        page.refs.sort()

        return render.refs(page = page)

    def _refSummary(self, page):
        page.breadcrumbs.append(Breadcrumb(None, 'summary'))

        ''' Resolve HEAD rev for current ref'''
        page.rev, err = self._ostree(['rev-parse', page.ref])

        rawmetadata, err = self._ostree(['cat', page.rev, 'metadata'])
        rawlog, err = self._ostree(['log', page.ref])
        page.log = OSTreeLog(rawlog.split('\n'))

        metadatastring = StringIO.StringIO()
        metadatastring.write(rawmetadata)
        metadatastring.seek(0)

        page.metadata = ConfigParser.ConfigParser()
        page.metadata.readfp(metadatastring, 'metadata')

        return render.refSummary(page = page)

    def _refLog(self, page):
        page.breadcrumbs.append(Breadcrumb(None, 'log'))

        rawlog, err = self._ostree(['log', page.ref])
        page.log = OSTreeLog(rawlog.split('\n'))

        return render.refLog(page = page)

    def _refCommit(self, page):
        page.breadcrumbs.append(Breadcrumb(None, 'commit'))

        commit, err = self._ostree(['show', page.rev])
        page.commit = OSTreeLog(commit.split('\n')).next()
        page.parentRev, err = self._ostree(['rev-parse', page.rev + '^'])

        page.diff, err = self._ostree(['diff', page.rev])
        page.diff = page.diff.split('\n')

        return render.refCommit(page = page)

    def _refBrowse(self, page):
        page.breadcrumbs.append(Breadcrumb(None, 'tree'))

        ''' If no rev is provided, use HEAD of current ref '''
        if not page.rev:
            page.rev, err = self._ostree(['rev-parse', page.ref])

        if not page.path:
            page.path = '/'

        listing, err = self._ostree(['ls', page.rev, page.path])
        page.listing = OSTreeDirList(listing.split('\n'))

        return render.refBrowse(page = page)

if __name__ == "__main__":
    app.run()