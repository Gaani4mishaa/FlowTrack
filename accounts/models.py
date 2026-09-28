from django.contrib.auth.models import AbstractUser
from django.db import models


class Organization(models.Model):
    ORGANIZATION_TYPES = [
        ('county', 'County Government'),
        ('university', 'University'),
        ('property', 'Property Management Company'),
        ('industrial', 'Industrial Park'),
        ('commercial', 'Shopping Mall / Commercial Property'),
        ('institution', 'Other Institution'),
    ]

    name = models.CharField(max_length=200)
    organization_type = models.CharField(
        max_length=30,
        choices=ORGANIZATION_TYPES
    )
    county = models.CharField(max_length=100)
    address = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class User(AbstractUser):
    ROLE_CHOICES = [
        ('resident', 'Resident'),
        ('engineer', 'Maintenance Engineer'),
        ('manager', 'Organization Manager'),
        ('admin', 'System Administrator'),
    ]

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='resident'
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users'
    )

    phone_number = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return self.get_full_name() or self.username