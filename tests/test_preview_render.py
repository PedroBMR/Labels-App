from hashlib import sha256

from model.template import TemplateDocument, TemplateVariable
from render.preview import render_template
from printing import compile_template


def _sample_template() -> TemplateDocument:
    return TemplateDocument(
        name="sample",
        page={"backend": "tspl", "width_mm": 40, "height_mm": 30, "dpi": 203},
        elements=[
            {
                "type": "text",
                "x_mm": 5,
                "y_mm": 5,
                "width_mm": 30,
                "height_mm": 10,
                "content": "Olá {nome}",
                "font": {"size": 24},
            }
        ],
        variables={
            "items": TemplateVariable(name="items", scope="template", required=True),
            "nome": TemplateVariable(name="nome", default="Mundo"),
        },
    )


def test_preview_renders_text(tmp_path):
    document = _sample_template()
    image = render_template(document.to_dict(), {"nome": "Preview"})
    assert image.mode == "L"
    assert image.size[0] > 100 and image.size[1] > 50
    path = tmp_path / "preview.png"
    image.save(path, format="PNG")
    digest = sha256(path.read_bytes()).hexdigest()
    assert digest == "cd907fa7353b185f2ec329655ea58c626d00c66ab32d9dd177dd4275772e9f0e"


def test_compile_tspl_snapshot():
    document = _sample_template()
    backend, commands = compile_template(document, {"items": [{"nome": "Teste"}]}, backend_name="tspl")
    assert backend == "tspl"
    lines = [line.strip() for line in commands.strip().splitlines() if line.strip()]
    assert lines[0].startswith("SIZE")
    assert any("Olá Teste" in line for line in lines)


def test_render_qrcode_without_dependency(monkeypatch):
    from render import preview

    document = TemplateDocument(
        name="qr-missing",
        page={"backend": "tspl", "width_mm": 40, "height_mm": 30, "dpi": 203},
        elements=[
            {
                "type": "qrcode",
                "x_mm": 2,
                "y_mm": 2,
                "width_mm": 20,
                "height_mm": 20,
                "value": "{codigo}",
            }
        ],
        variables={
            "codigo": TemplateVariable(name="codigo", required=True),
        },
    )

    monkeypatch.setattr(preview, "qrcode", None)

    image = preview.render_template(document.to_dict(), {"codigo": "123456"})
    assert image.mode == "L"
