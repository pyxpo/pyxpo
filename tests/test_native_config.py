import importlib

nc = importlib.import_module("pyxpo.native_config")
pre = importlib.import_module("pyxpo.build.prebuild")


def test_resolve_defaults_and_overrides(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname="p"\nversion="0.9.1"\n')
    r = nc.resolve({"name": "My App!", "bundle_id": "dev.a.b", "ios": {"team_id": "T1"}}, tmp_path)
    assert r["product_name"] == "MyApp" and r["scheme"] == "dev.a.b" and r["version"] == "0.9.1"
    assert r["team_id"] == "T1" and r["build_number"] == 1
    r = nc.resolve({"scheme": "myapp", "version": "3.0", "build_number": "7"}, tmp_path)
    assert r["scheme"] == "myapp" and r["version"] == "3.0" and r["build_number"] == 7


def test_plan_prebuild_cases(tmp_path):
    rendered = {"a": b"new", "b": b"same", "c": b"new", "d": b"new"}
    (tmp_path / "b").write_bytes(b"same")
    (tmp_path / "c").write_bytes(b"old")
    (tmp_path / "d").write_bytes(b"edited")
    stamp = {"files": {"c": pre.sha(b"old"), "d": pre.sha(b"old")}}
    got = dict((rel, act) for act, rel in pre.plan_prebuild(rendered, tmp_path, stamp))
    assert got == {"a": "write", "b": "keep", "c": "overwrite", "d": "conflict"}
