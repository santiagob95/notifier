import json
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest

from imax_notifier.config import Config, load_config
from imax_notifier.errors import MonitorError, RejectedMessage, UncertainMessage
from imax_notifier.runner import message_batches, resolve_pending, run_monitor
from imax_notifier.showcase import Performance, Showcase, discover, matches_title, parse_tree
from imax_notifier.state import LocalStore, empty_state

ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT / "config.toml")
NOW = datetime(2026, 10, 26, 22, 0, tzinfo=timezone.utc)


def reference(filename="funciones-imax-6234.json"):
    return json.loads((ROOT / "docs/evidencia" / filename).read_text(encoding="utf-8-sig"))


def target_tree():
    # Caso sintético: estructura de una respuesta real; ID/título de Dune inventados SOLO para tests.
    tree = reference()
    tree["id"], tree["name"] = 9000, "Dune: Part Three"
    return tree


def performances():
    return parse_tree(target_tree(), 9000, CONFIG, NOW.date())


@pytest.mark.parametrize("title", ["DUNE: PART THREE", "Duna: Parte Tres", "Dune: Part III (IMAX)", "Dune 3 - IMAX Subtitulado", "Duna: Parte 3"])
def test_target_aliases(title):
    assert matches_title(title, CONFIG.aliases)


@pytest.mark.parametrize("title", ["Dune", "Dune: Part Two", "Dune: Parte II", "Dune 30", "Dune 3 trailer", "Making of Dune Part Three", "Dune Part Three reestreno"])
def test_do_not_confuse_other_films(title):
    assert not matches_title(title, CONFIG.aliases)


def test_discovery_both_html_layouts_and_distinct_ids():
    html = '''<div class="boxfilm"><h2><a href="https://entradas.todoshowcase.com/showcase/pelicula?filmid=9000&amp;house_id=3250">Duna: Parte Tres</a></h2></div>
    <div class="category-thumb"><a href="pelicula.aspx?filmid=9001"><ul><li>R-13</li></ul><h3 class="name">DUNE: PART THREE</h3></a></div>
    <a href="pelicula.aspx?filmid=9001">Dune: Part Three</a>
    <a href="https://example.com/showcase/pelicula?filmid=9002">Dune 3</a>
    <a href="pelicula.aspx?filmid=9003">Dune: Part Two</a>'''
    assert discover(html, CONFIG) == {9000, 9001}


def test_valid_catalog_without_target_is_not_error():
    assert discover('<a href="pelicula.aspx?filmid=1">Godzilla Minus Zero</a>', CONFIG) == set()


@pytest.mark.parametrize("html", ["<h1>Access denied</h1>", "", '<a href="pelicula.aspx?filmid=abc">Dune 3</a>'])
def test_unknown_catalog_is_error(html):
    with pytest.raises(MonitorError):
        discover(html, CONFIG)


def test_real_positive_fixture_preserves_ids():
    data = reference()
    result = parse_tree(data, 6234, Config(("Godzilla Minus Zero",)), date(2026, 10, 26))
    assert [p.performance_id for p in result] == [572772, 572773, 572794]
    assert all(p.cinema_id == 18 and p.url.endswith("house_id=3250") for p in result)


def test_real_empty_days_no_alert():
    data = reference("sin-funciones-imax-6016.json")
    assert parse_tree(data, 6016, Config((data["name"],)), NOW.date()) == []


def test_other_cinema_not_imax_even_same_ewave():
    data = reference("funciones-norcenter-6234.json")
    assert parse_tree(data, 6234, Config((data["name"],)), NOW.date()) == []


def test_film_record_alone_has_no_performances():
    assert parse_tree({"id": 9000, "name": "Dune 3", "days": {}}, 9000, CONFIG, NOW.date()) == []


def test_2d_format_is_ignored():
    data = target_tree()
    data["days"]["2026-11-03"][0]["formats"][0]["formatDescription"] = "2D-Subtitulado"
    assert parse_tree(data, 9000, CONFIG, NOW.date()) == []


@pytest.mark.parametrize("change", ["wrong_id", "wrong_title", "missing_days", "invalid_time", "missing_performance_id", "wrong_cinema_name", "conflicting_id"])
def test_invalid_or_inconsistent_api_fails_closed(change):
    data = target_tree()
    cinema = data["days"]["2026-11-03"][0]
    perfs = cinema["formats"][0]["performances"]
    if change == "wrong_id": data["id"] = 6234
    elif change == "wrong_title": data["name"] = "Dune Part Two"
    elif change == "missing_days": del data["days"]
    elif change == "invalid_time": perfs[0]["showTime"] = "35:12"
    elif change == "missing_performance_id": del perfs[0]["performanceId"]
    elif change == "wrong_cinema_name": cinema["name"] = "Showcase Norcenter"
    elif change == "conflicting_id": perfs[1]["performanceId"] = perfs[0]["performanceId"]
    with pytest.raises(MonitorError):
        parse_tree(data, 9000, CONFIG, NOW.date())


def test_old_dates_ignored_and_night_marker_preserved():
    data = target_tree()
    data["days"]["2026-11-03"][0]["formats"][0]["performances"][0]["showTime"] = "N 01:00"
    assert any(p.show_time == "N 01:00" for p in parse_tree(data, 9000, CONFIG, date(2026, 11, 3)))
    assert parse_tree(data, 9000, CONFIG, date(2026, 11, 4)) == []


def setup_run(tmp_path, perfs=None):
    store = LocalStore(tmp_path / "state.json")
    showcase = Mock()
    showcase.discover.return_value = {9000}
    showcase.performances.return_value = performances() if perfs is None else perfs
    telegram = Mock()
    return store, showcase, telegram


def test_repeated_run_sends_only_new_functions(tmp_path):
    store, showcase, telegram = setup_run(tmp_path)
    assert run_monitor(showcase, store, telegram, now=NOW) == 3
    assert run_monitor(showcase, store, telegram, now=NOW) == 0
    assert telegram.send.call_count == 1
    new = Performance(9000, 18, 123456, "2026-11-04", "19:00", "IMAX-Subtitulado", "x")
    showcase.performances.return_value = performances() + [new]
    assert run_monitor(showcase, store, telegram, now=NOW) == 1
    assert "2026-11-04" in telegram.send.call_args.args[0]
    assert "2026-11-03" not in telegram.send.call_args.args[0]
    assert len(store.load()["sent"]) == 4


def test_no_functions_sends_nothing(tmp_path):
    store, showcase, telegram = setup_run(tmp_path, [])
    assert run_monitor(showcase, store, telegram, now=NOW) == 0
    telegram.send.assert_not_called()


def test_dry_run_never_writes_or_sends(tmp_path):
    store, showcase, telegram = setup_run(tmp_path)
    assert run_monitor(showcase, store, telegram, now=NOW, dry_run=True) == 3
    assert not store.path.exists()
    telegram.send.assert_not_called()


def test_state_is_reserved_before_network_send(tmp_path):
    store, showcase, telegram = setup_run(tmp_path)
    telegram.send.side_effect = lambda _: pytest.fail("state must fail first")
    store.save = Mock(side_effect=MonitorError("storage unavailable"))
    with pytest.raises(MonitorError): run_monitor(showcase, store, telegram, now=NOW)
    telegram.send.assert_not_called()


def test_ambiguous_send_blocks_repetition_and_can_be_resolved(tmp_path):
    store, showcase, telegram = setup_run(tmp_path)
    telegram.send.side_effect = UncertainMessage("timeout")
    with pytest.raises(UncertainMessage): run_monitor(showcase, store, telegram, now=NOW)
    assert store.load()["pending"] is not None
    telegram.send.reset_mock()
    with pytest.raises(MonitorError, match="pendiente"): run_monitor(showcase, store, telegram, now=NOW)
    telegram.send.assert_not_called()
    resolve_pending(store, store.load(), "sent")
    assert run_monitor(showcase, store, telegram, now=NOW) == 0


def test_rejected_send_is_retryable(tmp_path):
    store, showcase, telegram = setup_run(tmp_path)
    telegram.send.side_effect = RejectedMessage("403")
    with pytest.raises(RejectedMessage): run_monitor(showcase, store, telegram, now=NOW)
    assert store.load()["pending"] is None
    assert not store.load()["sent"]
    telegram.send.side_effect = None
    assert run_monitor(showcase, store, telegram, now=NOW) == 3


def test_state_write_failure_after_send_retains_reservation(tmp_path):
    store, showcase, telegram = setup_run(tmp_path)
    save = store.save
    def fail_after_send(state):
        if state["sent"]: raise MonitorError("commit failed")
        save(state)
    store.save = fail_after_send
    with pytest.raises(MonitorError): run_monitor(showcase, store, telegram, now=NOW)
    assert store.load()["pending"] is not None
    assert not store.load()["sent"]
    assert telegram.send.call_count == 1


def test_explicit_retry_resolution_does_not_send(tmp_path):
    store, showcase, telegram = setup_run(tmp_path)
    telegram.send.side_effect = UncertainMessage("timeout")
    with pytest.raises(UncertainMessage): run_monitor(showcase, store, telegram, now=NOW)
    resolve_pending(store, store.load(), "retry")
    assert store.load()["pending"] is None
    assert not store.load()["sent"]
    assert telegram.send.call_count == 1


def test_catalog_failure_does_not_hide_known_functions(tmp_path):
    store, showcase, telegram = setup_run(tmp_path)
    state = empty_state()
    state["film_ids"] = [9000]
    store.save(state)
    showcase.discover.side_effect = MonitorError("catalog error")
    with pytest.raises(MonitorError): run_monitor(showcase, store, telegram, now=NOW)
    assert telegram.send.call_count == 1
    assert len(store.load()["sent"]) == 3


def test_schema_error_does_not_notify_or_reset_state(tmp_path):
    store, showcase, telegram = setup_run(tmp_path)
    showcase.performances.side_effect = MonitorError("bad schema")
    with pytest.raises(MonitorError): run_monitor(showcase, store, telegram, now=NOW)
    telegram.send.assert_not_called()
    assert not store.path.exists()


def test_corrupt_local_state_fails_closed(tmp_path):
    store = LocalStore(tmp_path / "state.json")
    store.path.write_text("{broken", encoding="utf-8")
    with pytest.raises(MonitorError): store.load()


def test_message_batches_fit_telegram_limit():
    sample = performances()[0]
    samples = [Performance(sample.film_id, 18, i, sample.day, sample.show_time, "x" * 500, sample.show_id) for i in range(1, 101)]
    batches = list(message_batches(samples))
    assert sum(len(chunk) for chunk, _ in batches) == 100
    assert all(len(text) < 4096 for _, text in batches)


def test_argentina_day_used_near_utc_midnight(tmp_path):
    store, showcase, telegram = setup_run(tmp_path, [])
    run_monitor(showcase, store, telegram, now=datetime(2026, 10, 27, 1, 0, tzinfo=timezone.utc), dry_run=True)
    showcase.performances.assert_called_once_with(9000, date(2026, 10, 26))



def test_disappearing_and_reappearing_functions_are_not_repeated(tmp_path):
    store, showcase, telegram = setup_run(tmp_path)
    run_monitor(showcase, store, telegram, now=NOW)
    showcase.performances.return_value = []
    run_monitor(showcase, store, telegram, now=NOW)
    showcase.performances.return_value = performances()
    assert run_monitor(showcase, store, telegram, now=NOW) == 0
    assert telegram.send.call_count == 1


def test_duplicate_performance_entries_are_collapsed():
    data = target_tree()
    perfs = data["days"]["2026-11-03"][0]["formats"][0]["performances"]
    perfs.append(dict(perfs[0]))
    assert len(parse_tree(data, 9000, CONFIG, NOW.date())) == 3
