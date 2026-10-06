from rest_framework import serializers
from .models import Map, Node, GameSession, TeamNode, GameHistory


class NodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Node
        fields = [
            'id',
            'map',
            'parent',
            'alt_parent',
            'data',
            'answer',
            'alt_answer',
            'effects',
            'score',
            'bonus',
            'attack',
            'life',
            'clue',
            'is_nearest',
            'position',
            'created_at',
        ]


class MapSerializer(serializers.ModelSerializer):
    nodes = NodeSerializer(many=True, read_only=True)

    class Meta:
        model = Map
        fields = ['id', 'name', 'description', 'is_active', 'nodes', 'created_at', 'updated_at']


class GameSessionSerializer(serializers.ModelSerializer):
    map_details = MapSerializer(source='map', read_only=True)

    class Meta:
        model = GameSession
        fields = [
            'id',
            'name',
            'map',
            'map_details',
            'status',
            'is_active',
            'start_time',
            'end_time',
            'created_at',
            'updated_at',
        ]


class TeamNodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeamNode
        fields = ['id', 'team', 'node', 'parent', 'created_at']


class GameHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = GameHistory
        fields = ['id', 'team', 'node', 'action', 'created_at']
