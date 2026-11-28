from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tracker", "0001_initial"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="layoff",
            options={
                "permissions": [
                    ("manage_layoffs", "Can manage layoffs"),
                ],
            },
        ),
    ]