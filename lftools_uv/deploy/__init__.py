# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2017 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Library of functions for deploying artifacts to Nexus."""

from __future__ import annotations

# The standard library and third party modules below are not all used here.
# They are imported so that "lftools_uv.deploy.<module>" keeps resolving for
# callers and tests that reach through this module, as they could when these
# helpers were a single module.
import concurrent.futures
import datetime
import errno
import fnmatch
import glob
import gzip
import logging
import math
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, NoReturn

import boto3
import requests

# aislop-ignore-next-line hallucinated-import -- botocore ships with the declared boto3 dependency
from botocore.exceptions import ClientError
from defusedxml.minidom import parseString

from lftools_uv.deploy._common import (
    _BANNER_HASHES,
    _CONTENT_TYPE_TEXT,
    _CONTENT_TYPE_XML,
    _DEFAULT_URL_SCHEME,
    log,
)
from lftools_uv.deploy._http import _request_post, _request_post_file, _request_put_file
from lftools_uv.deploy._util import (
    _compress_text,
    _format_url,
    _get_filenames_in_zipfile,
    _get_node_from_xml,
    _log_error_and_exit,
    _remove_duplicates_and_sort,
)
from lftools_uv.deploy.archives import copy_archives, deploy_archives, deploy_logs
from lftools_uv.deploy.nexus import (
    deploy_nexus,
    deploy_nexus_stage,
    deploy_nexus_zip,
    nexus_stage_repo_close,
    nexus_stage_repo_create,
    upload_maven_file_to_nexus,
)
from lftools_uv.deploy.s3 import deploy_s3

# Everything the single deploy module used to expose, including the private
# helpers that lftools_uv.cli.deploy and the tests reach for by name.
__all__ = [
    "Any",
    "ClientError",
    "NoReturn",
    "Path",
    "_BANNER_HASHES",
    "_CONTENT_TYPE_TEXT",
    "_CONTENT_TYPE_XML",
    "_DEFAULT_URL_SCHEME",
    "_compress_text",
    "_format_url",
    "_get_filenames_in_zipfile",
    "_get_node_from_xml",
    "_log_error_and_exit",
    "_remove_duplicates_and_sort",
    "_request_post",
    "_request_post_file",
    "_request_put_file",
    "boto3",
    "concurrent",
    "copy_archives",
    "datetime",
    "deploy_archives",
    "deploy_logs",
    "deploy_nexus",
    "deploy_nexus_stage",
    "deploy_nexus_zip",
    "deploy_s3",
    "errno",
    "fnmatch",
    "glob",
    "gzip",
    "log",
    "logging",
    "math",
    "mimetypes",
    "nexus_stage_repo_close",
    "nexus_stage_repo_create",
    "os",
    "parseString",
    "re",
    "requests",
    "shutil",
    "subprocess",
    "sys",
    "tempfile",
    "upload_maven_file_to_nexus",
    "zipfile",
]
