from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def require_empty_layoffs(apps, schema_editor):
    Layoff = apps.get_model('tracker', 'Layoff')
    if Layoff.objects.using(schema_editor.connection.alias).exists():
        raise RuntimeError(
            'Layoff rows exist. This migration cannot replace or reverse '
            'schedule fields without a reviewed data-conversion plan. '
            'No layoff records have been deleted by this guard.'
        )


class Migration(migrations.Migration):
    dependencies = [
        ('tracker', '0002_manage_layoff_permissions'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(
            require_empty_layoffs,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='layoff',
            name='lot',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='layoffs',
                to='tracker.lot',
            ),
        ),
        migrations.AddField(
            model_name='layoff',
            name='starts_at',
            field=models.DateTimeField(db_index=True),
        ),
        migrations.AddField(
            model_name='layoff',
            name='ends_at',
            field=models.DateTimeField(db_index=True),
        ),
        migrations.AddField(
            model_name='layoff',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AddField(
            model_name='layoff',
            name='created_by',
            field=models.ForeignKey(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='created_layoffs',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='layoff',
            name='cancelled_at',
            field=models.DateTimeField(
                blank=True, editable=False, null=True,
            ),
        ),
        migrations.AddField(
            model_name='layoff',
            name='cancelled_by',
            field=models.ForeignKey(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='cancelled_layoffs',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='layoff',
            name='replaces',
            field=models.OneToOneField(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='replacement',
                to='tracker.layoff',
            ),
        ),
        migrations.AddField(
            model_name='layoff',
            name='version',
            field=models.PositiveIntegerField(
                default=1, editable=False,
            ),
        ),
        migrations.RemoveField(
            model_name='layoff', name='active_date',
        ),
        migrations.RemoveField(
            model_name='layoff', name='start_time',
        ),
        migrations.RemoveField(
            model_name='layoff', name='end_time',
        ),
        migrations.AlterModelOptions(
            name='layoff',
            options={
                'ordering': ['-starts_at', '-pk'],
                'permissions': [
                    ('manage_layoffs', 'Can manage layoffs'),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name='layoff',
            constraint=models.CheckConstraint(
                check=models.Q(ends_at__gt=models.F('starts_at')),
                name='layoff_end_after_start',
            ),
        ),
        migrations.AddConstraint(
            model_name='layoff',
            constraint=models.CheckConstraint(
                check=models.Q(version__gte=1),
                name='layoff_version_at_least_one',
            ),
        ),
        migrations.AddConstraint(
            model_name='layoff',
            constraint=models.CheckConstraint(
                check=(
                    models.Q(cancelled_at__isnull=True)
                    | models.Q(
                        cancelled_at__gte=models.F('created_at')
                    )
                ),
                name='layoff_cancellation_after_creation',
            ),
        ),
        migrations.AddConstraint(
            model_name='layoff',
            constraint=models.CheckConstraint(
                check=(
                    models.Q(cancelled_by__isnull=True)
                    | models.Q(cancelled_at__isnull=False)
                ),
                name='layoff_cancel_actor_needs_time',
            ),
        ),
        migrations.RunPython(
            migrations.RunPython.noop,
            require_empty_layoffs,
        ),
    ]