.. SPDX-FileCopyrightText: 2025 The Linux Foundation
..
.. SPDX-License-Identifier: EPL-1.0

*********
openstack
*********

Requires a `pip install lftools-uv[openstack]` to activate this command.
Requires `qemu-img` binary to upload images

.. program-output:: lftools-uv openstack --help

Commands
========



image
-----

.. program-output:: lftools-uv openstack --os-cloud docs image --help

cleanup
^^^^^^^

The intent of this command is to automatically cleanup old images in the cloud.
The OpenDaylight project has 2 clouds, a Private Cloud and a Public cloud which
needs the `--clouds` option to automatically remove the same images from
more than one cloud simultaneously.

.. program-output:: lftools-uv openstack --os-cloud docs image cleanup --help

list
^^^^

.. program-output:: lftools-uv openstack --os-cloud docs image list --help

cluster
-------

Command for managing Container Orchestration Engine (COE) clusters.

.. program-output:: lftools-uv openstack --os-cloud docs cluster --help

cleanup
^^^^^^^

Remove orphaned COE clusters from the cloud. This command scans for
Kubernetes clusters not in use by active Jenkins builds and removes them.
The cleanup operation preserves managed clusters (names containing
-managed-prod-k8s- or -managed-test-k8s-) as these are long-lived
infrastructure.

The command queries Jenkins URLs for active builds to prevent deletion of
clusters in use. Provide one or more Jenkins URLs separated by
spaces.

.. program-output:: lftools-uv openstack --os-cloud docs cluster cleanup --help

Example usage:

.. code-block:: bash

   # Cleanup orphaned clusters, checking two Jenkins instances
   lftools-uv openstack --os-cloud mycloud cluster cleanup \
     --jenkins "https://jenkins.example.org https://jenkins.example.io"

list
^^^^

List all COE clusters on the specified cloud with their current status.

.. program-output:: lftools-uv openstack --os-cloud docs cluster list --help

remove
^^^^^^

Remove a single COE cluster by name or UUID. The optional ``--minutes``
filter skips clusters that are not older than the specified number of
minutes; the default of 0 removes the cluster without an age limit.
Missing clusters and failed deletions exit non-zero.

.. program-output:: lftools-uv openstack --os-cloud docs cluster remove --help

show
^^^^

Show details of a single COE cluster by name or UUID. Missing clusters
exit non-zero.

.. program-output:: lftools-uv openstack --os-cloud docs cluster show --help

object
------

Command for managing objects.

.. program-output:: lftools-uv openstack --os-cloud docs object --help

list-containers
^^^^^^^^^^^^^^^

.. program-output:: lftools-uv openstack --os-cloud docs object list-containers --help

stack
-----

Command for managing stacks.

.. program-output:: lftools-uv openstack --os-cloud docs stack --help

create
^^^^^^

Create a new stack.

.. program-output:: lftools-uv openstack --os-cloud docs stack create --help

The create command requires a parameters file in the following format to
build out the stack:

.. code-block: yaml
   :caption: parameter_file

   parameters:
     job_name: JOB_NAME
     silo: SILO
     vm_0_count: 1
     vm_0_flavor: odl-highcpu-4
     vm_0_image: ZZCI - CentOS 7 - builder - 20180802-220823.782
     vm_1_count: 1
     vm_1_flavor: odl-standard-4
     vm_1_image: ZZCI - CentOS 7 - devstack-pike - 20171208-1649


delete
^^^^^^

Delete existing stack.

.. program-output:: lftools-uv openstack --os-cloud docs stack delete --help


cost
^^^^

Get total cost of existing stack.

.. program-output:: lftools-uv openstack --os-cloud docs stack cost --help

Return sum of costs for each member of the running stack.
