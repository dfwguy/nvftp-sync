"""Slack Socket Mode control plane with allowlists and human-gated writes."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from .config import Config, read_secret
from .gitlab import GitlabClient
from .intent import Operation, SlackIntent, parse_intent
from .models import ImportRequest
from .operations import BranchOperation, OperationStore
from .routing import resolve_target
from .state import Job, JobStore
from .worker import ImportWorker

LOG = logging.getLogger(__name__)


def build_app(config: Config) -> tuple[Any, str]:
    from slack_bolt import App

    app_token = read_secret(config.slack.app_token_file)
    app = App(token=read_secret(config.slack.bot_token_file))
    store = JobStore(config.paths.state / "jobs.sqlite3")
    operations = OperationStore(config.paths.state / "operations.sqlite3")
    worker = ImportWorker(config, store)
    worker_lock = threading.Lock()

    def authorized(user_id: str, channel_id: str, *, approval: bool = False) -> bool:
        users = config.slack.approver_user_ids if approval else config.slack.allowed_user_ids
        return user_id in users and channel_id in config.slack.allowed_channel_ids

    def dispatch(
        text: str,
        *,
        user_id: str,
        channel_id: str,
        idempotency_key: str,
        send: Callable[..., Any],
        legacy_import: bool = False,
    ) -> None:
        if not authorized(user_id, channel_id):
            send(text="This user or channel is not authorized for NVIS operations.")
            return
        try:
            intent = parse_intent(text, config.gitlab.group_path, legacy_import=legacy_import)
            _handle_intent(
                intent,
                user_id=user_id,
                channel_id=channel_id,
                idempotency_key=idempotency_key,
                send=send,
                config=config,
                store=store,
                operations=operations,
                worker=worker,
            )
        except Exception as exc:
            send(text=f"Request rejected: {str(exc)[:500]}\nTry `/nvis help`.")

    def slash_handler(ack: Any, body: dict[str, Any], respond: Any) -> None:
        ack()
        dispatch(
            str(body.get("text", "")),
            user_id=str(body.get("user_id", "")),
            channel_id=str(body.get("channel_id", "")),
            idempotency_key=str(body.get("trigger_id") or body.get("command_ts") or ""),
            send=lambda **payload: respond(response_type="ephemeral", **payload),
            legacy_import=str(body.get("command", "")) == "/nvis-import",
        )

    app.command("/nvis")(slash_handler)
    app.command("/nvis-import")(slash_handler)

    def event_handler(event: dict[str, Any], say: Any) -> None:
        if event.get("bot_id") or event.get("subtype"):
            return
        dispatch(
            str(event.get("text", "")),
            user_id=str(event.get("user", "")),
            channel_id=str(event.get("channel", "")),
            idempotency_key=str(event.get("client_msg_id") or event.get("event_ts") or ""),
            send=say,
        )

    app.event("app_mention")(event_handler)

    @app.event("message")
    def direct_message(event: dict[str, Any], say: Any) -> None:
        if event.get("channel_type") == "im":
            event_handler(event, say)

    @app.action("approve_nvis_import")
    def approve_import(ack: Any, body: dict[str, Any], say: Any) -> None:
        ack()
        user_id, channel_id, job_id = _action_context(body)
        if not authorized(user_id, channel_id, approval=True):
            say(text="Approval rejected: user or channel is not authorized.")
            return
        try:
            if store.get(job_id).requester == user_id:
                raise PermissionError("requesters cannot approve their own import")
            store.transition(job_id, expected=("planned",), status="approved", actor=user_id)
        except Exception as exc:
            say(text=f"Job was not approved: {str(exc)[:500]}")
            return
        say(text=f"Import `{job_id}` approved by <@{user_id}>; verification started.")

        def execute() -> None:
            try:
                with worker_lock:
                    result = worker.run(job_id)
                say(text=f"Import `{job_id}` is ready for human review: {result}")
            except Exception as exc:
                LOG.exception("import job failed", extra={"job_id": job_id})
                say(text=f"Import `{job_id}` failed safely: {str(exc)[:500]}")

        threading.Thread(target=execute, name=f"import-{job_id[:8]}", daemon=True).start()

    @app.action("approve_nvis_branch")
    def approve_branch(ack: Any, body: dict[str, Any], say: Any) -> None:
        ack()
        user_id, channel_id, operation_id = _action_context(body)
        if not authorized(user_id, channel_id, approval=True):
            say(text="Approval rejected: user or channel is not authorized.")
            return
        try:
            if operations.get_branch(operation_id).requester == user_id:
                raise PermissionError("requesters cannot approve their own branch operation")
            operation = operations.transition_branch(
                operation_id, expected=("planned",), status="running", actor=user_id
            )
            result = GitlabClient(config.gitlab).create_branch(
                target=operation.project, branch=operation.branch, ref=operation.base
            )
            operations.transition_branch(
                operation_id,
                expected=("running",),
                status="succeeded",
                actor="system",
                result_url=result,
            )
            say(text=f"Feature branch created by <@{user_id}>: {result}")
        except Exception as exc:
            try:
                operations.transition_branch(
                    operation_id, expected=("running",), status="failed", actor="system"
                )
            except Exception:
                LOG.exception(
                    "could not record failed branch operation",
                    extra={"operation_id": operation_id},
                )
            say(text=f"Branch operation failed safely: {str(exc)[:500]}")

    @app.action("cancel_nvis_operation")
    def cancel(ack: Any, body: dict[str, Any], say: Any) -> None:
        ack()
        user_id, channel_id, value = _action_context(body)
        if not authorized(user_id, channel_id, approval=True):
            say(text="Cancellation rejected: user or channel is not authorized.")
            return
        kind, operation_id = value.split(":", 1)
        try:
            if kind == "import":
                store.transition(
                    operation_id,
                    expected=("planned", "approved"),
                    status="cancelled",
                    actor=user_id,
                )
            elif kind == "branch":
                operations.transition_branch(
                    operation_id, expected=("planned",), status="cancelled", actor=user_id
                )
            else:
                raise ValueError("unknown operation type")
            say(text=f"Operation `{operation_id}` cancelled by <@{user_id}>.")
        except Exception as exc:
            say(text=f"Operation was not cancelled: {str(exc)[:500]}")

    return app, app_token


def _handle_intent(
    intent: SlackIntent,
    *,
    user_id: str,
    channel_id: str,
    idempotency_key: str,
    send: Callable[..., Any],
    config: Config,
    store: JobStore,
    operations: OperationStore,
    worker: ImportWorker,
) -> None:
    if intent.operation is Operation.HELP:
        send(text="NVIS OVA commands", blocks=_help_blocks())
        return
    if intent.operation is Operation.STATUS:
        if intent.job_id is None:
            valid, events = store.verify_audit_chain()
            send(
                text=f"NVIS Hub is online. Import audit chain: {'valid' if valid else 'INVALID'} ({events} events)."
            )
        else:
            send(
                text=f"Import {intent.job_id}", blocks=_job_status_blocks(store.get(intent.job_id))
            )
        return
    if intent.operation is Operation.CANCEL:
        assert intent.job_id
        job = store.get(intent.job_id)
        if job.requester != user_id and user_id not in config.slack.approver_user_ids:
            raise PermissionError("only the requester or an approver may request cancellation")
        send(text=f"Confirm cancellation of {job.id}", blocks=_cancel_blocks("import", job.id))
        return
    if intent.operation is Operation.REPLAY:
        assert intent.job_id
        original = store.get(intent.job_id)
        request = resolve_target(
            ImportRequest(original.source, original.artifact, original.target), config.routing
        )
        job = _plan_import(
            request,
            requester=user_id,
            channel=channel_id,
            idempotency_key=f"replay:{idempotency_key}",
            store=store,
            worker=worker,
        )
        send(
            text=f"Review replay import {job.id}",
            blocks=_approval_blocks(job.id, request, replay_of=original.id),
        )
        return
    if intent.operation is Operation.IMPORT:
        assert intent.request
        request = resolve_target(intent.request, config.routing)
        job = _plan_import(
            request,
            requester=user_id,
            channel=channel_id,
            idempotency_key=idempotency_key,
            store=store,
            worker=worker,
        )
        send(text=f"Review NVFTP import {job.id}", blocks=_approval_blocks(job.id, request))
        return
    if intent.operation is Operation.BRANCH:
        assert intent.project and intent.branch and intent.base
        operation = operations.create_branch(
            requester=user_id,
            channel=channel_id,
            project=intent.project,
            branch=intent.branch,
            base=intent.base,
            idempotency_key=idempotency_key,
        )
        send(text=f"Review branch operation {operation.id}", blocks=_branch_blocks(operation))
        return
    raise ValueError("unsupported operation")


def _plan_import(
    request: ImportRequest,
    *,
    requester: str,
    channel: str,
    idempotency_key: str,
    store: JobStore,
    worker: ImportWorker,
) -> Job:
    if not idempotency_key:
        raise ValueError("Slack request has no idempotency identifier")
    job = store.create(
        request, requester=requester, channel=channel, idempotency_key=idempotency_key
    )
    worker.plan(job)
    return job


def _action_context(body: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(body.get("user", {}).get("id", "")),
        str(body.get("channel", {}).get("id", "")),
        str(body.get("actions", [{}])[0].get("value", "")),
    )


def _approval_blocks(
    job_id: str,
    request: ImportRequest,
    *,
    replay_of: str | None = None,
) -> list[dict[str, Any]]:
    replay = f"\n*Replay of:* `{replay_of}`" if replay_of else ""
    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Approval required: NVFTP import"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Source:* `{request.source}`\n*Artifact:* `{request.artifact}`\n"
                    f"*Target:* `{request.target}`{replay}\nChecksums, archives, secrets, malware, and "
                    "Git history will be verified. The bot may push a branch and open an MR; it never approves or merges."
                ),
            },
        },
        _action_row("approve_nvis_import", job_id, "Approve import", "import", job_id),
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"Job `{job_id}` • awaiting an authorized approver"}
            ],
        },
    ]


def _branch_blocks(operation: BranchOperation) -> list[dict[str, Any]]:
    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Approval required: create feature branch"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Project:* `{operation.project}`\n*New branch:* `{operation.branch}`\n"
                    f"*Starting ref:* `{operation.base}`\nNo force, deletion, merge, or protected-branch write is permitted."
                ),
            },
        },
        _action_row("approve_nvis_branch", operation.id, "Create branch", "branch", operation.id),
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"Operation `{operation.id}`"}],
        },
    ]


def _action_row(
    approve_action: str,
    approve_value: str,
    approve_label: str,
    kind: str,
    operation_id: str,
) -> dict[str, Any]:
    return {
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": approve_label},
                "style": "primary",
                "action_id": approve_action,
                "value": approve_value,
                "confirm": {
                    "title": {"type": "plain_text", "text": "Authorize external write?"},
                    "text": {
                        "type": "mrkdwn",
                        "text": "This operation can write to NVIDIA GitLab.",
                    },
                    "confirm": {"type": "plain_text", "text": "Authorize"},
                    "deny": {"type": "plain_text", "text": "Back"},
                },
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Cancel"},
                "style": "danger",
                "action_id": "cancel_nvis_operation",
                "value": f"{kind}:{operation_id}",
            },
        ],
    }


def _cancel_blocks(kind: str, operation_id: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Confirm cancel"},
                    "style": "danger",
                    "action_id": "cancel_nvis_operation",
                    "value": f"{kind}:{operation_id}",
                }
            ],
        }
    ]


def _job_status_blocks(job: Job) -> list[dict[str, Any]]:
    result = f"\n*Result:* {job.result_url}" if job.result_url else ""
    error = f"\n*Error:* `{job.error[:300]}`" if job.error else ""
    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"Import • {job.status.upper()}"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Job:* `{job.id}`\n*Artifact:* `{job.artifact}`\n*Target:* `{job.target}`"
                    f"\n*Requested by:* <@{job.requester}>{result}{error}"
                ),
            },
        },
    ]


def _help_blocks() -> list[dict[str, Any]]:
    return [
        {"type": "header", "text": {"type": "plain_text", "text": "NVIS OVA CI/CD Hub"}},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*Import / stage / check in*\n"
                    "`/nvis import nvftp=/allowed/path artifact=release target=nvis-ova/project`\n"
                    "or `@NVIS import release from /allowed/path into project`\n\n"
                    '*Feature branch* ("fork" is accepted as an alias)\n'
                    "`/nvis branch project=project name=feature/my-change base=main`\n\n"
                    "*Observe and control*\n"
                    "`/nvis status [job=<id>]` • `/nvis cancel job=<id>` • `/nvis replay job=<id>`\n\n"
                    "Writes always require an authorized human to confirm. The bot never merges or approves MRs."
                ),
            },
        },
    ]


def serve(config: Config) -> None:
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    app, app_token = build_app(config)
    SocketModeHandler(app, app_token).start()
