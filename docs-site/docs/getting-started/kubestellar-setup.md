---
sidebar_position: 4
---

# KubeStellar Setup Guide

Complete guide for setting up KubeStellar v0.28.0 using the A2A agent's automated setup functionality. This guide follows the [official KubeStellar get-started documentation](https://docs.kubestellar.io/release-0.28.0/direct/get-started/) with comprehensive prerequisite verification and automated cluster management.

## Overview

The KubeStellar setup function provides a complete implementation of the official get-started guide with additional features:

- ✅ **Automated prerequisite verification** for all required tools
- ✅ **Cleanup of existing clusters** to ensure clean setup
- ✅ **Step-by-step manual setup** following the documentation
- ✅ **Automated script option** for quick deployment
- ✅ **Comprehensive error handling** and status reporting
- ✅ **Integration with existing A2A functions** for ongoing management

## Prerequisites Verification

Before starting the setup, verify all required tools are installed:

```bash
# Check prerequisites
uv run kubestellar execute kubestellar_setup -p '{"operation": "verify_prerequisites"}'
```

### Required Tools

The setup function automatically checks for:

| Tool | Minimum Version | Required | Purpose |
|------|----------------|----------|---------|
| `kubectl` | 1.26.0 | ✅ Yes | Kubernetes CLI |
| `helm` | 3.8.0 | ✅ Yes | Helm package manager |
| `docker` | 20.0.0 | ✅ Yes | Container runtime |
| `kind` OR `k3d` | 0.17.0 / 5.4.0 | ✅ Yes | Local cluster creation |
| `kflex` | 0.6.0 | ✅ Yes | KubeFlex CLI |
| `clusteradm` | 0.4.0 | ✅ Yes | Open Cluster Management CLI |

### Installation Instructions

If any tools are missing, the function provides installation commands:

```bash
# Install kubectl
curl -LO https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl
chmod +x kubectl && sudo mv kubectl /usr/local/bin/

# Install Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh

# Install kind
go install sigs.k8s.io/kind@v0.20.0

# Install KubeFlex CLI
go install github.com/kubestellar/kubeflex/cmd/kflex@latest

# Install clusteradm (OCM CLI)
curl -L https://raw.githubusercontent.com/open-cluster-management-io/clusteradm/main/install.sh | bash
```

## Setup Options

### 1. Automated Quick Setup (Recommended)

Use the official KubeStellar automated script:

```bash
uv run kubestellar execute kubestellar_setup -p '{
  "operation": "full_setup",
  "automated_script": true,
  "platform": "kind",
  "kubestellar_version": "v0.28.0"
}'
```

### 2. Manual Step-by-Step Setup

For more control and understanding:

```bash
uv run kubestellar execute kubestellar_setup -p '{
  "operation": "full_setup",
  "platform": "kind",
  "cluster_name": "kubeflex",
  "kubestellar_version": "v0.28.0",
  "cleanup_existing": true,
  "verify_prerequisites": true,
  "create_wec_clusters": true,
  "wec_cluster_names": ["cluster1", "cluster2"]
}'
```

### 3. Individual Operations

Execute specific setup steps independently:

#### Cleanup Existing Clusters
```bash
uv run kubestellar execute kubestellar_setup -p '{
  "operation": "cleanup",
  "platform": "kind"
}'
```

#### Create KubeFlex Cluster Only
```bash
uv run kubestellar execute kubestellar_setup -p '{
  "operation": "create_kubeflex",
  "platform": "kind",
  "cluster_name": "kubeflex",
  "kubestellar_version": "v0.28.0"
}'
```

#### Setup Workload Execution Clusters
```bash
uv run kubestellar execute kubestellar_setup -p '{
  "operation": "setup_wec_clusters",
  "platform": "kind",
  "wec_cluster_names": ["cluster1", "cluster2"]
}'
```

## Configuration Options

### Platform Selection

Choose between `kind` or `k3d` for local cluster creation:

```bash
# Using kind (default)
-p '{"platform": "kind"}'

# Using k3d
-p '{"platform": "k3d"}'
```

### Cluster Naming

Customize cluster names:

```bash
-p '{
  "cluster_name": "my-kubeflex",
  "wec_cluster_names": ["edge-east", "edge-west", "cloud-central"]
}'
```

### KubeStellar Version

Specify the KubeStellar version to install:

```bash
-p '{"kubestellar_version": "v0.28.0"}'
```

### Timeout Configuration

Adjust timeouts for Helm operations:

```bash
-p '{"helm_timeout": "15m"}'
```

## Verification

After setup completion, verify the installation:

```bash
# Check cluster status
kubectl config get-contexts

# Verify KubeStellar components
kubectl get pods -A

# Check binding policies and work statuses
uv run kubestellar execute kubestellar_management -p '{
  "operation": "topology_map",
  "verify_setup": true
}'
```

## Expected Output

A successful setup will create:

1. **KubeFlex Cluster** (`kind-kubeflex`)
   - KubeStellar core components
   - ITS (Inventory and Transport Space)
   - WDS (Workload Description Space)

2. **Workload Execution Clusters**
   - `kind-cluster1`
   - `kind-cluster2`
   - Registered with OCM hub

3. **Kubectl contexts** for all clusters

## Troubleshooting

### Common Issues

#### Prerequisites Missing
```bash
# Re-run verification to see missing tools
uv run kubestellar execute kubestellar_setup -p '{"operation": "verify_prerequisites"}'
```

#### Cluster Creation Fails
```bash
# Clean up and retry
uv run kubestellar execute kubestellar_setup -p '{
  "operation": "cleanup",
  "platform": "kind"
}'
```

#### Helm Installation Timeout
```bash
# Increase timeout
-p '{"helm_timeout": "20m", "wait_for_ready": false}'
```

#### Port Conflicts
```bash
# Check if ports 6443, 80, 443 are available
netstat -tlnp | grep -E ':(6443|80|443)'

# Stop conflicting services or use different ports
```

### Log Analysis

Check detailed logs from the setup process:

```bash
# Get detailed output
-p '{"output_format": "detailed"}'

# Check cluster logs
kubectl logs -n kubestellar-system --all-containers=true
```

### Manual Verification

Verify each component manually:

```bash
# Check KubeFlex components
kflex ctx

# Check OCM managed clusters
kubectl get managedclusters -A

# Check binding policies
kubectl get bindingpolicies -A

# Check work statuses
kubectl get workstatuses -A
```

## Integration with A2A Functions

Once KubeStellar is set up, use other A2A functions for ongoing management:

### Cluster Management
```bash
# Deep analysis of your KubeStellar setup
uv run kubestellar execute kubestellar_management -p '{
  "operation": "deep_search",
  "binding_policies": true,
  "work_statuses": true,
  "placement_analysis": true
}'
```

### Application Deployment
```bash
# Deploy applications with binding policies
uv run kubestellar execute helm_deploy -p '{
  "chart_name": "nginx",
  "repository_url": "https://kubernetes.github.io/ingress-nginx",
  "target_clusters": ["cluster1", "cluster2"],
  "create_binding_policy": true
}'
```

### Multi-Cluster Operations
```bash
# Create resources across clusters
uv run kubestellar execute multicluster_create -p '{
  "resource_type": "deployment",
  "resource_name": "test-app",
  "image": "nginx:latest",
  "replicas": 2
}'
```

## Next Steps

After successful KubeStellar setup:

1. **Explore the [CLI Reference](../cli-reference)** to understand all available functions
2. **Try [Multi-Cluster Deployments](./quick-start)** with your new setup
3. **Configure [Binding Policies](../troubleshooting)** for advanced workload placement
4. **Set up [AI Assistant Integration](./installation)** for conversational cluster management

## Example: Complete Setup Workflow

Here's a complete example workflow:

```bash
# 1. Verify prerequisites
uv run kubestellar execute kubestellar_setup -p '{"operation": "verify_prerequisites"}'

# 2. Clean up any existing setup
uv run kubestellar execute kubestellar_setup -p '{"operation": "cleanup", "platform": "kind"}'

# 3. Run full automated setup
uv run kubestellar execute kubestellar_setup -p '{
  "operation": "full_setup",
  "platform": "kind",
  "kubestellar_version": "v0.28.0",
  "create_wec_clusters": true,
  "wec_cluster_names": ["cluster1", "cluster2"],
  "output_format": "detailed"
}'

# 4. Verify the setup
uv run kubestellar execute kubestellar_management -p '{
  "operation": "topology_map",
  "verify_setup": true
}'

# 5. Deploy a test application
uv run kubestellar execute multicluster_create -p '{
  "resource_type": "deployment",
  "resource_name": "hello-kubestellar",
  "image": "nginx:latest",
  "namespace": "default"
}'
```

This will give you a fully functional KubeStellar environment ready for multi-cluster workload management! 🚀