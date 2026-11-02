"""Приёмки SPEC-0009 v0.1.2 п.9: очередь — в момент отправки.

Механизм scripts/upstream_send.py: порядок fail-closed карта → очередь → POST.
Приёмки исполняются на фейковом поиске — ни одного сетевого вызова; живые
данные донорства (organs/donation.yaml, реестр, матрица) используются как есть:
спека сдаёт свою кровь на настоящих картах.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "upstream_send.py"


def _load():
    spec = importlib.util.spec_from_file_location("upstream_send", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["upstream_send"] = module
    spec.loader.exec_module(module)
    return module


upstream_send = _load()


def _boom(query):  # любой сетевой вызов — провал приёмки порядка
    raise AssertionError(f"сетевой вызов не должен был случиться: {query}")


def _boom_post(base_repo, payload):
    raise AssertionError(f"POST не должен был случиться: {payload}")


class TestQueueVerdict:
    def test_occupied_queue_refuses_with_pr_numbers(self):
        """Занятая очередь → отказ queue-occupied с номерами конкурентов (п.9)."""
        def fake_search(query):
            assert "repo:microsoft/markitdown" in query
            assert "is:pr" in query and "is:open" in query
            return [
                {"number": 2465, "title": "Escape pipes in HTML/DOCX/XLSX table cells"},
                {"number": 2608, "title": "fix: escape pipes in HTML table cell content"},
            ]

        ok, rule, reason = upstream_send.queue_verdict("microsoft/markitdown", "escape pipes table", fake_search)
        assert ok is False
        assert rule == "queue-occupied"
        assert "#2465" in reason and "#2608" in reason

    def test_clear_queue_passes(self):
        """Свободная очередь → queue-clear."""
        ok, rule, _ = upstream_send.queue_verdict("org/repo", "rare defect genre", lambda q: [])
        assert ok is True
        assert rule == "queue-clear"

    def test_empty_keywords_refuses_before_search(self):
        """Пустой жанр → missing-keywords, поиск не выполняется (G1)."""
        called = []

        def spy(query):
            called.append(query)
            return []

        ok, rule, _ = upstream_send.queue_verdict("org/repo", "   ", spy)
        assert ok is False
        assert rule == "missing-keywords"
        assert called == []

    def test_search_failure_refuses_not_silences(self):
        """Ошибка поиска — отказ search-failed, не зелёный вердикт (G1)."""

        def broken(query):
            raise upstream_send.SearchError("HTTP 403: rate limit")

        ok, rule, _ = upstream_send.queue_verdict("org/repo", "some genre", broken)
        assert ok is False
        assert rule == "search-failed"


def _with_synthetic_collar_card(monkeypatch):
    """Живых cla+donate карт не существует (гейт их отвергает) — collar-приёмка
    исполняется на синтетической карте зарегистрированного органа (ollama/ollama)."""
    card = {
        "repo": "ollama/ollama",
        "protocol": "cla",
        "decision": "donate",
        "evidence": [
            {"date": "2026-11-02", "url": "https://example.org/cla", "fact": "CLA обнаружен — синтетика приёмки"},
        ],
    }
    monkeypatch.setattr(upstream_send.donation, "load_cards", lambda *a, **k: [card])


class TestOrder:
    def test_collar_organ_refused_before_network(self, capsys, monkeypatch):
        """cla+donate — отказ гейтом карт ДО сетевых вызовов (п.9)."""
        _with_synthetic_collar_card(monkeypatch)
        code = upstream_send.run_send(
            "ollama/ollama", "escape pipes", search_fn=_boom, create_fn=_boom_post,
        )
        out = capsys.readouterr().out
        assert code == 1
        assert "UPSTREAM: FAIL (collar)" in out
        assert "ошейник" in out

    def test_organ_without_card_refused(self, capsys):
        """Орган без карты донорства — отказ no-card до поиска (G1, п.9)."""
        code = upstream_send.run_send(
            "someone/untyped-organ", "some genre", search_fn=_boom, create_fn=_boom_post,
        )
        out = capsys.readouterr().out
        assert code == 1
        assert "UPSTREAM: FAIL (no-card)" in out
        assert "донорства нет" in out

    def test_occupied_queue_blocks_post(self, capsys):
        """Карта зелёная, очередь занята → отказ, POST не выполняется (п.9)."""
        code = upstream_send.run_send(
            "microsoft/markitdown",
            "escape pipes table",
            head="rtynbirf:fix/x",
            title="fix",
            send=True,
            search_fn=lambda q: [{"number": 2465, "title": "Escape pipes"}],
            create_fn=_boom_post,
        )
        out = capsys.readouterr().out
        assert code == 1
        assert "OK карта:" in out
        assert "UPSTREAM: FAIL (queue-occupied)" in out
        assert "#2465" in out

    def test_clear_queue_dry_run_never_posts(self, capsys):
        """Без --send POST не выполняется даже на зелёной карте и чистой очереди."""
        code = upstream_send.run_send(
            "microsoft/markitdown",
            "escape pipes table",
            head="rtynbirf:fix/x",
            title="fix",
            send=False,
            search_fn=lambda q: [],
            create_fn=_boom_post,
        )
        out = capsys.readouterr().out
        assert code == 0
        assert "UPSTREAM: queue-clear" in out
        assert "готов к POST" in out

    def test_send_requires_head_and_title(self, capsys):
        """--send без --head/--title — отказ missing, POST не вызывается."""
        code = upstream_send.run_send(
            "microsoft/markitdown",
            "escape pipes table",
            head="",
            title="",
            send=True,
            search_fn=lambda q: [],
            create_fn=_boom_post,
        )
        out = capsys.readouterr().out
        assert code == 1
        assert "UPSTREAM: FAIL (missing)" in out
        assert "--head" in out and "--title" in out

    def test_send_posts_on_green_path(self, capsys):
        """Зелёный путь: карта → очередь → POST → URL в выводе."""
        calls = []

        def fake_create(base_repo, payload):
            calls.append((base_repo, payload))
            return {"html_url": "https://github.com/org/repo/pull/42"}

        code = upstream_send.run_send(
            "microsoft/markitdown",
            "escape pipes table",
            head="rtynbirf:fix/x",
            title="fix: escape pipes",
            send=True,
            search_fn=lambda q: [],
            create_fn=fake_create,
        )
        out = capsys.readouterr().out
        assert code == 0
        assert calls == [("microsoft/markitdown", {
            "title": "fix: escape pipes",
            "head": "rtynbirf:fix/x",
            "base": "main",
            "body": "",
        })]
        assert "UPSTREAM: PR https://github.com/org/repo/pull/42" in out


class TestObservable:
    def test_all_verdicts_human_readable(self, capsys, monkeypatch):
        """G3: каждый отказ несёт rule и reason; итог — строкой UPSTREAM:."""
        _with_synthetic_collar_card(monkeypatch)
        upstream_send.run_send("ollama/ollama", "genre", search_fn=_boom, create_fn=_boom_post)
        out = capsys.readouterr().out
        for line in out.splitlines():
            assert line.startswith(("OK ", "UPSTREAM:"))
        assert "collar" in out
