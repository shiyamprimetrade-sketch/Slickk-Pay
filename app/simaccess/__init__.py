"""Slickk Pay fictional customer/agent access simulation, Cycle 004.

This package does not register routes with app.live or create a bank. The only
HTTP application is created explicitly by create_local_access_app and requires
sandbox opt-in, local-only request sources and seeded synthetic identities.
"""
from .errors import LabError
from .service import AccessLab,create_local_lab
from .store import LabStore

__all__ = ["LabError","AccessLab","create_local_lab","LabStore"]
