"""Wire shapes for the API, plus the builders that fill them from models.

These replace the DRF serializers. Field order here is the field order on the
wire, and it deliberately matches what DRF emitted so existing clients see no
difference. msgspec renders datetimes the same way DRF did
(``2026-08-17T14:48:00.123456Z``), so ``created_at`` needs no special handling.

Serialising a Node depends on state that does not live on the Node — which
team is asking, and when that team visited it — so the conversions are plain
functions taking that context, rather than methods on the structs.
"""
from typing import Any

import msgspec
from msgspec import UNSET, UnsetType

from .models import Effects, Node, NodeStatus, TeamNode


class AnswerOut(msgspec.Struct):
    id: int
    answer: str
    is_nearest: bool


class NodeOut(msgspec.Struct):
    id: int
    data: str
    clue: str | None
    encoded_answer: str
    answers: list[AnswerOut]
    effects: str
    score: int
    bonus: int
    life: int
    attack: int
    created_at: Any
    status: str


class MemberOut(msgspec.Struct):
    id: int
    email: str


class BasicTeamOut(msgspec.Struct):
    id: int
    name: str
    score: int
    life: int
    attack: int
    is_won: bool


class TeamOut(msgspec.Struct):
    id: int
    name: str
    score: int
    life: int
    attack: int
    is_won: bool
    members: list[MemberOut]


class UserOut(msgspec.Struct):
    """The shape djoser's /users/me/ returned: USERNAME_FIELD, id, then team."""

    email: str
    id: int
    team: TeamOut | None


class DetailOut(msgspec.Struct, omit_defaults=True):
    """The ``{detail, data?}`` envelope the game endpoints answer with.

    ``data`` is UNSET rather than None so it is dropped from the JSON entirely
    when there is nothing to send, which is what DRF's ``required=False`` did.
    It stays untyped because its shape varies by endpoint — a node here, a
    team there, a bare pair of ids elsewhere.
    """

    detail: str
    data: Any | UnsetType = UNSET


class TargetTeamsOut(msgspec.Struct):
    detail: str
    data: list[BasicTeamOut]


class TargetAttackIn(msgspec.Struct):
    """The attack body.

    ``attack_value`` carries no msgspec constraint on purpose. Bolt answers a
    failed body constraint with 422, where DRF's ``min_value=1`` answered 400,
    so the range check happens in the handler and reports 400 like every other
    rejection this endpoint can produce.
    """

    target_team: int
    attack_value: int


class StreamTicketOut(msgspec.Struct):
    ticket: str


def encode_answer(answer: str) -> str:
    """Mask the answer, preserving word lengths, for the client-side hint."""
    return " ".join("*" * len(word) for word in answer.split())


def node_answers(node: Node) -> list[AnswerOut]:
    """The two branches of a junction, or nothing for an ordinary node."""
    if node.effects != Effects.JUNCTION:
        return []
    return [
        AnswerOut(
            id=node.next_node.id,
            answer=node.answer,
            is_nearest=node.next_node.is_nearest,
        ),
        AnswerOut(
            id=node.alt_next_node.id,
            answer=node.alt_answer,
            is_nearest=node.alt_next_node.is_nearest,
        ),
    ]


def node_status(node, team, team_node_map=None, current_node_created_at=None) -> str:
    """Where this node sits relative to the team's own progress.

    ``team_node_map``/``current_node_created_at`` are the batched form used by
    the visited-nodes listing, which has already loaded every TeamNode row it
    needs. Without them this falls back to querying per node, as the single
    node endpoints do.
    """
    if not team:
        return NodeStatus.COMPLETED

    if team.current_node_id and node.id == team.current_node_id:
        return NodeStatus.IN_PROGRESS

    if team_node_map is None:
        tn = TeamNode.objects.filter(team=team, node=node).first()
        if not tn:
            return NodeStatus.COMPLETED

        if team.current_node_id:
            cur_tn = TeamNode.objects.filter(
                team=team, node_id=team.current_node_id
            ).first()
            if cur_tn and tn.created_at > cur_tn.created_at:
                return NodeStatus.LOCKED
        return NodeStatus.COMPLETED

    obj_created_at = team_node_map.get(node.id)
    if obj_created_at and current_node_created_at and obj_created_at > current_node_created_at:
        return NodeStatus.LOCKED
    return NodeStatus.COMPLETED


def node_out(node, team=None, team_node_map=None, current_node_created_at=None) -> NodeOut:
    return NodeOut(
        id=node.id,
        data=node.data,
        clue=node.clue,
        encoded_answer=encode_answer(node.answer),
        answers=node_answers(node),
        effects=node.effects,
        score=node.score,
        bonus=node.bonus,
        life=node.life,
        attack=node.attack,
        created_at=node.created_at,
        status=node_status(node, team, team_node_map, current_node_created_at),
    )


def basic_team_out(team) -> BasicTeamOut:
    return BasicTeamOut(
        id=team.id,
        name=team.name,
        score=team.score,
        life=team.life,
        attack=team.attack,
        is_won=team.is_won,
    )


def team_out(team) -> TeamOut:
    return TeamOut(
        id=team.id,
        name=team.name,
        score=team.score,
        life=team.life,
        attack=team.attack,
        is_won=team.is_won,
        members=[
            MemberOut(id=member.id, email=member.email)
            for member in team.user_set.all()
        ],
    )


def user_out(user) -> UserOut:
    return UserOut(
        email=user.email,
        id=user.id,
        team=team_out(user.team) if user.team else None,
    )
