import pytest

from src.shared.functions.kubestellar_context import (
    ExportKubeStellarContextFunction,
)
from src.a2a.context_manager import get_shared_context


@pytest.mark.asyncio
async def test_export_kubestellar_context_merges_results():
    fn = ExportKubeStellarContextFunction()
    result = await fn.execute(
        cluster_results={
            "cluster1": {
                "cluster_type": "wec",
                "resources_by_type": {"pod": [{"name": "p1"}]},
                "kubestellar_resources": [],
            }
        }
    )
    assert result["status"] == "success"
    # shared context should now contain cluster1
    ctx = get_shared_context()
    text = ctx.serialize()
    assert "cluster1" in text


