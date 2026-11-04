"""Synthetic-device capabilities and privacy guardrails.

No actual Android Keystore, Play Integrity, biometric or FIDO attestation is
claimed. This module models explicit constraints to be implemented natively.
"""
from __future__ import annotations
from dataclasses import dataclass
from .errors import LabError,require
from .sessions import SessionContext


@dataclass(frozen=True)
class DeviceSignals:
    app_foreground:bool
    screen_unlocked:bool
    secure_local_storage:bool
    os_supported:bool
    network_online:bool
    device_rooted:bool
    emulator:bool
    session_active:bool
    displayed_demo_warning:bool


@dataclass(frozen=True)
class DeviceDecision:
    can_view_public_demo:bool
    can_view_private_samples:bool
    can_review_synthetic_quote:bool
    can_authorize_real_money:bool
    reasons:tuple[str,...]
    actual_attestation_verified:bool=False
    simulation:bool=True

    def public(self)->dict[str,object]:
        return {"can_view_public_demo":self.can_view_public_demo,
                "can_view_private_samples":self.can_view_private_samples,
                "can_review_synthetic_quote":self.can_review_synthetic_quote,
                "can_authorize_real_money":False,
                "reasons":list(self.reasons),"attestation_verified":False,"simulation":True}


class DevicePolicy:
    def evaluate(self,signals:DeviceSignals,session:SessionContext|None)->DeviceDecision:
        require(isinstance(signals,DeviceSignals),"INVALID_INPUT")
        reasons=[]
        if not signals.app_foreground:
            reasons.append("APP_IN_BACKGROUND")
        if not signals.screen_unlocked:
            reasons.append("SCREEN_LOCKED")
        if not signals.secure_local_storage:
            reasons.append("NO_SECURE_STORAGE_EVIDENCE")
        if not signals.os_supported:
            reasons.append("UNSUPPORTED_OS")
        if signals.device_rooted:
            reasons.append("DEVICE_ROOTED_OR_UNKNOWN")
        if signals.emulator:
            reasons.append("EMULATOR_ONLY")
        if not signals.network_online:
            reasons.append("OFFLINE_NO_AUTHORIZATION")
        if not signals.session_active or session is None:
            reasons.append("SESSION_NOT_VERIFIED")
        if not signals.displayed_demo_warning:
            reasons.append("SIMULATION_WARNING_MISSING")
        may_view=all((signals.app_foreground,signals.screen_unlocked,signals.session_active,
                      signals.displayed_demo_warning,session is not None))
        may_quote=may_view and signals.network_online and signals.os_supported and not signals.device_rooted
        return DeviceDecision(True,may_view,may_quote,False,tuple(reasons))

    def require_quote_preview(self,signals:DeviceSignals,session:SessionContext)->None:
        if not self.evaluate(signals,session).can_review_synthetic_quote:
            raise LabError("ROLE_FORBIDDEN")

    def permission_contract(self)->dict[str,object]:
        return {"device_attestation_implemented":False,"biometrics_implemented":False,
                "hardware_key_storage_verified":False,"background_payment_queue":False,
                "offline_balance_authorization":False,"can_move_money":False,
                "require_secure_session_for_private_preview":True,"simulation":True}

    def platform_requirements(self)->tuple[str,...]:
        return ("Android Keystore for any future real credentials",
                "Native biometric user-presence where supported",
                "Server-side verification of session and transaction context",
                "No offline balance authorization or acceptance of pending transfers",
                "Explicit accessibility tests for Bangla and low-memory Android devices")
