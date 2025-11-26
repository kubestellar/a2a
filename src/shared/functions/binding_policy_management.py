from __future__ import annotations

import json
from collections.abc import MutableMapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List

import yaml

from src.shared.base_functions import BaseFunction
from src.shared.utils import run_subprocess_with_cancellation


@dataclass
class BPResult:
    name: str
    namespace: str
    status: str
    bindingMode: str
    clusters: List[str]
    workloads: List[str]
    creationTimestamp: str
    yaml: str


class BindingPolicyManagement(BaseFunction):
    """
    Lightweight Binding-Policy helper.

    Operations
    ----------
    list          – list all BPs in the given WDS context
    create        – apply a raw YAML / JSON manifest
    delete        – delete BP by name
    quick_create  – build a BP from plain parameters (cluster-labels, resources …)
    """

    def __init__(self) -> None:
        super().__init__(
            name="binding_policy_management",
            description="Fast operations on KubeStellar BindingPolicy objects "
                        "(list, create, delete, quick-create) against a single WDS."
        )

    def _convert_to_native(self, obj: Any) -> Any:
        """
        Recursively convert protobuf-like objects (MapComposite, RepeatedComposite)
        and other structures to native Python dicts and lists.
        """
        if obj is None:
            return None
        if isinstance(obj, (str, int, float, bool)):
            return obj
        
        # Explicitly handle protobuf MapComposite/RepeatedComposite by type name
        # This catches objects that might not pass standard ABC checks
        type_str = str(type(obj))
        if 'MapComposite' in type_str and hasattr(obj, 'items'):
            return {k: self._convert_to_native(v) for k, v in obj.items()}
        if 'RepeatedComposite' in type_str and hasattr(obj, '__iter__'):
            return [self._convert_to_native(i) for i in obj]

        # Convert Dict/Mapping
        if isinstance(obj, (dict, MutableMapping)):
            return {k: self._convert_to_native(v) for k, v in obj.items()}
        
        # Convert List/Sequence (exclude str/bytes)
        if isinstance(obj, (list, tuple, Sequence)) and not isinstance(obj, (str, bytes)):
            return [self._convert_to_native(i) for i in obj]
            
        return obj

    async def execute(
        self,
        operation: str = "list",                     # list | create | delete | quick_create
        context: str = "wds1",
        kubeconfig: str = "",
        policy_yaml: str = "",
        policy_json: Dict[str, Any] | None = None,
        policy_name: str = "",
        selector_labels: Dict[str, str] | None = None,
        resources: List[str] | None = None,          # "apps/deployments", "core/namespaces"
        namespaces: List[str] | None = None,
        specific_workloads: List[Dict[str, str]] | None = None,
        # Advanced features
        cluster_selectors: List[Dict[str, Any]] | None = None,  # Complex cluster selectors with OR logic
        object_selectors: List[Dict[str, Any]] | None = None,   # Multiple object selectors with OR logic
        want_singleton_reported_state: bool = False,            # Status aggregation
        subject: Dict[str, Any] | None = None,                  # Subject for the BindingPolicy
        **_: Any,
    ) -> Dict[str, Any]:
        """
        Execute binding policy operations for KubeStellar workload distribution.
        
        Args:
            operation (str): Operation type to perform.
                Options: 'list', 'create', 'delete', 'quick_create'
                Default: 'list'
                - 'list': Show all existing binding policies
                - 'create': Apply a raw YAML/JSON manifest
                - 'delete': Remove a binding policy by name
                - 'quick_create': Build a policy from parameters
            
            context (str): WDS (Workload Description Space) context name.
                The Kubernetes context where binding policies are stored.
                Default: 'wds1'
                Example: 'wds1', 'wds2'
            
            kubeconfig (str, optional): Path to kubeconfig file.
                Uses default kubeconfig if not specified.
                Example: '/path/to/kubeconfig'
            
            policy_yaml (str, optional): Raw YAML manifest for create operation.
                Complete binding policy definition in YAML format.
                Used when operation='create'.
                Example:
                ```
                apiVersion: control.kubestellar.io/v1alpha1
                kind: BindingPolicy
                metadata:
                  name: nginx-bpolicy
                spec:
                  clusterSelectors:
                  - matchLabels:
                      location-group: edge
                ```
            
            policy_json (Dict[str, Any], optional): JSON object for create operation.
                Alternative to policy_yaml. Same structure in JSON format.
                Used when operation='create'.
            
            policy_name (str, optional): Name for the binding policy.
                Required for create and delete operations.
                Example: 'nginx-bpolicy', 'production-policy'
            
            selector_labels (Dict[str, str], optional): Labels to select clusters.
                Clusters with these labels will receive the workloads.
                Used for quick_create operation.
                Example: {'location-group': 'edge', 'environment': 'production'}
            
            resources (List[str], optional): Resource types to bind.
                Format: 'apiGroup/resource' (e.g., 'apps/deployments', 'core/namespaces').
                Use 'core' for core API group.
                Used for quick_create operation.
                Example: ['apps/deployments', 'core/services']
            
            namespaces (List[str], optional): Namespaces where policy applies.
                Restricts policy to specific namespaces.
                Used for quick_create operation.
                Example: ['default', 'production']
            
            specific_workloads (List[Dict[str, str]], optional): Specific workloads to bind.
                Array of objects with apiVersion, kind, name, namespace fields.
                Used for targeting specific workloads instead of all matching resources.
                Example: [{
                    'apiVersion': 'apps/v1',
                    'kind': 'Deployment', 
                    'name': 'nginx',
                    'namespace': 'default'
                }]
            
            cluster_selectors (List[Dict[str, Any]], optional): Complex cluster selectors with OR logic.
                Array of cluster selector objects for advanced matching.
                Supports multiple selectors that will be combined with OR logic.
                Used for quick_create operation.
                Example: [
                    {'matchLabels': {'tier': 'frontend'}},
                    {'matchLabels': {'tier': 'backend'}}
                ]
            
            object_selectors (List[Dict[str, Any]], optional): Multiple object selectors with OR logic.
                Array of object selector objects for advanced workload matching.
                Supports multiple selectors that will be combined with OR logic.
                Used for quick_create operation.
                Example: [
                    {'matchLabels': {'app': 'web-app'}},
                    {'matchLabels': {'app': 'api-service'}}
                ]
            
            want_singleton_reported_state (bool, optional): Enable status aggregation.
                When true, enables singleton reported state for the BindingPolicy.
                Default: false
                Used for quick_create operation.
            
            subject (Dict[str, Any], optional): Subject for the BindingPolicy.
                Defines the subject for workload binding.
                Used for quick_create operation.
                Example: {'name': 'user1', 'kind': 'User', 'apiGroup': 'rbac.authorization.k8s.io'}
        
        Returns:
            Dict[str, Any]: Operation result containing:
                - status: 'success' or 'error'
                - operation: Type of operation performed
                - For 'list': Array of binding policies with details
                - For 'create'/'quick_create': Creation confirmation
                - For 'delete': Deletion confirmation
                - error: Error message if status='error'
        
        Examples:
            # List all policies
            >>> binding_policy_management(operation='list')
            
            # Quick create with parameters
            >>> binding_policy_management(
            ...     operation='quick_create',
            ...     policy_name='nginx-bpolicy',
            ...     selector_labels={'location-group': 'edge'},
            ...     resources=['apps/deployments'],
            ...     namespaces=['default']
            ... )
            
            # Create from YAML
            >>> binding_policy_management(
            ...     operation='create',
            ...     policy_yaml=yaml_content
            ... )
            
            # Delete policy
            >>> binding_policy_management(
            ...     operation='delete',
            ...     policy_name='nginx-bpolicy'
            ... )
            
            # Advanced quick create with complex selectors
            >>> binding_policy_management(
            ...     operation='quick_create',
            ...     policy_name='multi-app-policy',
            ...     cluster_selectors=[
            ...         {'matchLabels': {'tier': 'frontend'}},
            ...         {'matchLabels': {'tier': 'backend'}}
            ...     ],
            ...     object_selectors=[
            ...         {'matchLabels': {'app': 'web-app'}},
            ...         {'matchLabels': {'app': 'api-service'}}
            ...     ],
            ...     resources=['apps/deployments', 'core/services'],
            ...     want_singleton_reported_state=True
            ... )
        """
        # validating the arguments :))
        operation = self._convert_to_native(operation)
        context = self._convert_to_native(context)
        kubeconfig = self._convert_to_native(kubeconfig)
        policy_yaml = self._convert_to_native(policy_yaml)
        policy_json = self._convert_to_native(policy_json)
        policy_name = self._convert_to_native(policy_name)
        selector_labels = self._convert_to_native(selector_labels)
        resources = self._convert_to_native(resources)
        namespaces = self._convert_to_native(namespaces)
        specific_workloads = self._convert_to_native(specific_workloads)
        cluster_selectors = self._convert_to_native(cluster_selectors)
        object_selectors = self._convert_to_native(object_selectors)
        want_singleton_reported_state = self._convert_to_native(want_singleton_reported_state)
        subject = self._convert_to_native(subject)

        if isinstance(selector_labels, str):
            try:
                selector_labels = json.loads(selector_labels)
            except json.JSONDecodeError:
                k, _, v = selector_labels.partition("=")
                selector_labels = {k.strip(): v.strip()}
        if isinstance(resources, str):
            try:
                resources = json.loads(resources)
            except json.JSONDecodeError:
                resources = [s.strip() for s in resources.split(",") if s.strip()]
        if isinstance(namespaces, str):
            try:
                namespaces = json.loads(namespaces)
            except json.JSONDecodeError:
                namespaces = [s.strip() for s in namespaces.split(",") if s.strip()]
        def _as_dict(obj):
            return dict(obj) if not isinstance(obj, dict) else obj
        def _as_list(obj):
            return list(obj) if not isinstance(obj, list) else obj
        
        if selector_labels not in (None, "", {}):
            selector_labels = _as_dict(selector_labels)
        if resources not in (None, "", []):
            resources = _as_list(resources)
        if namespaces not in (None, "", []):
            namespaces = _as_list(namespaces)

        if operation == "quick_create":
            if not resources or resources in (None, "", []):
                return {
                    "status": "error", 
                    "error": "resources parameter is REQUIRED for quick_create operation. Example: ['apps/deployments', 'core/services']"
                }

        if operation == "create" and not (policy_yaml or policy_json) \
           and selector_labels and resources:
            operation = "quick_create"

        if operation == "list":
            return await self._op_list(context, kubeconfig)

        if operation == "create":
            if not (policy_yaml or policy_json):
                return {"status": "error", "error": "policy_yaml or policy_json required"}
            manifest = policy_yaml or yaml.safe_dump(policy_json, sort_keys=False)
            return await self._kubectl_apply(manifest, context, kubeconfig)
            
        if operation == "delete":
            if not policy_name:
                return {"status": "error", "error": "policy_name required"}
            return await self._kubectl_delete(policy_name, context, kubeconfig)

        if operation == "quick_create":
            effective_selectors = cluster_selectors or selector_labels or {}
            
            manifest, err = self._build_quick_manifest(
                policy_name or "",
                effective_selectors,
                resources or [],
                namespaces or [],
                specific_workloads or [],
                cluster_selectors=cluster_selectors,
                object_selectors=object_selectors,
                want_singleton_reported_state=want_singleton_reported_state,
                subject=subject
            )
            if err:
                return {"status": "error", "error": err}
            return await self._kubectl_apply(manifest, context, kubeconfig)

        return {"status": "error", "error": f"unknown operation {operation}"}

    async def _op_list(self, ctx: str, kubeconfig: str) -> Dict[str, Any]:
        cmd = ["kubectl", "--context", ctx, "get",
               "bindingpolicies.control.kubestellar.io", "-o", "json"]
        if kubeconfig:
            cmd += ["--kubeconfig", kubeconfig]
        ret = await self._run(cmd)
        if ret["returncode"] != 0:
            return {"status": "error", "error": ret["stderr"]}

        items = json.loads(ret["stdout"]).get("items", [])
        results = [self._make_result(i) for i in items]

        return {
            "status": "success",
            "operation": "list",
            "total": len(results),
            "policies": [r.__dict__ for r in results],
        }

    def _build_quick_manifest(
        self,
        name: str,
        selector_labels: Dict[str, str],
        resources: List[str],
        namespaces: List[str],
        specific_wl: List[Dict[str, str]],
        cluster_selectors: List[Dict[str, Any]] | None = None,
        object_selectors: List[Dict[str, Any]] | None = None,
        want_singleton_reported_state: bool = False,
        subject: Dict[str, Any] | None = None,
    ) -> tuple[str, str | None]:
        # Accept either cluster_selectors (new) or selector_labels (old)
        if not cluster_selectors and not selector_labels:
            return "", "cluster_selectors or selector_labels cannot be empty"
        if not resources:
            return "", "resources list cannot be empty"
        if not name:
            name = f"bp-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        if object_selectors:
             object_selectors = self._convert_to_native(object_selectors)
             if not isinstance(object_selectors, list):
                 object_selectors = [object_selectors]

        down = []
        for entry in resources:
            grp, _, res = entry.partition("/")
            rule: Dict[str, Any] = {"resources": [res]}
            if grp and grp != "core":
                rule["apiGroup"] = grp
            if namespaces:
                rule["namespaces"] = namespaces
            
            if object_selectors:
                rule["objectSelectors"] = object_selectors
            
            if want_singleton_reported_state:
                rule["wantSingletonReportedState"] = True
                
            down.append(rule)

        if cluster_selectors:
            if isinstance(cluster_selectors, list):
                cluster_selectors_list = cluster_selectors
            else:
                cluster_selectors_list = [cluster_selectors]
        else:
            # Convert old selector_labels to new format
            cluster_selectors_list = [{"matchLabels": selector_labels}]
        
        manifest = {
            "apiVersion": "control.kubestellar.io/v1alpha1",
            "kind": "BindingPolicy",
            "metadata": {"name": name},
            "spec": {
                "clusterSelectors": cluster_selectors_list,
                "downsync": down,
            },
        }

        
        if subject:
            manifest["spec"]["subject"] = subject
        
        def _fix_kubernetes_operators(obj):
            """Fix invalid Kubernetes operators in matchExpressions"""
            if isinstance(obj, dict):
                fixed = {}
                for k, v in obj.items():
                    if k == 'operator' and isinstance(v, str):
                        if v.lower() in ['equals', 'equal', '=', '==']:
                            fixed[k] = 'In'
                        elif v.lower() in ['not_equals', 'notequal', '!=', '<>']:
                            fixed[k] = 'NotIn'
                        elif v.lower() in ['exists', 'present']:
                            fixed[k] = 'Exists'
                        elif v.lower() in ['not_exists', 'absent', '!exists']:
                            fixed[k] = 'DoesNotExist'
                        else:
                            fixed[k] = v
                    else:
                        fixed[k] = _fix_kubernetes_operators(v)
                return fixed
            elif isinstance(obj, list):
                return [_fix_kubernetes_operators(item) for item in obj]
            return obj
        
        manifest = _fix_kubernetes_operators(manifest)
                
        manifest = self._convert_to_native(manifest)

        if specific_wl:
            clean_specific_wl = self._convert_to_native(specific_wl)
            
            if clean_specific_wl:
                wl = clean_specific_wl[0]
                manifest["metadata"].setdefault("annotations", {})["specificWorkloads"] = ",".join([
                    wl.get("apiVersion", ""),
                    wl.get("kind", ""),
                    wl.get("name", ""),
                    wl.get("namespace", "")
                ])

        return yaml.safe_dump(manifest, sort_keys=False), None

    # ───────────────────────── kubectl helpers ─────────────────────────
    async def _kubectl_apply(self, yaml_body: str, ctx: str, kubeconfig: str) -> Dict[str, Any]:
        cmd = ["kubectl", "--context", ctx, "apply", "-f", "-"]
        if kubeconfig:
            cmd += ["--kubeconfig", kubeconfig]
        ret = await self._run(cmd, stdin_data=yaml_body.encode())
        if ret["returncode"] != 0:
           # include both stdout & stderr in the response so the LLM can show it
           return {
               "status": "error",
               "operation": "apply",
               "stderr": ret["stderr"],
               "stdout": ret["stdout"],
               "cmd": " ".join(cmd[:4]) + " -f -",   # truncated for readability
           }
        status = "success" if ret["returncode"] == 0 else "error"
        return {"status": status, "operation": "apply", "output": ret["stdout"] or ret["stderr"]}

    async def _kubectl_delete(self, name: str, ctx: str, kubeconfig: str) -> Dict[str, Any]:
        cmd = ["kubectl", "--context", ctx, "delete", "bindingpolicy", name]
        if kubeconfig:
            cmd += ["--kubeconfig", kubeconfig]
        ret = await self._run(cmd)
        status = "success" if ret["returncode"] == 0 else "error"
        return {"status": status, "operation": "delete", "output": ret["stdout"] or ret["stderr"]}

    async def _run(self, cmd: List[str], stdin_data: bytes | None = None) -> Dict[str, str]:
        """Run command with cancellation support."""
        return await run_subprocess_with_cancellation(cmd, stdin_data)

    # ───────────────────────── result helpers ─────────────────────────
    def _make_result(self, item: Dict[str, Any]) -> BPResult:
        meta = item["metadata"]
        spec = item.get("spec", {})
        status = "active" if meta.get("generation") == item.get("status", {}).get(
            "observedGeneration"
        ) else "inactive"

        clusters: List[str] = []
        for sel in spec.get("clusterSelectors", []):
            labs = sel.get("matchLabels", {})
            if "kubernetes.io/cluster-name" in labs:
                clusters.append(labs["kubernetes.io/cluster-name"])
            else:
                clusters += [f"{k}:{v}" for k, v in labs.items()]

        wls: List[str] = []
        for ds in spec.get("downsync", []):
            grp = ds.get("apiGroup") or "core"
            for res in ds.get("resources", []):
                base = f"{grp}/{res.lower()}"
                if ds.get("namespaces"):
                    wls += [f"{base} (ns:{ns})" for ns in ds["namespaces"]]
                else:
                    wls.append(base)

        return BPResult(
            name=meta["name"],
            namespace=meta.get("namespace", ""),
            status=status,
            bindingMode="Downsync",
            clusters=sorted(set(clusters)),
            workloads=sorted(set(wls)),
            creationTimestamp=meta.get("creationTimestamp", ""),
            yaml=yaml.safe_dump(item, sort_keys=False),
        )

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["list", "create", "delete", "quick_create"],
                    "default": "list",
                },
                "context": {"type": "string", "default": "wds1", "description": "WDS context name"},
                "kubeconfig": {"type": "string"},
                "policy_yaml": {"type": "string"},
                "policy_json": {"type": "object"},
                "policy_name": {"type": "string"},
                "selector_labels": {"type": "object", "description": "OLD parameter - use cluster_selectors instead"},
                "cluster_selectors": {
                    "type": "array", 
                    "items": {"type": "object"},
                    "description": "Advanced cluster selectors with matchLabels and matchExpressions"
                },
                "resources": {
                    "type": "array", 
                    "items": {"type": "string"},
                    "description": "Resource types to bind. REQUIRED for quick_create. Example: ['apps/deployments', 'core/services']"
                },
                "namespaces": {"type": "array", "items": {"type": "string"}},
                "specific_workloads": {"type": "array", "items": {"type": "object"}},
                "object_selectors": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Multiple object selectors with OR logic"
                },
                "want_singleton_reported_state": {
                    "type": "boolean",
                    "description": "Status aggregation",
                    "default": False
                },
                "subject": {"type": "object", "description": "Subject for the BindingPolicy"},
            },
            "required": [],
            "allOf": [
                {
                    "if": {"properties": {"operation": {"const": "quick_create"}}},
                    "then": {
                        "required": ["resources"],
                        "properties": {
                            "resources": {
                                "type": "array", 
                                "items": {"type": "string"},
                                "description": "Resource types to bind. REQUIRED for quick_create. Example: ['apps/deployments', 'core/services']"
                            }
                        }
                    }
                }
            ]
        }
        