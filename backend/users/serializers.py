from rest_framework import serializers
from djoser.serializers import UserSerializer as DjoserUserSerializer
from .models import User, Team

# Re-export game serializers for backward-compatibility
from game.serializers import (
    NodeCreateSerializer,
    NodeUpdateSerializer,
    NodeSerializer,
    SubmitRequestSerializer,
    SubmitResponseSerializer,
    BasicTeamSerializer,
    TargetTeamsResponseSerializer,
    TargetAttackSerializer,
    MapNodeSerializer,
    MapEdgeSerializer,
    MapTeamStateSerializer,
    MapSkeletonNodeSerializer,
    MapSkeletonResponseSerializer,
    MapGraphResponseSerializer,
    EstablishRelationRequestSerializer,
    EstablishRelationResponseSerializer,
    RemoveRelationRequestSerializer,
    RemoveRelationResponseSerializer,
    ClearMapResponseSerializer,
    MapSerializer,
    GameSessionSerializer,
    TeamNodeSerializer,
    GameHistorySerializer,
)


class TeamMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'email')


class TeamSerializer(serializers.ModelSerializer):
    members = TeamMemberSerializer(source='user_set', many=True, read_only=True)

    class Meta:
        model = Team
        fields = ('id', 'name', 'score', 'life', 'attack', 'is_won', 'members')


class CustomUserSerializer(DjoserUserSerializer):
    team = TeamSerializer(read_only=True)

    class Meta(DjoserUserSerializer.Meta):
        fields = DjoserUserSerializer.Meta.fields + ('team',)


class StreamTicketSerializer(serializers.Serializer):
    ticket = serializers.CharField()


__all__ = [
    "TeamMemberSerializer",
    "TeamSerializer",
    "CustomUserSerializer",
    "StreamTicketSerializer",
    "NodeCreateSerializer",
    "NodeUpdateSerializer",
    "NodeSerializer",
    "SubmitRequestSerializer",
    "SubmitResponseSerializer",
    "BasicTeamSerializer",
    "TargetTeamsResponseSerializer",
    "TargetAttackSerializer",
    "MapNodeSerializer",
    "MapEdgeSerializer",
    "MapTeamStateSerializer",
    "MapSkeletonNodeSerializer",
    "MapSkeletonResponseSerializer",
    "MapGraphResponseSerializer",
    "EstablishRelationRequestSerializer",
    "EstablishRelationResponseSerializer",
    "RemoveRelationRequestSerializer",
    "RemoveRelationResponseSerializer",
    "ClearMapResponseSerializer",
    "MapSerializer",
    "GameSessionSerializer",
    "TeamNodeSerializer",
    "GameHistorySerializer",
]
