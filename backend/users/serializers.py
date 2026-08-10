from rest_framework import serializers
from djoser.serializers import UserSerializer as DjoserUserSerializer
from .models import User, Team, Node, Effects


class NodeSerializer(serializers.ModelSerializer):
    clue = serializers.SerializerMethodField()
    clue_length = serializers.SerializerMethodField()
    answers = serializers.SerializerMethodField()

    class Meta:
        model = Node
        fields = ['id', 'data', 'clue', 'clue_length', 'answers', 'effects', 'score', 'bonus', 'created_at']

    def get_clue(self, obj) -> str:
        return ("_ " * len(obj.answer))[:-1]

    def get_clue_length(self, obj) -> str:
        return str(len(obj.answer))

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
        fields = ('id', 'name', 'score', 'life', 'members')

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
