# coding: utf-8
# pytest in hammers dir should invoke these tests

import unittest
from datetime import datetime, timedelta
import json

import os

from hammers.scripts.lease_stack_notifier import (
    calculate_overlap_percentage,
    Host, Lease,
    LeaseComplianceManager,
    project_lease_violation_body,
    DATETIME_NOW
)


today = DATETIME_NOW


class TestOverlapDuration(unittest.TestCase):
    def test_overlap(self):
        start_date = (today - timedelta(days=100)).strftime('%Y-%m-%d')
        end_date = (today + timedelta(days=6)).strftime('%Y-%m-%d')
        lease1 = Lease({
            'id': id,
            'start_date': start_date,
            'end_date': end_date,
            'status': 'active',
            'project_id': 'project1',
        })
        start_date = (
            today + timedelta(days=0)
        ).strftime('%Y-%m-%d')
        end_date = (today + timedelta(days=6)).strftime('%Y-%m-%d')
        lease2 = Lease({
            'id': id,
            'start_date': start_date,
            'end_date': end_date,
            'status': 'active',
            'project_id': 'project1',
        })
        self.assertAlmostEqual(calculate_overlap_percentage(lease1, lease2), 100)
        end_date = (today + timedelta(days=7)).strftime('%Y-%m-%d')
        lease2 = Lease({
            'id': id,
            'start_date': start_date,
            'end_date': end_date,
            'status': 'active',
            'project_id': 'project1',
        })
        lease1_overlap_percentage = calculate_overlap_percentage(lease1, lease2)
        self.assertTrue(lease1_overlap_percentage > 90)
        lease2_overlap_percentage = calculate_overlap_percentage(lease2, lease1)
        self.assertTrue(lease2_overlap_percentage < 90)


class TestHost(unittest.TestCase):
    def test_high_end_gpu(self):
        host = Host('host1', 'gpu_rtx_6000')
        self.assertTrue(host.is_high_end())

    def test_high_end_fpga(self):
        host = Host('host1', 'fpga')
        self.assertTrue(host.is_high_end())

    def test_high_end_storage(self):
        host = Host('host1', 'storage')
        self.assertTrue(host.is_high_end())

    def test_high_end_cascadelake(self):
        host = Host('host1', 'cascadelake_r')
        self.assertFalse(host.is_high_end())


class TestLease(unittest.TestCase):
    def test_date_parse(self):
        lease_details = {
            'id': id,
            'start_date': "2024-02-09T22:45:00.000000",
            'end_date': "2024-02-16T21:45:00.000000",
            'status': 'active',
            'project_id': 'project1',
        }
        lease = Lease(lease_details)
        self.assertEqual(lease.start.year, 2024)
        self.assertEqual(lease.start.day, 9)
        self.assertEqual(lease.start.month, 2)
        self.assertEqual(lease.end.year, 2024)
        self.assertEqual(lease.end.day, 16)
        self.assertEqual(lease.end.month, 2)


def create_lease(id, days_from_now_start, days_from_now_end,
                 project_id='project1', status='active'):
    start_date = (
        today + timedelta(days=days_from_now_start)
    ).strftime('%Y-%m-%d')
    end_date = (today + timedelta(days=days_from_now_end)).strftime('%Y-%m-%d')
    return {
        'id': id,
        'start_date': start_date,
        'end_date': end_date,
        'status': status,
        'project_id': project_id,
    }


class TestLeaseComplianceManager(unittest.TestCase):
    def setUp(self):
        self.hosts = [
            {'id': 'host1', 'node_type': 'compute_skylake'},
            {'id': 'host2', 'node_type': 'gpu_v100'},
            {'id': 'host3', 'node_type': 'gpu_v100'},
            {'id': 'host4', 'node_type': 'gpu_v100'},
            {'id': 'host5', 'node_type': 'gpu_v100'},
            {'id': 'host6', 'node_type': 'gpu_v100'},
            {'id': 'host7', 'node_type': 'compute_skylake'},
            {'id': 'host8', 'node_type': 'compute_cascadelake'},
            {'id': 'host9', 'node_type': 'compute_cascadelake'},
        ]

    def tearDown(self):
        self.run_test_scenario([], 'project1', [], {})

    def test_update_hosts(self):
        cwd = os.path.dirname(__file__)
        with open(f'{cwd}/lease-stacking-test-config.json') as cf_file:
            config = json.loads(cf_file.read())
        lcm = LeaseComplianceManager(config, {}, self.hosts, {})
        for host in self.hosts:
            self.assertTrue(host['id'] in lcm.hosts_by_id)

    def test_update_leases(self):
        leases = [
            create_lease('lease1', 0, 7),
            create_lease('lease2', 7, 14),
        ]
        allocations = [{
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease1'},
            ]
        }, {
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease2'},
            ]
        }]
        cwd = os.path.dirname(__file__)
        with open(f'{cwd}/lease-stacking-test-config.json') as cf_file:
            config = json.loads(cf_file.read())
        lcm = LeaseComplianceManager(config, leases, self.hosts, allocations)
        for lease in leases:
            self.assertTrue(lease['id'] in lcm.leases_by_id)
            lease = lcm.leases_by_id[lease['id']]
            self.assertTrue('project1' in lcm.projects_by_id)
            project = lcm.projects_by_id['project1']
            self.assertTrue(lease in project.leases)

    def test_furthest_and_earliest_dates(self):
        leases = [
            create_lease('lease1', 0, 7),
            create_lease('lease2', 7, 14),
            create_lease('lease3', 21, 28),
        ]
        allocations = [{
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease1'},
            ]
        }, {
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease2'},
            ]
        }, {
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease3'},
            ]
        }]
        cwd = os.path.dirname(__file__)
        with open(f'{cwd}/lease-stacking-test-config.json') as cf_file:
            config = json.loads(cf_file.read())
        lcm = LeaseComplianceManager(config, leases, self.hosts, allocations)
        project = lcm.projects_by_id['project1']
        self.assertEqual(
            project.furthest_end_date_by_node_type['compute_skylake'],
            datetime.strptime(leases[-1]['end_date'], '%Y-%m-%d')
        )
        self.assertEqual(
            project.start_date_by_node_type['compute_skylake'],
            datetime.strptime(leases[0]['start_date'], '%Y-%m-%d')
        )
        leases = [
            create_lease('lease1', 0, 7),
            create_lease('lease2', 7, 14),
            create_lease('lease3', 14, 21),
        ]
        allocations = [{
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease1'},
            ]
        }, {
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease2'},
            ]
        }, {
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease3'},
            ]
        }]
        cwd = os.path.dirname(__file__)
        with open(f'{cwd}/lease-stacking-test-config.json') as cf_file:
            config = json.loads(cf_file.read())
        lcm = LeaseComplianceManager(config, leases, self.hosts, allocations)
        project = lcm.projects_by_id['project1']
        self.assertEqual(
            project.furthest_end_date_by_node_type['compute_skylake'],
            today + timedelta(days=21)
        )
        self.assertEqual(
            project.start_date_by_node_type['compute_skylake'],
            datetime.strptime(leases[0]['start_date'], '%Y-%m-%d')
        )

    def test_update_allocations(self):
        leases = [
            create_lease('lease1', 0, 7, project_id='project1'),
            create_lease('lease2', 8, 15, project_id='project1'),
            create_lease('lease3', 15, 22, project_id='project1'),
            create_lease('lease4', 0, 7, project_id='project2'),
            create_lease('lease5', 7, 14, project_id='project2'),
            create_lease('lease6', 14, 21, project_id='project2'),
        ]
        allocations = [{
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease1'},
            ]
        }, {
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease2'},
            ]
        }, {
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease3'},
            ]
        }, {
            'resource_id': 'host7',
            'reservations': [
                {'lease_id': 'lease4'},
            ]
        }, {
            'resource_id': 'host7',
            'reservations': [
                {'lease_id': 'lease5'},
            ]
        }, {
            'resource_id': 'host7',
            'reservations': [
                {'lease_id': 'lease6'},
            ]
        }]
        cwd = os.path.dirname(__file__)
        with open(f'{cwd}/lease-stacking-test-config.json') as cf_file:
            config = json.loads(cf_file.read())
        lcm = LeaseComplianceManager(config, leases, self.hosts, allocations)
        for allocation in allocations:
            host = allocation['resource_id']
            for reservation in allocation['reservations']:
                lease_with_node = reservation['lease_id']
                lease_created = lcm.leases_by_id[lease_with_node]
                self.assertTrue(
                    host in [h.host_id for h in lease_created.hosts]
                )

    def run_test_scenario(self, leases, project_id,
                          allocations, expected_violations):
        # expected_violations from a project
        cwd = os.path.dirname(__file__)
        with open(f'{cwd}/lease-stacking-test-config.json') as cf_file:
            config = json.loads(cf_file.read())
        lcm = LeaseComplianceManager(config, leases, self.hosts, allocations)
        violations = lcm.get_project_violations(project_id)
        for node_type, expected_violation in expected_violations.items():
            self.assertIn(node_type, violations)
            # check what kind of violation node is in
            for key in expected_violation:
                self.assertTrue(key in violations[node_type])
        # if violations:
        #     project_lease_violation_body(lcm.projects_by_id.get(project_id), violations, '')

    def test_no_violations(self):
        leases = [
            create_lease('lease1', 0, 7),
            create_lease('lease2', 7, 14),
        ]
        allocations = [{
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease1'},
            ]
        }, {
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease2'},
            ]
        }, {
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease3'},
            ]
        }]
        self.run_test_scenario(
            leases,
            'project1',
            allocations,
            expected_violations={},
        )
        leases = [
            create_lease('lease1', 0, 7),
            create_lease('lease2', 14, 21),
            create_lease('lease3', 21, 28),
        ]
        self.run_test_scenario(
            leases,
            'project1',
            allocations,
            expected_violations={},
        )
        leases = [
            create_lease('lease1', 0, 7),
            create_lease('lease2', 7, 14),
            create_lease('lease3', 17, 24),
            create_lease('lease4', 24, 31),
        ]
        allocations = [{
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease1'},
            ]
        }, {
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease2'},
            ]
        }, {
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease3'},
            ]
        },{
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease4'},
            ]
        }]
        self.run_test_scenario(
            leases,
            'project1',
            allocations,
            expected_violations={}
        )

    def test_lease_duration_violation(self):
        leases = [
            create_lease('lease1', 0, 7),
            create_lease('lease2', 7, 14),
            create_lease('lease3', 14, 21),
        ]
        allocations = [{
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease1'},
            ]
        }, {
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease2'},
            ]
        }, {
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease3'},
            ]
        },{
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease4'},
            ]
        }]
        self.run_test_scenario(
            leases,
            'project1',
            allocations,
            expected_violations={
                'compute_skylake': {'coverage_percentage': 1.0}
            }
        )

    def test_lease_duration_with_parallel_reservation(self):
        leases = [
            create_lease('lease1', 0, 7),
            create_lease('lease2', 0, 7),
            create_lease('lease3', 0, 7),
            create_lease('lease4', 0, 7),
            create_lease('lease5', 0, 7),
            create_lease('lease6', 0, 7),
        ]
        allocations = [{
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease1'},
            ]
        }, {
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease2'},
            ]
        }, {
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease3'},
            ]
        }, {
            'resource_id': 'host7',
            'reservations': [
                {'lease_id': 'lease4'},
            ]
        }, {
            'resource_id': 'host7',
            'reservations': [
                {'lease_id': 'lease5'},
            ]
        }, {
            'resource_id': 'host7',
            'reservations': [
                {'lease_id': 'lease6'},
            ]
        }]
        self.run_test_scenario(
            leases,
            'project1',
            allocations,
            expected_violations={}
        )

    def test_high_end_resource_hogging(self):
        leases = [
            create_lease('lease3', 0, 7, project_id='project2'),
            create_lease('lease4', 0, 7, project_id='project2'),
            create_lease('lease5', 0, 7, project_id='project2'),
            create_lease('lease6', 0, 7, project_id='project2'),
        ]
        allocations = [{
            'resource_id': 'host3',
            'reservations': [
                {'lease_id': 'lease4'}
            ]
        }, {
            'resource_id': 'host3',
            'reservations': [
                {'lease_id': 'lease5'}
            ]
        }, {
            'resource_id': 'host2',
            'reservations': [
                {'lease_id': 'lease3'}
            ]
        }]
        self.run_test_scenario(
            leases,
            'project2',
            allocations,
            expected_violations={'gpu_v100': {'nodes_reserved': 3}},
        )
        allocations = [{
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease4'},
                {'lease_id': 'lease5'}
            ]},
            {
            'resource_id': 'host7',
            'reservations': [
                {'lease_id': 'lease3'}
            ]},
        ]
        self.run_test_scenario(
            leases,
            'project2',
            allocations,
            expected_violations={},
        )

    def test_excluded_project(self):
        leases = [
            create_lease(
                'lease1', 0, 7, project_id='975c0a94b784483a885f4503f70af655'
            ),
            create_lease(
                'lease2', 7, 14, project_id='975c0a94b784483a885f4503f70af655'
            ),
            create_lease(
                'lease3', 14, 21, project_id='975c0a94b784483a885f4503f70af655'
            ),
        ]
        allocations = [{
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease1'},
                {'lease_id': 'lease2'},
                {'lease_id': 'lease3'}
            ]
        }]
        self.run_test_scenario(
            leases,
            '975c0a94b784483a885f4503f70af655',
            allocations,
            expected_violations={}
        )

    def test_lease_stacking_with_multiple_projects(self):
        leases = [
            create_lease('lease1', 0, 7, project_id='project1'),
            create_lease('lease2', 8, 15, project_id='project1'),
            create_lease('lease3', 15, 22, project_id='project1'),
            create_lease('lease4', 0, 7, project_id='project2'),
            create_lease('lease5', 7, 14, project_id='project2'),
            create_lease('lease6', 14, 21, project_id='project2'),
        ]
        allocations = [{
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease1'},
            ]
        }, {
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease2'},
            ]
        }, {
            'resource_id': 'host1',
            'reservations': [
                {'lease_id': 'lease3'},
            ]
        }, {
            'resource_id': 'host8',
            'reservations': [
                {'lease_id': 'lease4'},
            ]
        }, {
            'resource_id': 'host8',
            'reservations': [
                {'lease_id': 'lease5'},
            ]
        }, {
            'resource_id': 'host8',
            'reservations': [
                {'lease_id': 'lease6'},
            ]
        }]
        self.run_test_scenario(
            leases, 'project1', allocations,
            expected_violations={
                'compute_skylake': {'coverage_percentage': 1.0}
            }
        )
        self.run_test_scenario(
            leases, 'project2', allocations,
            expected_violations={
                'compute_cascadelake': {'coverage_percentage': 1.0}
            }
        )


if __name__ == '__main__':
    unittest.main()
