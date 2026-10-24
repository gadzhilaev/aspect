"""Unconfirmed twin names must not become a confirmed supply-chain reason."""

from __future__ import annotations

from app.services.graph_names import is_unconfirmed_node_name, path_has_unconfirmed_nodes


def test_unconfirmed_markers():
    assert is_unconfirmed_node_name("не знаю")
    assert is_unconfirmed_node_name(" Не знаю ")
    assert is_unconfirmed_node_name("unknown")
    assert is_unconfirmed_node_name("n/a")
    assert is_unconfirmed_node_name("")
    assert not is_unconfirmed_node_name("Электронные модули")
    assert not is_unconfirmed_node_name("большая")  # real nickname allowed; not a marker
    assert not is_unconfirmed_node_name("Линия №2")


def test_path_filter():
    assert path_has_unconfirmed_nodes(
        [{"name": "Поставщик"}, {"name": "не знаю"}, {"name": "Линия"}]
    )
    assert not path_has_unconfirmed_nodes(
        [{"name": "Поставщик"}, {"name": "Модуль"}, {"name": "Линия"}]
    )
