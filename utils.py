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

import os.path

from dateutil import parser
from stat import *

class OSTreeLog:
    class Entry:
        def __init__(self, rev, date, msg, name, arch, branch):
            self.rev = rev
            self.date = date
            self.message = msg
            self.name = name
            self.arch = arch
            self.branch = branch


    def __init__(self, log):
        self._entries = []
        self._iter = 0

        commitMsg = ""
        rev = date = name = arch = branch = None
        for l in log:
            l = l.strip()
            if l.startswith('commit'):
                if rev:
                    self._entries.append(OSTreeLog.Entry(rev, date, commitMsg, name, arch, branch))
                    commitMsg = ""

                rev = l[7:]
            elif l.startswith('Date:'):
                date = parser.parse(l[7:])
                date = date.replace(tzinfo = None)
            elif l.startswith('Name:'):
                name = l[6:]
            elif l.startswith('Arch:'):
                arch = l[6:]
            elif l.startswith('Branch:'):
                branch = l[8:]
            elif (not commitMsg and l) or commitMsg:
                commitMsg += l + '\n'

        if rev:
            self._entries.append(OSTreeLog.Entry(rev, date, commitMsg, name, arch, branch))

    def next(self):
        if self._iter >= len(self._entries):
            raise StopIteration()
        else:
            self._iter += 1
            return self._entries[self._iter - 1]

    def __iter__(self):
        return self


class OSTreeDirList:
    class Entry:
        def __init__(self, type, mode, uid, gid, size, path):
            self.type = type
            self.mode = mode
            self.uid = uid
            self.gid = gid
            self.size = size
            self.path = path
            self.name = os.path.basename(path)

        def filemode(self):
            r = self.type

            r += 'r' if self.mode & S_IRUSR == S_IRUSR else '-'
            r += 'w' if self.mode & S_IWUSR == S_IWUSR else '-'
            r += 'x' if self.mode & S_IXUSR == S_IXUSR else '-'
            r += 'r' if self.mode & S_IRGRP == S_IRGRP else '-'
            r += 'w' if self.mode & S_IWGRP == S_IWGRP else '-'
            r += 'x' if self.mode & S_IXGRP == S_IXGRP else '-'
            r += 'r' if self.mode & S_IROTH == S_IROTH else '-'
            r += 'w' if self.mode & S_IWOTH == S_IWOTH else '-'
            r += 'x' if self.mode & S_IXOTH == S_IXOTH else '-'
            return r

        def isDir(self):
            return self.type == 'd'

    def __init__(self, lines):
        self._entries = []
        self._iter = 0

        for l in lines:
            l = l.strip()
            lcols = l.split(' ', 3)
            rcols = l.rsplit(' ', 2)

            if len(lcols) < 3:
                continue

            self._entries.append(OSTreeDirList.Entry(lcols[0][0], int(lcols[0][1:], 8),
                                                     lcols[1], lcols[2],
                                                     rcols[1], rcols[2]))

    def next(self):
        if self._iter >= len(self._entries):
            raise StopIteration()
        else:
            self._iter += 1
            return self._entries[self._iter - 1]

    def __iter__(self):
        return self