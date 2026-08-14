from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.configuration import ConfigurationParameter, ConfigurationValue
from app.configuration_store import ConfigurationParameterStore
from app.phase6_main import app
from app.release_builder import ReleaseBuildError
from app.release_candidate_service import _trusted_configuration_catalog


client = TestClient(app)
_APPROVER = {"X-SIMQIN-User": "approver-a", "X-SIMQIN-Role": "approver"}
_AUTHOR = {"X-SIMQIN-User": "author-a", "X-SIMQIN-Role": "author"}


def _parameter(**overrides) -> ConfigurationParameter:
    payload = {
        "parameter_id": "assay-mode",
        "label": "Assay mode",
        "description": "Approved assay configuration",
        "type": "enum",
        "default_value": "standard",
        "allowed_values": ["standard", "rapid"],
        "status": "approved",
        "revision": 2,
        "scope": "product",
        "allowed_roles": [],
    }
    payload.update(overrides)
    return ConfigurationParameter.from_dict(payload)


def test_configuration_store_is_immutable_and_checksum_protected(tmp_path):
    database = tmp_path / "configuration.sqlite3"
    store = ConfigurationParameterStore(database)
    created = store.add(_parameter(), registered_by="approver-a")
    assert created["parameter"]["allowed_values"] == ["standard", "rapid"]
    assert created["payload_checksum"]

    with pytest.raises(ValueError, match="already exists"):
        store.add(_parameter(), registered_by="approver-b")

    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT payload_json FROM configuration_parameter_revisions WHERE parameter_id = ? AND revision = ?",
            ("assay-mode", 2),
        ).fetchone()
        payload = json.loads(row[0])
        payload["allowed_values"].append("unapproved")
        connection.execute(
            "UPDATE configuration_parameter_revisions SET payload_json = ? WHERE parameter_id = ? AND revision = ?",
            (json.dumps(payload, sort_keys=True), "assay-mode", 2),
        )

    with pytest.raises(ValueError, match="failed checksum verification"):
        ConfigurationParameterStore(database).get("assay-mode", 2)


def test_configuration_registration_requires_approver(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    body = {"parameter": _parameter().to_dict()}
    forbidden = client.post("/api/v1/configuration/parameters", headers=_AUTHOR, json=body)
    assert forbidden.status_code == 403

    created = client.post("/api/v1/configuration/parameters", headers=_APPROVER, json=body)
    assert created.status_code == 201
    assert created.json()["registered_by"] == "approver-a"

    listed = client.get("/api/v1/configuration/parameters")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1


def test_candidate_catalog_loads_trusted_parameter_from_value_reference(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    trusted = ConfigurationParameterStore().add(_parameter(), registered_by="approver-a")
    values = [
        ConfigurationValue(
            parameter_id="assay-mode",
            parameter_revision=2,
            value="rapid",
            source="product-config",
            set_by="author-a",
        )
    ]

    catalog, checksums = _trusted_configuration_catalog([], values)
    loaded = catalog.get_revision("assay-mode", 2)
    assert loaded is not None
    assert loaded.allowed_values == ["standard", "rapid"]
    assert checksums == [trusted["payload_checksum"]]


def test_candidate_rejects_supplied_parameter_that_differs_from_trusted_catalog(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    ConfigurationParameterStore().add(_parameter(), registered_by="approver-a")
    asserted = _parameter(allowed_values=["standard", "rapid", "unapproved"]).to_dict()
    values = [ConfigurationValue(parameter_id="assay-mode", parameter_revision=2, value="rapid")]

    with pytest.raises(ReleaseBuildError) as exc_info:
        _trusted_configuration_catalog([asserted], values)

    assert "configuration-parameter-mismatch" in {
        finding["code"] for finding in exc_info.value.findings
    }
