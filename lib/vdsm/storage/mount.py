#
# Copyright 2011-2017 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
#
# Refer to the README and COPYING files for full details of the license
#

from __future__ import absolute_import

import errno
import logging
import os
import re
import stat

from collections import namedtuple

from vdsm import commands
from vdsm import constants
from vdsm import supervdsm
from vdsm import udevadm
from vdsm import utils

from vdsm.common import cmdutils
from vdsm.config import config
from vdsm.storage import fileUtils

# Common vfs types

VFS_EXT3 = "ext3"

MountRecord = namedtuple("MountRecord", "fs_spec fs_file fs_vfstype "
                         "fs_mntops fs_freq fs_passno")

_PROC_MOUNTS_PATH = '/proc/mounts'
_SYS_DEV_BLOCK_PATH = '/sys/dev/block/'

_DELETED_SUFFIX = ' (deleted)'
_ESCAPED_SPACES = re.compile(r"\\[0-7]{3}")


def _parseFstabLine(line):
    (fs_spec, fs_file, fs_vfstype, fs_mntops,
     fs_freq, fs_passno) = line.split()[:6]
    fs_mntops = fs_mntops.split(",")
    fs_freq = int(fs_freq)
    fs_passno = int(fs_passno)

    # Using NFS4 the kernel shows the mount path with double slashes,
    # regarless of the original (normalized) mount path.
    fs_spec = fileUtils.normalize_path(_unescape_spaces(fs_spec))

    # We expect normalized fs_file from the kernel.
    fs_file = _unescape_spaces(fs_file)
    if fs_file.endswith(_DELETED_SUFFIX):
        fs_file = fs_file[:-len(_DELETED_SUFFIX)]

    return MountRecord(fs_spec, fs_file, fs_vfstype, fs_mntops,
                       fs_freq, fs_passno)


def _unescape_spaces(path):
    return _ESCAPED_SPACES.sub(lambda s: chr(int(s.group()[1:], 8)), path)


class MountError(RuntimeError):
    pass


def _resolveLoopDevice(path):
    """
    Loop devices appear as the loop device under /proc/mount instead of the
    backing file. As the mount command does the resolution so must we.
    """
    if not path.startswith("/"):
        return path

    try:
        st = os.stat(path)
    except:
        return path

    if not stat.S_ISBLK(st.st_mode):
        return path

    minor = os.minor(st.st_rdev)
    major = os.major(st.st_rdev)
    backing_file = os.path.join(_SYS_DEV_BLOCK_PATH,
                                '%d:%d' % (major, minor),
                                'loop',
                                'backing_file')

    try:
        with open(backing_file, "r") as f:
            # Remove trailing newline
            return f.read()[:-1]
    except IOError as e:
        if e.errno != errno.ENOENT:
            raise

    return path


def _iterKnownMounts():
    with open(_PROC_MOUNTS_PATH, "r") as f:
        for line in f:
            yield _parseFstabLine(line)


def _iterMountRecords():
    for rec in _iterKnownMounts():
        realSpec = _resolveLoopDevice(rec.fs_spec)
        if rec.fs_spec == realSpec:
            yield rec
            continue

        yield MountRecord(realSpec, rec.fs_file, rec.fs_vfstype,
                          rec.fs_mntops, rec.fs_freq, rec.fs_passno)


def iterMounts():
    for record in _iterMountRecords():
        yield Mount(record.fs_spec, record.fs_file)


def isMounted(target):
    """Checks if a target is mounted at least once"""
    try:
        getMountFromTarget(target)
        return True
    except OSError as ex:
        if ex.errno == errno.ENOENT:
            return False
        raise


def getMountFromTarget(target):
    """
    The given target should be normalized.
    """
    for rec in _iterMountRecords():
        if rec.fs_file == target:
            return Mount(rec.fs_spec, rec.fs_file)

    raise OSError(errno.ENOENT, 'Mount target %s not found' % target)


class Mount(object):

    log = logging.getLogger("storage.Mount")

    def __init__(self, fs_spec, fs_file):
        """
        The given fs_spec and fs_file should be normalized.
        """
        self.fs_spec = fs_spec
        self.fs_file = fs_file

    def __eq__(self, other):
        return (self.__class__ == other.__class__ and
                self.fs_spec == other.fs_spec and
                self.fs_file == other.fs_file)

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return hash((self.__class__, self.fs_spec, self.fs_file))

    def mount(self, mntOpts=None, vfstype=None, timeout=None, cgroup=None):
        mount = supervdsm.getProxy().mount if os.geteuid() != 0 else _mount
        self.log.info("mounting %s at %s", self.fs_spec, self.fs_file)
        with utils.stopwatch("%s mounted" % self.fs_file, log=self.log):
            mount(self.fs_spec, self.fs_file, mntOpts=mntOpts, vfstype=vfstype,
                  timeout=timeout, cgroup=cgroup)
        self._wait_for_events()

    def umount(self, force=False, lazy=False, freeloop=False, timeout=None):
        umount = supervdsm.getProxy().umount if os.geteuid() != 0 else _umount
        self.log.info("unmounting %s", self.fs_file)
        with utils.stopwatch("%s unmounted" % self.fs_file, log=self.log):
            umount(self.fs_file, force=force, lazy=lazy, freeloop=freeloop,
                   timeout=timeout)
        self._wait_for_events()

    def _wait_for_events(self):
        """
        This is an ugly hack to wait until the udev events generated when
        adding or removing a mount are processed.

        Note that we may wait for unrelated events, or wait too little if the
        system is overloaded.

        TODO: find a way to wait for the specific event.
        """
        with utils.stopwatch("Waiting for udev mount events", log=self.log):
            timeout = config.getint('irs', 'udev_settle_timeout')
            udevadm.settle(timeout)

    def isMounted(self):
        try:
            self.getRecord()
        except OSError:
            return False

        return True

    def getRecord(self):
        # We compare both specs as one of them may match, depending on the
        # system configuration (.e.g. on gfs2 we may match on the realpath).
        if os.path.islink(self.fs_spec):
            fs_specs = self.fs_spec, os.path.realpath(self.fs_spec)
        else:
            fs_specs = self.fs_spec, None

        for record in _iterMountRecords():
            if self.fs_file == record.fs_file and record.fs_spec in fs_specs:
                return record

        raise OSError(errno.ENOENT,
                      "Mount of `%s` at `%s` does not exist" %
                      (self.fs_spec, self.fs_file))

    def __repr__(self):
        return ("<%s fs_spec='%s' fs_file='%s'>" %
                (self.__class__.__name__, self.fs_spec, self.fs_file))


def _mount(fs_spec, fs_file, mntOpts=None, vfstype=None, timeout=None,
           cgroup=None):
    """
    Called from supervdsm for running the mount command as root.
    """
    cmd = [constants.EXT_MOUNT]

    if vfstype is not None:
        cmd.extend(("-t", vfstype))

    if mntOpts:
        cmd.extend(("-o", mntOpts))

    cmd.extend((fs_spec, fs_file))

    if cgroup:
        cmd = cmdutils.systemd_run(cmd, scope=True, slice=cgroup)

    _runcmd(cmd, timeout)


def _umount(fs_file, force=False, lazy=False, freeloop=False, timeout=None):
    """
    Called from supervdsm for running the umount command as root.
    """
    cmd = [constants.EXT_UMOUNT]
    if force:
        cmd.append("-f")

    if lazy:
        cmd.append("-l")

    if freeloop:
        cmd.append("-d")

    cmd.append(fs_file)

    _runcmd(cmd, timeout)


def _runcmd(cmd, timeout):
    p = commands.execCmd(cmd, sync=False)
    if not p.wait(timeout):
        p.kill()
        raise OSError(errno.ETIMEDOUT,
                      "%s operation timed out" % os.path.basename(cmd[0]))

    out, err = p.communicate()
    rc = p.returncode

    if rc == 0:
        return

    raise MountError(rc, ";".join((out, err)))
