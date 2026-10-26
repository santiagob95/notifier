import base64
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests
import yaml

from imax_notifier.config import Config
from imax_notifier.errors import MonitorError, RejectedMessage, UncertainMessage
from imax_notifier.http import Http
from imax_notifier.showcase import Showcase
from imax_notifier.state import GitHubStore, empty_state
from imax_notifier.telegram import Telegram


def response(status=200, data=None, text=None, headers=None):
    result = requests.Response()
    result.status_code = status
    result._content = (text if text is not None else json.dumps(data)).encode()
    result._content_consumed = True
    result.headers.update(headers or {})
    return result


def github():
    http = Mock()
    return http, GitHubStore(http, "example/repo", "fake-test-token", "main")


def test_github_initial_branch_and_state_creation():
    http, store = github()
    http.get.side_effect = [response(404), response(data={"name": "repo"}), response(data={"object": {"sha": "base"}})]
    http.write.side_effect = [response(201), response(201, {"content": {"sha": "first"}})]
    state = store.load()
    assert not http.write.called
    store.save(state)
    assert store.sha == "first"
    assert http.write.call_args_list[0].kwargs["json"]["ref"] == "refs/heads/monitor-state"
    payload = http.write.call_args_list[1].kwargs["json"]
    assert payload["branch"] == "monitor-state"
    assert json.loads(base64.b64decode(payload["content"])) == empty_state()
    assert "sha" not in payload


def test_github_existing_state_uses_sha_and_detects_conflict():
    http, store = github()
    encoded = base64.b64encode(json.dumps(empty_state()).encode()).decode()
    http.get.side_effect = [response(data={}), response(data={"encoding": "base64", "sha": "old", "content": encoded})]
    state = store.load()
    http.write.return_value = response(409)
    with pytest.raises(MonitorError, match="409"): store.save(state)
    assert http.write.call_args.kwargs["json"]["sha"] == "old"
    assert http.write.call_count == 1


def test_missing_state_in_existing_branch_is_not_reset():
    http, store = github()
    http.get.side_effect = [response(data={}), response(404)]
    with pytest.raises(MonitorError): store.load()
    http.write.assert_not_called()


def test_inaccessible_repository_not_considered_empty():
    http, store = github()
    http.get.side_effect = [response(404), response(404)]
    with pytest.raises(MonitorError): store.load()


def test_get_retries_transient_errors_only():
    http = Http()
    http.session = Mock()
    http.session.get.side_effect = [requests.Timeout("do not log"), response(503), response(data={"ok": 1})]
    with patch("imax_notifier.http.time.sleep") as sleep:
        assert http.get("https://example.com", label="Public API").status_code == 200
    assert http.session.get.call_count == 3
    assert sleep.call_count == 2


def test_http_auth_error_not_retried():
    http = Http()
    http.session = Mock()
    http.session.get.return_value = response(403)
    assert http.get("https://example.com", label="API").status_code == 403
    assert http.session.get.call_count == 1


def test_long_retry_after_defers_instead_of_hammering():
    http = Http()
    http.session = Mock()
    http.session.get.return_value = response(429, headers={"Retry-After": "300"})
    with pytest.raises(MonitorError, match="60"): http.get("https://example.com", label="API")
    assert http.session.get.call_count == 1


def test_catalog_fallback_only_on_error():
    http = Mock()
    http.get.side_effect = [response(503), response(text='<a href="pelicula.aspx?filmid=9000">Dune Part Three</a>')]
    assert Showcase(http, Config(("Dune Part Three",))).discover() == {9000}
    assert http.get.call_count == 2


def test_telegram_success():
    session = Mock()
    session.post.return_value = response(data={"ok": True, "result": {"message_id": 1}})
    Telegram("fake-test-token", "123", session).send("hello")
    assert session.post.call_count == 1
    assert session.post.call_args.kwargs["allow_redirects"] is False
    assert session.post.call_args.kwargs["json"]["chat_id"] == "123"


def test_telegram_timeout_never_retried_or_logged_with_secret():
    session = Mock()
    session.post.side_effect = requests.Timeout("https://api.telegram.org/botfake-test-token/sendMessage")
    with pytest.raises(UncertainMessage) as caught:
        Telegram("fake-test-token", "123", session).send("hello")
    assert "fake-test-token" not in str(caught.value)
    assert session.post.call_count == 1


def test_telegram_429_uses_server_delay():
    session = Mock()
    session.post.side_effect = [response(429, {"ok": False, "error_code": 429, "parameters": {"retry_after": 3}}), response(data={"ok": True})]
    with patch("imax_notifier.telegram.time.sleep") as sleep:
        Telegram("fake-test-token", "123", session).send("hello")
    sleep.assert_called_once_with(3)
    assert session.post.call_count == 2


@pytest.mark.parametrize("code", [400, 401, 403])
def test_telegram_explicit_rejection(code):
    session = Mock()
    session.post.return_value = response(code, {"ok": False, "error_code": code})
    with pytest.raises(RejectedMessage): Telegram("fake-test-token", "123", session).send("hello")
    assert session.post.call_count == 1


@pytest.mark.parametrize("reply", [response(502, text="<h1>error</h1>"), response(500, {"ok": False}), response(200, {"unexpected": True})])
def test_telegram_unknown_results_remain_uncertain(reply):
    session = Mock()
    session.post.return_value = reply
    with pytest.raises(UncertainMessage): Telegram("fake-test-token", "123", session).send("hello")
    assert session.post.call_count == 1


def test_workflow_serializes_and_uses_secret_env():
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.load((root / ".github/workflows/monitor.yml").read_text(encoding="utf-8-sig"), Loader=yaml.BaseLoader)
    assert workflow["on"]["schedule"][0]["cron"] == "7,37 * * * *"
    assert workflow["concurrency"] == {"group": "imax-ticket-monitor", "cancel-in-progress": "false"}
    assert workflow["jobs"]["monitor"]["permissions"]["contents"] == "write"
    step = workflow["jobs"]["monitor"]["steps"][-1]
    assert step["env"]["TELEGRAM_BOT_TOKEN"] == "${{ secrets.TELEGRAM_BOT_TOKEN }}"
    assert '--mode "$RUN_MODE"' in step["run"]
    assert "${{" not in step["run"]
