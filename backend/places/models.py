from django.db import models


class Town(models.Model):
    """A US town from GeoNames (cities1000), used to name places along a route offline.

    Coordinates are plain floats; nearest-town queries use PostGIS functions in SQL
    (see places/nearest.py), backed by a GiST index created in the initial migration.
    """

    name = models.CharField(max_length=120)
    state = models.CharField(max_length=2)
    population = models.PositiveIntegerField()
    lat = models.FloatField()
    lon = models.FloatField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["name", "state", "lat", "lon"], name="places_town_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name}, {self.state}"
