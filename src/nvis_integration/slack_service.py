"""Slack Socket Mode control plane."""

from __future__ import annotations

import logging
import threading
from typing import Any

from .config import Config, read_secret
from .models import ImportRequest, parse_import_command
from .routing import resolve_target
from .state import JobStore
from .worker import ImportWorker

LOG = logging.getLogger(__name__)


def build_app(config: Config) -> tuple[Any, str]:
    from slack_bolt import App

    bot_token = read_secret(config.slack.bot_token_file)
    app_token = read_secret(config.slack.app_token_file)
    app = App(token=bot_token)
    store = JobStore(config.paths.state / "jobs.sqlite3")
    worker = ImportWorker(config, store)
    worker_lock = threading.Lock()

    def authorized(user_id: str, channel_id: str, *, approval: bool = False) -> bool:
        users = config.slack.approver_user_ids if approval else config.slack.allowed_user_ids
        return user_id in users and channel_id in config.slack.allowed_channel_ids

    @app.command("/nvis-import")
    def import_command(ack: Any, body: dict[str, Any], respond: Any) -> None:
        ack()
        user_id = str(body.get("user_id", ""))
        channel_id = str(body.get("channel_id", ""))
        if not authorized(user_id, channel_id):
            respond("This user or channel is not authorized for NVIS imports.", response_type="ephemeral")
            return
        try:
            request = resolve_target(
                parse_import_command(str(body.get("text", "")), config.gitlab.group_path),
                config.routing,
            )
            idempotency_key = str(body.get("trigger_id") or body.get("command_ts") or "")
            if not idempotency_key:
                raise ValueError("Slack request has no idempotency identifier")
            job = store.create(
                request,
                requester=user_id,
                channel=channel_id,
                idempotency_key=idempotency_key,
            )
            worker.plan(job)
        except Exception as exc:
            respond(f"Import plan rejected: {exc}", response_type="ephemeral")
            return
        respond(
            text=f"Review NVFTP import job {job.id}",
            response_type="in_channel",
            blocks=_approval_blocks(job.id, request),
        )

    @app.action("approve_nvis_import")
    def approve(ack: Any, body: dict[str, Any], say: Any) -> None:
        ack()
        user_id = str(body.get("user", {}).get("id", ""))
        channel_id = str(body.get("channel", {}).get("id", ""))
        job_id = str(body.get("actions", [{}])[0].get("value", ""))
        if not authorized(user_id, channel_id, approval=True):
            say(text="Approval rejected: user or channel is not authorized.")
            return
        try:
            store.transition(job_id, expected=("planned",), status="approved")
        except Exception as exc:
            say(text=f"Job was not approved: {exc}")
            return
        say(text=f"NVIS import `{job_id}` approved by <@{user_id}>; verification started.")

        def execute() -> None:
            try:
                with worker_lock:
                    result = worker.run(job_id)
                say(text=f"NVIS import `{job_id}` is ready for human review: {result}")
            except Exception as exc:  # Slack receives only bounded safe error text.
                LOG.exception("import job failed", extra={"job_id": job_id})
                say(text=f"NVIS import `{job_id}` failed safely: {str(exc)[:500]}")

        threading.Thread(target=execute, name=f"import-{job_id[:8]}", daemon=True).start()

    @app.action("cancel_nvis_import")
    def cancel(ack: Any, body: dict[str, Any], say: Any) -> None:
        ack()
        user_id = str(body.get("user", {}).get("id", ""))
        channel_id = str(body.get("channel", {}).get("id", ""))
        job_id = str(body.get("actions", [{}])[0].get("value", ""))
        if not authorized(user_id, channel_id, approval=True):
            say(text="Cancellation rejected: user or channel is not authorized.")
            return
        try:
            store.transition(job_id, expected=("planned", "approved"), status="cancelled")
            say(text=f"NVIS import `{job_id}` cancelled by <@{user_id}>.")
        except Exception as exc:
            say(text=f"Job was not cancelled: {exc}")

    return app, app_token


def _approval_blocks(job_id: str, request: ImportRequest) -> list[dict[str, Any]]:
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*NVIS import requires approval*\n"
                    f"*Source:* `{request.source}`\n"
                    f"*Artifact:* `{request.artifact}`\n"
                    f"*Target:* `{request.target}`\n"
                    "The worker will verify, scan, push a branch/project, and stop for human review."
                ),
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Approve import"},
                    "style": "primary",
                    "action_id": "approve_nvis_import",
                    "value": job_id,
                    "confirm": {
                        "title": {"type": "plain_text", "text": "Approve import?"},
                        "text": {"type": "mrkdwn", "text": "This can write to NVIDIA GitLab."},
                        "confirm": {"type": "plain_text", "text": "Approve"},
                        "deny": {"type": "plain_text", "text": "Back"},
                    },
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Cancel"},
                    "style": "danger",
                    "action_id": "cancel_nvis_import",
                    "value": job_id,
                },
            ],
        },
        {"type": "context", "elements": [{"type": "mrkdwn", "text": f"Job `{job_id}`"}]},
    ]


def serve(config: Config) -> None:
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    app, app_token = build_app(config)
    SocketModeHandler(app, app_token).start()
