from __future__ import annotations

import asyncio, json, yaml
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List

from src.shared.base_functions import BaseFunction


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

    # ───────────────────────── Public entry ─────────────────────────
    async def execute(
        self,
        operation: str = "list",                     # list | create | delete | quick_create
        wds_context: str = "wds1",
        kubeconfig: str = "",
        # create / delete
        policy_yaml: str = "",
        policy_json: Dict[str, Any] | None = None,
        policy_name: str = "",
        # quick-create
        selector_labels: Dict[str, str] | None = None,
        resources: List[str] | None = None,          # "apps/deployments", "core/namespaces"
        namespaces: List[str] | None = None,
        specific_workloads: List[Dict[str, str]] | None = None,
        **_: Any,
    ) -> Dict[str, Any]:
        if isinstance(selector_labels, str):
            try:
                selector_labels = json.loads(selector_labels)
            except json.JSONDecodeError:
                # accept simple "key=value" shorthand
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
        # ------------------------------------------------------------------
        # IMPROVE robustness of incoming parameters
        # - the chat wrapper sometimes sends Google's MapComposite etc.
        # ------------------------------------------------------------------
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

        # ------------------------------------------------------------------
        # If the wrapper asked for "create" but gave no YAML/JSON and DID
        # give selector_labels + resources, treat it as quick_create.
        # (must happen BEFORE the explicit create-branch)
        # ------------------------------------------------------------------
        if operation == "create" and not (policy_yaml or policy_json) \
           and selector_labels and resources:
            operation = "quick_create"

        if operation == "list":
            return await self._op_list(wds_context, kubeconfig)

        if operation == "create":
            if not (policy_yaml or policy_json):
                return {"status": "error", "error": "policy_yaml or policy_json required"}
            manifest = policy_yaml or yaml.safe_dump(policy_json, sort_keys=False)
            return await self._kubectl_apply(manifest, wds_context, kubeconfig)
            
        if operation == "delete":
            if not policy_name:
                return {"status": "error", "error": "policy_name required"}
            return await self._kubectl_delete(policy_name, wds_context, kubeconfig)

        if operation == "quick_create":
            manifest, err = self._build_quick_manifest(
                policy_name or "",
                selector_labels or {},
                resources or [],
                namespaces or [],
                specific_workloads or [],
            )
            if err:
                return {"status": "error", "error": err}
            return await self._kubectl_apply(manifest, wds_context, kubeconfig)

        return {"status": "error", "error": f"unknown operation {operation}"}

    # ───────────────────────── list ─────────────────────────
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

    # ───────────────────────── quick-create helpers ─────────────────────────
    def _build_quick_manifest(
        self,
        name: str,
        selector_labels: Dict[str, str],
        resources: List[str],
        namespaces: List[str],
        specific_wl: List[Dict[str, str]],
    ) -> tuple[str, str | None]:
        if not selector_labels:
            return "", "selector_labels cannot be empty"
        if not resources:
            return "", "resources list cannot be empty"
        if not name:
            name = f"bp-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        down = []
        for entry in resources:
            grp, _, res = entry.partition("/")
            rule: Dict[str, Any] = {"resources": [res]}
            if grp and grp != "core":
                rule["apiGroup"] = grp
            if namespaces:
                rule["namespaces"] = namespaces
            down.append(rule)

        bp = {
            "apiVersion": "control.kubestellar.io/v1alpha1",
            "kind": "BindingPolicy",
            "metadata": {"name": name},
            "spec": {
                "clusterSelectors": [{"matchLabels": selector_labels}],
                "downsync": down,
            },
        }

        if specific_wl:
            wl = specific_wl[0]
            bp["metadata"].setdefault("annotations", {})["specificWorkloads"] = ",".join(
                [wl.get("apiVersion", ""), wl.get("kind", ""),
                 wl.get("name", ""), wl.get("namespace", "")]
            )

        return yaml.safe_dump(bp, sort_keys=False), None

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
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE if stdin_data else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(input=stdin_data)
        return {
            "returncode": proc.returncode,
            "stdout": stdout.decode(),
            "stderr": stderr.decode(),
        }

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

    # ───────────────────────── JSON schema ─────────────────────────
    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["list", "create", "delete", "quick_create"],
                    "default": "list",
                },
                "wds_context": {"type": "string", "default": "wds1"},
                "kubeconfig": {"type": "string"},
                "policy_yaml": {"type": "string"},
                "policy_json": {"type": "object"},
                "policy_name": {"type": "string"},
                "selector_labels": {"type": "object"},
                "resources": {"type": "array", "items": {"type": "string"}},
                "namespaces": {"type": "array", "items": {"type": "string"}},
                "specific_workloads": {"type": "array", "items": {"type": "object"}},
            },
            "required": [],
        }