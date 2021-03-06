#
# Copyright 2017 Red Hat, Inc.
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
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301  USA
#
# Refer to the README and COPYING files for full details of the license
#

import threading

from vdsm.common import response
from vdsm.virt import vmpowerdown

from testlib import recorded
from testlib import VdsmTestCase as TestCaseBase


class PowerDownTests(TestCaseBase):

    def setUp(self):
        self.dom = FakeDomain()
        self.event = threading.Event()

    def test_no_callbacks(self):
        vm = FakeVM(
            self.dom,
            FakeGuestAgent(responsive=False),
            acpiEnable='false'
        )
        obj = make_powerdown(vm, self.event)
        res = obj.start()
        self.assertTrue(response.is_error(res, 'exist'))

    def test_with_default_callbacks(self):
        vm = FakeVM(
            self.dom,
            FakeGuestAgent(responsive=True),
            acpiEnable='true'
        )
        obj = make_powerdown(vm, self.event)
        # no actual callback will be called now!
        res = obj.start()
        self.assertFalse(response.is_error(res))


def make_powerdown(vm, event):
    message = 'testing'
    delay = 1.0
    timeout = 1.0
    force = False
    return vmpowerdown.VmPowerDown(
        vm, delay, message, timeout, force, event
    )


class FakeVM(object):

    def __init__(self, dom, ga, acpiEnable='true'):
        self._dom = dom
        self.guestAgent = ga
        self.conf = {'acpiEnable': acpiEnable}

    @recorded
    def doDestroy(self):
        pass

    @recorded
    def acpiReboot(self):
        pass

    def acpi_enabled(self):
        return self.conf['acpiEnable'] == 'true'


class FakeGuestAgent(object):

    def __init__(self, responsive=True):
        self.responsive = responsive

    def isResponsive(self):
        return self.responsive

    @recorded
    def desktopShutdown(self, delay, message, reboot):
        pass


class FakeDomain(object):

    @recorded
    def reset(self, flags=0):
        pass
