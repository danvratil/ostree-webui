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
import subprocess
import ConfigParser
import urlparse
import StringIO

from utils import *

web.config.debug = True

app = web.application(fvars = globals())
app.add_mapping('/', 'App')

config = ConfigParser.ConfigParser()
config.read('ostreebrowser.cfg')


t_globals = {
    'datestr': web.datestr,
}
render = web.template.render('templates', base='base', globals = t_globals)


class App:
    def GET(self):
        query = urlparse.parse_qs(web.ctx.query[1:])
        if not 'ref' in query:
            return self._listRefs();
        else:
            if not 'a' in query:
                return self._refSummary(query['ref'][0])
            else:
                if query['a'][0] == 'log':
                    return self._refLog(query['ref'][0])
                elif query['a'][0] == 'browse':
                    return self._refBrowse(query['ref'][0],
                                           query['path'][0] if 'path' in query else None,
                                           query['rev'][0] if 'rev' in query else None)
                elif query['a'][0] == 'commit' and 'rev' in query:
                    return self._refCommit(query['ref'][0], query['rev'][0])

        return self._listRefs()

    def _ostree(self, args):
        p = subprocess.Popen(['ostree'] + args + ['--repo=%s' % config.get('General', 'repo')],
                             stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        print("Executed: %s" % (['ostree'] + args + ['--repo=%s' % config.get('General', 'repo')]))
        out, err = p.communicate()
        return out.decode('UTF-8'), err.decode('UTF-8')

    def _listRefs(self):
        refs, err = self._ostree(['refs'])
        refs = refs.split('\n')
        refs.sort()

        return render.refs(refs)

    def _refSummary(self, ref):
        rev, err = self._ostree(['rev-parse', ref])
        rev = rev.strip()

        rawmetadata, err = self._ostree(['cat', rev, 'metadata'])
        rawlog, err = self._ostree(['log', ref])

        metadatastring = StringIO.StringIO()
        metadatastring.write(rawmetadata)
        metadatastring.seek(0)

        metadata = ConfigParser.ConfigParser()
        metadata.readfp(metadatastring, 'metadata')

        return render.refSummary(ref, rev, metadata, OSTreeLog(rawlog.split('\n')))


    def _refCommit(self, ref, rev):
        commit, err = self._ostree(['show', rev])
        parentRev, err = self._ostree(['rev-parse', rev + '^'])
        parentRev = parentRev.strip()

        diff, err = self._ostree(['diff', rev])

        return render.refCommit(ref, rev, parentRev, OSTreeLog(commit.split('\n')).next(), diff.split('\n'))

    def _refBrowse(self, ref, path, rev = None):
        ''' If no rev is provided, use HEAD of current ref '''
        if not rev:
            rev, err = self._ostree(['rev-parse', ref])
            rev = rev.strip()

        if not path:
            path = '/'

        listing, err = self._ostree(['ls', rev, path])
        listing = listing.split('\n')

        return render.refBrowse(ref, rev, path, OSTreeDirList(listing))

if __name__ == "__main__":
    app.run()