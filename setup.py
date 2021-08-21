#! /usr/bin/env python3
# Copyright (C) 2020 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later

from setuptools import find_packages, setup

from git_delete_merged_branches._metadata import APP, DESCRIPTION, VERSION

_tests_require = [
    'parameterized',
]

_extras_require = {
    'tests': _tests_require,
}

setup(
    name=APP,
    version=VERSION,

    license='GPLv3+',
    description=DESCRIPTION,
    long_description=open('README.md', encoding='utf-8').read(),
    long_description_content_type='text/markdown',

    author='Sebastian Pipping',
    author_email='sebastian@pipping.org',
    url=f'https://github.com/hartwork/{APP}',

    python_requires='>=3.7',
    setup_requires=[
        'setuptools>=38.6.0',  # for long_description_content_type
    ],
    install_requires=[
        'colorama>=0.4.3',
        'prompt-toolkit>=3.0.18',
    ],
    extras_require=_extras_require,
    tests_require=_tests_require,

    packages=find_packages(),

    entry_points={
        'console_scripts': [
            f'{APP} = git_delete_merged_branches.__main__:main',
            'git-dmb = git_delete_merged_branches.__main__:main',
        ],
    },

    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
        'Intended Audience :: Developers',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Topic :: Software Development :: Version Control',
        'Topic :: Software Development :: Version Control :: Git',
    ],
)
