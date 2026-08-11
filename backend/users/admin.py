from django.contrib import admin
from .models import User, Team, Node, TeamNode


class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'team', 'is_captain', 'is_staff', 'is_superuser')
    list_filter = ('is_staff', 'is_superuser', 'is_captain')
    search_fields = ('email',)
    ordering = ('email',)
    filter_horizontal = ()

class UserInline(admin.TabularInline):
    model = User
    extra = 0
    fields = ('email', 'is_captain', 'is_staff')
    show_change_link = True


class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'life', 'score', 'created_at')
    search_fields = ('name',)
    ordering = ('name',)
    inlines = (UserInline,)

class NodeAdmin(admin.ModelAdmin):
    list_display = ('data', 'effects', 'score', 'bonus', 'created_at')
    search_fields = ('data',)
    ordering = ('created_at',)

class TeamNodeAdmin(admin.ModelAdmin):
    list_display = ('team', 'node', 'created_at')
    search_fields = ('team__name', 'node__data')
    ordering = ('created_at',)

admin.site.register(User, UserAdmin)
admin.site.register(Team, TeamAdmin)
admin.site.register(Node, NodeAdmin)
admin.site.register(TeamNode, TeamNodeAdmin)
