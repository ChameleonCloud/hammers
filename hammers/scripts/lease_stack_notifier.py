# coding: utf-8
'''
.. code-block:: bash

    lease-stack-notifier {info, notify}

Notify about projects that violate terms of use

* ``info`` to just display violations or notify them on email with ``notify``
'''
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta

import openstack
from blazarclient.client import Client as BlazarClient
from dateutil.parser import parse as datetime_parse

from hammers.notifications import _email
from hammers.util import base_parser


DATETIME_NOW = datetime.utcnow()
SECONDS_IN_DAY = timedelta(days=1).total_seconds()


def calculate_overlap_percentage(lease1, lease2):
    """
    Calculate the percentage of overlap between param:lease1 and param:lease2
    returns the overlap percentage of param:lease1 with param:lease2
    """
    start = max(max(lease1.start, lease2.start), DATETIME_NOW)
    end = min(lease1.end, lease2.end)
    if start >= end:
        return 0  # No overlap
    overlap_duration = (end - start).total_seconds()
    lease1_duration = (
        lease1.end - max(lease1.start, DATETIME_NOW)
    ).total_seconds()
    return (overlap_duration / lease1_duration) * 100


def does_host_overlap_with_lease(host, host_lease, other_lease):
    """
    Check if the given param:host from param:host_lease
    overlaps with param:other_lease for at least 90% of its duration.
    """
    # Only check overlap for leases with matching node types
    if (
        host.node_type in other_lease.node_types
        and calculate_overlap_percentage(host_lease, other_lease) >= 90
    ):
        return True
    return False


class Host:
    """ Represents a Host with host attributes """
    def __init__(self, host_id, node_type):
        self.host_id = host_id
        self.node_type = node_type
        self.calculate_coverage = True

    def __dict__(self):
        return {
            "id": self.host_id,
            "node_type": self.node_type
        }

    def encode(self):
        return self.__dict__()

    def is_high_end(self):
        if (
            self._is_gpu_type()
            or self._is_storage_type()
            or self._is_fpga_type()
        ):
            return True
        return False

    def _is_gpu_type(self):
        return 'gpu' in self.node_type.lower()

    def _is_storage_type(self):
        return 'storage' in self.node_type.lower()

    def _is_fpga_type(self):
        return 'fpga' in self.node_type.lower()


class Lease:
    """ Represents a lease with its attributes """
    def __init__(self, lease_details):
        self.lease_id = lease_details['id']
        self.start = datetime_parse(lease_details['start_date'])
        self.end = datetime_parse(lease_details['end_date'])
        self.status = lease_details['status']
        self.project_id = lease_details['project_id']
        self.hosts = []
        self.node_types = set()

    def __dict__(self):
        return {
            "id": self.lease_id,
            "start_date": str(self.start),
            "end_date": str(self.end),
            "status": self.status,
            "project_id": self.project_id,
            "hosts": [h.encode() for h in self.hosts]
        }

    def __str__(self):
        return json.dumps(self.__dict__(), indent=2)

    def toJson(self):
        return self.__str__()

    def add_host(self, host):
        self.hosts.append(host)
        if host.node_type in self.node_types:
            host.calculate_coverage = False
        self.node_types.add(host.node_type)


class Project:
    """ Represents a project with leases """
    def __init__(self, project_id, minimum_lease_window_days=21):
        self.project_id = project_id
        self.leases = set()
        self.minimum_lease_window = timedelta(days=minimum_lease_window_days)
        self.furthest_end_date_by_node_type = defaultdict(
            lambda: DATETIME_NOW + self.minimum_lease_window
        )
        self.start_date_by_host = defaultdict(lambda: DATETIME_NOW)
        self.start_date_by_node_type = defaultdict(lambda: DATETIME_NOW)

    def __str__(self):
        return {
            "id": self.project_id
        }

    def add_lease(self, lease):
        """Add a lease to the project."""
        self.leases.add(lease)
        for host in lease.hosts:
            # if the host does not have an overlapping reservation
            # with same node type then calculate coverage of host
            if not self._host_in_overlapping_reservation(host, lease):
                host.calculate_coverage = True
            node_type = host.node_type
            self.furthest_end_date_by_node_type[node_type] = max(
                self.furthest_end_date_by_node_type[node_type],
                lease.end
            )
            self.start_date_by_node_type[host.node_type] = min(
                self.start_date_by_node_type[host.node_type],
                lease.start
            )

    def _host_in_overlapping_reservation(self, host, lease):
        for other_lease in self.leases:
            if lease.lease_id == other_lease.lease_id:
                return True  # The same lease, so it overlaps by definition
            # if the host's node_type is not already seen/reserved in the
            # project then node_type does not have an overlapping lease
            if host.node_type not in self.furthest_end_date_by_node_type:
                return False
            if does_host_overlap_with_lease(host, lease, other_lease):
                return True
        return False

    def _summarize_stacking_violation(self, seconds_covered, total_seconds):
        return {
            "coverage_percentage": (seconds_covered / total_seconds) * 100,
            "days_covered": seconds_covered / SECONDS_IN_DAY,
            "total_days": total_seconds / SECONDS_IN_DAY
        }

    def get_coverage_by_node_type(self):
        coverage_by_node_type = defaultdict(int)
        # Calculate coverage based on the adjusted furthest end date
        for lease in self.leases:
            for host in lease.hosts:
                # Do not calculate coverage for multiple hosts
                # in almost similar reservation periods
                if not host.calculate_coverage:
                    continue
                seconds_covered = (
                    lease.end - max(DATETIME_NOW, lease.start)
                ).total_seconds()
                coverage_by_node_type[host.node_type] += seconds_covered
        return coverage_by_node_type

    def get_lease_stacking_violations(self, excluded_node_types, lease_coverage_threshold):
        coverage_by_node_type = self.get_coverage_by_node_type()
        # Check for violations based on coverage percentage
        violations = {}
        for node_type, seconds_covered in coverage_by_node_type.items():
            if node_type.lower() in excluded_node_types:
                print(f"Skipping excluded node type - {node_type}")
                continue
            seconds_in_coverage_period = (
                self.furthest_end_date_by_node_type[node_type]
                - self.start_date_by_node_type[node_type]
            ).total_seconds()
            coverage_percentage = seconds_covered / seconds_in_coverage_period

            if coverage_percentage >= lease_coverage_threshold:
                violations[node_type] = self._summarize_stacking_violation(
                    seconds_covered, seconds_in_coverage_period
                )
        return violations

    def get_high_end_hogging_violations(
        self, node_type_counts,
        high_end_node_types, high_end_node_coverage_threshold,
        min_nodes_for_coverage
    ):
        nodes_reserved_in_month = defaultdict(int)
        violations = {}
        for lease in self.leases:
            for host in lease.hosts:
                # check if lease end is within the check window
                if DATETIME_NOW <= lease.end <= DATETIME_NOW + self.minimum_lease_window:
                    nodes_reserved_in_month[host.node_type] += 1
        for node_type, node_counts in nodes_reserved_in_month.items():
            if high_end_node_types and node_type not in high_end_node_types:
                print(f"{node_type} - not included as high end")
                continue
            total_nodes = node_type_counts[node_type]
            if total_nodes <= min_nodes_for_coverage:
                continue
            if node_counts > high_end_node_coverage_threshold * total_nodes:
                violations[node_type] = {
                    "total_nodes": total_nodes,
                    "nodes_reserved": node_counts,
                }
        return violations


class LeaseComplianceManager:
    def __init__(self, config, leases, hosts, allocations):
        """ Manager for checking if leases comply with lease stacking policy

        Args:
            config (dict)
            leases (list)
            hosts (list)
            allocations (list)
            sender_email (str, optional)
        """
        self.config = config
        self.leases = leases
        self.hosts = hosts
        self.allocations = allocations
        self.sender_email = config['sender_email']
        self.hosts_by_id = {}
        self.leases_by_id = {}
        self.projects_by_id = {}
        self.node_type_counts = defaultdict(int)
        self._update_hosts()
        self._update_leases()
        self._update_from_allocations()

    def _update_hosts(self):
        for host in self.hosts:
            node_type = host["node_type"]
            host_id = host["id"]
            self.hosts_by_id[host_id] = Host(host_id, node_type)
            self.node_type_counts[node_type] += 1

    def _update_leases(self):
        # creates lease objects and adds leases to projects
        for lease_details in self.leases:
            lease_id = lease_details['id']
            if lease_details['status'].lower() in ['terminated', 'error', 'deleting']:
                continue
            lease = Lease(lease_details)
            self.leases_by_id[lease_id] = lease

    def _update_from_allocations(self):
        # adds hosts to the leases they are allocated to
        for allocation in self.allocations:
            for reservation in allocation['reservations']:
                lease = self.leases_by_id.get(reservation['lease_id'])
                if lease:
                    host = self.hosts_by_id[allocation['resource_id']]
                    lease.add_host(host)
                    project_id = lease.project_id
                    project = self.projects_by_id.get(project_id, Project(project_id))
                    project.add_lease(lease)
                    self.projects_by_id[project_id] = project

    def get_project_violations(self, project_id):
        violations = {}
        project = self.projects_by_id.get(project_id)
        if not project:
            return violations
        violations.update(project.get_lease_stacking_violations(
            self.config['exclude_node_types'], self.config['lease_coverage_threshold']
        ))
        violations.update(project.get_high_end_hogging_violations(
            self.node_type_counts,
            self.config['high_end_node_types'], self.config['high_end_node_coverage_threshold'],
            self.config['min_nodes_for_coverage']
        ))
        return violations


def project_lease_violation_body(project, project_violations,
                                 project_name, site_name):
    """
    Returns body of notification about the project violation(s)

    Args:
        project (Project): _description_
        project_violations (dict): dict of dicts with outer keys are node_types
            keys in inner dicts are describing violations
        project_name (str): charge code from project in CHI-xxxxxx format

    Returns:
        str: body of notification about the project violation(s)
    """
    body = "To ChameleonCloud project manager \n\n"
    body = f"Lease stacking violation in {site_name} \n\n"
    project_id = project.project_id
    for node_type, violation in project_violations.items():
        if 'days_covered' in violation:
            body += (
                f"Project {project_name} {project_id} has exceeded the lease stacking "
                f"limit for node type: {node_type}\n"
            )
            body += (
                f"\tDays covered by node type: {violation['days_covered']} / {violation['total_days']} \n\n"
            )
        else:
            body += (
                f"Project {project_name} {project_id} has exceeded reserving more than "
                f"half limit for node type: {node_type}\n"
            )
            body += f"\tCount of nodes reserved: {violation['nodes_reserved']} / {violation['total_nodes']}\n\n"
    body += "Leases in project \n\n"
    for lease in project.leases:
        body += f"{lease} \n\n"
    return body


def notify_lease_violations(project_id, message_body, send_to, sender):
    """Notify the lease stacking violations."""
    subject = f"Lease Stacking Violation Detected - {project_id}"
    # Send email to community manager
    send_email(subject, message_body, send_to, sender)


def send_email(subject, body, send_to, sender):
    """Send email about violating projects."""
    _email.send(
        _email.get_host(),
        send_to,
        sender,
        subject,
        body
    )


def main(argv=None):
    if argv is None:
        argv = sys.argv

    parser = base_parser('Lease Stack Notifier')
    parser.add_argument(
        'action', choices=['info', 'notify'],
        help='Just display info or notify them?')
    parser.add_argument(
        '--config',
        type=str,
        help='JSON file with configuration for lease stacking policy'
    )
    args = parser.parse_args(argv[1:])
    with open(args.config) as cf_file:
        config = json.loads(cf_file.read())

    conn = openstack.connect(cloud='envvars')
    sess = conn.session
    blazar = BlazarClient("1", session=sess)
    print("Getting hosts")
    hosts = blazar.host.list()
    print("Getting leases")
    leases = blazar.lease.list()
    print("Getting allocations")
    allocations = blazar.allocation.list("os-hosts")
    projects = conn.identity.projects
    project_charge_code_map = {p.id: p.name.lower() for p in projects()}
    json.dumps(project_charge_code_map, indent=2)
    lcm = LeaseComplianceManager(config, leases, hosts, allocations)

    for project_id in lcm.projects_by_id:
        project_name = project_charge_code_map.get(project_id, '')
        if (
            project_id in config['exclude_projects']
            or project_name in config['exclude_projects']
        ):
            print(f"Skipping Excluded project - {project_id}")
            continue
        violations = lcm.get_project_violations(project_id)
        if not violations:
            continue
        print(f"Found lease stacking violations with Project - {project_id}")
        message = project_lease_violation_body(
            lcm.projects_by_id[project_id], violations,
            project_name, config['site']
        )
        if args.action == 'notify':
            notify_lease_violations(
                project_id, message, config['manager_email'],
                config['sender_email']
            )
        else:
            print(message)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
