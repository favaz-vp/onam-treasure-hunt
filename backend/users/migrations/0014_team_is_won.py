from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0013_node_is_nearest'),
    ]

    operations = [
        migrations.AddField(
            model_name='team',
            name='is_won',
            field=models.BooleanField(default=False),
        ),
    ]
