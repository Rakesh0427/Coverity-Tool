#!/usr/bin/env python3
"""
cov_commit.py — headless commit of Coverity analysis results to Connect.

Uploads an existing intermediate directory (idir) to a Coverity Connect stream
by driving ``cov-commit-defects``. Building and analysing the code is done
separately by the user; this only performs the commit.

Examples
--------
Commit an analysed intermediate directory::

    export COVERITY_PASSPHRASE='...'
    python cov_commit.py --idir /work/cov-idir \
        --host coverity.example.com --port 443 \
        --stream MyStream --user rakesh

Show the command without running it::

    python cov_commit.py --idir /work/cov-idir --host h --stream s \
        --user u --dry-run

Check whether a folder can be committed::

    python cov_commit.py --idir /some/folder --inspect

Note
----
``cov-commit-defects`` uploads an **intermediate directory**: the folder passed
to ``cov-build --dir`` / ``cov-analyze --dir``, containing ``emit/`` (captured
source) and ``output/`` (analysis results). Use ``--inspect`` to check whether
a folder qualifies.

The password is read from the ``COVERITY_PASSPHRASE`` environment variable and
has no command-line flag, because argv is visible to other users via the
process list. An ``--auth-key-file`` is preferred.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys

import cov_cli


def build_parser():
    p = argparse.ArgumentParser(
        prog="cov_commit.py",
        description="Commit Coverity analysis results (an intermediate "
                    "directory) to a Coverity Connect stream.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Password: set COVERITY_PASSPHRASE, or use --auth-key-file.",
    )
    p.add_argument("--idir", required=True,
                   help="intermediate directory produced by cov-build/cov-analyze")
    p.add_argument("--bin-dir", default="",
                   help="Coverity Analysis bin folder (if not on PATH)")

    p.add_argument("--host", default="", help="Coverity Connect host")
    p.add_argument("--port", default="", help="Coverity Connect port")
    p.add_argument("--no-ssl", action="store_true", help="use http, not https")
    p.add_argument("--stream", default="", help="target stream (must exist)")
    p.add_argument("--user", default="", help="Coverity Connect username")
    p.add_argument("--auth-key-file", default="",
                   help="auth key file (preferred over a password)")
    p.add_argument("--description", default="", help="snapshot description")
    p.add_argument("--version", default="", help="snapshot version/SHA")
    p.add_argument("--strip-path", action="append", default=[],
                   help="strip this prefix from reported paths (repeatable)")
    p.add_argument("--no-trust-cert", action="store_true",
                   help="do not auto-trust an unseen server certificate")
    p.add_argument("--commit-args", default="",
                   help="extra cov-commit-defects arguments (quoted)")

    p.add_argument("--dry-run", action="store_true",
                   help="print the command without executing it")
    p.add_argument("--inspect", action="store_true",
                   help="report what --idir is and whether it can be committed")
    p.add_argument("--prompt-password", action="store_true",
                   help="prompt for the password interactively")
    return p


def config_from_args(args, password=""):
    return cov_cli.CommitConfig(
        idir=args.idir,
        bin_dir=args.bin_dir,
        host=args.host,
        port=args.port,
        stream=args.stream,
        username=args.user,
        password=password,
        auth_key_file=args.auth_key_file,
        use_ssl=not args.no_ssl,
        on_new_cert_trust=not args.no_trust_cert,
        description=args.description,
        version=args.version,
        strip_paths=list(args.strip_path),
        extra_args=args.commit_args,
    )


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.inspect:
        info = cov_cli.inspect_input(args.idir)
        print(f"Path : {info.path}")
        print(f"Type : {info.kind}")
        print(f"Commit-ready: {'yes' if info.committable else 'no'}")
        print(f"\n{info.message}")
        if info.hint:
            print(f"\n{info.hint}")
        return 0

    password = os.environ.get("COVERITY_PASSPHRASE", "")
    if args.prompt_password and not args.auth_key_file:
        password = getpass.getpass("Coverity Connect password: ")

    cfg = config_from_args(args, password)

    problems = cov_cli.validate_config(cfg)
    if problems:
        print("Cannot commit — please fix:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 2

    def log(text):
        sys.stdout.write(text)
        sys.stdout.flush()

    result = cov_cli.run_commit(cfg, log_cb=log, dry_run=args.dry_run)
    print("\n" + result.summary())
    if result.ok and not args.dry_run:
        print(f"Defects committed to stream '{cfg.stream}' on {cfg.host}.")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
