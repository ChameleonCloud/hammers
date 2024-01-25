'''
Basic Usage:

.. code-block:: bash

    k8s-calico-ip-cleanup --kubeconfig_path <path_to_site_kubeconfig>

This script cleans up the calico ipv4 address annotation for offline nodes in a kubernetes cluster.
Cleaning up these addresses is necessary to allow new nodes to start with the same ip addresses.
'''

import os
import sys

from kubernetes import client, config

from hammers.util import base_parser

# Kubernetes 10.x/12.x support
try:
    K8sApiException = client.ApiException  # >=12.x
except:
    K8sApiException = client.api_client.ApiException

_KUBERNETES_CLIENT = None

_KUBECONFIG_PATH = None

def kubernetes_client():
    global _KUBERNETES_CLIENT
    if not _KUBERNETES_CLIENT:
        config.load_kube_config(config_file=_KUBECONFIG_PATH)
        _KUBERNETES_CLIENT = client.CoreV1Api()
    return _KUBERNETES_CLIENT


def clear_calico_ipv4_annotation(node_name):
    try:
        v1 = kubernetes_client()

        node = v1.read_node(name=node_name)

        # Remove the Calico IPv4 annotation
        if "projectcalico.org/IPv4Address" in node.metadata.annotations:
            del node.metadata.annotations["projectcalico.org/IPv4Address"]

            v1.replace_node(name=node_name, body=node)
            print(f"Cleared Calico IPv4 annotation for node: {node_name}")

    except Exception as e:
        print(f"Error clearing Calico IPv4 annotation for node {node_name}: {e}")

def get_offline_nodes():
    try:
        v1 = kubernetes_client()

        nodes = v1.list_node(watch=False)


        offline_nodes = [
            node.metadata.name
            for node in nodes.items
            if (
                node.status.conditions is not None
                and all(
                    cond.status != "True"
                    for cond in node.status.conditions
                    if cond.type == "Ready"
                )
                and any(
                    taint.effect == "NoExecute" and taint.key == "node.kubernetes.io/unreachable"
                    for taint in node.spec.taints
                )
                and any(
                    taint.effect == "NoSchedule" and taint.key == "node.kubernetes.io/unreachable"
                    for taint in node.spec.taints
                )
            )
        ]

        return offline_nodes

    except Exception as e:
        print(f"Error getting offline nodes: {e}")
        return []

def main(argv=None):
    if argv is None:
        argv = sys.argv

    parser = base_parser('Calico IPv4 address K8s annotation remover for offline nodes')

    parser.add_argument('--kubeconfig_path',
                        type=str,
                        help='Path to Kubeconfig file for current cluster')
    parser.add_argument('--dry-run',
                        action='store_true',
                        help='Perform a dry run without making changes')

    args = parser.parse_args(argv[1:])

    global _KUBECONFIG_PATH
    _KUBECONFIG_PATH = args.kubeconfig_path

    offline_nodes = get_offline_nodes()

    for node_name in offline_nodes:
        if args.dry_run:
            print(f"Would clear Calico IPv4 annotation for node: {node_name} in dry run mode.")
        else:
            clear_calico_ipv4_annotation(node_name)

if __name__ == '__main__':
    sys.exit(main(sys.argv))
