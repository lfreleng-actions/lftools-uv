.. SPDX-FileCopyrightText: 2025 The Linux Foundation
..
.. SPDX-License-Identifier: EPL-1.0

############
Installation
############

.. note::

    lftools-uv requires Python 3.11 or later. Install it into a virtual
    environment, or with a tool that manages one for you such as ``uv``.
    Installing into the system Python can have serious negative side effects!


For Install
===========

lftools-uv is available on PyPI. Install it with ``uv pip install lftools-uv``
or ``pip install lftools-uv`` in your virtual environment. Optional features
such as LDAP and OpenStack support are extras, for example
``pip install "lftools-uv[ldap]"``.

The package installs the ``lftools-uv`` command. It does not install the
``lftools`` command from legacy lftools.


For Development
===============

Often during development you want to run tests and/or
try code out locally as you change it. To do this you
need the installation of lftools-uv to be your local git repo.
From a clone of the repository, run ``make install-dev``, which runs
``uv sync`` with the development, test, documentation, LDAP and OpenStack
extras.
