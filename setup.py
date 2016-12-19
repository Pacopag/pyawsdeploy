# -*- coding: utf-8 -*-
from distutils.core import setup
from setuptools import find_packages

setup(
    name='pyawsdeploy',
    version='0.1.0',
    author=u'Chris Pagnutti',
    author_email='chris.pagnutti@gmail.com',
    packages=find_packages(),
    url='https://bitbucket.org/Pacopag/pyawsdeploy',
    license='MIT',
    description='Easily setup scalable deployments on aws, without docker and all that.',
    long_description='Easily setup scalable deployments on aws, without docker and all that.',
    zip_safe=False,
)