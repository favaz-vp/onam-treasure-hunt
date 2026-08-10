from typing import Tuple
from rest_framework import serializers
from django.conf import settings
from .models import Node, Effects, TeamNode
from .serializers import NodeSerializer, TeamSerializer, SubmitResponseSerializer


def _record_node_visit(team, node):
    TeamNode.objects.get_or_create(team=team, node=node)

def process_submit(user, node_id) -> Tuple[int, serializers.Serializer]:
    """Process a submit request"""
    node = Node.objects.get(pk=node_id)
    team = user.team
    if not team:
        # user without a team
        resp = SubmitResponseSerializer({"detail": "User is not part of any team."})
        return 400, resp

    if team.life <= 0:
        resp = SubmitResponseSerializer({"detail": "Game Over! Your team has no lives left."})
        return 400, resp

    current_node = team.current_node
    # First node assignment
    if not current_node:
        if node.effects == Effects.JUNCTION:
            resp = SubmitResponseSerializer({"detail": "You cannot start with a junction node."})
            return 400, resp
        team.current_node = node
        team.head = node
        team.last_checkpoint = node
        team.save()
        _record_node_visit(team, node)
        data_serializer = NodeSerializer(node)
        resp = SubmitResponseSerializer({"detail": "Success", "data": data_serializer.data})
        return 200, resp
    else:
        if current_node == node:
            resp = SubmitResponseSerializer(
                {
                    "detail": "You’ve already submitted this answer. Please choose another one."
                }
            )
            return 400, resp

    # Wrong answer
    if not node.id in [current_node.next_node_id, current_node.alt_next_node_id]:
        team.life = max(1, team.life - 1)
        team.current_node = team.last_checkpoint
        team.save()
        resp = SubmitResponseSerializer({"detail": "Wrong answer"})
        return 400, resp

    # Correct answer
    team.current_node = node
    if node.effects == Effects.JUNCTION:
        team.last_checkpoint = node
    if not TeamNode.objects.filter(team=team, node=node).exists():
        max_health = getattr(settings, "MAX_TEAM_HEALTH", 5)
        team.score += node.score
        if team.life < max_health:
            team.life += 1
    team.save()
    _record_node_visit(team, node)
    # Win condition – when the next node points back to the head
    if node.next_node == team.head:
        team_serializer = TeamSerializer(team)
        resp = SubmitResponseSerializer({"detail": "You Win!", "data": team_serializer.data})
        return 200, resp
    data_serializer = NodeSerializer(node)
    resp = SubmitResponseSerializer({"detail": "Success", "data": data_serializer.data})
    return 200, resp
