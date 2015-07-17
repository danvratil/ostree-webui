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

import ConfigParser
import urlparse
import os.path
import magic
import lxml.etree as ET
from magic import *
from base64 import b64encode

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
        self.breadcrumbs = []

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


class Breadcrumb:
    def __init__(self, url, title):
        self.url = url
        self.title = title

class App:
    def GET(self):
        query = urlparse.parse_qs(web.ctx.query[1:])

        self._repo = ostree.Repo(config.get('General', 'repo'))

        page = Page()
        page.breadcrumbs.append(Breadcrumb('/', 'repo'))

        if 'ref' in query:
            page.ref = ostree.Ref(query['ref'][0])
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

    def _listRefs(self, page):
        page.runtimes = []
        page.apps = []
        for ref in self._repo.refs():
            if ref.type == ostree.Ref.Runtime:
                page.runtimes.append(ref)
            else:
                page.apps.append(AppMetadata(ref, withAppdata = False))

        return render.refs(page = page)

    def _refSummary(self, page):
        page.breadcrumbs.append(Breadcrumb(None, 'summary'))
        page.metadata = AppMetadata(page.ref)

        return render.refSummary(page = page)

    def _refLog(self, page):
        page.breadcrumbs.append(Breadcrumb(None, 'log'))
        page.metadata = AppMetadata(page.ref, withAppdata = False)
        page.log = self._repo.log(page.ref)

        return render.refLog(page = page)

    def _refCommit(self, page):
        page.breadcrumbs.append(Breadcrumb(None, 'commit'))
        page.metadata = AppMetadata(page.ref, withAppdata = False)
        page.commit = self._repo.show(page.rev)
        page.parentRev = self._repo.revParse(page.rev + '^')
        page.diff = self._repo.diff(page.rev)

        return render.refCommit(page = page)

    def _refBrowse(self, page):
        page.breadcrumbs.append(Breadcrumb(None, 'tree'))

        ''' If no rev is provided, use HEAD of current ref '''
        if not page.rev:
            page.rev = page.ref

        if not page.path:
            page.path = '/'

        page.metadata = AppMetadata(page.ref, withAppdata = False)
        page.listing = self._repo.ls(page.rev, page.path)

        return render.refBrowse(page = page)



if __name__ == "__main__":
    app.run()