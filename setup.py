#!/usr/bin/env python

from distutils.core import setup

setup(name='cli-pyutils',
      version='0.1',
      description='Collection of useful Python modules for CLI tools.',
      author='Ivano Bilenchi',
      author_email='ivanobilenchi@gmail.com',
      url='https://github.com/IvanoBilenchi/pyutils',
      packages=['pyutils', 'pyutils.io', 'pyutils.proc'],
      )
