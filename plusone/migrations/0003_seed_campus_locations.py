from django.db import migrations


LOCATIONS = [
    ("North Dining Hall", "dining", "North Campus"),
    ("Campus Sports Hall", "sports", "Central Campus"),
    ("Main Library", "study", "Library Quad"),
    ("Student Center", "event", "Central Campus"),
    ("Campus Quad", "outdoor", "South Lawn"),
]


def seed_locations(apps, schema_editor):
    CampusLocation = apps.get_model("plusone", "CampusLocation")
    for name, location_type, area in LOCATIONS:
        CampusLocation.objects.update_or_create(
            name=name,
            defaults={"location_type": location_type, "area": area},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("plusone", "0002_userprofile_avatar_initial"),
    ]

    operations = [
        migrations.RunPython(seed_locations, migrations.RunPython.noop),
    ]
