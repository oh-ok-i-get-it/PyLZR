"""Rules about Art-Net nodes, kept apart from sockets and Qt so they're
plain to test: which menu entries a set of ArtPollReplies makes
(node_choices), and when to ask a node "are you there?" and whether it has
answered recently (NodeWatch).
"""

import ipaddress
from collections.abc import Iterable
from dataclasses import dataclass

from .artnet import PollReply, PortAddress

_UNNAMED    = 'Art-Net node'
_NO_OUTPUTS = 'no DMX outputs (set it to Art-Net → DMX)'


@dataclass(frozen=True)
class NodeChoice:
    """One entry in the list of found nodes: send to `ip`, universe `port`."""

    label:   str                   # e.g. 'CR011R · 10.201.6.100 · 0:0:0'
    ip:      str
    port:    PortAddress | None    # None: shown, but can't be chosen
    tooltip: str = ''

    @property
    def enabled(self) -> bool:
        return self.port is not None


def node_choices(replies: Iterable[PollReply]) -> list[NodeChoice]:
    """One choice per DMX output of each node that replied, ordered by IP
    (as numbers) then universe. A node can answer with several replies (one
    per group of ports); they're combined, and an output reported twice is
    listed once. A node without outputs gets one entry that can't be chosen."""
    by_ip: dict[str, list[PollReply]] = {}
    for reply in replies:
        by_ip.setdefault(reply.ip, []).append(reply)

    choices = []
    for ip in sorted(by_ip, key=ipaddress.IPv4Address):
        group = by_ip[ip]
        main = min(group, key=lambda reply: reply.bind_index)     # the node's first reply
        name = main.short_name or main.long_name or _UNNAMED
        tooltip = '\n'.join(line for line in (main.long_name, main.report,
                                              f'MAC {main.mac}' if main.mac else '') if line)
        ports = sorted({port for reply in group for port in reply.outputs}, key=lambda port: port.value)
        if ports:
            choices += [NodeChoice(f'{name} · {ip} · {port}', ip, port, tooltip) for port in ports]
        else:
            choices.append(NodeChoice(f'{name} · {ip} — {_NO_OUTPUTS}', ip, None, tooltip))
    return choices


class NodeWatch:
    """When to ping a node, and whether it has answered lately. Time is
    counted in ticks (the caller's steady timer), so there's no clock.

    tick() moves time on and says when a ping is due: on the first tick
    after (re)starting, then every `ping_every` ticks. heard() records an
    answer; answered_by gives the node's name until that answer is more than
    `answer_within` ticks old.
    """

    def __init__(self, ping_every: int, answer_within: int):
        if not 1 <= ping_every <= answer_within:
            raise ValueError(f'need 1 ≤ ping_every ≤ answer_within, got {ping_every}, {answer_within}')
        self.ping_every    = ping_every
        self.answer_within = answer_within
        self._now = 0
        self.restart()

    def restart(self):
        """Forget any answer (e.g. a different node); ping on the next tick."""
        self._next_ping = self._now + 1
        self._heard_at: int | None = None
        self._name: str | None = None

    def tick(self) -> bool:
        """Move on one tick. True if a ping is due now."""
        self._now += 1
        if self._now < self._next_ping:
            return False
        self._next_ping = self._now + self.ping_every
        return True

    def heard(self, name: str):
        """The node answered (now)."""
        self._heard_at, self._name = self._now, name

    @property
    def answered_by(self) -> str | None:
        """The node's name if it answered within the last answer_within ticks."""
        if self._heard_at is None or self._now - self._heard_at > self.answer_within:
            return None
        return self._name
