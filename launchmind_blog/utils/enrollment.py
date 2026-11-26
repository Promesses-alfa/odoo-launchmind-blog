"""Auth-critical enrollment state, read past Odoo's per-worker parameter cache.

Connect, disconnect and every webhook take the same transaction advisory
lock first, then read the key slots with SQL, so a worker never decides on
a cached value another worker already replaced.

Odoo cursors are REPEATABLE READ and a request has usually taken its
snapshot before the controller waits on the lock. Every state change
therefore also updates one epoch row, and lock() locks that row: a
transaction whose snapshot predates a committed change fails with a
serialization error, which Odoo's request retrying replays on a fresh
snapshot instead of letting a stale state admit a request.
"""

from dataclasses import dataclass
from typing import Any

from .signing import KeySlot, dump_slot, load_slot

# Arbitrary constant; unique to this module within the database.
LOCK_KEY = 7366042519

PARAM_CURRENT = 'launchmind_blog.signing_current'
PARAM_PENDING = 'launchmind_blog.signing_pending'
# Set once the first pending key is stored and never cleared: from then on
# bearer delivery is refused, whatever happens to the slots.
PARAM_RATCHET = 'launchmind_blog.signing_ratchet'
PARAM_SUBSCRIPTION = 'launchmind_blog.subscription_id'
PARAM_API_KEY = 'launchmind_blog.api_key'
PARAM_CONNECTED = 'launchmind_blog.connected'
PARAM_EPOCH = 'launchmind_blog.signing_epoch'


def lock(env: Any) -> None:
    env.flush_all()
    env.cr.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK_KEY,))
    env.cr.execute(
        "INSERT INTO ir_config_parameter (key, value) VALUES (%s, '0') "
        'ON CONFLICT (key) DO NOTHING',
        (PARAM_EPOCH,),
    )
    env.cr.execute('SELECT 1 FROM ir_config_parameter WHERE key = %s FOR UPDATE', (PARAM_EPOCH,))


def fresh_param(env: Any, key: str) -> str:
    env.flush_all()
    env.cr.execute('SELECT value FROM ir_config_parameter WHERE key = %s', (key,))
    row = env.cr.fetchone()
    return (row[0] or '') if row else ''


def write_param(env: Any, key: str, value: str | bool) -> None:
    """Call only after lock(env); the epoch update exposes this change to stale snapshots."""
    params = env['ir.config_parameter'].sudo()
    params.set_param(key, value)
    params.flush_model()
    env.cr.execute(
        'UPDATE ir_config_parameter SET value = (value::bigint + 1)::text WHERE key = %s',
        (PARAM_EPOCH,),
    )


def write_slot(env: Any, key: str, slot: KeySlot | None) -> None:
    write_param(env, key, dump_slot(slot) if slot else False)


@dataclass(frozen=True)
class EnrollmentState:
    database_uuid: str
    current: KeySlot | None
    pending: KeySlot | None
    ratchet: bool
    connected: bool
    corrupt: bool

    @property
    def bound(self) -> bool:
        """Every stored key belongs to this database; a copy fails this."""
        return all(
            slot.installation_id == self.database_uuid
            for slot in (self.current, self.pending)
            if slot is not None
        )

    def slot(self, kid: str) -> tuple[str, KeySlot] | None:
        if self.pending is not None and self.pending.kid == kid:
            return 'pending', self.pending
        if self.current is not None and self.current.kid == kid:
            return 'current', self.current
        return None


def read_state(env: Any) -> EnrollmentState:
    """Call only after lock(env)."""
    current = pending = None
    corrupt = False
    try:
        current = load_slot(fresh_param(env, PARAM_CURRENT))
        pending = load_slot(fresh_param(env, PARAM_PENDING))
    except ValueError:
        corrupt = True
        current = pending = None
    ratchet = bool(fresh_param(env, PARAM_RATCHET)) or corrupt or bool(current or pending)
    return EnrollmentState(
        database_uuid=fresh_param(env, 'database.uuid'),
        current=current,
        pending=pending,
        ratchet=ratchet,
        connected=fresh_param(env, PARAM_CONNECTED).lower() == 'true',
        corrupt=corrupt,
    )
