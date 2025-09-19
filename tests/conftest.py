"""Shared test fixtures for printing-related tests."""

from __future__ import annotations

import typing as _t

import pytest


class _LogoResourcePatcher:
    """Patch ``printing`` helpers while allowing tests to tweak behavior."""

    def __init__(self, printing_module):
        self._printing = printing_module
        self._original_logo = printing_module.melhorar_logo
        self._original_recurso = printing_module.recurso_caminho
        self._logo_callable = self._as_logo_callable((b"A", 1, 1))
        self._recurso_callable = self._as_recurso_callable("fake")

        def fake_logo(path, largura_desejada=240):
            return self._logo_callable(path, largura_desejada)

        def fake_recurso(path):
            return self._recurso_callable(path)

        self._printing.melhorar_logo = fake_logo
        self._printing.recurso_caminho = fake_recurso

    @staticmethod
    def _as_logo_callable(value: _t.Union[_t.Callable, _t.Tuple[bytes, int, int]]):
        if callable(value):
            return value

        bitmap, largura, altura = value

        def _logo(_path, _largura_desejada=240):
            return bitmap, largura, altura

        return _logo

    @staticmethod
    def _as_recurso_callable(value: _t.Union[_t.Callable, _t.Any]):
        if callable(value):
            return value

        def _recurso(_path):
            return value

        return _recurso

    def set_logo(self, value: _t.Union[_t.Callable, _t.Tuple[bytes, int, int]]):
        self._logo_callable = self._as_logo_callable(value)

    def set_recurso(self, value: _t.Union[_t.Callable, _t.Any]):
        self._recurso_callable = self._as_recurso_callable(value)

    def __call__(self, *, logo=None, recurso=None):
        if logo is not None:
            self.set_logo(logo)
        if recurso is not None:
            self.set_recurso(recurso)

    def restore(self):
        self._printing.melhorar_logo = self._original_logo
        self._printing.recurso_caminho = self._original_recurso


@pytest.fixture
def fake_logo_recurso():
    import printing

    patcher = _LogoResourcePatcher(printing)
    try:
        yield patcher
    finally:
        patcher.restore()
