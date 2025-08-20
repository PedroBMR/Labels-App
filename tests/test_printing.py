"""Testes para rotinas de impressão.

Responsabilidade:
    Assegurar que comandos TSPL e envio à impressora funcionem.

Dependências:
    - printing

Exemplo:
    $ pytest tests/test_printing.py
"""

import logging
import os
import sys

import layout_builder as lb

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

    printing.win32print.written.clear()
    monkeypatch.setattr(lb, "melhorar_logo",
        lambda p, largura_desejada=240: (b"ABC", 1, 1),
    )
    monkeypatch.setattr(lb, "recurso_caminho", lambda p: "fake")

    total = 10
    faltantes = 3
    inicio = total - faltantes + 1

    dados = {
        "saida": "S1",
        "categoria": "Cat",
        "emissor": "Emissor",
        "municipio": "Mun",
        "volumes": faltantes,
        "data_hora": "2024-01-01",
        "inicio_indice": inicio,
        "total_exibicao": total,
    }
    tspl = lb.montar_tspl(lb.LAYOUT_ATUAL, dados)
    printing.imprimir_etiqueta(tspl)

    assert len(printing.win32print.written) == 1
    texto = printing.win32print.written[0].decode("latin1")
    assert "8 DE 10" in texto
    assert "9 DE 10" in texto
    assert "10 DE 10" in texto


def test_reimpressao_intervalo(monkeypatch):
    import printing

    fake_win32.written.clear()
    monkeypatch.setattr(lb, "melhorar_logo",
        lambda p, largura_desejada=240: (b"ABC", 1, 1),
    )
    monkeypatch.setattr(lb, "recurso_caminho", lambda p: "fake")

    total = 10
    inicio, fim = 5, 8
    volumes = fim - inicio + 1

    dados = {
        "saida": "S1",
        "categoria": "Cat",
        "emissor": "Emissor",
        "municipio": "Mun",
        "volumes": volumes,
        "data_hora": "2024-01-01",
        "inicio_indice": inicio,
        "total_exibicao": total,
    }
    tspl = lb.montar_tspl(lb.LAYOUT_ATUAL, dados)
    printing.imprimir_etiqueta(tspl)

    assert len(fake_win32.written) == 1
    texto = fake_win32.written[0].decode("latin1")
    assert "5 DE 10" in texto
    assert "8 DE 10" in texto
    assert "4 DE 10" not in texto
    assert "9 DE 10" not in texto


def test_imprimir_pagina_teste(monkeypatch):
    import printing

    fake_win32.written.clear()
    monkeypatch.setattr(lb, "melhorar_logo", lambda p, largura_desejada=240: (b"A", 1, 1)
    )
    monkeypatch.setattr(lb, "recurso_caminho", lambda p: "fake")

    ok, erro = printing.imprimir_pagina_teste()

    assert ok
    assert erro is None
    assert len(fake_win32.written) == 1
    texto = fake_win32.written[0].decode("latin1")
    assert f"DIRECTION {lb.DIRECTION}" in texto
    assert "1 DE 1" in texto
    dots_y = lb.ALTURA_ETIQUETA_MM * lb.DOTS_MM
    ruler_start = lb.LAYOUT_ATUAL["titulo"]["x"]
    ruler_len = min(
        50 * lb.DOTS_MM,
        lb.LARGURA_ETIQUETA_MM * lb.DOTS_MM - ruler_start,
    )
    ruler_len -= ruler_len % (10 * lb.DOTS_MM)
    expected = f"BAR {ruler_start},{dots_y - 40},{ruler_len},4"
    assert expected in texto


def test_direction_personalizado(monkeypatch):
    import printing

    original_templates = lb.TEMPLATES
    fake_win32.written.clear()
    monkeypatch.setattr(lb, "melhorar_logo", lambda p, largura_desejada=240: (b"A", 1, 1)
    )
    monkeypatch.setattr(lb, "recurso_caminho", lambda p: "fake")

    monkeypatch.setattr(
        lb,
        "TEMPLATES",
        {
            "60x80": {
                "largura_mm": 60,
                "altura_mm": 80,
                "gap_mm": 2,
                "direction": 0,
            },
            "100x30": {
                "largura_mm": 100,
                "altura_mm": 30,
                "gap_mm": 2,
                "direction": 1,
            },
        },
    )

    lb.aplicar_template("60x80")

    dados = {
        "saida": "S",
        "categoria": "C",
        "emissor": "E",
        "municipio": "M",
        "volumes": 1,
        "data_hora": "2024-01-01",
    }

    tspl = lb.montar_tspl(lb.LAYOUT_ATUAL, dados)
    assert "DIRECTION 0" in tspl

    ok, erro = printing.imprimir_pagina_teste()
    assert ok
    assert erro is None
    assert len(fake_win32.written) == 1
    texto = fake_win32.written[0].decode("latin1")
    assert "DIRECTION 0" in texto

    lb.TEMPLATES = original_templates
    lb.aplicar_template("Padrão")


def test_templates_arquivo_inexistente(monkeypatch, tmp_path, caplog):
    import printing

    monkeypatch.setattr(lb, "TEMPLATES", None)
    monkeypatch.setattr(
        lb, "recurso_caminho", lambda p: tmp_path / "inexistente.json"
    )

    with caplog.at_level(logging.ERROR):
        templates = lb.listar_templates()

    assert templates == ["60x80"]
    assert "templates.json" in caplog.text


def test_templates_chave_invalida(monkeypatch):
    import printing

    fake_win32.written.clear()
    monkeypatch.setattr(lb, "TEMPLATES", None)
    lb.aplicar_template("inexistente")
    monkeypatch.setattr(lb, "melhorar_logo", lambda p, largura_desejada=240: (b"A", 1, 1)
    )
    monkeypatch.setattr(lb, "recurso_caminho", lambda p: "fake")

    dados = {
        "saida": "S",
        "categoria": "C",
        "emissor": "E",
        "municipio": "M",
        "volumes": 1,
        "data_hora": "2024-01-01",
    }
    tspl = lb.montar_tspl(lb.LAYOUT_ATUAL, dados)
    printing.imprimir_etiqueta(tspl)
    texto = fake_win32.written[-1].decode("latin1")
    assert "SIZE 60 mm,80 mm" in texto


def test_templates_alteram_layout(monkeypatch):
    import printing

    fake_win32.written.clear()
    monkeypatch.setattr(lb, "melhorar_logo", lambda p, largura_desejada=240: (b"A", 1, 1)
    )
    lb.aplicar_template("100x30")
    monkeypatch.setattr(lb, "recurso_caminho", lambda p: "fake")
    dados = {
        "saida": "S",
        "categoria": "C",
        "emissor": "E",
        "municipio": "M",
        "volumes": 1,
        "data_hora": "2024-01-01",
    }
    tspl = lb.montar_tspl(lb.LAYOUT_ATUAL, dados)
    printing.imprimir_etiqueta(tspl)
    texto = fake_win32.written[-1].decode("latin1")
    assert "SIZE 100 mm,30 mm" in texto
    lb.aplicar_template("Padrão")


def test_100x30_layout(monkeypatch):
    import printing

    fake_win32.written.clear()
    monkeypatch.setattr(lb, "melhorar_logo", lambda p, largura_desejada=240: (b"A", 1, 1)
    )
    monkeypatch.setattr(lb, "recurso_caminho", lambda p: "fake")

    lb.TEMPLATES = {
        "60x80": {"largura_mm": 60, "altura_mm": 80, "gap_mm": 2, "direction": 1},
        "100x30": {"largura_mm": 100, "altura_mm": 30, "gap_mm": 2, "direction": 1},
    }
    lb.aplicar_template("100x30")
    dados = {
        "saida": "S",
        "categoria": "C",
        "emissor": "E",
        "municipio": "M",
        "volumes": 1,
        "data_hora": "2024-01-01",
    }
    tspl = lb.montar_tspl(lb.LAYOUT_ATUAL, dados)
    printing.imprimir_etiqueta(tspl)
    texto = fake_win32.written[-1].decode("latin1")
    assert "SIZE 100 mm,30 mm" in texto
    spec = lb.LAYOUTS["100x30"]["numeracao"]
    assert f'TEXT {spec["x"]},{spec["y"]}' in texto
    lb.aplicar_template("Padrão")


def test_100x30_coordenadas(monkeypatch):
    import re

    import printing

    fake_win32.written.clear()
    monkeypatch.setattr(lb, "melhorar_logo", lambda p, largura_desejada=240: (b"A", 1, 1)
    )
    monkeypatch.setattr(lb, "recurso_caminho", lambda p: "fake")

    lb.aplicar_template("100x30")
    dados = {
        "saida": "S",
        "categoria": "C",
        "emissor": "E",
        "municipio": "M",
        "volumes": 1,
        "data_hora": "2024-01-01",
    }
    tspl = lb.montar_tspl(lb.LAYOUT_ATUAL, dados)
    printing.imprimir_etiqueta(tspl)
    texto = fake_win32.written[-1].decode("latin1")
    assert "SIZE 100 mm,30 mm" in texto
    max_x = lb.LARGURA_ETIQUETA_MM * lb.DOTS_MM
    max_y = lb.ALTURA_ETIQUETA_MM * lb.DOTS_MM
    for line in texto.splitlines():
        m = re.match(r"TEXT (\d+),(\d+)", line)
        if m:
            x, y = map(int, m.groups())
            assert 0 <= x <= max_x
            assert 0 <= y <= max_y
    lb.aplicar_template("Padrão")


def test_100x30_pagina_teste(monkeypatch):
    import printing

    fake_win32.written.clear()
    monkeypatch.setattr(lb, "melhorar_logo",
        lambda p, largura_desejada=240: (
            b"A",
            max(1, largura_desejada // 8),
            largura_desejada,
        ),
    )
    monkeypatch.setattr(lb, "recurso_caminho", lambda p: "fake")

    lb.aplicar_template("100x30")
    ok, erro = printing.imprimir_pagina_teste()
    assert ok and erro is None
    assert len(fake_win32.written) == 1
    texto = fake_win32.written[-1].decode("latin1")
    assert "SIZE 100 mm,30 mm" in texto
    assert ",15,120,0," in texto
    dots_y = lb.ALTURA_ETIQUETA_MM * lb.DOTS_MM
    ruler_start = lb.LAYOUT_ATUAL["titulo"]["x"]
    ruler_len = min(
        50 * lb.DOTS_MM,
        lb.LARGURA_ETIQUETA_MM * lb.DOTS_MM - ruler_start,
    )
    ruler_len -= ruler_len % (10 * lb.DOTS_MM)
    expected = f"BAR {ruler_start},{dots_y - 40},{ruler_len},4"
    assert expected in texto
    lb.aplicar_template("Padrão")


def test_100x30_fracao_antes_de_fragil():
    import printing

    lb.aplicar_template("100x30")
    fracao_x = lb.LAYOUT_ATUAL["fracao"]["x"]
    fragil_x = lb.LAYOUT_ATUAL["fragil"]["x"]
    assert fracao_x < fragil_x
    lb.aplicar_template("Padrão")


def test_100x30_text_bitmap_dentro_largura(monkeypatch):
    import re

    import printing

    monkeypatch.setattr(lb, "melhorar_logo", lambda p, largura_desejada=240: (b"A", 15, 1)
    )
    monkeypatch.setattr(lb, "recurso_caminho", lambda p: "fake")

    lb.aplicar_template("100x30")
    dados = {
        "saida": "S",
        "categoria": "C",
        "emissor": "E",
        "municipio": "M",
        "volumes": 1,
        "data_hora": "2024-01-01",
    }
    tspl = lb.montar_tspl(lb.LAYOUT_ATUAL, dados)

    max_x = lb.LARGURA_ETIQUETA_MM * lb.DOTS_MM
    for line in tspl.splitlines():
        if line.startswith("TEXT "):
            m = re.match(
                r'TEXT (\d+),(\d+),"(\d+)",0,(\d+),(\d+),"(.*)"', line
            )
            assert m, f"Linha inesperada: {line}"
            x, _, font, xm, _, texto = m.groups()
            x, xm = int(x), int(xm)
            largura = lb._text_width_dots(texto, font, xm)
            assert x + largura <= max_x
        elif line.startswith("BITMAP "):
            m = re.match(r'BITMAP (\d+),(\d+),(\d+),(\d+),0,', line)
            assert m, f"Linha inesperada: {line}"
            x, _, largura_b, _ = map(int, m.groups())
            assert x + largura_b * 8 <= max_x
    lb.aplicar_template("Padrão")


def test_100x30_text_bitmap_dentro_limites(monkeypatch):
    import re

    import printing

    monkeypatch.setattr(lb, "melhorar_logo", lambda p, largura_desejada=240: (b"A", 2, 16)
    )
    monkeypatch.setattr(lb, "recurso_caminho", lambda p: "fake")

    lb.aplicar_template("100x30")
    dados = {
        "saida": "S",
        "categoria": "C",
        "emissor": "E",
        "municipio": "M",
        "volumes": 1,
        "data_hora": "2024-01-01",
    }
    tspl = lb.montar_tspl(lb.LAYOUT_ATUAL, dados)

    max_x = lb.LARGURA_ETIQUETA_MM * lb.DOTS_MM
    max_y = lb.ALTURA_ETIQUETA_MM * lb.DOTS_MM
    for line in tspl.splitlines():
        if line.startswith("TEXT "):
            m = re.match(
                r'TEXT (\d+),(\d+),"(\d+)",0,(\d+),(\d+),"(.*)"', line
            )
            assert m, f"Linha inesperada: {line}"
            x, y, font, xm, ym, texto = m.groups()
            x, y, xm, ym = map(int, (x, y, xm, ym))
            largura = lb._text_width_dots(texto, font, xm)
            altura = lb.FONT_BASE_W.get(font, 12) * max(1, ym)
            assert x + largura <= max_x
            assert y + altura <= max_y
        elif line.startswith("BITMAP "):
            m = re.match(r'BITMAP (\d+),(\d+),(\d+),(\d+),0,', line)
            assert m, f"Linha inesperada: {line}"
            x, y, largura_b, altura = map(int, m.groups())
            assert x + largura_b * 8 <= max_x
            assert y + altura <= max_y
    lb.aplicar_template("Padrão")


def test_total_exibicao_cinco_digitos(monkeypatch):
    import re

    import printing

    monkeypatch.setattr(lb, "melhorar_logo", lambda p, largura_desejada=240: (b"A", 1, 1)
    )
    monkeypatch.setattr(lb, "recurso_caminho", lambda p: "fake")

    lb.aplicar_template("100x30")
    total = 12345
    dados = {
        "saida": "S",
        "categoria": "C",
        "emissor": "E",
        "municipio": "M",
        "volumes": 1,
        "data_hora": "2024-01-01",
        "inicio_indice": total,
        "total_exibicao": total,
    }
    tspl = lb.montar_tspl(lb.LAYOUT_ATUAL, dados)
    m = re.search(r'TEXT (\d+),(\d+),"(\d+)",0,(\d+),(\d+),"12345 DE 12345"', tspl)
    assert m, tspl
    x, _, font, xm, _ = m.groups()
    x = int(x)
    xm = int(xm)
    largura_txt = lb._text_width_dots("12345 DE 12345", font, xm)
    max_x = lb.LARGURA_ETIQUETA_MM * lb.DOTS_MM
    assert x + largura_txt <= max_x
    lb.aplicar_template("Padrão")


def test_retry_exponencial_logging(monkeypatch, caplog):
    import logging

    import printing

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
    monkeypatch.setattr(lb, "melhorar_logo", lambda p, largura_desejada=240: (b"A", 1, 1)
    )
    monkeypatch.setattr(lb, "recurso_caminho", lambda p: "fake")
    monkeypatch.setattr(printing.time, "sleep", lambda s: None)

    dados = {
        "saida": "S",
        "categoria": "C",
        "emissor": "E",
        "municipio": "M",
        "volumes": 1,
        "data_hora": "2024-01-01",
    }
    tspl = lb.montar_tspl(lb.LAYOUT_ATUAL, dados)

    with caplog.at_level(logging.INFO):
        ok, erro = printing.imprimir_etiqueta(tspl, repetir_em_falha=True)

    assert not ok
    assert fake.calls == 3
    tentativas = [r for r in caplog.records if "Tentativa" in r.message]
    assert len(tentativas) == 3
