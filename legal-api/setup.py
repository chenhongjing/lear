# Copyright © 2019 Province of British Columbia.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Installer and setup for this module
"""
import ast
from glob import glob
from os.path import basename, splitext
import re

from setuptools import setup, find_packages

_version_re = re.compile(r'__version__\s+=\s+(.*)')  # pylint: disable=invalid-name

with open('src/legal_api/version.py', 'rb') as f:
    version = str(ast.literal_eval(_version_re.search(  # pylint: disable=invalid-name
        f.read().decode('utf-8')).group(1)))


def read_requirements(filename):
    """
    Get application requirements from
    the requirements.txt file.
    :return: Python requirements
    """
    with open(filename, 'r') as req:
        requirements = req.readlines()
    install_requires = [r.strip() for r in requirements if r.find('git+') != 0]
    return install_requires


def read(filepath):
    """
    Read the contents from a file.
    :param str filepath: path to the file to be read
    :return: file contents
    """
    with open(filepath, 'r') as file_handle:
        content = file_handle.read()
    return content


REQUIREMENTS = read_requirements('requirements.txt')

import os

report_templates = 'report-templates'

def get_data_files(directory):
    data_files = []
    for dirpath, dirnames, filenames in os.walk(directory):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            # Create the installation path by removing the base directory name
            install_path = os.path.relpath(dirpath, directory)
            data_files.append((os.path.join('legal_api', 'report-templates', install_path), [filepath]))
    return data_files


setup(
    name="legal_api",
    version=version,
    author_email='thor@wolpert.ca',
    packages=find_packages('src'),
    package_dir={'': 'src'},
    py_modules=[splitext(basename(path))[0] for path in glob('src/*.py')],
    include_package_data=True,
    data_files=get_data_files(report_templates) if os.path.exists(report_templates) else [],
    extras_require={
        'templates': [],
    },
    license=read('LICENSE'),
    long_description=read('README.md'),
    zip_safe=False,
    install_requires=REQUIREMENTS,
    setup_requires=["pytest-runner", ],
    tests_require=["pytest", ]
)