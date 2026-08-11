from typing import Tuple
from rest_framework import serializers
from django.conf import settings
from .models import Node, Effects, TeamNode, Team, GameHistory
from .serializers import NodeSerializer, TeamSerializer, SubmitResponseSerializer
from .sse import publish


def _record_node_visit(team, node):
    TeamNode.objects.get_or_create(team=team, node=node)


def record_game_history(team, node, action="Answered correctly"):
    return GameHistory.objects.create(
        team=team,
        node=node,
        action=action,
    )


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
        record_game_history(
            team=team,
            node=node,
            action="Started game",
        )
        data_serializer = NodeSerializer(node)
        resp = SubmitResponseSerializer(
            {"detail": "Game started successfully.", "data": data_serializer.data}
        )
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
        team.life = max(0, team.life - 1)
        team.current_node = team.last_checkpoint
        team.save()
        record_game_history(
            team=team,
            node=current_node,
            action="Answered incorrectly",
        )
        resp = SubmitResponseSerializer({"detail": "Wrong answer"})
        return 400, resp

    # Correct answer
    team.current_node = node
    if node.effects == Effects.JUNCTION:
        team.last_checkpoint = node
    
    if not TeamNode.objects.filter(team=team, node=node).exists() or team.head == node:
        team.score += node.score

        if node.attack > 0:
            team.attack += node.attack
            node.attack = 0  # Reset attack value after it's been used(Only first collected team get the attack value)
            node.save(update_fields=["attack"])

        if node.bonus > 0:
            team.score += node.bonus
            node.bonus = 0  # Reset bonus value after it's been used(Only first collected team get the bonus)
            node.save(update_fields=["bonus"])

        if node.life > 0:
            team.life += node.life
            node.life = 0  # Reset life value after it's been used(Only first collected team get the life)
            node.save(update_fields=["life"])

    team.save()
    _record_node_visit(team, node)
    record_game_history(
        team=team,
        node=node,
        action="Answered correctly",
    )

    # Win condition – when the next node points back to the head
    if current_node.next_node == node and node == team.head:
        team_serializer = TeamSerializer(team)
        resp = SubmitResponseSerializer({"detail": "You Win!", "data": team_serializer.data})
        return 200, resp
    data_serializer = NodeSerializer(node)
    resp = SubmitResponseSerializer({"detail": "Correct answer", "data": data_serializer.data})
    return 200, resp


def target_attack(attacking_team, target_team_id, attack_value) -> Tuple[int, serializers.Serializer]:
    try:
        target_team = Team.objects.get(pk=target_team_id)
    except Team.DoesNotExist:
        resp = SubmitResponseSerializer({"detail": "Target team does not exist.", "data": {"target_team_id": target_team_id}})
        return 400, resp

    if attacking_team.id == target_team.id:
        resp = SubmitResponseSerializer({"detail": "You cannot attack your own team.", "data": {"target_team": target_team.name}})
        return 400, resp

    if attacking_team.attack < attack_value:
        resp = SubmitResponseSerializer({"detail": "Not enough attack points to perform this attack.", "data": {"available_attack_points": attacking_team.attack}})
        return 400, resp

    # Deduct the life from the target team
    target_team.life = max(0, target_team.life - attack_value)
    target_team.save()

    # Deduct the attack points from the attacking team
    attacking_team.attack -= attack_value
    attacking_team.save()
    
    record_game_history(
        team=attacking_team,
        node=attacking_team.current_node,
        action=f"Attacked {target_team.name} for {attack_value} life points",
    )

    publish(target_team.id, "team_attacked", {
        "life": target_team.life,
        "score": target_team.score,
        "attack": target_team.attack,
        "attacked_by": attacking_team.name,
        "damage": attack_value,
        "detail": f"{attacking_team.name} attacked you for {attack_value} life points.",
    })
    publish(attacking_team.id, "team_update", {
        "life": attacking_team.life,
        "score": attacking_team.score,
        "attack": attacking_team.attack,
        "detail": f"You attacked {target_team.name} for {attack_value} life points.",
    })

    resp = SubmitResponseSerializer({"detail": f"Successfully attacked {target_team.name} for {attack_value} life points.", "data": {"target_team": target_team.name, "remaining_life": target_team.life}})
    return 200, resp
