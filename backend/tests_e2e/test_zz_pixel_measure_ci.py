"""THROWAWAY — a measurement, not a test (#1605). This file exists only on the
branch `measure/dev2-1605-ci-vs-local`, whose pull request is never merged.

Question: how much does a screen rendered on the CI runner differ from the same
screen rendered in the local helper container (same pinned Chromium, another
operating system)? The answer decides where the baselines are made.

In CI it builds the pixel run itself — a database of its own, seeded and served
under the frozen clock — renders every screen of the set, and PRINTS the
difference with the locally recorded PNGs of this branch at several tolerances.
It never fails on a difference.
"""

import hashlib
import os
import subprocess
import sys
import time
import urllib.request

import pytest

from tests_e2e import pixels

PORT = 8001


@pytest.mark.skipif(
    os.environ.get("GITHUB_ACTIONS") != "true", reason="a measurement on the CI runner"
)
def test_measure_the_runner_against_the_local_baselines():
    from playwright.sync_api import sync_playwright
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    subprocess.run(
        ["sudo", "apt-get", "install", "-y", "-q", "faketime"], check=True, capture_output=True
    )

    # The app's own engine: its URL carries the password whatever the tests
    # before this one did to the environment.
    from app.database import engine

    url = make_url(engine.url.render_as_string(hide_password=False))
    print(
        "MEASURE-CI env url has password:",
        "@" in os.environ.get("DATABASE_URL", "")
        and ":" in os.environ.get("DATABASE_URL", "").split("@")[0][13:],
    )
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text("DROP DATABASE IF EXISTS raakpixel_ci WITH (FORCE)"))
        connection.execute(text("CREATE DATABASE raakpixel_ci"))
        print("MEASURE-CI db now:", connection.execute(text("select now()")).scalar())
    env = {
        **os.environ,
        "DATABASE_URL": url.set(database="raakpixel_ci").render_as_string(hide_password=False),
        "E2E_SEED": "1",
    }
    fake = ["faketime", pixels.PIXEL_NOW]
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        env=env,
        capture_output=True,
    )
    subprocess.run(
        [sys.executable, "seed_postal_codes.py"], check=True, env=env, capture_output=True
    )
    seeded = subprocess.run(
        [*fake, sys.executable, "seed_e2e.py"], check=True, env=env, capture_output=True, text=True
    )
    print("MEASURE-CI seed:", seeded.stdout.strip().splitlines()[-1])
    log = open("/tmp/pixel-backend.log", "w")
    server = subprocess.Popen(
        [
            *fake,
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
        ],
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/health")
                break
            except Exception:
                time.sleep(1)
        else:
            raise AssertionError(
                "the pixel server did not come up: " + open("/tmp/pixel-backend.log").read()[-2000:]
            )
        os.environ["PIXEL_BASE_URL"] = f"http://127.0.0.1:{PORT}"
        print(
            "MEASURE-CI os:",
            open("/etc/os-release").read().split("PRETTY_NAME=")[1].splitlines()[0],
        )
        with sync_playwright() as pw:
            browser = pixels.launch(pw)
            print("MEASURE-CI chromium:", browser.version)
            context = browser.new_context(
                base_url=os.environ["PIXEL_BASE_URL"], **pixels.context_options()
            )
            page = context.new_page()
            sessions = pixels.sessions()
            for screen, width in pixels.pairs():
                baseline = pixels.baseline_path(screen, width).read_bytes()
                first = pixels.render(page, screen, width, sessions)
                second = pixels.render(page, screen, width, sessions)
                twice = pixels.compare(first, second, tolerance=0)
                row = [
                    f"{screen.key}-{width[0]}",
                    f"same-bytes={hashlib.sha256(first).hexdigest() == hashlib.sha256(baseline).hexdigest()}",
                ]
                for tolerance in (0, 8, 16, 24, 48, 96):
                    d = pixels.compare(baseline, first, tolerance=tolerance)
                    row.append(f"t{tolerance}={d.pixels}")
                d = pixels.compare(baseline, first)
                row.append(
                    f"size={d.actual_size[0]}x{d.actual_size[1]}/{d.baseline_size[0]}x{d.baseline_size[1]}"
                )
                row.append(f"worst={d.worst}")
                row.append(f"box={d.box}")
                row.append(f"runner-twice: {twice.pixels}px worst {twice.worst}")
                print("MEASURE-CI", " | ".join(row))
            browser.close()
    finally:
        server.terminate()
