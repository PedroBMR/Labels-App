import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))


class FakeWin32:
    def __init__(self):
        self.written: list[bytes] = []

    def GetDefaultPrinter(self):
        return "dummy"

    def OpenPrinter(self, name):
        return object()

    def StartDocPrinter(self, h, level, info):
        pass

    def StartPagePrinter(self, h):
        pass

    def WritePrinter(self, h, data):
        self.written.append(data)

    def EndPagePrinter(self, h):
        pass

    def EndDocPrinter(self, h):
        pass

    def ClosePrinter(self, h):
        pass


fake_win32 = FakeWin32()
sys.modules["win32print"] = fake_win32  # type: ignore[assignment]


def test_descobrir_impressora_padrao():
    import printing

    assert printing.descobrir_impressora_padrao() == "dummy"


def test_reimpressao_faltantes(monkeypatch):
    import printing

    fake = printing.win32print
    monkeypatch.setattr(
        printing,
        "melhorar_logo",
        lambda p, largura_desejada=240: (b"ABC", 1, 1),
    )
    monkeypatch.setattr(printing, "recurso_caminho", lambda p: "fake")

    total = 10
    faltantes = 3
    inicio = total - faltantes + 1

    printing.imprimir_etiqueta(
        "S1",
        "Cat",
        "Emissor",
        "Mun",
        faltantes,
        "2024-01-01",
        0,
        0,
        inicio_indice=inicio,
        total_exibicao=total,
    )

    assert len(fake.written) == faltantes
    textos = [data.decode("latin1") for data in fake.written]
    assert any("8 DE 10" in t for t in textos)
    assert any("9 DE 10" in t for t in textos)
    assert any("10 DE 10" in t for t in textos)


def test_reimpressao_intervalo(monkeypatch):
    import printing

    fake_win32.written.clear()
    monkeypatch.setattr(
        printing,
        "melhorar_logo",
        lambda p, largura_desejada=240: (b"ABC", 1, 1),
    )
    monkeypatch.setattr(printing, "recurso_caminho", lambda p: "fake")

    total = 10
    inicio, fim = 5, 8
    volumes = fim - inicio + 1

    printing.imprimir_etiqueta(
        "S1",
        "Cat",
        "Emissor",
        "Mun",
        volumes,
        "2024-01-01",
        0,
        0,
        inicio_indice=inicio,
        total_exibicao=total,
    )

    assert len(fake_win32.written) == volumes
    textos = [data.decode("latin1") for data in fake_win32.written]
    assert any("5 DE 10" in t for t in textos)
    assert any("8 DE 10" in t for t in textos)
    assert all("4 DE 10" not in t for t in textos)
    assert all("9 DE 10" not in t for t in textos)


def test_imprimir_pagina_teste(monkeypatch):
    import printing

    fake_win32.written.clear()
    monkeypatch.setattr(
        printing, "melhorar_logo", lambda p, largura_desejada=240: (b"A", 1, 1)
    )
    monkeypatch.setattr(printing, "recurso_caminho", lambda p: "fake")

    ok, erro = printing.imprimir_pagina_teste()

    assert ok
    assert erro is None
    assert len(fake_win32.written) == 1
    texto = fake_win32.written[0].decode("latin1")
    assert "1 DE 1" in texto
    assert "BAR 30,600,400,4" in texto


def test_templates_alteram_layout(monkeypatch):
    import printing

    fake_win32.written.clear()
    monkeypatch.setattr(
        printing, "melhorar_logo", lambda p, largura_desejada=240: (b"A", 1, 1)
    )
    monkeypatch.setattr(printing, "recurso_caminho", lambda p: "fake")

    printing.aplicar_template("Compacto")
    printing.imprimir_etiqueta("S", "C", "E", "M", 1, "2024-01-01")
    texto = fake_win32.written[-1].decode("latin1")
    assert "SIZE 50 mm,60 mm" in texto
    printing.aplicar_template("Padrão")


def test_panoramico_layout(monkeypatch):
    import printing

    fake_win32.written.clear()
    monkeypatch.setattr(
        printing, "melhorar_logo", lambda p, largura_desejada=240: (b"A", 1, 1)
    )
    monkeypatch.setattr(printing, "recurso_caminho", lambda p: "fake")

    printing.aplicar_template("Panoramico")
    printing.imprimir_etiqueta("S", "C", "E", "M", 1, "2024-01-01")
    texto = fake_win32.written[-1].decode("latin1")
    assert "SIZE 100 mm,30 mm" in texto
    spec = printing.LAYOUTS["Panoramico"]["numeracao"]
    assert f'TEXT {spec["x"]},{spec["y"]}' in texto
    printing.aplicar_template("Padrão")


def test_retry_exponencial_logging(monkeypatch, caplog):
    import printing
    import logging

    class FailingWin32:
        def __init__(self):
            self.calls = 0

        def GetDefaultPrinter(self):
            return "dummy"

        def OpenPrinter(self, name):
            return object()

        def StartDocPrinter(self, h, level, info):
            self.calls += 1
            raise RuntimeError("boom")

        def StartPagePrinter(self, h):
            pass

        def WritePrinter(self, h, data):
            pass

        def EndPagePrinter(self, h):
            pass

        def EndDocPrinter(self, h):
            pass

        def ClosePrinter(self, h):
            pass

    fake = FailingWin32()
    monkeypatch.setattr(printing, "win32print", fake)
    monkeypatch.setattr(
        printing, "melhorar_logo", lambda p, largura_desejada=240: (b"A", 1, 1)
    )
    monkeypatch.setattr(printing, "recurso_caminho", lambda p: "fake")
    monkeypatch.setattr(printing.time, "sleep", lambda s: None)

    with caplog.at_level(logging.INFO):
        ok, erro = printing.imprimir_etiqueta(
            "S", "C", "E", "M", 1, "2024-01-01", 0, 0, repetir_em_falha=True
        )

    assert not ok
    assert fake.calls == 3
    tentativas = [r for r in caplog.records if "Tentativa" in r.message]
    assert len(tentativas) == 3
