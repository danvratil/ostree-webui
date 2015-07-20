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

import subprocess
import os.path

from dateutil import parser
from stat import *

class ParseException(Exception):
    def __init__(self, message):
        pass

class Commit:
    def __init__(self, lines):
        self.rev = None
        self.date = None
        self.message = None

        if len(lines) < 4:
            raise ParseException('Unexpected commit format')

        self.rev = lines[0][7:]
        self.date = parser.parse(lines[1][7:])
        self.date = self.date.replace(tzinfo = None)
        self.message = '\n'.join(lines[3:])

class Diff:
    Added = 1
    Modified = 2
    Removed = 3

    def __init__(self, line):
        self.mode = 0
        self.filePath = None

        line = line.strip()
        if line.startswith('A'):
            self.mode = Diff.Added
        elif line.startswith('M'):
            self.mode = Diff.Modified
        elif line.startswith('R'):
            self.mode = Diff.Removed

        self.filePath = line.rsplit(' ', 1)[1]

class FileEntry:
    File = 1
    Dir = 2
    Symlink = 3

    def __init__(self, line):
        line = line.strip()
        lcols = line.split(' ', 3)
        rcols = line.rsplit(' ', 4)

        if len(lcols) < 3:
            raise ParseException('Unexpected file entry format')

        if lcols[0][0] == '-':
            self.type = FileEntry.File
        elif lcols[0][0] == 'd':
            self.type = FileEntry.Dir
        elif lcols[0][0] == 'l':
            self.type = FileEntry.Symlink
        else:
            self.type = None

        mode = int(lcols[0][1:], 8)
        self.mode = ''
        self.mode += 'r' if mode & S_IRUSR == S_IRUSR else '-'
        self.mode += 'w' if mode & S_IWUSR == S_IWUSR else '-'
        self.mode += 'x' if mode & S_IXUSR == S_IXUSR else '-'
        self.mode += 'r' if mode & S_IRGRP == S_IRGRP else '-'
        self.mode += 'w' if mode & S_IWGRP == S_IWGRP else '-'
        self.mode += 'x' if mode & S_IXGRP == S_IXGRP else '-'
        self.mode += 'r' if mode & S_IROTH == S_IROTH else '-'
        self.mode += 'w' if mode & S_IWOTH == S_IWOTH else '-'
        self.mode += 'x' if mode & S_IXOTH == S_IXOTH else '-'

        self.uid = int(lcols[1])
        self.gid = int(lcols[2])
        if self.type == FileEntry.Symlink:
            self.size = int(rcols[1])
            self.filePath = rcols[2]
            self.linkDest = os.path.abspath(os.path.join(os.path.dirname(self.filePath) + '/', rcols[4]))
        else:
            self.size = int(rcols[3])
            self.filePath = rcols[4]
            self.linkDest = None

        self.fileName = os.path.basename(self.filePath)

class Ref:
    Application = 1
    Runtime = 2

    def __init__(self, ref):
        parts = ref.split('/')
        if len(parts) < 4:
            raise ParseException('Unexpected ref format')

        self._typeStr = parts[0]
        if self._typeStr == 'app':
            self.type = Ref.Application
        elif self._typeStr == 'runtime':
            self.type = Ref.Runtime
        else:
            raise ParseException('Unexpected ref type')

        self.name = parts[1]
        self.arch = parts[2]
        self.branch = parts[3]

    def __repr__(self):
        return '/'.join([self._typeStr, self.name, self.arch, self.branch])

    def __str__(self):
        return self.__repr__()


class Repo:
    def __init__(self, repo):
        self._repo = repo

    def refs(self):
        rv = []
        for ref in self._cmd(['refs']).split('\n'):
            rv.append(Ref(ref))

        return rv

    def revParse(self, rev):
        return self._cmd(['rev-parse', str(rev)])

    def cat(self, rev, path):
        return self._cmd(['cat', str(rev), path], decode = False)

    def log(self, rev):
        log = self._cmd(['log', str(rev)])
        rv = []
        commit = []
        for line in log.split('\n'):
            if line.startswith('commit ') and commit:
                rv.append(Commit(commit))
                commit = []

            commit.append(line)
        return rv

    def show(self, rev):
        commit = self._cmd(['show', str(rev)])
        return Commit(commit.split('\n'))

    def diff(self, rev):
        diff = self._cmd(['diff', str(rev)])
        rv = []
        for line in diff.split('\n'):
            if line:
                rv.append(Diff(line))
        return rv

    def ls(self, rev, path, recursive = False):
        cmd = ['ls']
        if recursive:
            cmd += ['--recursive']
        cmd += [str(rev), path]
        ls = self._cmd(cmd)
        rv = []
        for line in ls.split('\n'):
            if line:
                rv.append(FileEntry(line))
        return rv

    def _cmd(self, args, decode = True):
        cmd = ['ostree'] + args + ['--repo=%s' % self._repo]
        print('Executing:', cmd)
        p = subprocess.Popen(cmd, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        out, _ = p.communicate()
        if decode:
            return out.decode('UTF-8').strip()
        else:
            return out
