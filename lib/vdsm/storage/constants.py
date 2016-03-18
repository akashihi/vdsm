#
# Copyright 2010-2016 Red Hat, Inc.
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
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA
#
# Refer to the README and COPYING files for full details of the license
#

from __future__ import absolute_import

STORAGE = "Storage"
SECTOR_SIZE = 512

FILE_VOLUME_PERMISSIONS = 0o660
LEASE_FILEEXT = ".lease"

# Temporary volume indicators
TEMP_VOL_FILEEXT = ".volatile"         # Added to FileVolume metadata filenames
TEMP_VOL_LVTAG = "OVIRT_VOL_VOLATILE"  # Tag applied to BlockVolume LVs

# StorageDomain Metadata keys
MDK_POOLS = "POOL_UUID"