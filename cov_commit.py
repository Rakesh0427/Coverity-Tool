#!/usr/bin/env python3
"""
cov_commit.py — headless build → analyse → commit for Coverity Connect.

Populates an empty Coverity stream from a local source tree, without the GUI.
Useful on a build machine or in CI.

Examples
--------
Full run::

    python cov_commit.py \
        --idir /work/cov-idir \
        --source /work/src \
        --build-command "make -j8" \
        --host coverity.example.com --port 443 \
        --stream MyStream --user rakesh

Print the commands without running them::

    python cov_commit.py ... --dry-run

Commit an already-analysed intermediate directory::

    python cov_commit.py --idir /work/cov-idir --stages commit \
        --host coverity.example.com --stream MyStream \
        --auth-key-file ~/.coverity/auth-key.txt

The password is read from the ``COVERITY_PASSPHRASE`` environment variable —
it is never accepted as a command-line flag, since argv is world-readable on
most systems. An ``--auth-key-file`` is preferred over a password.
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
        description="Build, analyse and commit defects to Coverity Connect.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Password: set COVERITY_PASSPHRASE, or use --auth-key-file.",
    )
    p.add_argument("--idir", required=True,
                   help="intermediate directory (cov-* --dir)")
    p.add_argument("--source", default="",
                   help="source folder; used as the build working directory")
    p.add_argument("--bin-dir", default="",
                   help="Coverity Analysis bin folder (if not on PATH)")

    cap = p.add_argument_group("capture (cov-build)")
    cap.add_argument("--build-command", default="",
                     help="build command to wrap, e.g. 'make -j8'")
    cap.add_argument("--no-command", action="store_true",
                     help="scan the source tree instead of running a build")

    an = p.add_argument_group("analysis (cov-analyze)")
    an.add_argument("--no-all", action="store_true",
                    help="do not pass --all (all checkers are on by default)")
    an.add_argument("--aggressiveness", choices=["low", "medium", "high"],
                    default="", help="--aggressiveness-level")
    an.add_argument("--strip-path", action="append", default=[],
                    help="strip this prefix from reported paths (repeatable)")
    an.add_argument("--analyze-args", default="",
                    help="extra cov-analyze arguments (quoted)")

    co = p.add_argument_group("commit (cov-commit-defects)")
    co.add_argument("--host", default="", help="Coverity Connect host")
    co.add_argument("--port", default="", help="Coverity Connect port")
    co.add_argument("--no-ssl", action="store_true", help="use http, not https")
    co.add_argument("--stream", default="", help="target stream (must exist)")
    co.add_argument("--user", default="", help="Coverity Connect username")
    co.add_argument("--auth-key-file", default="",
                    help="auth key file (preferred over a password)")
    co.add_argument("--description", default="", help="commit description")
    co.add_argument("--version", default="", help="commit version/SHA")
    co.add_argument("--no-trust-cert", action="store_true",
                    help="do not auto-trust an unseen server certificate")
    co.add_argument("--commit-args", default="",
                    help="extra cov-commit-defects arguments (quoted)")

    p.add_argument("--stages", default="build,analyze,commit",
                   help="comma-separated subset of: build,analyze,commit")
    p.add_argument("--dry-run", action="store_true",
                   help="print the commands without executing them")
    p.add_argument("--prompt-password", action="store_true",
                   help="prompt for the password interactively")
    return p


def config_from_args(args, password=""):
    return cov_cli.CommitConfig(
        idir=args.idir,
        build_command=args.build_command,
        source_dir=args.source,
        bin_dir=args.bin_dir,
        all_checkers=not args.no_all,
        aggressiveness=args.aggressiveness,
        strip_paths=list(args.strip_path),
        extra_analyze_args=args.analyze_args,
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
        extra_commit_args=args.commit_args,
        no_command=args.no_command,
        fs_capture_search=args.source,
    )


def parse_stages(text):
    valid = {cov_cli.STAGE_BUILD, cov_cli.STAGE_ANALYZE, cov_cli.STAGE_COMMIT}
    order = [cov_cli.STAGE_BUILD, cov_cli.STAGE_ANALYZE, cov_cli.STAGE_COMMIT]
    wanted = {s.strip().lower() for s in (text or "").split(",") if s.strip()}
    unknown = wanted - valid
    if unknown:
        raise ValueError(f"unknown stage(s): {', '.join(sorted(unknown))}")
    if not wanted:
        raise ValueError("no stages selected")
    return [s for s in order if s in wanted]


def main(argv=None):
    args = build_parser().parse_args(argv)

    try:
        stages = parse_stages(args.stages)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    password = os.environ.get("COVERITY_PASSPHRASE", "")
    if args.prompt_password and not args.auth_key_file:
        password = getpass.getpass("Coverity Connect password: ")

    cfg = config_from_args(args, password)

    problems = cov_cli.validate_config(cfg, stages)
    if problems:
        print("Cannot start — please fix:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 2

    try:
        os.makedirs(cfg.idir, exist_ok=True)
    except OSError as exc:
        print(f"error: cannot create intermediate directory: {exc}",
              file=sys.stderr)
        return 2

    def log(text):
        sys.stdout.write(text)
        sys.stdout.flush()

    def stage_started(stage):
        log(f"\n=== {cov_cli.STAGE_LABELS.get(stage, stage)} ===\n")

    result = cov_cli.run_pipeline(cfg, stages=stages, log_cb=log,
                                  stage_cb=stage_started,
                                  dry_run=args.dry_run)
    print("\n" + result.summary())
    if result.ok and cov_cli.STAGE_COMMIT in stages and not args.dry_run:
        print(f"\nDefects committed to stream '{cfg.stream}'.")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
