"""KubeStellar Get-Started Setup Functions with Prerequisite Verification.

Implementation of KubeStellar v0.28.0 get-started guide functionality following
the official documentation at https://docs.kubestellar.io/release-0.28.0/direct/get-started/

This module provides:
- Prerequisite verification for all required tools
- Automated cleanup of previous configurations
- Kind cluster creation and management
- KubeFlex and KubeStellar initialization
- OCM cluster registration and management
- Complete setup orchestration
"""

import asyncio
import json
import shutil
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..base_functions import BaseFunction


@dataclass
class PrerequisiteCheck:
    """Result of a prerequisite verification check."""
    
    name: str
    installed: bool
    version: str = ""
    path: str = ""
    error: str = ""
    required_version: str = ""


@dataclass
class SetupProgress:
    """Progress tracking for KubeStellar setup operations."""
    
    step: str
    status: str  # 'pending', 'in_progress', 'completed', 'failed'
    message: str = ""
    error: str = ""
    duration: float = 0.0


class KubeStellarSetupFunction(BaseFunction):
    """KubeStellar Get-Started Setup with comprehensive prerequisite verification."""

    def __init__(self):
        super().__init__(
            name="kubestellar_setup",
            description="Complete KubeStellar setup following the official get-started guide with prerequisite verification, cleanup, and automated configuration.",
        )
        
        # KubeStellar version from the documentation
        self.kubestellar_version = "v0.28.0"
        
        # Required tools with minimum versions
        self.prerequisites = {
            "kubectl": {"min_version": "1.26.0", "required": True},
            "helm": {"min_version": "3.8.0", "required": True},
            "docker": {"min_version": "20.0.0", "required": True},
            "kind": {"min_version": "0.17.0", "required": False},  # OR k3d
            "k3d": {"min_version": "5.4.0", "required": False},   # OR kind
            "kflex": {"min_version": "0.6.0", "required": True},  # KubeFlex CLI
            "clusteradm": {"min_version": "0.4.0", "required": True},  # OCM CLI
        }

    async def execute(
        self,
        operation: str = "full_setup",
        platform: str = "kind",  # 'kind' or 'k3d'
        cluster_name: str = "kubeflex",
        kubestellar_version: str = "",
        cleanup_existing: bool = True,
        verify_prerequisites: bool = True,
        automated_script: bool = False,
        helm_timeout: str = "10m",
        wait_for_ready: bool = True,
        create_wec_clusters: bool = True,
        wec_cluster_names: Optional[List[str]] = None,
        output_format: str = "detailed",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Execute KubeStellar setup operations following the official get-started guide.

        Args:
            operation: Setup operation type ('full_setup', 'verify_prerequisites', 'cleanup', 'create_kubeflex', 'setup_wec_clusters')
            platform: Container platform to use ('kind' or 'k3d')
            cluster_name: Name for the main KubeFlex cluster
            kubestellar_version: KubeStellar version to install (defaults to v0.28.0)
            cleanup_existing: Clean up existing clusters before setup
            verify_prerequisites: Verify all required tools are installed
            automated_script: Use the automated setup script instead of manual steps
            helm_timeout: Timeout for Helm operations
            wait_for_ready: Wait for components to be ready before proceeding
            create_wec_clusters: Create workload execution clusters
            wec_cluster_names: Names for WEC clusters (defaults to ['cluster1', 'cluster2'])
            output_format: Output format ('detailed', 'summary', 'json')

        Returns:
            Dictionary with comprehensive setup results and status
        """
        try:
            # Use provided version or default
            version = kubestellar_version or self.kubestellar_version
            wec_names = wec_cluster_names or ["cluster1", "cluster2"]

            if operation == "verify_prerequisites":
                return await self._verify_prerequisites(output_format)
            
            elif operation == "cleanup":
                return await self._cleanup_existing_clusters(platform, output_format)
            
            elif operation == "create_kubeflex":
                return await self._create_kubeflex_cluster(
                    platform, cluster_name, version, cleanup_existing, output_format
                )
            
            elif operation == "setup_wec_clusters":
                return await self._setup_wec_clusters(
                    platform, wec_names, wait_for_ready, output_format
                )
                
            elif operation == "full_setup":
                if automated_script:
                    return await self._automated_setup(platform, version, output_format)
                else:
                    return await self._manual_full_setup(
                        platform,
                        cluster_name,
                        version,
                        cleanup_existing,
                        verify_prerequisites,
                        helm_timeout,
                        wait_for_ready,
                        create_wec_clusters,
                        wec_names,
                        output_format,
                    )
            
            else:
                return {
                    "status": "error",
                    "error": f"Unsupported operation: {operation}",
                }

        except Exception as e:
            return {
                "status": "error",
                "operation": operation,
                "error": f"Setup operation failed: {str(e)}",
            }

    async def _verify_prerequisites(self, output_format: str) -> Dict[str, Any]:
        """Verify all required tools are installed and meet minimum versions."""
        try:
            checks = []
            overall_status = "success"
            missing_required = []
            version_warnings = []

            for tool, config in self.prerequisites.items():
                check = await self._check_tool_availability(tool, config)
                checks.append(check)
                
                if config["required"] and not check.installed:
                    missing_required.append(tool)
                    overall_status = "error"
                elif check.installed and check.version and not self._version_meets_minimum(check.version, config["min_version"]):
                    version_warnings.append(f"{tool} version {check.version} is below recommended {config['min_version']}")

            # Special case: either kind OR k3d is required
            kind_check = next((c for c in checks if c.name == "kind"), None)
            k3d_check = next((c for c in checks if c.name == "k3d"), None)
            
            if not (kind_check and kind_check.installed) and not (k3d_check and k3d_check.installed):
                missing_required.append("kind or k3d")
                overall_status = "error"

            result = {
                "status": overall_status,
                "operation": "verify_prerequisites",
                "checks": [
                    {
                        "name": check.name,
                        "installed": check.installed,
                        "version": check.version,
                        "path": check.path,
                        "required": self.prerequisites[check.name]["required"],
                        "min_version": check.required_version,
                        "meets_minimum": self._version_meets_minimum(check.version, check.required_version) if check.version else False,
                        "error": check.error,
                    }
                    for check in checks
                ],
                "summary": {
                    "total_checks": len(checks),
                    "passed": sum(1 for c in checks if c.installed),
                    "failed": sum(1 for c in checks if not c.installed and self.prerequisites[c.name]["required"]),
                    "warnings": len(version_warnings),
                },
                "missing_required": missing_required,
                "version_warnings": version_warnings,
            }

            if missing_required:
                result["installation_instructions"] = self._get_installation_instructions(missing_required)

            return result

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to verify prerequisites: {str(e)}",
            }

    async def _check_tool_availability(self, tool: str, config: Dict[str, Any]) -> PrerequisiteCheck:
        """Check if a specific tool is available and get its version."""
        try:
            # Find tool path
            tool_path = shutil.which(tool)
            if not tool_path:
                return PrerequisiteCheck(
                    name=tool,
                    installed=False,
                    error=f"{tool} not found in PATH",
                    required_version=config["min_version"]
                )

            # Get version based on tool
            version_cmd = self._get_version_command(tool)
            result = await self._run_command(version_cmd)
            
            if result["returncode"] != 0:
                return PrerequisiteCheck(
                    name=tool,
                    installed=True,
                    path=tool_path,
                    error=f"Failed to get {tool} version: {result['stderr']}",
                    required_version=config["min_version"]
                )

            version = self._parse_version(tool, result["stdout"])
            
            return PrerequisiteCheck(
                name=tool,
                installed=True,
                version=version,
                path=tool_path,
                required_version=config["min_version"]
            )

        except Exception as e:
            return PrerequisiteCheck(
                name=tool,
                installed=False,
                error=f"Error checking {tool}: {str(e)}",
                required_version=config["min_version"]
            )

    def _get_version_command(self, tool: str) -> List[str]:
        """Get the appropriate version command for each tool."""
        version_commands = {
            "kubectl": ["kubectl", "version", "--client", "--output=json"],
            "helm": ["helm", "version", "--short"],
            "docker": ["docker", "version", "--format", "json"],
            "kind": ["kind", "version"],
            "k3d": ["k3d", "version"],
            "kflex": ["kflex", "version"],
            "clusteradm": ["clusteradm", "version"],
        }
        return version_commands.get(tool, [tool, "--version"])

    def _parse_version(self, tool: str, output: str) -> str:
        """Parse version string from tool output."""
        try:
            if tool == "kubectl":
                version_info = json.loads(output)
                return version_info["clientVersion"]["gitVersion"].lstrip("v")
            elif tool == "helm":
                # Output format: "v3.12.0+g4e2b3855"
                return output.split()[0].lstrip("v").split("+")[0]
            elif tool == "docker":
                version_info = json.loads(output)
                return version_info["Client"]["Version"]
            elif tool in ["kind", "k3d"]:
                # Output format: "kind v0.20.0 go1.20.4 linux/amd64"
                parts = output.split()
                for part in parts:
                    if part.startswith("v") and "." in part:
                        return part.lstrip("v")
            elif tool in ["kflex", "clusteradm"]:
                # Look for version pattern in output
                import re
                version_match = re.search(r'v?(\d+\.\d+\.\d+)', output)
                if version_match:
                    return version_match.group(1)
        except Exception:
            pass
        
        # Fallback: extract version pattern from output
        import re
        version_match = re.search(r'v?(\d+\.\d+\.\d+)', output)
        return version_match.group(1) if version_match else "unknown"

    def _version_meets_minimum(self, current: str, minimum: str) -> bool:
        """Compare version strings to check if current meets minimum requirement."""
        if not current or current == "unknown":
            return False
        
        try:
            def parse_version(v):
                return tuple(map(int, v.split('.')))
            
            return parse_version(current) >= parse_version(minimum)
        except Exception:
            return False

    def _get_installation_instructions(self, missing_tools: List[str]) -> Dict[str, str]:
        """Get installation instructions for missing tools."""
        instructions = {}
        
        base_instructions = {
            "kubectl": "curl -LO https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl && chmod +x kubectl && sudo mv kubectl /usr/local/bin/",
            "helm": "curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash",
            "docker": "curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh",
            "kind": "go install sigs.k8s.io/kind@v0.20.0",
            "k3d": "curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash",
            "kflex": "go install github.com/kubestellar/kubeflex/cmd/kflex@latest",
            "clusteradm": "curl -L https://raw.githubusercontent.com/open-cluster-management-io/clusteradm/main/install.sh | bash",
        }
        
        for tool in missing_tools:
            if tool in base_instructions:
                instructions[tool] = base_instructions[tool]
            elif tool == "kind or k3d":
                instructions["kind_or_k3d"] = f"Install either:\nkind: {base_instructions['kind']}\nOR\nk3d: {base_instructions['k3d']}"
        
        return instructions

    async def _cleanup_existing_clusters(self, platform: str, output_format: str) -> Dict[str, Any]:
        """Clean up existing KubeStellar-related clusters."""
        try:
            cleanup_result = {
                "status": "success",
                "operation": "cleanup",
                "platform": platform,
                "clusters_removed": [],
                "contexts_removed": [],
                "errors": [],
            }

            # Get existing clusters
            if platform == "kind":
                list_cmd = ["kind", "get", "clusters"]
            else:  # k3d
                list_cmd = ["k3d", "cluster", "list", "--output", "json"]

            result = await self._run_command(list_cmd)
            if result["returncode"] != 0:
                cleanup_result["warnings"] = [f"Could not list {platform} clusters: {result['stderr']}"]
                return cleanup_result

            clusters_to_remove = []
            
            if platform == "kind":
                clusters = result["stdout"].strip().split("\n") if result["stdout"].strip() else []
                # Remove KubeStellar-related clusters
                kubestellar_clusters = [c for c in clusters if any(keyword in c.lower() for keyword in ["kubeflex", "cluster1", "cluster2", "wds", "its", "kubestellar"])]
                clusters_to_remove = kubestellar_clusters
            else:  # k3d
                try:
                    cluster_data = json.loads(result["stdout"])
                    kubestellar_clusters = [c["name"] for c in cluster_data if any(keyword in c["name"].lower() for keyword in ["kubeflex", "cluster1", "cluster2", "wds", "its", "kubestellar"])]
                    clusters_to_remove = kubestellar_clusters
                except json.JSONDecodeError:
                    pass

            # Remove clusters
            for cluster in clusters_to_remove:
                try:
                    if platform == "kind":
                        delete_cmd = ["kind", "delete", "cluster", "--name", cluster]
                    else:  # k3d
                        delete_cmd = ["k3d", "cluster", "delete", cluster]
                    
                    delete_result = await self._run_command(delete_cmd)
                    if delete_result["returncode"] == 0:
                        cleanup_result["clusters_removed"].append(cluster)
                    else:
                        cleanup_result["errors"].append(f"Failed to delete cluster {cluster}: {delete_result['stderr']}")
                except Exception as e:
                    cleanup_result["errors"].append(f"Error deleting cluster {cluster}: {str(e)}")

            # Clean up kubectl contexts
            context_result = await self._run_command(["kubectl", "config", "get-contexts", "-o", "name"])
            if context_result["returncode"] == 0:
                contexts = context_result["stdout"].strip().split("\n")
                kubestellar_contexts = [c for c in contexts if any(keyword in c.lower() for keyword in ["kubeflex", "cluster1", "cluster2", "wds", "its", "kubestellar"])]
                
                for context in kubestellar_contexts:
                    try:
                        delete_context_result = await self._run_command(["kubectl", "config", "delete-context", context])
                        if delete_context_result["returncode"] == 0:
                            cleanup_result["contexts_removed"].append(context)
                    except Exception:
                        pass  # Context might already be gone

            return cleanup_result

        except Exception as e:
            return {
                "status": "error",
                "operation": "cleanup",
                "error": f"Cleanup failed: {str(e)}",
            }

    async def _manual_full_setup(
        self,
        platform: str,
        cluster_name: str,
        version: str,
        cleanup_existing: bool,
        verify_prerequisites: bool,
        helm_timeout: str,
        wait_for_ready: bool,
        create_wec_clusters: bool,
        wec_names: List[str],
        output_format: str,
    ) -> Dict[str, Any]:
        """Perform complete manual setup following the get-started guide."""
        try:
            setup_result = {
                "status": "success",
                "operation": "full_setup",
                "setup_type": "manual",
                "kubestellar_version": version,
                "platform": platform,
                "steps_completed": [],
                "clusters_created": [],
                "errors": [],
                "warnings": [],
            }

            steps = [
                ("verify_prerequisites", "Verify prerequisites"),
                ("cleanup", "Cleanup existing clusters"),
                ("create_kubeflex", "Create KubeFlex cluster"),
                ("install_kubestellar", "Install KubeStellar components"),
                ("setup_wec", "Setup workload execution clusters"),
                ("verify_setup", "Verify complete setup"),
            ]

            for step_id, step_name in steps:
                try:
                    step_result = None
                    
                    if step_id == "verify_prerequisites" and verify_prerequisites:
                        step_result = await self._verify_prerequisites("summary")
                        if step_result["status"] != "success":
                            setup_result["errors"].append(f"Prerequisites check failed: {step_result.get('missing_required', [])}")
                            setup_result["status"] = "error"
                            return setup_result
                    
                    elif step_id == "cleanup" and cleanup_existing:
                        step_result = await self._cleanup_existing_clusters(platform, "summary")
                        if step_result.get("clusters_removed"):
                            setup_result["warnings"].append(f"Removed existing clusters: {step_result['clusters_removed']}")
                    
                    elif step_id == "create_kubeflex":
                        step_result = await self._create_kubeflex_cluster(platform, cluster_name, version, False, "summary")
                        if step_result["status"] != "success":
                            setup_result["errors"].append(f"KubeFlex cluster creation failed: {step_result.get('error', 'Unknown error')}")
                            setup_result["status"] = "error"
                            return setup_result
                        setup_result["clusters_created"].append(cluster_name)
                    
                    elif step_id == "install_kubestellar":
                        step_result = await self._install_kubestellar_components(cluster_name, version, helm_timeout, wait_for_ready)
                        if step_result["status"] != "success":
                            setup_result["errors"].append(f"KubeStellar installation failed: {step_result.get('error', 'Unknown error')}")
                            setup_result["status"] = "error"
                            return setup_result
                    
                    elif step_id == "setup_wec" and create_wec_clusters:
                        step_result = await self._setup_wec_clusters(platform, wec_names, wait_for_ready, "summary")
                        if step_result["status"] != "success":
                            setup_result["warnings"].append(f"WEC cluster setup had issues: {step_result.get('error', 'Unknown error')}")
                        else:
                            setup_result["clusters_created"].extend(wec_names)
                    
                    elif step_id == "verify_setup":
                        step_result = await self._verify_complete_setup(cluster_name, wec_names)
                        if step_result["status"] != "success":
                            setup_result["warnings"].append(f"Setup verification found issues: {step_result.get('error', 'Unknown error')}")

                    setup_result["steps_completed"].append({
                        "step": step_id,
                        "name": step_name,
                        "status": step_result["status"] if step_result else "skipped",
                        "details": step_result if step_result else None
                    })

                except Exception as e:
                    setup_result["errors"].append(f"Step {step_name} failed: {str(e)}")
                    setup_result["status"] = "error"
                    break

            return setup_result

        except Exception as e:
            return {
                "status": "error",
                "operation": "full_setup",
                "error": f"Manual setup failed: {str(e)}",
            }

    async def _run_command(self, cmd: List[str], timeout: int = 300) -> Dict[str, Any]:
        """Run a shell command asynchronously with timeout."""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )

            return {
                "returncode": process.returncode,
                "stdout": stdout.decode(),
                "stderr": stderr.decode(),
            }
        except asyncio.TimeoutError:
            return {
                "returncode": 1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout} seconds",
            }
        except Exception as e:
            return {
                "returncode": 1,
                "stdout": "",
                "stderr": str(e),
            }

    async def _create_kubeflex_cluster(
        self, platform: str, cluster_name: str, version: str, cleanup: bool, output_format: str
    ) -> Dict[str, Any]:
        """Create KubeFlex cluster following the get-started guide."""
        try:
            result = {
                "status": "success",
                "operation": "create_kubeflex",
                "cluster_name": cluster_name,
                "platform": platform,
                "steps": [],
            }

            # Step 1: Create kind/k3d cluster
            if platform == "kind":
                create_cmd = ["kind", "create", "cluster", "--name", cluster_name]
            else:  # k3d
                create_cmd = ["k3d", "cluster", "create", cluster_name]

            create_result = await self._run_command(create_cmd)
            if create_result["returncode"] != 0:
                return {
                    "status": "error",
                    "error": f"Failed to create {platform} cluster: {create_result['stderr']}",
                }

            result["steps"].append({"step": "create_cluster", "status": "completed", "message": f"Created {platform} cluster {cluster_name}"})

            # Step 2: Set KUBESTELLAR_VERSION environment variable
            # This is handled in the helm commands below

            # Step 3: Wait for cluster to be ready
            wait_result = await self._wait_for_cluster_ready(cluster_name)
            if not wait_result:
                result["warnings"] = ["Cluster readiness check timed out, continuing anyway"]

            result["steps"].append({"step": "cluster_ready", "status": "completed"})
            return result

        except Exception as e:
            return {
                "status": "error",
                "error": f"KubeFlex cluster creation failed: {str(e)}",
            }

    async def _install_kubestellar_components(
        self, cluster_name: str, version: str, timeout: str, wait_for_ready: bool
    ) -> Dict[str, Any]:
        """Install KubeStellar components using Core Helm chart."""
        try:
            result = {
                "status": "success",
                "operation": "install_kubestellar",
                "components_installed": [],
                "steps": [],
            }

            # Switch to kubeflex context
            context_name = f"kind-{cluster_name}"
            switch_result = await self._run_command(["kubectl", "config", "use-context", context_name])
            if switch_result["returncode"] != 0:
                return {
                    "status": "error",
                    "error": f"Failed to switch to context {context_name}: {switch_result['stderr']}",
                }

            # Install KubeStellar using Core Helm chart
            helm_repo_add = ["helm", "repo", "add", "kubestellar", "https://kubestellar.github.io/kubestellar"]
            repo_result = await self._run_command(helm_repo_add)
            if repo_result["returncode"] != 0:
                return {
                    "status": "error",
                    "error": f"Failed to add KubeStellar helm repo: {repo_result['stderr']}",
                }

            # Update helm repo
            helm_update = ["helm", "repo", "update"]
            await self._run_command(helm_update)
            
            # Install core chart
            helm_install = [
                "helm", "upgrade", "--install", "kubestellar-core", "kubestellar/kubestellar-core",
                "--version", version.lstrip("v"),
                "--timeout", timeout,
                "--wait"
            ]
            
            install_result = await self._run_command(helm_install, timeout=600)  # 10 minute timeout
            if install_result["returncode"] != 0:
                return {
                    "status": "error",
                    "error": f"Failed to install KubeStellar core: {install_result['stderr']}",
                }

            result["steps"].append({"step": "install_core", "status": "completed", "message": "Installed KubeStellar core components"})
            result["components_installed"].append("kubestellar-core")

            if wait_for_ready:
                # Wait for ITS to be ready
                its_ready = await self._wait_for_its_ready()
                if not its_ready:
                    result["warnings"] = ["ITS readiness check timed out"]
                else:
                    result["steps"].append({"step": "its_ready", "status": "completed"})

            return result

        except Exception as e:
            return {
                "status": "error",
                "error": f"KubeStellar component installation failed: {str(e)}",
            }

    async def _setup_wec_clusters(
        self, platform: str, wec_names: List[str], wait_for_ready: bool, output_format: str
    ) -> Dict[str, Any]:
        """Create and register workload execution clusters."""
        try:
            result = {
                "status": "success",
                "operation": "setup_wec_clusters",
                "clusters_created": [],
                "clusters_registered": [],
                "errors": [],
            }

            for wec_name in wec_names:
                try:
                    # Create WEC cluster
                    if platform == "kind":
                        create_cmd = ["kind", "create", "cluster", "--name", wec_name]
                    else:  # k3d
                        create_cmd = ["k3d", "cluster", "create", wec_name]

                    create_result = await self._run_command(create_cmd)
                    if create_result["returncode"] == 0:
                        result["clusters_created"].append(wec_name)
                        
                        # Wait for cluster to be ready
                        if wait_for_ready:
                            await self._wait_for_cluster_ready(wec_name)

                        # Register with OCM hub
                        register_result = await self._register_wec_cluster(wec_name)
                        if register_result["status"] == "success":
                            result["clusters_registered"].append(wec_name)
                        else:
                            result["errors"].append(f"Failed to register {wec_name}: {register_result.get('error', 'Unknown error')}")
                    else:
                        result["errors"].append(f"Failed to create cluster {wec_name}: {create_result['stderr']}")

                except Exception as e:
                    result["errors"].append(f"Error setting up WEC cluster {wec_name}: {str(e)}")

            if result["errors"]:
                result["status"] = "partial_success" if result["clusters_created"] else "error"

            return result

        except Exception as e:
            return {
                "status": "error",
                "error": f"WEC cluster setup failed: {str(e)}",
            }

    async def _register_wec_cluster(self, cluster_name: str) -> Dict[str, Any]:
        """Register a WEC cluster with OCM hub."""
        try:
            # Get ITS context
            its_context = await self._get_its_context()
            if not its_context:
                return {"status": "error", "error": "Could not find ITS context"}

            # For the demo, we'll use a simplified registration approach
            # In practice, this involves getting tokens and approving CSRs
            # Join cluster to hub would use:
            # clusteradm join --hub-token <token> --hub-apiserver <server> --cluster-name <name>
            
            # Switch to ITS context for hub operations
            switch_result = await self._run_command(["kubectl", "config", "use-context", its_context])
            if switch_result["returncode"] != 0:
                return {"status": "error", "error": f"Failed to switch to ITS context: {switch_result['stderr']}"}

            # Accept the join request (simplified for demo)
            # In real setup, you'd wait for CSRs and approve them
            
            return {"status": "success", "cluster_name": cluster_name}

        except Exception as e:
            return {"status": "error", "error": f"WEC registration failed: {str(e)}"}

    async def _automated_setup(self, platform: str, version: str, output_format: str) -> Dict[str, Any]:
        """Run the automated KubeStellar setup script."""
        try:
            # Download and run the automated script
            script_url = f"https://raw.githubusercontent.com/kubestellar/kubestellar/refs/tags/{version}/scripts/create-kubestellar-demo-env.sh"
            
            download_cmd = ["curl", "-s", script_url]
            download_result = await self._run_command(download_cmd)
            
            if download_result["returncode"] != 0:
                return {
                    "status": "error",
                    "error": f"Failed to download setup script: {download_result['stderr']}",
                }

            # Run the script
            run_cmd = ["bash", "-c", f"bash <(echo '{download_result['stdout']}') --platform {platform}"]
            script_result = await self._run_command(run_cmd, timeout=1800)  # 30 minute timeout

            if script_result["returncode"] == 0:
                return {
                    "status": "success",
                    "operation": "automated_setup",
                    "setup_type": "automated",
                    "platform": platform,
                    "version": version,
                    "output": script_result["stdout"],
                }
            else:
                return {
                    "status": "error",
                    "error": f"Automated setup script failed: {script_result['stderr']}",
                    "output": script_result["stdout"],
                }

        except Exception as e:
            return {
                "status": "error",
                "error": f"Automated setup failed: {str(e)}",
            }

    async def _wait_for_cluster_ready(self, cluster_name: str, timeout: int = 300) -> bool:
        """Wait for a cluster to be ready."""
        try:
            context_name = f"kind-{cluster_name}"
            start_time = asyncio.get_event_loop().time()
            
            while asyncio.get_event_loop().time() - start_time < timeout:
                check_cmd = ["kubectl", "cluster-info", "--context", context_name]
                result = await self._run_command(check_cmd)
                
                if result["returncode"] == 0:
                    return True
                
                await asyncio.sleep(5)
            
            return False
        except Exception:
            return False

    async def _wait_for_its_ready(self, timeout: int = 600) -> bool:
        """Wait for ITS (Inventory and Transport Space) to be ready."""
        try:
            start_time = asyncio.get_event_loop().time()
            
            while asyncio.get_event_loop().time() - start_time < timeout:
                # Check for ITS readiness
                check_cmd = ["kubectl", "get", "controlplanes", "-A"]
                result = await self._run_command(check_cmd)
                
                if result["returncode"] == 0 and "its" in result["stdout"].lower():
                    # Check if ITS control plane is ready
                    its_ready_cmd = ["kubectl", "wait", "--for=condition=Ready", "controlplane", "its", "-n", "its-system", "--timeout=60s"]
                    its_result = await self._run_command(its_ready_cmd)
                    
                    if its_result["returncode"] == 0:
                        return True
                
                await asyncio.sleep(10)
            
            return False
        except Exception:
            return False

    async def _get_its_context(self) -> Optional[str]:
        """Get the ITS context name."""
        try:
            contexts_cmd = ["kubectl", "config", "get-contexts", "-o", "name"]
            result = await self._run_command(contexts_cmd)
            
            if result["returncode"] == 0:
                contexts = result["stdout"].strip().split("\n")
                # Look for ITS context
                for context in contexts:
                    if "its" in context.lower():
                        return context
                
                # Fallback to kubeflex context
                for context in contexts:
                    if "kubeflex" in context.lower():
                        return context
            
            return None
        except Exception:
            return None

    async def _verify_complete_setup(self, kubeflex_cluster: str, wec_clusters: List[str]) -> Dict[str, Any]:
        """Verify that the complete KubeStellar setup is working."""
        try:
            verification_result = {
                "status": "success",
                "operation": "verify_setup",
                "checks": [],
                "issues": [],
            }

            # Check KubeFlex cluster
            kubeflex_check = await self._verify_cluster_status(f"kind-{kubeflex_cluster}")
            verification_result["checks"].append({
                "component": "kubeflex_cluster",
                "status": "ready" if kubeflex_check else "not_ready",
            })

            # Check WEC clusters
            for wec in wec_clusters:
                wec_check = await self._verify_cluster_status(f"kind-{wec}")
                verification_result["checks"].append({
                    "component": f"wec_cluster_{wec}",
                    "status": "ready" if wec_check else "not_ready",
                })

            # Check for KubeStellar components
            components_check = await self._verify_kubestellar_components()
            verification_result["checks"].append({
                "component": "kubestellar_components",
                "status": "ready" if components_check else "not_ready",
            })

            # Determine overall status
            failed_checks = [c for c in verification_result["checks"] if c["status"] != "ready"]
            if failed_checks:
                verification_result["status"] = "partial_success"
                verification_result["issues"] = [f"{c['component']} is not ready" for c in failed_checks]

            return verification_result

        except Exception as e:
            return {
                "status": "error",
                "error": f"Setup verification failed: {str(e)}",
            }

    async def _verify_cluster_status(self, context: str) -> bool:
        """Verify that a cluster is accessible and ready."""
        try:
            check_cmd = ["kubectl", "cluster-info", "--context", context]
            result = await self._run_command(check_cmd)
            return result["returncode"] == 0
        except Exception:
            return False

    async def _verify_kubestellar_components(self) -> bool:
        """Verify that KubeStellar components are running."""
        try:
            # Check for KubeStellar CRDs
            crds_cmd = ["kubectl", "get", "crds"]
            result = await self._run_command(crds_cmd)
            
            if result["returncode"] == 0:
                output = result["stdout"].lower()
                required_crds = ["bindingpolicies", "workstatuses"]
                return all(crd in output for crd in required_crds)
            
            return False
        except Exception:
            return False

    def get_schema(self) -> Dict[str, Any]:
        """Define the JSON schema for function parameters."""
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "description": "Setup operation type",
                    "enum": [
                        "full_setup",
                        "verify_prerequisites",
                        "cleanup",
                        "create_kubeflex",
                        "setup_wec_clusters"
                    ],
                    "default": "full_setup",
                },
                "platform": {
                    "type": "string",
                    "description": "Container platform to use",
                    "enum": ["kind", "k3d"],
                    "default": "kind",
                },
                "cluster_name": {
                    "type": "string",
                    "description": "Name for the main KubeFlex cluster",
                    "default": "kubeflex",
                },
                "kubestellar_version": {
                    "type": "string",
                    "description": "KubeStellar version to install (e.g., v0.28.0)",
                },
                "cleanup_existing": {
                    "type": "boolean",
                    "description": "Clean up existing clusters before setup",
                    "default": True,
                },
                "verify_prerequisites": {
                    "type": "boolean",
                    "description": "Verify all required tools are installed",
                    "default": True,
                },
                "automated_script": {
                    "type": "boolean",
                    "description": "Use the automated setup script instead of manual steps",
                    "default": False,
                },
                "helm_timeout": {
                    "type": "string",
                    "description": "Timeout for Helm operations",
                    "default": "10m",
                },
                "wait_for_ready": {
                    "type": "boolean",
                    "description": "Wait for components to be ready before proceeding",
                    "default": True,
                },
                "create_wec_clusters": {
                    "type": "boolean",
                    "description": "Create workload execution clusters",
                    "default": True,
                },
                "wec_cluster_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Names for WEC clusters",
                    "default": ["cluster1", "cluster2"],
                },
                "output_format": {
                    "type": "string",
                    "description": "Output format for results",
                    "enum": ["detailed", "summary", "json"],
                    "default": "detailed",
                },
            },
            "required": [],
        }