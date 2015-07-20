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
from mako import exceptions

import ConfigParser
import urlparse
import os.path
import magic
import lxml.etree as ET
from magic import *
from base64 import b64encode
from copy import *

import ostree
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

mimeTypeMagic = magic.open(magic.MAGIC_MIME_TYPE)
mimeTypeMagic.load()

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

        self.runtime = None
        self.ref = None
        self.action = None
        self.rev = None
        self.path = None

class AppMetadata:
    def __init__(self, ref, withAppdata = True):
        self.ref = ref
        self.name = None
        self.genericName = None
        self.description = None
        self.categories = []
        self.iconName = None
        self.iconData = None
        self.iconType = None
        self.help = None
        self.images = []
        self.homepage = None
        self.runtime = None
        self.sdk = None

        self._repo = ostree.Repo(config.get('General', 'repo'))

        self._populateFromMetadata()
        self._populateFromDesktopFile()
        if withAppdata:
            self._populateFromAppdata()

    def _populateFromMetadata(self):
        metadata = stringToConfig(self._repo.cat(self.ref, '/metadata').decode('utf8'))
        self.runtime = metadata.get('Application', 'runtime')
        self.sdk = metadata.get('Application', 'sdk')

    def _populateFromDesktopFile(self):
        files = self._repo.ls(self.ref, '/export/share/applications/%s.desktop' % self.ref.name)
        if not files:
            self.name = self.ref
            return

        desktop = stringToConfig(self._repo.cat(self.ref, files[0].filePath).decode('utf8'), os.path.basename(files[0].filePath))

        self.name = desktop.get('Desktop Entry', 'Name')
        self.genericName = desktop.get('Desktop Entry', 'GenericName')
        self.categories = filter(None, desktop.get('Desktop Entry', 'categories').split(';'))
        self.iconName = desktop.get('Desktop Entry', 'Icon')
        self._loadIcon()

    def _loadIcon(self):
        icons = self._repo.ls(self.ref, '/export/share/icons', recursive = True)
        iconsSizes = {}
        iconName = None
        for icon in icons:
            if icon.type == ostree.FileEntry.File:
                path = icon.filePath.split('/')
                sizestr = path[len(path) - 3]
                if sizestr == 'scalable':
                    iconName = icon.filePath
                    break
                else:
                    size = int(sizestr.split('x')[0])
                    iconsSizes[size] = icon.filePath

        if not iconName and iconsSizes:
            iconName = iconsSizes[sorted(iconsSizes)[-1]]

        if iconName:
            rawIcon = self._repo.cat(self.ref, iconName)
            self.iconType = mimeTypeMagic.buffer(rawIcon)
            if self.iconType == 'application/x-gzip':
                # TODO: Cache those icons
                rawIcon = ungzipIcon(rawIcon)
                if rawIcon:
                    self.iconType = mimeTypeMagic.buffer(rawIcon)

            if rawIcon:
                self.iconData = b64encode(rawIcon)

    def _populateFromAppdata(self):
        ls = self._repo.ls(self.ref, '/files/share/appdata')
        appdataFile = None
        for l in ls:
            if l.type == ostree.FileEntry.File:
                if l.fileName.endswith('.appdata.xml'):
                    appdataFile = l.filePath
                    break

        if not appdataFile:
            return

        appdataXml = self._repo.cat(self.ref, appdataFile)
        root = ET.fromstring(appdataXml)

        find = ET.XPath('./name[lang("en")]', namespaces = { 'xml' : 'http://www.w3.org/XML/1998/namespace' })
        self.name = find(root)[0].text

        find = ET.XPath('./description')
        results = find(root)
        if results:
            desc = results[0]
            for d in desc.iter():
                if '{http://www.w3.org/XML/1998/namespace}lang' in d.keys():
                    d.getparent().remove(d)

            find = ET.XPath('.//*[1]')
            results = find(desc)
            if results and results[0].tag == 'p':
                results[0].set('class', 'lead')

            find = ET.XPath('./*')
            results = find(desc)
            self.description = ''
            for result in results:
                self.description += ET.tostring(result)

        find = ET.XPath('./url[@type="homepage"]')
        results = find(root)
        if results:
            self.homepage = results[0].text
        find = ET.XPath('./url[@type="help"]')
        results = find(root)
        if results:
            self.help = results[0].text

        find = ET.XPath("./screenshots/screenshot/image/text()")
        self.images = find(root)

class RuntimeMetadata:
    def __init__(self, ref):
        self.ref = ref
        self.name = ref.name.rsplit('.', 1)[0]

class App:
    def GET(self):
        query = urlparse.parse_qs(web.ctx.query[1:])

        self._repo = ostree.Repo(config.get('General', 'repo'))

        page = Page()

        if 'ref' in query:
            page.ref = ostree.Ref(query['ref'][0])
        if 'a' in query:
            page.action = query['a'][0]
        if 'rev' in query:
            page.rev = query['rev'][0]
        if 'path' in query:
            page.path = query['path'][0]

        if not page.ref and not page.runtime:
            return self.refs(page);
        else:
            if not page.action or page.action == 'summary':
                if page.ref.type == ostree.Ref.Runtime:
                    return self._runtimeSummary(page)
                else:
                    return self._appSummary(page)
            elif page.action == 'log':
                return self._log(page)
            elif page.action == 'browse':
                return self._browse(page)
            elif page.action == 'commit' and page.rev:
                return self._commit(page)
            elif page.action == 'blob' and page.rev and page.path:
                return self._blob(page)

        raise web.seeother('/')

    @staticmethod
    def _refMetadata(ref, withAppdata = False):
        return AppMetadata(ref, withAppdata) if ref.type == ostree.Ref.Application else RuntimeMetadata(ref)

    def refs(self, page):
        page.runtimes = []
        page.apps = []
        page.platformVersions = {}
        page.sdkVersions = {}

        for ref in self._repo.refs():
            if ref.type == ostree.Ref.Runtime:
                meta = RuntimeMetadata(ref)
                if ref.name.endswith('.Platform'):
                    page.runtimes.append(meta)
                    page.platformVersions[meta.name] = (page.platformVersions[meta.name] if meta.name in page.platformVersions else []) + [(ref.arch, ref.branch)]
                elif ref.name.endswith('.Sdk'):
                    page.sdkVersions[meta.name] = (page.sdkVersions[meta.name] if meta.name in page.sdkVersions else []) + [(ref.arch, ref.branch)]

            else:
                page.apps.append(AppMetadata(ref, withAppdata = False))

        try:
            return render.refs(page = page)
        except:
            return exceptions.text_error_template().render()

    def _appSummary(self, page):
        page.metadata = AppMetadata(page.ref)

        try:
            return render.summary(page = page)
        except:
            return exceptions.text_error_template().render()

    def _runtimeSummary(self, page):
        page.locales = {}
        page.versions = []
        page.var = {}

        if '.Platform' in page.ref.name:
            baseref = page.ref.name.split('.Platform')[0]
            refType = 'Platform'
        else:
            baseref = page.ref.name.split('.Sdk')[0]
            refType = 'Sdk'

        page.basePlatform = ostree.Ref('runtime/%s.Platform/%s/%s' % (baseref, page.ref.arch, page.ref.branch))
        page.baseSdk = ostree.Ref('runtime/%s.Sdk/%s/%s' % (baseref, page.ref.arch, page.ref.branch))

        refs = {}
        for ref in self._repo.refs():
            refs[ref.name] = ref

        for refName, ref in refs.iteritems():
            if ref.type == ostree.Ref.Application:
                continue

            if not refName.startswith(baseref):
                continue

            if not '%s/%s' % (ref.arch, ref.branch) in page.versions:
                page.versions.append('%s/%s' % (ref.arch, ref.branch))

            if refName.startswith(baseref + '.Platform.Locale') or refName.startswith(baseref + '.Sdk.Locale'):
                if '.Platform' in ref.name:
                    platform = ref
                    sdkRefName = platform.name.replace('.Platform', '.Sdk')
                    if sdkRefName in refs.keys():
                        sdk = refs[sdkRefName]
                    else:
                        sdk = None
                else:
                    sdk = ref
                    platformRefName = sdk.name.replace('.Sdk', '.Platform')
                    if platformRefName in refs.keys():
                        platform = refs[platformRefName]
                    else:
                        platform = None

                page.locales[ref.name.rsplit('.', 1)[-1]] = (platform, sdk)

        try:
            return render.summary(page = page)
        except:
            return exceptions.text_error_template().render()


    def _log(self, page):
        page.metadata = App._refMetadata(page.ref)
        page.log = self._repo.log(page.ref)

        try:
            return render.log(page = page)
        except:
            return exceptions.text_error_template().render()

    def _commit(self, page):
        page.metadata = App._refMetadata(page.ref)
        page.commit = self._repo.show(page.rev)
        page.parentRev = self._repo.revParse(page.rev + '^')
        page.diff = self._repo.diff(page.rev)

        try:
            return render.commit(page = page)
        except:
            return exceptions.text_error_template().render()

    def _browse(self, page):
        ''' If no rev is provided, use HEAD of current ref '''
        if not page.rev:
            page.rev = page.ref

        if not page.path:
            page.path = '/'

        page.metadata = App._refMetadata(page.ref)
        page.listing = self._repo.ls(page.rev, page.path)

        try:
            return render.browser(page = page)
        except:
            return exceptions.text_error_template().render()

    def _blob(self, page):
        page.metadata = App._refMetadata(page.ref)
        files = self._repo.ls(page.rev, page.path)
        if not files:
            page.error = "No such file or directory '%s'" % page.path
            return render.error(page = page)

        filedesc = files[0]
        if filedesc.type == ostree.FileEntry.Dir:
            raise web.seeother('?ref=' + str(page.ref) + '&a=browse&rev=' + page.rev + '&path=' + page.path)

        rawdata = self._repo.cat(page.rev, page.path)
        page.mimetype = mimeTypeMagic.buffer(rawdata)
        page.isText = page.mimetype.startswith('text/')
        page.isImage = page.mimetype.startswith('image/')
        page.size = len(rawdata)
        if page.isText:
            page.fileContents = rawdata.decode('utf8')
        elif page.isImage:
            page.fileContents = b64encode(rawdata)
        else:
            page.fileContents = None

        try:
            return render.blob(page = page)
        except:
            return exceptions.text_error_template().render()

if __name__ == "__main__":
    app.run()