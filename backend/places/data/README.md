# Town data

`us_towns.csv` lists places in the continental US (plus DC) with at least 1,000 people:
name, state, population, latitude, longitude. It is a subset of the GeoNames `cities1000` dump,
used offline to name places along a route.

- Source: https://download.geonames.org/export/dump/ (`cities1000.zip`)
- Licence: [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/)
  by GeoNames (https://www.geonames.org/)
- Load it with `python manage.py seed_towns` (idempotent).
