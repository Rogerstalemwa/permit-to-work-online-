from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('permits', '0002_resetcode_person_recovery')]
    operations = [migrations.CreateModel(name='PermitDraft', fields=[
        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        ('owner', models.CharField(db_index=True, max_length=120)),
        ('kind', models.CharField(default='HW', max_length=10)),
        ('title', models.CharField(blank=True, default='', max_length=180)),
        ('data', models.TextField(default='{}')),
        ('updated', models.DateTimeField(auto_now=True)),
    ])]
