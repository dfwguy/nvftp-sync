"""Administrative CLI and systemd entry point."""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import pathlib
import sys

from .config import load_config, read_secret
from .models import ensure_allowed_source, parse_import_command
from .nvftp import NvftpClient
from .producer import build_envelope
from .routing import resolve_target
from .slack_service import serve
from .state import JobStore

DEFAULT_CONFIG = pathlib.Path("/etc/nvis-integration/config.toml")
LOG = logging.getLogger(__name__)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nvis-integration")
    parser.add_argument("--config", type=pathlib.Path, default=DEFAULT_CONFIG)
    subcommands = parser.add_subparsers(dest="command", required=True)
    doctor = subcommands.add_parser("doctor", help="validate config and credentials")
    doctor.add_argument("--network", action="store_true")
    listing = subcommands.add_parser("nvftp-list", help="read-only allowed NVFTP listing")
    listing.add_argument("path")
    plan = subcommands.add_parser("plan", help="validate a proposed import without downloading")
    plan.add_argument("--nvftp", required=True)
    plan.add_argument("--artifact", required=True)
    plan.add_argument("--target", default="auto")
    subcommands.add_parser("serve", help="run Slack Socket Mode service")
    bootstrap = subcommands.add_parser(
        "portal-bootstrap", help="create local portal login/session credentials"
    )
    bootstrap.add_argument("--runtime-root", type=pathlib.Path, required=True)
    hub = subcommands.add_parser("hub-serve", help="run the localhost NVIS-OVA portal")
    hub.add_argument("--web-root", type=pathlib.Path, required=True)
    hub.add_argument("--auth-records", type=pathlib.Path, required=True)
    hub.add_argument("--session-secret", type=pathlib.Path, required=True)
    hub.add_argument("--credential-root", type=pathlib.Path, required=True)
    hub.add_argument("--port", type=int, default=8787)
    hub.add_argument("--host", default="127.0.0.1")
    hub.add_argument("--allow-network", action="store_true")
    hub.add_argument("--insecure-http", action="store_true")
    audit = subcommands.add_parser("audit-verify", help="verify the hash-chained audit ledger")
    audit.add_argument("--json", action="store_true")
    subcommands.add_parser(
        "portal-audit-verify", help="verify the portal-level hash-chained audit ledger"
    )
    job = subcommands.add_parser("job-show", help="show one job and its audit events")
    job.add_argument("job_id")
    package = subcommands.add_parser("package", help="create a verified NVFTP envelope")
    package.add_argument("--repo", type=pathlib.Path, required=True)
    package.add_argument("--output", type=pathlib.Path, required=True)
    package.add_argument("--artifact", required=True)
    package.add_argument("--target", required=True)
    package.add_argument("--source-kind", choices=("snapshot", "change-set"), required=True)
    package.add_argument("--classification-attested-by", required=True)
    package.add_argument("--base-commit")
    return parser


def _doctor(config: object, network: bool) -> int:
    from .config import Config

    assert isinstance(config, Config)
    checks: dict[str, str] = {}
    for label, path in {
        "nvftp_identity": config.nvftp.identity_file,
        "known_hosts": config.nvftp.known_hosts_file,
        "slack_bot_token": config.slack.bot_token_file,
        "slack_app_token": config.slack.app_token_file,
        "gitlab_token": config.gitlab.token_file,
    }.items():
        try:
            if label.endswith("token"):
                read_secret(path)
            elif not path.is_file():
                raise FileNotFoundError(path)
            checks[label] = "ok"
        except Exception as exc:
            checks[label] = f"not-ready: {exc}"
    checks["gitlab_bot_username"] = (
        "ok" if config.gitlab.bot_username != "REPLACE_GITLAB_BOT_USERNAME" else "not-ready"
    )
    checks["slack_authorization"] = (
        "ok"
        if config.slack.allowed_user_ids
        and config.slack.approver_user_ids
        and config.slack.allowed_channel_ids
        else "not-ready: allowlists are empty"
    )
    if network:
        try:
            NvftpClient(config.nvftp).list(config.nvftp.allowed_prefixes[0])
            checks["nvftp_network"] = "ok"
        except Exception as exc:
            checks["nvftp_network"] = f"failed: {exc}"
    print(json.dumps(checks, indent=2, sort_keys=True))
    return 0 if all(value == "ok" for value in checks.values()) else 1


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        if args.command == "package":
            print(
                json.dumps(
                    build_envelope(
                        repository=args.repo.resolve(),
                        output=args.output.resolve(),
                        artifact=args.artifact,
                        target=args.target,
                        source_kind=args.source_kind,
                        classification_attested_by=args.classification_attested_by,
                        base_commit=args.base_commit,
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return
        if args.command == "portal-bootstrap":
            from .portal_runtime import bootstrap_portal

            paths = bootstrap_portal(args.runtime_root.resolve())
            print(
                json.dumps(
                    {name: str(path) for name, path in paths.items()}, indent=2, sort_keys=True
                )
            )
            return
        config = load_config(args.config)
        if args.command == "doctor":
            raise SystemExit(_doctor(config, args.network))
        if args.command == "nvftp-list":
            ensure_allowed_source(args.path, config.nvftp.allowed_prefixes)
            print(NvftpClient(config.nvftp).list(args.path))
            return
        if args.command == "plan":
            text = f"nvftp={args.nvftp} artifact={args.artifact} target={args.target}"
            request = resolve_target(
                parse_import_command(text, config.gitlab.group_path), config.routing
            )
            ensure_allowed_source(request.source, config.nvftp.allowed_prefixes)
            NvftpClient(config.nvftp).assert_artifact_set(request.source, request.artifact)
            print(json.dumps({"status": "ready-for-approval", **request.__dict__}, indent=2))
            return
        if args.command == "serve":
            serve(config)
            return
        if args.command == "hub-serve":
            from .hub_api import serve_localhost
            from .portal_runtime import build_portal

            application = build_portal(
                config,
                web_root=args.web_root,
                auth_records_file=args.auth_records,
                session_secret_file=args.session_secret,
                credential_root=args.credential_root,
                secure_cookies=not args.insecure_http,
            )
            server = serve_localhost(
                application,
                port=args.port,
                host=args.host,
                allow_network=args.allow_network,
            )
            LOG.info("NVIS-OVA Hub listening on http://%s:%s", args.host, args.port)
            server.serve_forever()
            return
        if args.command == "audit-verify":
            store = JobStore(config.paths.state / "jobs.sqlite3")
            valid, position = store.verify_audit_chain()
            result = {"valid": valid, "events_checked": position if valid else position - 1}
            print(json.dumps(result, sort_keys=True) if args.json else result)
            raise SystemExit(0 if valid else 1)
        if args.command == "job-show":
            store = JobStore(config.paths.state / "jobs.sqlite3")
            print(
                json.dumps(
                    {
                        "job": dataclasses.asdict(store.get(args.job_id)),
                        "events": [
                            dataclasses.asdict(event) for event in store.events(args.job_id)
                        ],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return
        if args.command == "portal-audit-verify":
            from .portal_audit import PortalAuditLog

            valid, position = PortalAuditLog(
                config.paths.state / "portal-audit.jsonl"
            ).verify()
            print(json.dumps({"valid": valid, "events_checked": position}, sort_keys=True))
            raise SystemExit(0 if valid else 1)
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
