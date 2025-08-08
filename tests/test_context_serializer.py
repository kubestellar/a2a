from src.a2a.context import SharedContext, ClusterSnapshot, ContextSerializer


def test_context_serialize_and_delta():
    ctx = SharedContext()
    assert ctx.get_delta_if_changed() is not None  # first snapshot yields delta

    # Update cluster and ensure hash changes
    ctx.update_cluster(
        ClusterSnapshot(
            name="c1",
            cluster_type="wec",
            resources_by_type={"pod": [{"name": "p1"}]},
            kubestellar_resources=[],
        )
    )
    delta = ctx.get_delta_if_changed()
    assert delta is not None

    # No changes → no delta
    assert ctx.get_delta_if_changed() is None

    # Serializer round trip
    text = ctx.serialize()
    h1 = ContextSerializer.hash(text)
    ctx2 = ContextSerializer.loads(text)
    assert "clusters" in ctx2
    assert isinstance(h1, str)


