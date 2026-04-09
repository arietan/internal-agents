"""
Core abstraction layer for multi-cloud agent deployment.

Provides abstract interfaces that decouple agent business logic from
cloud-specific services. Runtime backend selection via CLOUD_PROVIDER
environment variable (local | aws | azure | gcp).
"""
