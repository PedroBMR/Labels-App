import pytest

pytest.importorskip("PIL")

from PIL import Image

try:
    Image.new("1", (1, 1))
except Exception:
    pytest.skip("Pillow não está disponível", allow_module_level=True)

from model.template import TemplateDocument, TemplateVariable
from printing import Template, export_labels


def _sample_template() -> Template:
    document = TemplateDocument(
        name="sample",
        page={"backend": "tspl", "width_mm": 40, "height_mm": 30, "dpi": 203},
        elements=[
            {
                "type": "text",
                "x_mm": 5,
                "y_mm": 5,
                "content": "{nome}",
                "font": {"size": 18},
            },
            {
                "type": "text",
                "x_mm": 5,
                "y_mm": 15,
                "content": "{numero}/{total}",
                "font": {"size": 14},
            },
        ],
        variables={
            "items": TemplateVariable(name="items", scope="template", required=True),
            "nome": TemplateVariable(name="nome", default="Exemplo"),
            "numero": TemplateVariable(name="numero", default=1),
            "total": TemplateVariable(name="total", default=1),
        },
    )
    return Template(document)


def test_export_png_single(tmp_path):
    template = _sample_template()
    destino = tmp_path / "etiqueta"
    caminhos, total = export_labels(
        template,
        {"nome": "Unitário", "volumes": 3},
        destino,
        "png",
    )
    assert total == 3
    assert len(caminhos) == 1
    assert caminhos[0].exists()
    assert caminhos[0].suffix == ".png"


def test_export_png_batch(tmp_path):
    template = _sample_template()
    destino = tmp_path / "etiqueta.png"
    caminhos, total = export_labels(
        template,
        {"nome": "Lote", "volumes": 2},
        destino,
        "png",
        batch=True,
    )
    assert total == 2
    assert len(caminhos) == 2
    nomes = sorted(path.name for path in caminhos)
    assert nomes == ["etiqueta-001.png", "etiqueta-002.png"]
    assert all(path.exists() for path in caminhos)


def test_export_pdf_batch(tmp_path):
    template = _sample_template()
    destino = tmp_path / "etiqueta.pdf"
    caminhos, total = export_labels(
        template,
        {"nome": "PDF", "volumes": 4},
        destino,
        "pdf",
        batch=True,
    )
    assert total == 4
    assert len(caminhos) == 1
    caminho = caminhos[0]
    assert caminho.exists()
    assert caminho.suffix == ".pdf"
    assert caminho.stat().st_size > 0


def test_export_svg_batch(tmp_path):
    template = _sample_template()
    destino = tmp_path / "etiqueta.svg"
    caminhos, total = export_labels(
        template,
        {"nome": "SVG", "volumes": 2},
        destino,
        "svg",
        batch=True,
    )
    assert total == 2
    assert len(caminhos) == 2
    for caminho in caminhos:
        assert caminho.exists()
        conteudo = caminho.read_text(encoding="utf-8")
        assert "<svg" in conteudo
        assert "data:image/png;base64" in conteudo
