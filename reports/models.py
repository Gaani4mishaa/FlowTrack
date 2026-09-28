from django.conf import settings
from django.db import models


class Report(models.Model):
    ISSUE_TYPE_CHOICES = [
        ("blocked_drain", "Blocked drain"),
        ("flooding", "Flooding"),
        ("damaged_culvert", "Damaged culvert"),
        ("overflowing_drain", "Overflowing drain"),
        ("illegal_dumping", "Waste obstructing drainage"),
        ("damaged_channel", "Damaged drainage channel"),
        ("other", "Other"),
    ]

    COUNTY_CHOICES = [
        ("Baringo", "Baringo"),
        ("Bomet", "Bomet"),
        ("Bungoma", "Bungoma"),
        ("Busia", "Busia"),
        ("Elgeyo Marakwet", "Elgeyo Marakwet"),
        ("Embu", "Embu"),
        ("Garissa", "Garissa"),
        ("Homa Bay", "Homa Bay"),
        ("Isiolo", "Isiolo"),
        ("Kajiado", "Kajiado"),
        ("Kakamega", "Kakamega"),
        ("Kericho", "Kericho"),
        ("Kiambu", "Kiambu"),
        ("Kilifi", "Kilifi"),
        ("Kirinyaga", "Kirinyaga"),
        ("Kisii", "Kisii"),
        ("Kisumu", "Kisumu"),
        ("Kitui", "Kitui"),
        ("Kwale", "Kwale"),
        ("Laikipia", "Laikipia"),
        ("Lamu", "Lamu"),
        ("Machakos", "Machakos"),
        ("Makueni", "Makueni"),
        ("Mandera", "Mandera"),
        ("Marsabit", "Marsabit"),
        ("Meru", "Meru"),
        ("Migori", "Migori"),
        ("Mombasa", "Mombasa"),
        ("Murang'a", "Murang'a"),
        ("Nairobi City", "Nairobi City"),
        ("Nakuru", "Nakuru"),
        ("Nandi", "Nandi"),
        ("Narok", "Narok"),
        ("Nyamira", "Nyamira"),
        ("Nyandarua", "Nyandarua"),
        ("Nyeri", "Nyeri"),
        ("Samburu", "Samburu"),
        ("Siaya", "Siaya"),
        ("Taita Taveta", "Taita Taveta"),
        ("Tana River", "Tana River"),
        ("Tharaka Nithi", "Tharaka Nithi"),
        ("Trans Nzoia", "Trans Nzoia"),
        ("Turkana", "Turkana"),
        ("Uasin Gishu", "Uasin Gishu"),
        ("Vihiga", "Vihiga"),
        ("Wajir", "Wajir"),
        ("West Pokot", "West Pokot"),
    ]

    STATUS_CHOICES = [
        ("submitted", "Submitted"),
        ("under_review", "Under Review"),
        ("assigned", "Assigned"),
        ("in_progress", "In Progress"),
        ("resolved", "Resolved"),
        ("closed", "Closed"),
    ]

    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("critical", "Critical"),
    ]

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reports",
    )
    organization = models.ForeignKey(
    "accounts.Organization",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="reports",
)

    issue_type = models.CharField(
        max_length=50,
        choices=ISSUE_TYPE_CHOICES,
    )

    county = models.CharField(
        max_length=50,
        choices=COUNTY_CHOICES,
    )

    area = models.CharField(
        max_length=150,
    )

    location_description = models.CharField(
        max_length=255,
        blank=True,
    )

    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )

    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )

    photo = models.ImageField(
        upload_to="reports/%Y/%m/",
        blank=True,
        null=True,
    )

    description = models.TextField(
        max_length=1000,
        blank=True,
    )

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="submitted",
    )

    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default="medium",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_issue_type_display()} - {self.county} - {self.area}"