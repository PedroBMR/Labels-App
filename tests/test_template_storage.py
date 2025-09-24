from __future__ import annotations

import os
from pathlib import Path

import pytest

import persistence
from compile import CompilationError
from model.template import TemplateDocument, TemplateVariable
from printing import Template, compile_template


def _patch_assets(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        persistence,
        "recurso_caminho",
        lambda rel: os.path.join(tmp_path, rel),
    )


def test_template_round_trip(monkeypatch, tmp_path):
    _patch_assets(monkeypatch, tmp_path)
    documento = TemplateDocument(
        name="Modelo Teste",
        page={"backend": "tspl", "width_mm": 70, "height_mm": 30, "gap_mm": 2},
        elements=[{"type": "text", "x_mm": 5, "y_mm": 5, "content": "{codigo}"}],
        variables={
            "items": TemplateVariable(name="items", scope="template", required=True),
            "codigo": TemplateVariable(name="codigo", default="000"),
        },
    )

    caminho = persistence.salvar_template_documento(documento)
    assert Path(caminho).exists()
    nome_arquivo = Path(caminho).name

    carregado = persistence.carregar_template_documento(nome_arquivo)
    assert carregado.to_dict() == documento.to_dict()

    carregado.page["width_mm"] = 80
    persistence.salvar_template_documento(carregado, nome_arquivo=nome_arquivo)
    reaberto = persistence.carregar_template_documento(nome_arquivo)
    assert reaberto.page["width_mm"] == 80

    export_dir = tmp_path / "export"
    exportado = persistence.exportar_template_documento(reaberto, str(export_dir))
    assert Path(exportado).exists()

    importado = persistence.importar_template_documento(exportado)
    assert importado.name == reaberto.name

    arquivos = persistence.listar_arquivos_template()
    assert nome_arquivo in arquivos


def test_compile_template_missing_required_variables():
    documento = TemplateDocument(
        name="Validacao",
        page={"backend": "tspl", "width_mm": 60, "height_mm": 40, "gap_mm": 2},
        elements=[],
        variables={
            "items": TemplateVariable(name="items", scope="template", required=True),
            "codigo": TemplateVariable(name="codigo", required=True),
        },
    )
    template = Template(documento)

    with pytest.raises(CompilationError):
        compile_template(template, {})

    with pytest.raises(CompilationError):
        compile_template(template, {"items": [{}]})
