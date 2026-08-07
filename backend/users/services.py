from typing import Tuple
from rest_framework import serializers

from .models import Node, Effects
from .serializers import NodeSerializer, TeamSerializer, SubmitResponseSerializer


def process_submit(user, node_id) -> Tuple[int, serializers.Serializer]:
    """Process a submit request"""
    node = Node.objects.get(pk=node_id)
    team = user.team
    if not team:
        # user without a team
        resp = SubmitResponseSerializer({"detail": "User is not part of any team."})
        return 400, resp

    current_node = team.current_node
    # First node assignment
    if not current_node:
        team.current_node = node
        team.head = node
        team.save()
        data_serializer = NodeSerializer(node)
        resp = SubmitResponseSerializer({"detail": "Success", "data": data_serializer.data})
        return 200, resp

    # Win condition – when the next node points back to the head
    if current_node.next_node == team.head:
        team.score += node.score
        team.save()
        team_serializer = TeamSerializer(team)
        resp = SubmitResponseSerializer({"detail": "You Win!", "data": team_serializer.data})
        return 200, resp

    # Wrong answer
    if current_node.next_node_id != node.id:
        team.life -= 1
        team.current_node = team.last_checkpoint
        team.save()
        resp = SubmitResponseSerializer({"detail": "Wrong answer"})
        return 400, resp

    # Correct answer
    team.current_node = node
    if node.effects == Effects.JUNCTION:
        team.last_checkpoint = node
    team.score += node.score
    team.save()
    data_serializer = NodeSerializer(node)
    resp = SubmitResponseSerializer({"detail": "Success", "data": data_serializer.data})
    return 200, resp
