from django.conf import settings
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager


class Effects(models.TextChoices):
    JUNCTION = 'JUNCTION', 'Junction'
    UNLOCKED = 'UNLOCKED', 'Unlocked'


class NodeStatus(models.TextChoices):
    COMPLETED = 'completed', 'Completed'
    IN_PROGRESS = 'in-progress', 'In-Progress'
    LOCKED = 'locked', 'Locked'



class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        # Assign user to a team based on ID modulo number of teams
        # Create teams if needed
        from .models import Team
        if getattr(settings, 'CREATE_TEAMS', True):
            if Team.objects.count() == 0:
                team_objs = [Team(name=f"Team {i+1}", life=getattr(settings, "MAX_TEAM_HEALTH", 5)) for i in range(int(getattr(settings, 'TEAM_COUNT', 3)))]
                Team.objects.bulk_create(team_objs)
        teams = Team.objects.all()
        if teams.exists():
            team = teams[user.id % teams.count()]
            user.team = team
            user.save(update_fields=['team'])
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None  # Remove username field
    email = models.EmailField(unique=True)
    team = models.ForeignKey('users.Team', on_delete=models.SET_NULL, null=True, blank=True)
    is_captain = models.BooleanField(default=False)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()
    
    def __str__(self):
        return self.email


class Team(models.Model):
    name = models.CharField(max_length=100)
    life = models.IntegerField(default=5)
    score = models.IntegerField(default=0)
    head = models.ForeignKey('users.Node', on_delete=models.SET_NULL, null=True, blank=True)
    current_node = models.ForeignKey('users.Node', on_delete=models.SET_NULL, null=True, blank=True, related_name='current_node')
    last_checkpoint = models.ForeignKey('users.Node', on_delete=models.SET_NULL, null=True, blank=True, related_name='last_checkpoint')
    created_at = models.DateTimeField(auto_now_add=True)
    attack = models.IntegerField(default=0)

    def __str__(self):
        return self.name


class Node(models.Model):
    data = models.TextField()
    answer = models.TextField(default="", blank=True)
    alt_answer = models.TextField(default="", blank=True)
    next_node = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)
    alt_next_node = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='alternative_next_node')
    effects = models.CharField(default=Effects.UNLOCKED, max_length=20, choices=Effects.choices)
    score = models.IntegerField(default=10) # Junction nodes no score, handle manually when adding questions
    bonus = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    attack = models.IntegerField(default=0)
    life = models.IntegerField(default=0)
    clue = models.TextField(default="", blank=True, null=True)
    is_nearest = models.BooleanField(default=False)
    
    def __str__(self):
        return self.data


class TeamNode(models.Model):
    team = models.ForeignKey('users.Team', on_delete=models.CASCADE)
    node = models.ForeignKey('users.Node', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('team', 'node')

class GameHistory(models.Model):
    team = models.ForeignKey('users.Team', on_delete=models.CASCADE)
    node = models.ForeignKey('users.Node', on_delete=models.CASCADE, null=True, blank=True)
    action = models.TextField(default="", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self) -> str:
        return f"{self.team.name} - {self.action} - Q(self.node.id)"