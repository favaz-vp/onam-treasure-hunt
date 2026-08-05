from django.contrib import admin
from .models import User, Team, Node, TeamNode


admin.site.register(User)
admin.site.register(Team)
admin.site.register(Node)
admin.site.register(TeamNode)
