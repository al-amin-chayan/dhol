"""Every stage, transport, and administration combination, checked against one invariant.

This suite exists because the same defect class was reported three times: the
connection address was correct for the case under review and wrong for a
neighbouring one. Patching the reported combination does not establish the rule,
so the whole state space is enumerated here and the invariant asserted over all
of it.

    Invariant: a run whose desired state can close public SSH must connect and
    probe over the tunnel, so the path being adopted is proven before the path
    being removed is taken away.
"""

from __future__ import annotations

import importlib.util
import itertools
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]


def load_module():
    spec = importlib.util.spec_from_file_location(
        "dholbeat_host_baseline", ROOT / "infra/inventories/host_baseline.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HOST_BASELINE = load_module()

PUBLIC_ADDRESS = "203.0.113.20"
TUNNEL_ADDRESS = "10.99.0.1"

CONTRACTS = {
    "none": {"mode": "none"},
    "public": {
        "mode": "wireguard",
        "administration": "public",
        "host_address": f"{TUNNEL_ADDRESS}/24",
    },
    "tunnel": {
        "mode": "wireguard",
        "administration": "tunnel",
        "host_address": f"{TUNNEL_ADDRESS}/24",
    },
}
STAGES = ("bootstrap", "converged")
TRANSPORTS = ("auto", "public", "tunnel")
COMBINATIONS = list(itertools.product(sorted(CONTRACTS), STAGES, TRANSPORTS))


def resolve(administration: str, stage: str, transport: str) -> str | None:
    """Return the resolved address, or None when the combination is refused."""

    try:
        return HOST_BASELINE.resolve_connection_address(
            CONTRACTS[administration], PUBLIC_ADDRESS, stage, transport
        )
    except ValueError:
        return None


@pytest.mark.parametrize(("administration", "stage", "transport"), COMBINATIONS)
def test_a_run_that_can_close_public_ssh_always_proves_the_tunnel(
    administration: str, stage: str, transport: str
) -> None:
    """The load-bearing invariant, over the entire state space."""

    resolved = resolve(administration, stage, transport)
    if resolved is None:
        return  # Refused combinations cannot violate the invariant.
    if HOST_BASELINE.closes_public_administration(CONTRACTS[administration]):
        assert resolved == TUNNEL_ADDRESS, (
            f"{administration}/{stage}/{transport} would close public SSH while proving "
            f"{resolved}"
        )


@pytest.mark.parametrize(("administration", "stage", "transport"), COMBINATIONS)
def test_every_combination_is_decided_rather_than_defaulted(
    administration: str, stage: str, transport: str
) -> None:
    """Each combination either resolves to a real address or is refused outright."""

    resolved = resolve(administration, stage, transport)
    assert resolved in (None, PUBLIC_ADDRESS, TUNNEL_ADDRESS)


@pytest.mark.parametrize("transport", TRANSPORTS)
def test_a_tunnel_only_contract_can_never_be_bootstrapped(transport: str) -> None:
    """First contact is public, so bootstrapping it would prove the path being closed."""

    assert resolve("tunnel", "bootstrap", transport) is None


@pytest.mark.parametrize(("administration", "transport"), [("none", "tunnel"), ("public", "tunnel")])
def test_first_contact_never_uses_a_tunnel(administration: str, transport: str) -> None:
    assert resolve(administration, "bootstrap", transport) is None


def test_the_reverse_cutover_is_the_one_public_contract_carried_by_the_tunnel() -> None:
    """Rollback must connect over the live tunnel while re-adding the public rule."""

    assert resolve("public", "converged", "tunnel") == TUNNEL_ADDRESS


def test_a_tunnel_only_contract_refuses_an_explicit_public_transport() -> None:
    assert resolve("tunnel", "converged", "public") is None


def test_a_non_vpn_contract_can_never_resolve_to_a_tunnel() -> None:
    for stage, transport in itertools.product(STAGES, TRANSPORTS):
        assert resolve("none", stage, transport) in (None, PUBLIC_ADDRESS)


def test_the_matrix_covers_every_combination() -> None:
    """A matrix that silently shrinks stops proving anything."""

    assert len(COMBINATIONS) == len(CONTRACTS) * len(STAGES) * len(TRANSPORTS) == 18


@pytest.mark.parametrize("transport", ["", "Tunnel", "vpn", "auto "])
def test_an_unknown_transport_is_refused(transport: str) -> None:
    with pytest.raises(ValueError):
        HOST_BASELINE.resolve_connection_address(
            CONTRACTS["public"], PUBLIC_ADDRESS, "converged", transport
        )


@pytest.mark.parametrize("stage", ["", "first-contact", "Converged"])
def test_an_unknown_stage_is_refused(stage: str) -> None:
    with pytest.raises(ValueError):
        HOST_BASELINE.resolve_connection_address(
            CONTRACTS["public"], PUBLIC_ADDRESS, stage, "auto"
        )


# --- The transport carrying a run is decided, never inferred (PR44-R04) ---

def test_the_tunnel_address_is_refused_where_a_public_one_belongs() -> None:
    """Supplying the tunnel address made address-equality mistake it for public.

    known_hosts legitimately records the tunnel address, so this was an operator
    input path, not a theoretical one.
    """

    with pytest.raises(ValueError):
        HOST_BASELINE.resolve_connection_address(
            CONTRACTS["tunnel"], TUNNEL_ADDRESS, "converged", "auto"
        )


@pytest.mark.parametrize("administration", ["public", "tunnel", "none"])
def test_the_tunnel_address_is_refused_for_every_contract(administration: str) -> None:
    if administration == "none":
        return  # No tunnel address exists to confuse.
    with pytest.raises(ValueError):
        HOST_BASELINE.resolve_connection_address(
            CONTRACTS[administration], TUNNEL_ADDRESS, "converged", "auto"
        )


@pytest.mark.parametrize(("administration", "stage", "transport"), COMBINATIONS)
def test_the_resolved_transport_matches_the_resolved_address(
    administration: str, stage: str, transport: str
) -> None:
    """Transport and address must agree, since a guard depends on the transport."""

    try:
        resolution = HOST_BASELINE.resolve_connection(
            CONTRACTS[administration], PUBLIC_ADDRESS, stage, transport
        )
    except ValueError:
        return
    expected = "tunnel" if resolution["address"] == TUNNEL_ADDRESS else "public"
    assert resolution["transport"] == expected


def test_a_tunnel_carried_run_is_never_reported_as_public() -> None:
    """The guard that refuses a key change depends on exactly this."""

    for administration, transport in (("tunnel", "auto"), ("public", "tunnel")):
        resolution = HOST_BASELINE.resolve_connection(
            CONTRACTS[administration], PUBLIC_ADDRESS, "converged", transport
        )
        assert resolution["address"] == TUNNEL_ADDRESS
        assert resolution["transport"] == "tunnel"


def test_a_public_carried_run_is_reported_as_public() -> None:
    resolution = HOST_BASELINE.resolve_connection(
        CONTRACTS["public"], PUBLIC_ADDRESS, "converged", "auto"
    )
    assert resolution == {"address": PUBLIC_ADDRESS, "transport": "public"}
