from rest_framework import serializers
from djoser.serializers import UserSerializer as DjoserUserSerializer
from .models import User, Team, Node, Effects


class NodeSerializer(serializers.ModelSerializer):
    encoded_answer = serializers.SerializerMethodField()
    answers = serializers.SerializerMethodField()

    class Meta:
        model = Node
        fields = ['id', 'data', 'clue', 'encoded_answer', 'answers', 'effects', 'score', 'bonus', 'created_at']

    def get_encoded_answer(self, obj) -> str:
        return " ".join("*" * len(word) for word in obj.answer.split())

    def get_answers(self, obj) -> list:
        answers = []
        if obj.effects == Effects.JUNCTION:
            answers = [
                {
                    "id": obj.next_node.id,
                    "answer": obj.answer,           
                },
                {
                    "id": obj.alt_next_node.id,
                    "answer": obj.alt_answer,           
                },
            ]
        return answers

class TeamMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'email')

class TeamSerializer(serializers.ModelSerializer):
    members = TeamMemberSerializer(source='user_set', many=True, read_only=True)

    class Meta:
        model = Team
        fields = ('id', 'name', 'score', 'life', 'attack', 'members')

class CustomUserSerializer(DjoserUserSerializer):
    team = TeamSerializer(read_only=True)

    class Meta(DjoserUserSerializer.Meta):
        fields = DjoserUserSerializer.Meta.fields + ('team',)

class SubmitRequestSerializer(serializers.Serializer):
    # No body required
    pass

class SubmitResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()
    data = serializers.JSONField(required=False)


class BasicTeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ("id", "name", "score", "life", "attack")


class TargetTeamsResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()
    data = BasicTeamSerializer(many=True)


class TargetAttackSerializer(serializers.Serializer):
    target_team = serializers.IntegerField()
    attack_value = serializers.IntegerField(min_value=1)


class StreamTicketSerializer(serializers.Serializer):
    ticket = serializers.CharField()
