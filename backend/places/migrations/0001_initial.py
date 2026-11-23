from django.db import migrations, models


def enable_postgis(apps, schema_editor):  # type: ignore[no-untyped-def]
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("CREATE EXTENSION IF NOT EXISTS postgis")


def create_spatial_index(apps, schema_editor):  # type: ignore[no-untyped-def]
    """GiST index on the town location so nearest-town (KNN) queries stay fast."""
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "CREATE INDEX places_town_geog_gist ON places_town "
            "USING GIST ((ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography))"
        )


def drop_spatial_index(apps, schema_editor):  # type: ignore[no-untyped-def]
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("DROP INDEX IF EXISTS places_town_geog_gist")


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.RunPython(enable_postgis, migrations.RunPython.noop),
        migrations.CreateModel(
            name="Town",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("name", models.CharField(max_length=120)),
                ("state", models.CharField(max_length=2)),
                ("population", models.PositiveIntegerField()),
                ("lat", models.FloatField()),
                ("lon", models.FloatField()),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("name", "state", "lat", "lon"), name="places_town_unique"
                    )
                ],
            },
        ),
        migrations.RunPython(create_spatial_index, drop_spatial_index),
    ]
