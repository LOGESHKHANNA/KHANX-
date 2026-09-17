"""
KHANX Login Security — Failed Attempt Tracker & Account Lockout
================================================================

In-memory rate limiter that tracks failed login attempts per email and per IP.
Works alongside slowapi's per-IP rate limiting as a second layer of defence.

Thresholds (configurable):
  - Per email:  5 consecutive failures  → 15 min lockout
  - Per IP:    10 consecutive failures  → 30 min lockout

On successful login, all counters for that email+IP are reset.

Thread-safe using threading.Lock. Stale entries are auto-purged every 10 minutes.
"""

import threading
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Tuple

logger = logging.getLogger("khanx.login_security")

# ── Configuration ─────────────────────────────────────────────────────────────
MAX_EMAIL_FAILURES = 5          # lock email after this many consecutive failures
MAX_IP_FAILURES    = 10         # lock IP after this many consecutive failures
EMAIL_LOCKOUT_SECS = 15 * 60   # 15 minutes
IP_LOCKOUT_SECS    = 30 * 60   # 30 minutes
CLEANUP_INTERVAL   = 10 * 60   # purge stale entries every 10 minutes


@dataclass
class _AttemptRecord:
    """Tracks consecutive failures and lockout state for a single key (email or IP)."""
    failures: int = 0
    locked_until: float = 0.0          # epoch timestamp; 0 = not locked
    last_attempt: float = field(default_factory=time.time)

    @property
    def is_locked(self) -> bool:
        return self.locked_until > time.time()

    @property
    def remaining_seconds(self) -> int:
        """Seconds remaining on the lockout (0 if not locked)."""
        rem = self.locked_until - time.time()
        return max(0, int(rem))


class LoginSecurityTracker:
    """Thread-safe in-memory tracker for brute-force login protection."""

    def __init__(
        self,
        max_email_failures: int = MAX_EMAIL_FAILURES,
        max_ip_failures: int = MAX_IP_FAILURES,
        email_lockout_secs: int = EMAIL_LOCKOUT_SECS,
        ip_lockout_secs: int = IP_LOCKOUT_SECS,
    ):
        self._email_records: Dict[str, _AttemptRecord] = {}
        self._ip_records: Dict[str, _AttemptRecord] = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.time()

        self.max_email_failures = max_email_failures
        self.max_ip_failures = max_ip_failures
        self.email_lockout_secs = email_lockout_secs
        self.ip_lockout_secs = ip_lockout_secs

    # ── Public API ────────────────────────────────────────────────────────

    def check_lockout(self, email: str, ip: str) -> Tuple[bool, Optional[str], int]:
        """
        Check whether the given email or IP is currently locked out.

        Returns:
            (is_locked, message, retry_after_seconds)
        """
        email_key = email.lower().strip()
        self._maybe_cleanup()

        with self._lock:
            # Check email lockout
            rec = self._email_records.get(email_key)
            if rec and rec.is_locked:
                remaining = rec.remaining_seconds
                minutes = max(1, (remaining + 59) // 60)
                msg = (
                    f"Too many failed login attempts for this account. "
                    f"Please try again in {minutes} minute{'s' if minutes != 1 else ''}."
                )
                return True, msg, remaining

            # Check IP lockout
            rec = self._ip_records.get(ip)
            if rec and rec.is_locked:
                remaining = rec.remaining_seconds
                minutes = max(1, (remaining + 59) // 60)
                msg = (
                    f"Too many login attempts from your network. "
                    f"Please try again in {minutes} minute{'s' if minutes != 1 else ''}."
                )
                return True, msg, remaining

        return False, None, 0

    def record_failure(self, email: str, ip: str) -> Tuple[bool, Optional[str], int]:
        """
        Record a failed login attempt. Increments counters and may trigger lockout.

        Returns:
            (newly_locked, message, retry_after_seconds)
        """
        email_key = email.lower().strip()
        now = time.time()
        newly_locked = False
        message = None
        retry_after = 0

        with self._lock:
            # ── Email tracking ────────────────────────────────────────────
            if email_key not in self._email_records:
                self._email_records[email_key] = _AttemptRecord()
            erec = self._email_records[email_key]
            erec.failures += 1
            erec.last_attempt = now

            if erec.failures >= self.max_email_failures and not erec.is_locked:
                erec.locked_until = now + self.email_lockout_secs
                newly_locked = True
                minutes = self.email_lockout_secs // 60
                message = (
                    f"Too many failed login attempts. "
                    f"Account locked for {minutes} minutes. Please try again later."
                )
                retry_after = self.email_lockout_secs
                logger.warning(
                    f"LOGIN_LOCKOUT email={email_key} failures={erec.failures} "
                    f"locked_for={minutes}min ip={ip}"
                )

            # ── IP tracking ───────────────────────────────────────────────
            if ip not in self._ip_records:
                self._ip_records[ip] = _AttemptRecord()
            irec = self._ip_records[ip]
            irec.failures += 1
            irec.last_attempt = now

            if irec.failures >= self.max_ip_failures and not irec.is_locked:
                irec.locked_until = now + self.ip_lockout_secs
                if not newly_locked:
                    newly_locked = True
                    minutes = self.ip_lockout_secs // 60
                    message = (
                        f"Too many login attempts from your network. "
                        f"Please try again in {minutes} minutes."
                    )
                    retry_after = self.ip_lockout_secs
                logger.warning(
                    f"LOGIN_LOCKOUT ip={ip} failures={irec.failures} "
                    f"locked_for={self.ip_lockout_secs // 60}min"
                )

            # Log every failure for audit trail
            if not newly_locked:
                remaining_email = self.max_email_failures - erec.failures
                logger.info(
                    f"LOGIN_FAILURE email={email_key} ip={ip} "
                    f"attempt={erec.failures}/{self.max_email_failures} "
                    f"remaining_before_lock={max(0, remaining_email)}"
                )

        return newly_locked, message, retry_after

    def record_success(self, email: str, ip: str) -> None:
        """Reset all failure counters for the given email and IP after a successful login."""
        email_key = email.lower().strip()

        with self._lock:
            if email_key in self._email_records:
                del self._email_records[email_key]
            if ip in self._ip_records:
                del self._ip_records[ip]

        logger.info(f"LOGIN_SUCCESS email={email_key} ip={ip} — counters reset")

    def get_status(self, email: str, ip: str) -> dict:
        """Return current status for debugging / admin endpoints."""
        email_key = email.lower().strip()
        with self._lock:
            erec = self._email_records.get(email_key)
            irec = self._ip_records.get(ip)
        return {
            "email": email_key,
            "email_failures": erec.failures if erec else 0,
            "email_locked": erec.is_locked if erec else False,
            "email_lock_remaining_s": erec.remaining_seconds if erec else 0,
            "ip": ip,
            "ip_failures": irec.failures if irec else 0,
            "ip_locked": irec.is_locked if irec else False,
            "ip_lock_remaining_s": irec.remaining_seconds if irec else 0,
        }

    # ── Internal ──────────────────────────────────────────────────────────

    def _maybe_cleanup(self) -> None:
        """Purge expired lockout records to prevent unbounded memory growth."""
        now = time.time()
        if now - self._last_cleanup < CLEANUP_INTERVAL:
            return
        with self._lock:
            self._last_cleanup = now
            cutoff = now - max(self.email_lockout_secs, self.ip_lockout_secs) * 2
            self._email_records = {
                k: v for k, v in self._email_records.items()
                if v.last_attempt > cutoff
            }
            self._ip_records = {
                k: v for k, v in self._ip_records.items()
                if v.last_attempt > cutoff
            }
        logger.debug("LOGIN_SECURITY cleanup completed")


# ── Module-level singleton ────────────────────────────────────────────────────
login_tracker = LoginSecurityTracker()
