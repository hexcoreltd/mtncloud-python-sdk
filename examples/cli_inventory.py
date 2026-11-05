"""Run the installed read-only CLI from Python.

For shell usage, prefer directly invoking::

    mtncloud inventory --only instances,networks,routers --output json
"""

from mtn_cloud.cli import main

if __name__ == "__main__":
    raise SystemExit(
        main(["inventory", "--only", "instances,networks,routers", "--output", "json"])
    )
