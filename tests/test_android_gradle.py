"""Gradle runs recover from a stuck daemon or a held cache lock by stopping the daemons and building once more."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pyxpo.build import android

WEDGED = "FAILURE: Build failed with an exception.\n* What went wrong:\nGradle build daemon disappeared unexpectedly\n"
LOCKED = ("Timeout waiting to lock journal cache (/x/.gradle/caches/journal-1). "
          "It is currently in use by another Gradle instance.\nOwner PID: 24980\n")


def test_wedged_signatures():
    assert android._gradle_wedged(WEDGED)
    assert android._gradle_wedged(LOCKED)
    assert android._gradle_wedged("java.lang.NoClassDefFoundError: org/gradle/internal/exceptions/Contextual")
    assert not android._gradle_wedged("e: MainActivity.kt:12: Unresolved reference: foo")


def test_gradle_version_from_wrapper(tmp_path):
    props = tmp_path / "gradle" / "wrapper"
    props.mkdir(parents=True)
    (props / "gradle-wrapper.properties").write_text(
        "distributionUrl=https\\://services.gradle.org/distributions/gradle-8.10.2-bin.zip\n")
    (tmp_path / "gradlew").write_text("#!/bin/sh\n")
    assert android._gradle_version(str(tmp_path / "gradlew")) == "8.10.2"
    assert android._gradle_version("/repo/.cache/gradle-8.10.2/bin/gradle") == "8.10.2"
    assert android._gradle_version("/usr/local/bin/gradle") is None


def test_daemon_pids_only_live_gradle(tmp_path, monkeypatch):
    logs = tmp_path / "daemon" / "8.10.2"
    logs.mkdir(parents=True)
    for pid in (111, 222):
        (logs / ("daemon-%d.out.log" % pid)).write_text("")
    monkeypatch.setenv("GRADLE_USER_HOME", str(tmp_path))
    commands = {111: "java ... org.gradle.launcher.daemon.bootstrap.GradleDaemon 8.10.2", 24980: "java GradleDaemon"}

    def ps(cmd, **kw):
        pid = int(cmd[-1])
        if pid in commands:
            return subprocess.CompletedProcess(cmd, 0, commands[pid] + "\n")
        return subprocess.CompletedProcess(cmd, 1, "")  # 222 exited; its log stays behind

    monkeypatch.setattr(android.subprocess, "run", ps)
    assert android._gradle_daemon_pids("8.10.2", LOCKED) == [111, 24980]


def _script(tmp_path: Path, body: str) -> Path:
    s = tmp_path / "fake-gradle"
    s.write_text("#!/bin/sh\n" + body)
    s.chmod(0o755)
    return s


def test_run_gradle_retries_once_after_wedge(tmp_path, monkeypatch, capsys):
    # first run fails with a wedged daemon, the second one succeeds
    marker = tmp_path / "ran"
    gradle = _script(tmp_path, 'if [ -f "%s" ]; then echo BUILD SUCCESSFUL; exit 0; fi\n'
                               'touch "%s"; echo "Gradle build daemon disappeared unexpectedly"; exit 1\n'
                     % (marker, marker))
    resets = []
    monkeypatch.setattr(android, "_reset_gradle", lambda g, out, env: resets.append(out))
    android.run_gradle([gradle, "assembleDebug"], env=dict(os.environ))
    assert len(resets) == 1 and "disappeared" in resets[0]
    out = capsys.readouterr().out
    assert "BUILD SUCCESSFUL" in out and "stuck" in out


def test_run_gradle_app_error_does_not_retry(tmp_path, monkeypatch):
    gradle = _script(tmp_path, 'echo "e: Unresolved reference: foo"; exit 1\n')
    monkeypatch.setattr(android, "_reset_gradle", lambda *a: pytest.fail("reset on an app error"))
    with pytest.raises(android.BuildError) as e:
        android.run_gradle([gradle, "assembleDebug"], env=dict(os.environ))
    assert "pyxpo clean" not in str(e.value)


def test_run_gradle_still_wedged_points_at_clean(tmp_path, monkeypatch):
    gradle = _script(tmp_path, 'echo "Gradle build daemon disappeared unexpectedly"; exit 1\n')
    monkeypatch.setattr(android, "_reset_gradle", lambda *a: None)
    with pytest.raises(android.BuildError) as e:
        android.run_gradle([gradle, "assembleDebug"], env=dict(os.environ))
    assert "pyxpo clean android" in str(e.value)


def test_clean_throwaway_project(tmp_path, monkeypatch):
    shell = tmp_path / "build" / "android" / "shell" / "app" / "build"
    shell.mkdir(parents=True)
    monkeypatch.setattr(android, "_reset_gradle", lambda *a: None)
    monkeypatch.setattr(android, "find_gradle", lambda native=None: "gradle")
    assert android.clean(tmp_path) == [tmp_path / "build" / "android"]
    assert not (tmp_path / "build" / "android").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="sh scripts")
def test_stream_returns_tail(tmp_path):
    s = _script(tmp_path, 'i=0; while [ $i -lt 500 ]; do echo line$i; i=$((i+1)); done; exit 3\n')
    code, tail = android._stream([s], dict(os.environ))
    assert code == 3 and "line499" in tail and "line0\n" not in tail


def test_refresh_shell_keeps_gradle_state(tmp_path):
    native = tmp_path / "shell"
    for rel in (".gradle/x", "app/build/out.apk", "app/.cxx/c", "pyxpo-gen/assets/a", "app/old.kt", "build.gradle.kts"):
        (native / rel).parent.mkdir(parents=True, exist_ok=True)
        (native / rel).write_text("old")
    android._refresh_shell(native, {"build.gradle.kts": b"new", "app/src/A.kt": b"a", "gradlew": b"#!/bin/sh\n"})
    for rel in (".gradle/x", "app/build/out.apk", "app/.cxx/c", "pyxpo-gen/assets/a"):
        assert (native / rel).read_text() == "old"
    assert not (native / "app" / "old.kt").exists()
    assert (native / "build.gradle.kts").read_bytes() == b"new" and (native / "app/src/A.kt").is_file()
    assert os.access(str(native / "gradlew"), os.X_OK)
