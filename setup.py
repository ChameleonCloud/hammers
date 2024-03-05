#!/usr/bin/env python
import sys
import setuptools
from setuptools import setup, find_packages

import hammers

setup(
    name='hammers',
    version=hammers.__version__,
    description='Bag of hammers to fix problems',
    packages=find_packages(),

    author='Nick Timkovich',
    author_email='npt@uchicago.edu',
    url='https://github.com/ChameleonCloud/hammers',

    long_description=open('README.rst', 'r').read(),
    keywords=[
        'chameleon-cloud', 'chameleon', 'openstack',
    ],

    entry_points={
        'console_scripts': [
            'conflict-macs = hammers.scripts.conflict_macs:main',
            'curiouser = hammers.scripts.curiouser:main',
            'dirty-ports = hammers.scripts.dirty_ports:main',
            'lease-stack-notifier = hammers.scripts.lease_stack_notifier:main',
            'maintenance-reservation = hammers.scripts.maintenance_reservation:main',
            'metadata-sync = hammers.scripts.metadata_sync:main',
            'neutron-reaper = hammers.scripts.neutron_reaper:main',
            'ironic-error-resetter = hammers.scripts.ironic_error_resetter:main',
            'orphan-resource-providers = hammers.scripts.orphan_resource_providers:main',
            'undead-instances = hammers.scripts.undead_instances:main',
            'reservation-usage-notification = hammers.scripts.reservation_usage_notification:main',
            'orphans-detector = hammers.scripts.orphans_detector:main',
            'clean-old-aggregates = hammers.scripts.clean_old_aggregates:main',
            'floatingip-reaper = hammers.scripts.floatingip_reaper:main',
            'unutilized-lease-reaper = hammers.scripts.unutilized_lease_reaper:main',
            'node-doctor = hammers.scripts.node_doctor:main',
            'retirement-enforcer = hammers.scripts.enforce_retirement:main',
            'k8s-calico-ip-cleanup = hammers.scripts.k8s_calico_ip_cleanup:main'
        ],
    },

    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: OpenStack',
        'Intended Audience :: System Administrators',
        'Topic :: Utilities',
    ],

    install_requires=[
        'python-dateutil',
        'requests',
        # 'mysqlclient>=1.3.6', # assume this is installed; could also be mysql-python
    ],
)
