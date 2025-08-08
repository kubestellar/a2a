"""Lightweight consensus primitives for distributed agent decisions.

Implements a simple majority-vote proposal mechanism suitable for small
clusters of cooperating agents. Not a replacement for Raft/Paxos.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Dict, Optional

from .broker import A2ABroker
from .protocol import Message, MessageType


@dataclass
class ProposalResult:
    proposal_id: str
    accepted: bool
    votes_for: int
    votes_against: int
    total: int
    decided_ms: int


class MajorityConsensus:
    """Propose/collect votes with timeouts over the broker."""

    def __init__(self, broker: A2ABroker, agent_id: str) -> None:
        self.broker = broker
        self.agent_id = agent_id

    async def propose(self, topic: str, proposal: Dict, voters: int, timeout_ms: int = 1000) -> ProposalResult:
        proposal_id = proposal.get("id") or str(int(time.time() * 1000))
        msg = Message(
            type=MessageType.PROPOSAL,
            sender_id=self.agent_id,
            topic=topic,
            payload={"id": proposal_id, "proposal": proposal},
        )
        await self.broker.publish(msg)

        votes_for = 1  # self vote
        votes_against = 0
        deadline = time.time() + timeout_ms / 1000.0

        inbox = await self.broker.register_direct_inbox(self.agent_id)
        while time.time() < deadline and votes_for + votes_against < voters:
            try:
                remaining = max(0, deadline - time.time())
                resp: Message = await asyncio.wait_for(inbox.get(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            if resp.type == MessageType.VOTE and resp.payload.get("proposal_id") == proposal_id:
                if resp.payload.get("accept", False):
                    votes_for += 1
                else:
                    votes_against += 1

        accepted = votes_for > votes_against
        return ProposalResult(
            proposal_id=proposal_id,
            accepted=accepted,
            votes_for=votes_for,
            votes_against=votes_against,
            total=voters,
            decided_ms=int(time.time() * 1000),
        )


