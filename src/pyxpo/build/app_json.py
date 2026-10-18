"""The `pyxpo/_app_config.json` shipped inside the app: the public subset of the resolved app config.

`pyxpo.Constants` reads it at runtime. Signing material (keystore, team id) and native passthroughs are left out.
"""
import json
from pathlib import Path
from typing import Any, Dict

NAME = "_app_config.json"


def public(nc: Dict[str, Any]) -> Dict[str, Any]:
    out = {"name": nc["name"], "slug": nc["slug"], "version": nc["version"], "build_number": nc["build_number"],
           "scheme": nc["scheme"], "schemes": list(nc["schemes"]), "extra": dict(nc["extra"]),
           "ios": {"bundle_identifier": nc["ios"]["bundle_id"], "build_number": nc["ios"]["build_number"]},
           "android": {"package": nc["android"]["package"], "version_code": nc["android"]["version_code"]}}
    if nc.get("module_data"):  # what module build hooks shipped (pyxpo.modules.build_data)
        out["modules"] = dict(nc["module_data"])
    return out


def write(pyxpo_dir: Path, nc: Dict[str, Any]) -> None:
    Path(pyxpo_dir).mkdir(parents=True, exist_ok=True)
    (Path(pyxpo_dir) / NAME).write_text(json.dumps(public(nc), indent=2, sort_keys=True))


def dumps(nc: Dict[str, Any]) -> str:
    return json.dumps(public(nc), indent=2, sort_keys=True)
