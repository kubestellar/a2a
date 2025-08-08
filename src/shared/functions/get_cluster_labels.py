"""Get labels from ManagedClusters for KubeStellar deployments.

This function helps users discover cluster labels to use with BindingPolicy
cluster selectors when deploying with KubeStellar.
"""

import asyncio
import json
from typing import Any, Dict, List

from ..base_functions import BaseFunction


class GetClusterLabelsFunction(BaseFunction):
    """Get labels from ManagedClusters in OCM/KubeStellar setup."""

    def __init__(self) -> None:
        super().__init__(
            name="get_cluster_labels",
            description="Get labels from ManagedClusters to help with KubeStellar BindingPolicy creation. Shows available cluster labels for use with cluster_selector_labels parameter in helm_deploy.",
        )

    async def execute(
        self,
        context: str = "",
        kubeconfig: str = "",
        output_format: str = "table",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Get ManagedCluster labels for KubeStellar deployments.
        
        Args:
            context: Kubernetes context to use (default: current context)
            kubeconfig: Path to kubeconfig file
            output_format: Output format (table, json, yaml)
            
        Returns:
            Dictionary with cluster information and labels
        """
        try:
            # Build kubectl command
            cmd = ["kubectl", "get", "managedclusters", "-A"]
            
            if output_format == "json":
                cmd.extend(["-o", "json"])
            elif output_format == "yaml":
                cmd.extend(["-o", "yaml"])
            else:
                cmd.append("--show-labels")
                
            if context:
                cmd.extend(["--context", context])
                
            if kubeconfig:
                cmd.extend(["--kubeconfig", kubeconfig])
                
            # Execute command
            result = await self._run_command(cmd)
            
            if result["returncode"] != 0:
                # Try without -A flag (some setups don't support it)
                cmd = ["kubectl", "get", "managedclusters"]
                if output_format == "json":
                    cmd.extend(["-o", "json"])
                elif output_format == "yaml":
                    cmd.extend(["-o", "yaml"])
                else:
                    cmd.append("--show-labels")
                if context:
                    cmd.extend(["--context", context])
                if kubeconfig:
                    cmd.extend(["--kubeconfig", kubeconfig])
                    
                result = await self._run_command(cmd)
                
            if result["returncode"] != 0:
                return {
                    "status": "error",
                    "error": result["stderr"] or "Failed to get ManagedClusters",
                    "suggestion": "Make sure you're connected to a hub/ITS cluster with OCM installed"
                }
                
            # Parse results based on format
            if output_format == "json":
                data = json.loads(result["stdout"])
                clusters = []
                
                for item in data.get("items", []):
                    cluster_info = {
                        "name": item["metadata"]["name"],
                        "labels": item["metadata"].get("labels", {}),
                        "status": item["status"].get("conditions", [{}])[0].get("type", "Unknown"),
                        "accepted": item["spec"].get("hubAcceptedManagedCluster", False)
                    }
                    clusters.append(cluster_info)
                    
                # Extract unique labels
                all_labels = {}
                for cluster in clusters:
                    for key, value in cluster["labels"].items():
                        if key not in all_labels:
                            all_labels[key] = set()
                        all_labels[key].add(value)
                        
                # Convert sets to lists for JSON serialization
                unique_labels = {k: list(v) for k, v in all_labels.items()}
                
                return {
                    "status": "success",
                    "clusters": clusters,
                    "unique_labels": unique_labels,
                    "total_clusters": len(clusters),
                    "example_selectors": self._generate_example_selectors(unique_labels)
                }
            else:
                # Return raw output for table/yaml format
                return {
                    "status": "success",
                    "output": result["stdout"],
                    "format": output_format
                }
                
        except Exception as e:
            return {
                "status": "error", 
                "error": str(e)
            }
            
    def _generate_example_selectors(self, labels: Dict[str, List[str]]) -> List[Dict[str, str]]:
        """Generate example cluster selector labels for BindingPolicy."""
        examples = []
        
        # Single label examples
        for key, values in labels.items():
            if key != "name":  # Skip name label as it's too specific
                for value in values[:2]:  # Limit to 2 examples per key
                    examples.append({key: value})
                    
        # Multi-label example if we have multiple keys
        if len(labels) > 1:
            multi_example = {}
            for i, (key, values) in enumerate(labels.items()):
                if i >= 2:  # Limit to 2 labels
                    break
                if key != "name" and values:
                    multi_example[key] = values[0]
            if multi_example:
                examples.append(multi_example)
                
        return examples[:5]  # Return max 5 examples
            
    async def _run_command(self, cmd: List[str]) -> Dict[str, Any]:
        """Execute command and return results."""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            return {
                "returncode": process.returncode,
                "stdout": stdout.decode("utf-8"),
                "stderr": stderr.decode("utf-8"),
            }
        except Exception as e:
            return {
                "returncode": 1,
                "stdout": "",
                "stderr": str(e),
            }

    def get_schema(self) -> Dict[str, Any]:
        """Return JSON schema for function parameters."""
        return {
            "type": "object",
            "properties": {
                "context": {
                    "type": "string",
                    "description": "Kubernetes context to use"
                },
                "kubeconfig": {
                    "type": "string", 
                    "description": "Path to kubeconfig file"
                },
                "output_format": {
                    "type": "string",
                    "enum": ["table", "json", "yaml"],
                    "description": "Output format",
                    "default": "table"
                }
            },
            "required": []
        }