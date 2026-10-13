"""Synthetic document builders only; never a human permission issuer."""

import hashlib
import json
from uuid import uuid4


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def separate(freeze, authorization, freeze_path):
    """Upgrade test descriptors, not real or persisted historical artifacts."""
    context = {
        "schema": "invoice-execution-context/1.0", "context_id": str(uuid4()),
        "created_at": freeze["created_at"], "freeze_sha256": "",
        "freeze_path": str(freeze_path), "project_root": freeze.pop("project_root"),
        "run_dir": freeze.pop("run_dir"), "destination": authorization["run_dir"] + "/results",
        "input_paths": freeze.pop("input_paths"),
    }
    # Use platform's canonical path spelling, without touching any inputs.
    context["destination"] = str(freeze_path.parent / "results")
    context["input_hashes_sha256"] = {
        name: freeze["pre_access_sha256"].get(name) for name in context["input_paths"]
    }
    freeze.update({
        "schema": "invoice-portable-freeze/1.1", "freeze_id": str(uuid4()),
        "input_names": list(context["input_paths"]), "test_authorized": False,
    })
    authorization.update({"schema": "invoice-real-authorization/1.3",
                          "context_sha256": "", "destination": context["destination"]})
    return context


def seal_context(freeze, context, authorization, freeze_path, context_path, authorization_path):
    freeze_bytes = canonical(freeze)
    context["freeze_sha256"] = digest(freeze_bytes)
    context_bytes = canonical(context)
    authorization["freeze_sha256"] = digest(freeze_bytes)
    authorization["context_sha256"] = digest(context_bytes)
    authorization["configuration_sha256"] = digest(canonical(freeze["configuration"]))
    auth_bytes = canonical(authorization)
    freeze_path.write_bytes(freeze_bytes)
    context_path.write_bytes(context_bytes)
    authorization_path.write_bytes(auth_bytes)
    return {"context_path": context_path, "expected_context_sha256": digest(context_bytes),
            "expected_freeze_sha256": digest(freeze_bytes),
            "expected_authorization_sha256": digest(auth_bytes)}
