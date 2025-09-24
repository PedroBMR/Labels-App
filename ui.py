"""Elementos da interface gráfica do gerador de etiquetas.

Responsabilidade:
    Definir widgets e coordenar a interação do usuário com a impressão.

Dependências:
    - log
    - persistence
    - printing
    - qt_compat
    - utils

Exemplo:
    >>> from qt_compat import QApplication
    >>> from ui import EtiquetaApp
    >>> app = QApplication([])
    >>> janela = EtiquetaApp()
    >>> janela.show()
"""

import os
import subprocess
import sys
import threading
from datetime import datetime
from typing import Any, TypedDict

from _version import __version__
from editor.window import LabelEditorWindow
from log import LOG_FILE, logger, register_status_callback
from persistence import (
    atualizar_recentes,
    carregar_config,
    carregar_contagem,
    carregar_historico_mensal,
    carregar_recentes_listas,
    gerar_relatorio_mensal,
    registrar_contagem_mensal,
    salvar_config,
    salvar_contagem,
    salvar_historico,
)
from printing import (
    Template,
    aplicar_template,
    descobrir_impressora_padrao,
    imprimir_etiqueta,
    imprimir_pagina_teste,
    listar_impressoras,
    listar_templates,
    montar_tspl,
)
from qt_compat import (
    QCheckBox,
    QCloseEvent,
    QColor,
    QComboBox,
    QDateTime,
    QDesktopServices,
    QDialog,
    QDialogButtonBox,
    QFont,
    QFormLayout,
    QFrame,
    QGridLayout,
    QIcon,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QObject,
    QPalette,
    QPixmap,
    QPushButton,
    QRegularExpression,
    QRegularExpressionValidator,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    Qt,
    QThread,
    QTime,
    QTimeEdit,
    QTimer,
    QToolButton,
    QUrl,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
    pyqtSlot,
)
from utils import backup_automatico, normalize_text, recurso_caminho

CATEGORIAS_PADRAO = [
    "LIMPEZA, COPA, COZINHA",
    "DEVOLUCAO",
    "ORTOPEDICO",
    "CRE CHOPIM",
    "EXPEDIENTE",
    "OSTOMIA",
    "CURATIVOS",
    "LIMPEZA",
    "NUTRIÇAO",
    "MEDICAMENTO",
    "AMBULATORIAL",
    "ODONTO",
]

EMISSORES_PADRAO = [
    "FERNANDO",
    "DANIELA",
    "RUDINEY",
    "ELIZANGELA",
    "DANIELA E RUDINEY",
    "DANIELA E ELIZANGELA",
    "RUDINEY E ELIZANGELA",
    "DANIELA, RUDINEY E ELIZANGELA",
    "LUAN",
    "LUCAS",
    "ANDREY",
    "LUAN E LUCAS",
    "LUAN E ANDREY",
    "LUCAS E ANDREY",
    "LUAN, LUCAS E ANDREY",
    "PEDRO LUIZ",
]

MUNICIPIOS_PADRAO = [
    "ABELARDO LUZ",
    "BOM SUCESSO DO SUL",
    "CAIBI",
    "CAMPO ERE",
    "CHOPINZINHO",
    "CRE CHOPIN",
    "CLEVELANDIA",
    "CORONEL DOMINGOS SOARES",
    "CORONEL MARTINS",
    "CORONEL VIVIDA",
    "FORMOSA DO SUL",
    "GALVAO",
    "HONORIO SERPA",
    "IPUACU",
    "IRATI",
    "ITAPEJARA D' OESTE",
    "JUPIA",
    "MANGUEIRINHA",
    "MARIOPOLIS",
    "NOVO HORIZONTE",
    "OURO VERDE",
    "PALMA SOLA",
    "PALMAS",
    "PATO BRANCO",
    "SANTIAGO DO SUL",
    "SAO BERNARDINO",
    "SAO JOAO",
    "SAO LOURENCO DO OESTE",
    "SAUDADE DO IGUACU",
    "SULINA",
    "VITORINO",
]


class ConfigDialog(QDialog):
    """Janela de configurações do aplicativo."""

    def __init__(self, parent: QWidget, settings: dict[str, Any]):
        super().__init__(parent)
        self.setWindowTitle("Configurações")
        layout = QVBoxLayout(self)

        self._settings = settings

        form = QFormLayout()
        self.printer_combo = QComboBox()
        self.printer_combo.setEditable(True)
        form.addRow("Impressora:", self.printer_combo)

        self.template_combo = QComboBox()
        form.addRow("Modelo:", self.template_combo)

        self.retry_check = QCheckBox("Repetir automaticamente em falha (3x)")
        self.retry_check.setChecked(bool(settings.get("retry_automatico")))
        form.addRow("Repetir em falha:", self.retry_check)

        self.time_edit = QTimeEdit()
        horario = settings.get("backup_horario", "17:10")
        hora = QTime.fromString(str(horario), "HH:mm")
        if not hora.isValid():
            hora = QTime(17, 10)
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setTime(hora)
        form.addRow("Horário backup:", self.time_edit)

        layout.addLayout(form)

        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def showEvent(self, event: QCloseEvent) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._preparar_campos)

    def _preparar_campos(self) -> None:
        self._preencher_impressoras()
        self._preencher_templates()

    def _preencher_impressoras(self) -> None:
        self.printer_combo.clear()
        impressoras = listar_impressoras()
        if impressoras:
            self.printer_combo.addItems(impressoras)

        preferida = str(self._settings.get("ultima_impressora", "")).strip()
        if not preferida:
            preferida = descobrir_impressora_padrao() or ""

        if preferida:
            idx = self.printer_combo.findText(preferida)
            if idx >= 0:
                self.printer_combo.setCurrentIndex(idx)
            else:
                self.printer_combo.setEditText(preferida)
        elif self.printer_combo.isEditable():
            self.printer_combo.clearEditText()

    def _preencher_templates(self) -> None:
        self.template_combo.clear()
        self.template_combo.addItems(listar_templates())
        preferido = self._settings.get("template", "")
        idx = self.template_combo.findText(preferido)
        if idx >= 0:
            self.template_combo.setCurrentIndex(idx)

    def obter_config(self) -> dict[str, Any]:
        return {
            "ultima_impressora": self.printer_combo.currentText().strip(),
            "template": self.template_combo.currentText(),
            "retry_automatico": self.retry_check.isChecked(),
            "backup_horario": self.time_edit.time().toString("HH:mm"),
        }


class EtiquetaInfo(TypedDict):
    saida: int
    categoria: str
    emissor: str
    municipio: str
    volumes: int
    data_hora: str
    template: str  # <- modelo usado na impressão


class PrintingWorker(QObject):
    finished = pyqtSignal(bool, object)  # (ok, erro dict | None)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.args = args
        self.kwargs = kwargs

    @pyqtSlot()
    def run(self) -> None:
        try:
            ok, erro = imprimir_etiqueta(*self.args, **self.kwargs)
        except Exception as e:  # pragma: no cover - segurança
            logger.exception("Erro no worker de impressão")
            ok, erro = False, {"code": -1, "message": str(e)}
        self.finished.emit(ok, erro)


class EtiquetaApp(QWidget):
    """Janela principal do gerador de etiquetas."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Gerador de Etiquetas CONIMS")
        # tamanho inicial (aplicado já aqui, e reforçado no showEvent)
        self.resize(600, 800)
        self.setWindowIcon(QIcon(recurso_caminho("color.png")))
        self.config = carregar_config()
        self.contagem_total, self.contagem_mensal = carregar_contagem()
        self.ultima_etiqueta: EtiquetaInfo | None = None
        self.cancel_event = threading.Event()
        self._worker: PrintingWorker | None = None
        self._thread: QThread | None = None
        self._impressao_context: tuple[int, str, str, str, int, str] | None = None

        self._impressao_template: str | None = None  # <- lembra o modelo usado
        self._template: Template | None = None
        self._tem_impressora: bool | None = None
        self._editor_window: LabelEditorWindow | None = None

        # Estilo base precisa existir antes de sinais dispararem
        self._input_style_base = (
            "background:#191919;color:#e5e5e5;padding:7px;"
            "border:1px solid #282828;border-radius: 6px;font-size: 14px;"
        )
        self._ui_ready = False
        self._contagem_label = QLabel()
        self._contagem_label.setStyleSheet(
            "color: #CCCCCC; font-size: 15px; font-weight: 500; padding: 8px; "
            "letter-spacing: 1px;"
        )
        self._atualizar_contagem_label()

        self._logo_pixmap: QPixmap | None = None
        logo_path = recurso_caminho("color.png")
        if os.path.exists(logo_path):
            self._logo_pixmap = QPixmap(logo_path).scaledToWidth(
                120, Qt.SmoothTransformation
            )

        self._setup_ui()
        self._aplicar_tema_escuro()
        self._registrar_logger_ui()

        # Validação dinâmica
        self._wire_validation_signals()
        self._ui_ready = True
        self._update_print_button_state()

        self._atualizar_status("🟢 Pronto")
        QTimer.singleShot(0, self._agendar_backup_diario)
        QTimer.singleShot(0, self._verificar_impressora)

        self._printer_refresh_timer = QTimer(self)
        self._printer_refresh_timer.setInterval(60000)
        self._printer_refresh_timer.timeout.connect(self._verificar_impressora)
        self._printer_refresh_timer.start()

        # flag para aplicar o tamanho/centralização só uma vez após mostrar
        self._aplicou_tamanho_inicial = False

    # --- garante 600x1080 e centraliza DEPOIS que o layout calculou tudo ---
    def showEvent(self, event: QCloseEvent) -> None:
        super().showEvent(event)
        if not getattr(self, "_aplicou_tamanho_inicial", False):
            # reaplica para vencer size hints dos filhos
            self.resize(600, 800)
            # centraliza na tela disponível (desconta barra de tarefas)
            geo = self.frameGeometry()
            centro = self.screen().availableGeometry().center()
            geo.moveCenter(centro)
            self.move(geo.topLeft())
            self._aplicou_tamanho_inicial = True
            QTimer.singleShot(0, self._carregar_templates)
            QTimer.singleShot(
                0,
                lambda: self._aplicar_template(self.template_input.currentText()),
            )
            QTimer.singleShot(0, self._carregar_listas)

    def _agendar_backup_diario(self) -> None:
        horario = str(self.config.get("backup_horario", "17:10"))
        try:
            horas, minutos = [int(x) for x in horario.split(":", 1)]
        except Exception:
            horas, minutos = 17, 10

        agora = QDateTime.currentDateTime()
        fim_do_dia = QDateTime(agora.date(), QTime(horas, minutos, 0))
        if agora > fim_do_dia:
            fim_do_dia = fim_do_dia.addDays(1)
        ms_ate_backup = agora.msecsTo(fim_do_dia)

        if hasattr(self, "_timer_backup"):
            self._timer_backup.stop()
        self._timer_backup = QTimer(self)
        self._timer_backup.setSingleShot(True)
        self._timer_backup.timeout.connect(self._executar_backup_diario)
        self._timer_backup.start(ms_ate_backup)

    def _executar_backup_diario(self) -> None:
        backup_automatico()
        self._agendar_backup_diario()

    def closeEvent(self, event: QCloseEvent) -> None:
        backup_automatico()
        event.accept()

    def _setup_ui(self) -> None:
        layout_base = QVBoxLayout(self)
        layout_base.setContentsMargins(0, 0, 0, 0)
        layout_base.addSpacerItem(
            QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        )

        layout_central = QVBoxLayout()
        layout_central.setAlignment(Qt.AlignTop)
        layout_central.setContentsMargins(50, 30, 50, 30)
        layout_central.setSpacing(20)
        layout_base.addLayout(layout_central)

        # Logo e título
        logo_area = QVBoxLayout()
        logo_area.setAlignment(Qt.AlignCenter)
        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignCenter)
        logo_path = recurso_caminho("color.png")
        if os.path.exists(logo_path) and self._logo_pixmap is None:
            self._logo_pixmap = QPixmap(logo_path).scaledToWidth(
                120, Qt.SmoothTransformation
            )
        if self._logo_pixmap is not None:
            logo_label.setPixmap(self._logo_pixmap)
        logo_area.addWidget(logo_label)
        titulo = QLabel("Gerador de Etiquetas CONIMS")
        titulo.setFont(QFont("Segoe UI", 14, QFont.Bold))
        titulo.setAlignment(Qt.AlignCenter)
        logo_area.addWidget(titulo)
        layout_central.addLayout(logo_area)
        layout_central.addWidget(self._contagem_label)

        # Formulário
        quadro = QFrame()
        quadro.setStyleSheet(
            "QFrame{background:#232323;border-radius:12px;border: 1px solid #333;}"
        )
        layout_quadro = QVBoxLayout(quadro)
        layout_quadro.setContentsMargins(40, 30, 40, 30)
        layout_central.addWidget(quadro)

        grid = QGridLayout()
        layout_quadro.addLayout(grid)

        self.saida_input = QLineEdit()
        self.saida_input.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"\d*"))
        )
        self.saida_input.returnPressed.connect(self._imprimir_etiqueta)

        self.categoria_input = QComboBox()
        self.categoria_input.setEditable(True)
        self.categoria_input.lineEdit().returnPressed.connect(self._imprimir_etiqueta)

        self.emissor_input = QComboBox()
        self.emissor_input.setEditable(True)
        self.emissor_input.lineEdit().returnPressed.connect(self._imprimir_etiqueta)

        self.municipio_input = QComboBox()
        self.municipio_input.setEditable(True)
        self.municipio_input.lineEdit().returnPressed.connect(self._imprimir_etiqueta)

        self.volumes_input = QSpinBox()
        self.volumes_input.setMinimum(1)
        self.volumes_input.lineEdit().returnPressed.connect(self._imprimir_etiqueta)
        self.template_input = QComboBox()
        self.template_input.currentTextChanged.connect(self._aplicar_template)
        self.template_input.currentTextChanged.connect(self._salvar_template_config)
        self.template_input.currentTextChanged.connect(self._update_print_button_state)

        self.toggle_template_btn = QPushButton("Alternar modelo")
        self.toggle_template_btn.clicked.connect(self._toggle_template)

        # Estilo base para inputs (reaplicado nas validações)
        def _estilo(w):
            w.setStyleSheet(self._input_style_base)

        for w in (
            self.saida_input,
            self.categoria_input,
            self.emissor_input,
            self.municipio_input,
            self.volumes_input,
            self.template_input,
        ):
            _estilo(w)

        def _lbl(texto: str) -> QLabel:
            label = QLabel(texto)
            label.setStyleSheet(
                "color: #bbb; font-size: 13px; border: none; background: none;"
            )
            return label

        grid.addWidget(_lbl("Saída:"), 0, 0)
        grid.addWidget(self.saida_input, 0, 1)
        grid.addWidget(_lbl("Categoria:"), 1, 0)
        grid.addWidget(self.categoria_input, 1, 1)
        grid.addWidget(_lbl("Emissor:"), 2, 0)
        grid.addWidget(self.emissor_input, 2, 1)
        grid.addWidget(_lbl("Município:"), 3, 0)
        grid.addWidget(self.municipio_input, 3, 1)
        grid.addWidget(_lbl("Número de Volumes:"), 4, 0)
        grid.addWidget(self.volumes_input, 4, 1)
        grid.addWidget(_lbl("Modelo:"), 5, 0)
        grid.addWidget(self.template_input, 5, 1)
        grid.addWidget(self.toggle_template_btn, 5, 2)

        self.retry_checkbox = QCheckBox("Repetir automaticamente em falha (3x)")
        self.retry_checkbox.setStyleSheet(
            "color: #bbb; font-size: 13px; padding: 5px; border: none;"
        )
        self.retry_checkbox.setChecked(bool(self.config.get("retry_automatico")))
        self.retry_checkbox.stateChanged.connect(self._salvar_retry_config)
        layout_quadro.addWidget(self.retry_checkbox)

        # Botões
        botoes = QGridLayout()
        self.imprimir_btn = QPushButton("Imprimir\nAgora")
        self.imprimir_btn.setDefault(True)
        self.imprimir_btn.clicked.connect(self._imprimir_etiqueta)

        self.reimprimir_btn = QPushButton("Reimprimir\nÚltima")
        self.reimprimir_btn.clicked.connect(self._reimprimir_ultima)

        self.cancelar_btn = QPushButton("Cancelar")
        self.cancelar_btn.clicked.connect(self._cancelar_impressao)

        self.editor_btn = QPushButton("Edição de\nEtiqueta")
        self.editor_btn.clicked.connect(self._abrir_editor_etiqueta)

        self.menu_btn = QToolButton()
        self.menu_btn.setIcon(QIcon(recurso_caminho("menu-aberto.png")))
        self.menu_btn.setAutoRaise(True)  # remove relevo
        self.menu_btn.setStyleSheet("border: none;")  # evita moldura/ fundo
        self.menu_btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self.menu_btn)
        self.menu_btn.setMenu(menu)

        ac_faltantes = menu.addAction(
            "Reimprimir Faltantes", self._reimprimir_faltantes
        )
        ac_faltantes.setShortcut("Ctrl+F")
        ac_intervalo = menu.addAction(
            "Reimprimir Intervalo…", self._reimprimir_intervalo
        )
        ac_intervalo.setShortcut("Ctrl+I")
        ac_hist = menu.addAction("Abrir Histórico", self._abrir_historico)
        ac_hist.setShortcut("Ctrl+H")
        ac_hist_mes = menu.addAction("Histórico Mensal", self._mostrar_historico_mensal)
        ac_hist_mes.setShortcut("Ctrl+M")
        ac_relatorio = menu.addAction(
            "Exportar relatório do mês atual", self._exportar_relatorio_mes_atual
        )
        ac_relatorio.setShortcut("Ctrl+E")
        ac_log = menu.addAction("Ver Log", self._abrir_log)
        ac_log.setShortcut("Ctrl+L")
        ac_teste = menu.addAction("Imprimir página de teste", self._imprimir_teste)
        ac_teste.setShortcut("Ctrl+T")
        ac_config = menu.addAction("Configurações", self._abrir_configuracoes)
        ac_config.setShortcut("Ctrl+,")
        ac_verificar = menu.addAction("Testar conexão", self._verificar_impressora)
        ac_verificar.setShortcut("F5")

        for b in (
            self.imprimir_btn,
            self.reimprimir_btn,
            self.cancelar_btn,
            self.editor_btn,
        ):
            b.setStyleSheet(
                "background:#24292e;color:#eeeeee;padding:8px 18px;border-radius:6px;"
                "font-size: 14px;border: none;",
            )

        self.cancelar_btn.setStyleSheet(
            "background:#24292e;color:#ff5555;padding:8px 18px;border-radius:6px;"
            "font-size: 14px;border: none;",
        )

        botoes.addWidget(self.imprimir_btn, 0, 0)
        botoes.addWidget(self.reimprimir_btn, 0, 1)
        botoes.addWidget(self.cancelar_btn, 1, 0)
        botoes.addWidget(self.menu_btn, 1, 1)
        botoes.addWidget(self.editor_btn, 2, 0, 1, 2)

        layout_quadro.addLayout(botoes)

        # Status
        self.status_label = QLabel()
        self.status_label.setStyleSheet(
            "color: #8bc34a; font-size: 13px; border: none; background: none; "
            "padding: 5px;"
        )
        layout_quadro.addWidget(self.status_label)

        layout_base.addSpacerItem(
            QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        )

        self._footer_label = QLabel(
            "Feito por Pedro Luiz Bortot Monteiro do Rosário 2025 — "
            f"Versão {__version__}"
        )
        self._footer_label.setAlignment(Qt.AlignCenter)
        self._footer_label.setStyleSheet(
            "color: #555; font-size: 12px; border: none; "
            "background: none; padding: 10px;"
        )
        layout_base.addWidget(self._footer_label)

    def _aplicar_tema_escuro(self) -> None:
        p = QPalette()
        p.setColor(QPalette.Window, QColor(30, 30, 30))
        p.setColor(QPalette.WindowText, Qt.white)
        p.setColor(QPalette.Base, QColor(45, 45, 45))
        p.setColor(QPalette.Text, Qt.white)
        p.setColor(QPalette.Button, QColor(45, 45, 45))
        p.setColor(QPalette.ButtonText, Qt.white)
        self.setPalette(p)

    # =========================
    # Validação dinâmica
    # =========================
    def _wire_validation_signals(self) -> None:
        self.saida_input.textChanged.connect(self._update_print_button_state)
        for combo in (self.categoria_input, self.emissor_input, self.municipio_input):
            combo.currentTextChanged.connect(self._update_print_button_state)
            if combo.isEditable() and combo.lineEdit() is not None:
                combo.lineEdit().textChanged.connect(self._update_print_button_state)
        self.volumes_input.valueChanged.connect(self._update_print_button_state)

    def _is_form_valid(self) -> tuple[bool, str]:
        saida_ok = bool(self.saida_input.text().strip())
        cat_ok = bool(self.categoria_input.currentText().strip())
        emi_ok = bool(self.emissor_input.currentText().strip())
        mun_ok = bool(self.municipio_input.currentText().strip())
        vol_ok = self.volumes_input.value() >= 1

        if not saida_ok:
            return False, "Preencha o campo 'Saída'."
        if not cat_ok:
            return False, "Preencha o campo 'Categoria'."
        if not emi_ok:
            return False, "Preencha o campo 'Emissor'."
        if not mun_ok:
            return False, "Preencha o campo 'Município'."
        if not vol_ok:
            return False, "O campo 'Número de Volumes' deve ser ≥ 1."
        return True, ""

    def _apply_field_highlights(self) -> None:
        base = getattr(
            self,
            "_input_style_base",
            (
                "background:#191919;color:#e5e5e5;padding:7px;border:1px solid "
                "#282828;border-radius: 6px;font-size: 14px;"
            ),
        )

        def mark(widget, bad: bool):
            widget.setStyleSheet(base + ("border:1px solid #ff4d4d;" if bad else ""))

        saida_bad = not bool(self.saida_input.text().strip())
        cat_bad = not bool(self.categoria_input.currentText().strip())
        emi_bad = not bool(self.emissor_input.currentText().strip())
        mun_bad = not bool(self.municipio_input.currentText().strip())
        vol_bad = self.volumes_input.value() < 1

        mark(self.saida_input, saida_bad)
        mark(self.categoria_input, cat_bad)
        mark(self.emissor_input, emi_bad)
        mark(self.municipio_input, mun_bad)
        mark(self.volumes_input, vol_bad)

    def _update_print_button_state(self) -> None:
        # Evita rodar antes de a UI terminar de montar
        if not getattr(self, "_ui_ready", False):
            return
        ok, _ = self._is_form_valid()
        self._apply_field_highlights()
        tem_imp = bool(self._tem_impressora)
        if hasattr(self, "imprimir_btn"):
            self.imprimir_btn.setEnabled(ok and tem_imp)

    # =========================
    # Listas e normalização
    # =========================
    def _carregar_templates(self) -> None:
        self.template_input.clear()
        self.template_input.addItems(listar_templates())
        preferido = self.config.get("template", "")
        idx_tpl = self.template_input.findText(preferido)
        if idx_tpl < 0:
            idx_tpl = self.template_input.findText("100x30")
            if idx_tpl < 0:
                idx_tpl = self.template_input.findText("60x80")
            if idx_tpl < 0 and self.template_input.count() > 0:
                idx_tpl = 0
        if idx_tpl >= 0:
            self.template_input.setCurrentIndex(idx_tpl)

    def _popular_combo(
        self, combo: QComboBox, recentes: list[str], padroes: list[str]
    ) -> None:
        combo.clear()
        combo.addItem("")
        for item in recentes:
            combo.addItem(item)
        for item in padroes:
            if item not in recentes:
                combo.addItem(item)

    def _reordenar_combo(self, combo: QComboBox, recentes: list[str]) -> None:
        atuais = [combo.itemText(i) for i in range(combo.count()) if combo.itemText(i)]
        restantes = [item for item in atuais if item not in recentes]
        combo.clear()
        combo.addItem("")
        combo.addItems(recentes + restantes)

    def _carregar_listas(self) -> None:
        recentes = carregar_recentes_listas()
        self._popular_combo(
            self.categoria_input, recentes.get("categoria", []), CATEGORIAS_PADRAO
        )
        self._popular_combo(
            self.emissor_input, recentes.get("emissor", []), EMISSORES_PADRAO
        )
        self._popular_combo(
            self.municipio_input, recentes.get("municipio", []), MUNICIPIOS_PADRAO
        )
        self._update_print_button_state()

    def _coletar_campos(self) -> tuple[int, str, str, str, int, str]:
        saida_texto = self.saida_input.text().strip()
        saida = int(saida_texto) if saida_texto else 0
        categoria = self.categoria_input.currentText().strip()
        emissor = self.emissor_input.currentText().strip()
        municipio = self.municipio_input.currentText().strip()
        categoria, _ = normalize_text(categoria, max_len=50)
        emissor, _ = normalize_text(emissor, max_len=50)
        municipio, _ = normalize_text(municipio, max_len=50)
        volumes = int(self.volumes_input.value())
        data_hora = datetime.now().strftime("%d/%m/%Y %H:%M")
        return saida, categoria, emissor, municipio, volumes, data_hora

    def _atualizar_listas_recentes(
        self, categoria: str, emissor: str, municipio: str
    ) -> None:
        atualizar_recentes(categoria, emissor, municipio)
        recentes = carregar_recentes_listas()
        self._reordenar_combo(self.categoria_input, recentes.get("categoria", []))
        self._reordenar_combo(self.emissor_input, recentes.get("emissor", []))
        self._reordenar_combo(self.municipio_input, recentes.get("municipio", []))

    def _limpar_campos(self) -> None:
        self.saida_input.clear()
        for combo in (self.categoria_input, self.emissor_input, self.municipio_input):
            combo.setCurrentIndex(0)
        self.volumes_input.setValue(1)
        self._update_print_button_state()

    def _aplicar_template(self, nome: str) -> None:
        try:
            self._template = aplicar_template(nome)
            self._impressao_template = nome  # lembra o modelo atual
        except ValueError as e:
            QMessageBox.critical(self, "Erro", str(e))

    def _toggle_template(self) -> None:
        atual = self.template_input.currentText()
        novo = "60x80" if atual == "100x30" else "100x30"
        idx = self.template_input.findText(novo)
        if idx >= 0:
            self.template_input.setCurrentIndex(idx)

    def _abrir_editor_etiqueta(self) -> None:
        if self._editor_window is None:
            self._editor_window = LabelEditorWindow()
            self._editor_window.destroyed.connect(self._editor_window_closed)
        self._editor_window.show()
        self._editor_window.raise_()
        self._editor_window.activateWindow()

    def _editor_window_closed(self, _obj: QObject | None = None) -> None:
        self._editor_window = None

    # =========================
    # Persistência e ações
    # =========================
    def _salvar_template_config(self, texto: str) -> None:
        self.config["template"] = texto
        salvar_config(self.config)

    def _salvar_retry_config(self, estado: int) -> None:
        self.config["retry_automatico"] = bool(estado)
        salvar_config(self.config)

    def _abrir_configuracoes(self) -> None:
        dlg = ConfigDialog(self, self.config)
        if dlg.exec_():
            self.config.update(dlg.obter_config())
            salvar_config(self.config)
            # tenta posicionar no combo o mesmo template salvo
            idx = self.template_input.findText(self.config.get("template", ""))
            if idx >= 0:
                self.template_input.setCurrentIndex(idx)
            self.retry_checkbox.setChecked(bool(self.config.get("retry_automatico")))
            self._agendar_backup_diario()
            self._verificar_impressora()

    def _verificar_impressora(self) -> None:
        nome = descobrir_impressora_padrao()
        self._tem_impressora = nome is not None
        self._update_print_button_state()
        if nome is None:
            self._atualizar_status("⚠️ Nenhuma impressora detectada", "orange")
        else:
            self._atualizar_status("🟢 Pronto")
            self.config["ultima_impressora"] = nome
            salvar_config(self.config)

    def _atualizar_status(
        self, mensagem: str = "🟢 Pronto", cor: str = "white"
    ) -> None:
        self.status_label.setText(mensagem)
        self.status_label.setStyleSheet(f"color:{cor};padding:5px")

    def _registrar_logger_ui(self) -> None:
        def _cb(msg: str) -> None:
            QTimer.singleShot(0, lambda: self._atualizar_status(f"⚠️ {msg}", "orange"))

        register_status_callback(_cb)

    # =========================
    # Ações de impressão e utilitários
    # =========================
    def _abrir_historico(self) -> None:
        caminho = recurso_caminho("historico_impressoes.csv")
        if os.path.exists(caminho):
            try:
                if sys.platform.startswith("win"):
                    os.startfile(caminho)  # type: ignore[attr-defined]
                elif sys.platform == "darwin":
                    subprocess.run(["open", caminho], check=True)
                else:
                    subprocess.run(["xdg-open", caminho], check=True)
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Histórico",
                    f"Não foi possível abrir o arquivo de histórico:\n{e}",
                )
        else:
            QMessageBox.information(
                self, "Histórico", "O arquivo de histórico ainda não existe."
            )

    def _imprimir_etiqueta(self) -> None:
        self._update_print_button_state()
        ok, msg = self._is_form_valid()
        if not ok:
            self._atualizar_status("⚠️ Campos obrigatórios", "orange")
            QMessageBox.warning(self, "Campos obrigatórios", msg)
            return

        self._atualizar_status("🖨️ Imprimindo…")
        self.cancel_event.clear()
        (
            saida,
            categoria,
            emissor,
            municipio,
            volumes,
            data_hora,
        ) = self._coletar_campos()

        # pega o modelo exibido no combo (o mesmo que foi aplicado)
        tpl = (
            self.template_input.currentText().strip()
            or (self._impressao_template or "")
        )
        if not tpl:
            QMessageBox.warning(self, "Modelo", "Selecione um modelo de etiqueta.")
            return
        self._impressao_template = tpl  # reforça

        dados = {
            "saida": str(saida),
            "categoria": categoria,
            "emissor": emissor,
            "municipio": municipio,
            "volumes": volumes,
            "data_hora": data_hora,
        }
        if self._template is None:
            QMessageBox.warning(self, "Modelo", "Selecione um modelo de etiqueta.")
            return
        tspl = montar_tspl(self._template, dados)
        logger.debug("TSPL gerado:\n%s", tspl)

        # guarda o contexto desta impressão (inclui template para salvar depois)
        self._impressao_context = (
            saida,
            categoria,
            emissor,
            municipio,
            volumes,
            data_hora,
        )

        self._worker = PrintingWorker(
            tspl,
            repetir_em_falha=self.retry_checkbox.isChecked(),
        )
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._impressao_finalizada)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _cancelar_impressao(self) -> None:
        self.cancel_event.set()
        if self._thread and self._thread.isRunning():
            self._thread.quit()
        self._atualizar_status("❌ Impressão cancelada", "orange")

    def _impressao_finalizada(self, ok: bool, erro: dict | None) -> None:
        if self._impressao_context is None:
            return
        (
            saida,
            categoria,
            emissor,
            municipio,
            volumes,
            data_hora,
        ) = self._impressao_context
        if not ok:
            if self.cancel_event.is_set():
                self._atualizar_status("❌ Impressão cancelada", "orange")
            else:
                if erro is not None:
                    msg = f"{erro['code']}: {erro['message']}"
                else:
                    msg = "Erro desconhecido"
                self._atualizar_status(f"⚠️ Erro na impressão ({msg})", "orange")
                logger.error("Erro na impressão: %s", erro)
                QMessageBox.critical(self, "Erro", msg)
        else:
            try:
                self.contagem_total += volumes
                self.contagem_mensal += volumes
                salvar_contagem(self.contagem_total, self.contagem_mensal)

                salvar_historico(
                    saida, categoria, emissor, municipio, volumes, data_hora
                )
                self.ultima_etiqueta = EtiquetaInfo(
                    saida=saida,
                    categoria=categoria,
                    emissor=emissor,
                    municipio=municipio,
                    volumes=volumes,
                    data_hora=data_hora,
                    template=(
                        self._impressao_template
                        or self.template_input.currentText().strip()
                        or ""
                    ),
                )

                self._atualizar_listas_recentes(categoria, emissor, municipio)

                mes_atual = datetime.now().strftime("%m-%Y")
                registrar_contagem_mensal(mes_atual, volumes)
                self._atualizar_status("✅ Impressão concluída", "lightgreen")
                QTimer.singleShot(30000, self._limpar_campos)
                self._atualizar_contagem_label()
            except Exception as e:
                self._atualizar_status("⚠️ Erro na impressão", "orange")
                logger.exception("Erro na impressão")
                QMessageBox.critical(self, "Erro", str(e))

        self.cancel_event.clear()
        self._impressao_context = None

    def _cleanup_thread(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None

    def _imprimir_teste(self) -> None:
        self._atualizar_status("🖨️ Imprimindo teste…")
        if self._template is None:
            QMessageBox.warning(self, "Modelo", "Selecione um modelo de etiqueta.")
            return
        ok, erro = imprimir_pagina_teste(
            self._template, repetir_em_falha=self.retry_checkbox.isChecked()
        )
        if ok:
            self._atualizar_status("✅ Página de teste impressa", "lightgreen")
        else:
            self._atualizar_status("⚠️ Erro na impressão de teste", "orange")
            logger.error("Erro na impressão de teste: %s", erro)
            QMessageBox.critical(self, "Erro", f"{erro['code']}: {erro['message']}")

    def _reimprimir_ultima(self) -> None:
        if self.ultima_etiqueta is None:
            QMessageBox.information(
                self, "Nenhuma etiqueta", "Nenhuma etiqueta foi impressa ainda."
            )
            return
        dados = self.ultima_etiqueta

        # aplica o mesmo template da impressão original
        tpl_name = (
            dados.get("template", "")
            or self.template_input.currentText().strip()
        )
        if tpl_name:
            try:
                self._template = aplicar_template(tpl_name)
            except Exception:
                pass

        self.cancel_event.clear()
        if self._template is None:
            QMessageBox.warning(self, "Modelo", "Selecione um modelo de etiqueta.")
            return
        dados_tspl = dict(dados)
        dados_tspl["saida"] = str(dados_tspl.get("saida", ""))
        tspl = montar_tspl(self._template, dados_tspl)
        ok, erro = imprimir_etiqueta(
            tspl,
            repetir_em_falha=self.retry_checkbox.isChecked(),
        )
        if ok:
            self._atualizar_status("♻️ Reimpressão concluída", "lightblue")
        else:
            self._atualizar_status("⚠️ Erro na reimpressão", "orange")
            logger.error("Erro na reimpressão: %s", erro)
            QMessageBox.critical(self, "Erro", f"{erro['code']}: {erro['message']}")

    def _reimprimir_faltantes(self) -> None:
        if self.ultima_etiqueta is None:
            QMessageBox.information(
                self, "Nenhuma etiqueta", "Nenhuma etiqueta foi impressa ainda."
            )
            return

        dados = self.ultima_etiqueta
        total = int(dados["volumes"])

        faltantes, ok = QInputDialog.getInt(
            self,
            "Reimprimir Faltantes",
            f"Quantas etiquetas faltaram desse lote de {total}?",
            1,
            1,
            total,
            1,
        )
        if not ok:
            return

        inicio = total - faltantes + 1

        try:
            # aplica o mesmo template da impressão original
            tpl_name = self.ultima_etiqueta.get("template", "")
            if tpl_name:
                try:
                    self._template = aplicar_template(tpl_name)
                except Exception:
                    pass

            self.cancel_event.clear()
            dados_tspl = {
                "saida": str(dados["saida"]),
                "categoria": dados["categoria"],
                "emissor": dados["emissor"],
                "municipio": dados["municipio"],
                "volumes": faltantes,
                "data_hora": dados["data_hora"],
                "inicio_indice": inicio,
                "total_exibicao": total,
            }
            if self._template is None:
                QMessageBox.warning(self, "Modelo", "Selecione um modelo de etiqueta.")
                return
            tspl = montar_tspl(self._template, dados_tspl)
            ok, erro = imprimir_etiqueta(
                tspl,
                repetir_em_falha=self.retry_checkbox.isChecked(),
            )

            if not ok:
                self._atualizar_status("⚠️ Erro na reimpressão de faltantes", "orange")
                logger.error("Erro na reimpressão de faltantes: %s", erro)
                QMessageBox.critical(self, "Erro", f"{erro['code']}: {erro['message']}")
                return

            self.contagem_total += faltantes
            self.contagem_mensal += faltantes
            salvar_contagem(self.contagem_total, self.contagem_mensal)
            salvar_historico(
                dados["saida"],
                dados["categoria"],
                dados["emissor"],
                dados["municipio"],
                faltantes,
                datetime.now().strftime("%d/%m/%Y %H:%M"),
            )
            self._atualizar_contagem_label()

            self._atualizar_status("♻️ Faltantes reimpressas", "lightblue")
        except Exception as e:
            self._atualizar_status("⚠️ Erro na reimpressão de faltantes", "orange")
            logger.exception("Erro na reimpressão de faltantes")
            QMessageBox.critical(self, "Erro", str(e))

    def _reimprimir_intervalo(self) -> None:
        if self.ultima_etiqueta is None:
            QMessageBox.information(
                self, "Nenhuma etiqueta", "Nenhuma etiqueta foi impressa ainda."
            )
            return

        dados = self.ultima_etiqueta
        total = int(dados["volumes"])

        intervalo, ok = QInputDialog.getText(
            self,
            "Reimprimir Intervalo",
            f"Informe o intervalo (1-{total}, ex.: 5-8):",
        )
        if not ok or not intervalo:
            return

        try:
            intervalo = intervalo.replace("–", "-").replace(" ", "")
            inicio_str, fim_str = intervalo.split("-")
            inicio = int(inicio_str)
            fim = int(fim_str)
        except ValueError:
            QMessageBox.warning(
                self,
                "Intervalo inválido",
                "Use o formato início-fim, ex.: 5-8.",
            )
            return

        if inicio < 1 or fim > total or inicio > fim:
            QMessageBox.warning(
                self,
                "Intervalo inválido",
                f"O intervalo deve estar entre 1 e {total}.",
            )
            return

        volumes = fim - inicio + 1

        try:
            # aplica o mesmo template da impressão original
            tpl_name = self.ultima_etiqueta.get("template", "")
            if tpl_name:
                try:
                    self._template = aplicar_template(tpl_name)
                except Exception:
                    pass

            self.cancel_event.clear()
            dados_tspl = {
                "saida": str(dados["saida"]),
                "categoria": dados["categoria"],
                "emissor": dados["emissor"],
                "municipio": dados["municipio"],
                "volumes": volumes,
                "data_hora": dados["data_hora"],
                "inicio_indice": inicio,
                "total_exibicao": total,
            }
            if self._template is None:
                QMessageBox.warning(self, "Modelo", "Selecione um modelo de etiqueta.")
                return
            tspl = montar_tspl(self._template, dados_tspl)
            ok, erro = imprimir_etiqueta(
                tspl,
                repetir_em_falha=self.retry_checkbox.isChecked(),
            )
            if ok:
                self._atualizar_status("♻️ Intervalo reimposto", "lightblue")
            else:
                self._atualizar_status("⚠️ Erro na reimpressão do intervalo", "orange")
                logger.error("Erro na reimpressão do intervalo: %s", erro)
                QMessageBox.critical(self, "Erro", f"{erro['code']}: {erro['message']}")
        except Exception as e:
            self._atualizar_status("⚠️ Erro na reimpressão do intervalo", "orange")
            logger.exception("Erro na reimpressão do intervalo")
            QMessageBox.critical(self, "Erro", str(e))

    def _abrir_log(self) -> None:
        if not os.path.exists(LOG_FILE):
            QMessageBox.information(
                self, "Log", "O arquivo de log ainda não foi criado."
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(LOG_FILE))

    def _mostrar_historico_mensal(self) -> None:
        hist = carregar_historico_mensal()
        if not hist:
            QMessageBox.information(self, "Histórico Mensal", "Nenhum dado encontrado.")
            return
        texto = "Histórico de Etiquetas por Mês:\n\n"
        for mes, total in sorted(hist.items()):
            texto += f"Mês: {mes}   —   Total: {total}\n"
        QMessageBox.information(self, "Histórico Mensal", texto)

    def _exportar_relatorio_mes_atual(self) -> None:
        mes = datetime.now().strftime("%Y-%m")
        try:
            caminho = gerar_relatorio_mensal(mes)
            QMessageBox.information(
                self,
                "Relatório Mensal",
                f"Relatório salvo em:\n{caminho}",
            )
        except FileNotFoundError:
            QMessageBox.information(
                self,
                "Relatório Mensal",
                "Histórico de impressões não encontrado.",
            )
        except Exception as e:
            logger.exception("Erro ao gerar relatório mensal")
            QMessageBox.critical(self, "Erro", str(e))

    def _atualizar_contagem_label(self) -> None:
        nome_mes = datetime.now().strftime("%m/%Y")
        self._contagem_label.setText(
            "Etiquetas do mês: "
            f"<span style='font-weight:600'>{self.contagem_mensal}</span> "
            "&nbsp;|&nbsp; "
            f"Total geral: <span style='font-weight:600'>{self.contagem_total}</span> "
            f"<span style='color:#888;font-size:13px'>(Mês: {nome_mes})</span>"
        )
