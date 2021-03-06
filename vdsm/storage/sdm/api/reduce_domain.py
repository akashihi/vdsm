#
# Copyright 2016 Red Hat, Inc.
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
# along with this program if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA
#
# Refer to the README and COPYING files for full details of the license
#

from __future__ import absolute_import

from storage.sdc import sdCache
from vdsm import properties
from vdsm.storage import exception as se
from vdsm.storage.constants import STORAGE
from vdsm.storage import resourceManager as rm

from . import base


class Job(base.Job):
    """
    Reduces the device from the given domain devices.
    """

    def __init__(self, job_id, host_id, reduce_params):
        super(Job, self).__init__(job_id, 'reduce_domain', host_id)
        self.params = StorageDomainReduceParams(reduce_params)

    def _run(self):
        sd_manifest = sdCache.produce_manifest(self.params.sd_id)
        if not sd_manifest.supports_device_reduce():
            raise se.StorageDomainVersionError(
                "reduce device not supported for domain version %s" %
                sd_manifest.getVersion())

        # TODO: we assume at this point that the domain isn't active and can't
        # be activated - we need to ensure that.
        with rm.acquireResource(STORAGE, self.params.sd_id, rm.EXCLUSIVE):
            with sd_manifest.domain_id(self.host_id), \
                    sd_manifest.domain_lock(self.host_id):
                sd_manifest.reduceVG(self.params.guid)


class StorageDomainReduceParams(properties.Owner):
    sd_id = properties.UUID(required=True)
    guid = properties.String(required=True)

    def __init__(self, params):
        self.sd_id = params.get('sd_id')
        self.guid = params.get('guid')
