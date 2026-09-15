from __future__ import annotations

import io
import json
import pathlib

from nvis_integration.gitlab_read import GitLabReadModel


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def test_gitlab_read_model_only_gets_and_allowlists_fields(tmp_path: pathlib.Path) -> None:
    token = tmp_path / "token"
    token.write_text("top-secret")
    requests = []

    def open_request(request, *, timeout):
        requests.append((request, timeout))
        return _Response(
            json.dumps(
                [
                    {
                        "id": 1,
                        "name": "repo",
                        "path_with_namespace": "nvis-ova/repo",
                        "web_url": "https://gitlab.example/nvis-ova/repo",
                        "runners_token": "must-not-leak",
                    }
                ]
            ).encode()
        )

    reader = GitLabReadModel(
        base_url="https://gitlab.example", group="nvis-ova", token_file=token, opener=open_request
    )
    assert reader.repositories() == [
        {
            "id": 1,
            "name": "repo",
            "path_with_namespace": "nvis-ova/repo",
            "web_url": "https://gitlab.example/nvis-ova/repo",
        }
    ]
    request, timeout = requests[0]
    assert request.method == "GET"
    assert request.headers["Private-token"] == "top-secret"
    assert "top-secret" not in request.full_url
    assert timeout == 10
