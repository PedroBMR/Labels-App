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
