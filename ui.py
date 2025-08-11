"""Elementos da interface gráfica do gerador de etiquetas."""

import os
from datetime import datetime
from typing import Any, TypedDict

from PyQt5.QtCore import QDateTime, Qt, QTime, QTimer, QUrl
from PyQt5.QtGui import (
    QCloseEvent,
    QColor,
    QDesktopServices,
    QFont,
    QIcon,
    QPalette,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from log import LOG_FILE, logger
from persistence import (
    atualizar_recentes,
    carregar_contagem,
    carregar_config,
    carregar_historico_mensal,
    carregar_recentes_listas,
    gerar_relatorio_mensal,
    registrar_contagem_mensal,
    salvar_contagem,
    salvar_config,
    salvar_historico,
)
from printing import (
    aplicar_template,
    descobrir_impressora_padrao,
    imprimir_etiqueta,
    imprimir_pagina_teste,
    listar_templates,
)
from utils import backup_automatico, recurso_caminho

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

        form = QFormLayout()
        self.printer_edit = QLineEdit(settings.get("ultima_impressora", ""))
        form.addRow("Impressora:", self.printer_edit)

        self.template_combo = QComboBox()
        self.template_combo.addItems(listar_templates())
        idx = self.template_combo.findText(settings.get("template", "Padrão"))
        if idx >= 0:
            self.template_combo.setCurrentIndex(idx)
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

    def obter_config(self) -> dict[str, Any]:
        """Retorna as configurações ajustadas pelo usuário."""

        return {
            "ultima_impressora": self.printer_edit.text().strip(),
            "template": self.template_combo.currentText(),
            "retry_automatico": self.retry_check.isChecked(),
            "backup_horario": self.time_edit.time().toString("HH:mm"),
        }


class EtiquetaInfo(TypedDict):
    saida: str
    categoria: str
    emissor: str
    municipio: str
    volumes: int
    data_hora: str


class EtiquetaApp(QWidget):
    """Janela principal do gerador de etiquetas."""

    def __init__(self) -> None:
        """Inicializa a interface gráfica e configura a janela."""

        super().__init__()
        self.setWindowTitle("Gerador de Etiquetas CONIMS")
        self.setGeometry(300, 100, 800, 720)
        self.setWindowIcon(QIcon(recurso_caminho("color.png")))
        self.config = carregar_config()
        self.contagem_total, self.contagem_mensal = carregar_contagem()
        self.ultima_etiqueta: EtiquetaInfo | None = None
        self._contagem_label = QLabel()
        self._contagem_label.setStyleSheet(
            "color: #CCCCCC; font-size: 15px; font-weight: 500; padding: 8px; "
            "letter-spacing: 1px;"
        )
        self._atualizar_contagem_label()

        self._setup_ui()
        self._aplicar_tema_escuro()
        self._atualizar_status("🟢 Pronto")
        self._agendar_backup_diario()
        self._verificar_impressora()

    def _agendar_backup_diario(self) -> None:
        """Agenda a execução do backup diário conforme configuração."""

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
        """Executa o backup e reagenda a próxima execução."""

        backup_automatico()
        self._agendar_backup_diario()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Garante um backup ao fechar a janela.

        Args:
            event: Evento de fechamento recebido do Qt.
        """

        backup_automatico()
        event.accept()

    def _setup_ui(self) -> None:
        """Monta todos os widgets e layouts da interface."""

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
        if os.path.exists(logo_path):
            logo_label.setPixmap(
                QPixmap(logo_path).scaledToWidth(120, Qt.SmoothTransformation)
            )
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
        self.categoria_input = QComboBox()
        self.categoria_input.setEditable(True)
        self.emissor_input = QComboBox()
        self.emissor_input.setEditable(True)
        self.municipio_input = QComboBox()
        self.municipio_input.setEditable(True)
        self.volumes_input = QSpinBox()
        self.volumes_input.setMinimum(1)
        self.template_input = QComboBox()
        self.template_input.addItems(listar_templates())
        self.template_input.currentTextChanged.connect(aplicar_template)
        self.template_input.currentTextChanged.connect(self._salvar_template_config)
        idx_tpl = self.template_input.findText(self.config.get("template", "Padrão"))
        if idx_tpl >= 0:
            self.template_input.setCurrentIndex(idx_tpl)
        aplicar_template(self.template_input.currentText())
        self._carregar_listas()

        def _estilo(w):
            w.setStyleSheet(
                "background:#191919;color:#e5e5e5;padding:7px;"
                "border:1px solid #282828;border-radius: 6px;font-size: 14px;"
            )

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

        self.retry_checkbox = QCheckBox("Repetir automaticamente em falha (3x)")
        self.retry_checkbox.setStyleSheet(
            "color: #bbb; font-size: 13px; padding: 5px; border: none;"
        )
        self.retry_checkbox.setChecked(bool(self.config.get("retry_automatico")))
        self.retry_checkbox.stateChanged.connect(self._salvar_retry_config)
        layout_quadro.addWidget(self.retry_checkbox)

        # Botões
        botoes = QHBoxLayout()
        self.imprimir_btn = QPushButton("Imprimir Agora")
        self.imprimir_btn.clicked.connect(self._imprimir_etiqueta)

        self.reimprimir_btn = QPushButton("Reimprimir Última")
        self.reimprimir_btn.clicked.connect(self._reimprimir_ultima)

        self.reimprimir_faltantes_btn = QPushButton("Reimprimir Faltantes")
        self.reimprimir_faltantes_btn.clicked.connect(self._reimprimir_faltantes)

        self.reimprimir_intervalo_btn = QPushButton("Reimprimir Intervalo…")
        self.reimprimir_intervalo_btn.clicked.connect(self._reimprimir_intervalo)

        self.historico_btn = QPushButton("Abrir Histórico")
        self.historico_btn.clicked.connect(self._abrir_historico)

        self.historico_mes_btn = QPushButton("Histórico Mensal")
        self.historico_mes_btn.clicked.connect(self._mostrar_historico_mensal)

        self.exportar_relatorio_btn = QPushButton("Exportar relatório do mês atual")
        self.exportar_relatorio_btn.clicked.connect(self._exportar_relatorio_mes_atual)

        self.log_btn = QPushButton("Ver Log")
        self.log_btn.clicked.connect(self._abrir_log)

        self.teste_pagina_btn = QPushButton("Imprimir página de teste")
        self.teste_pagina_btn.clicked.connect(self._imprimir_teste)

        self.config_btn = QPushButton("Configurações")
        self.config_btn.clicked.connect(self._abrir_configuracoes)

        self.testar_conexao_btn = QPushButton("Testar conexão")
        self.testar_conexao_btn.clicked.connect(self._verificar_impressora)

        for b in (
            self.imprimir_btn,
            self.reimprimir_btn,
            self.reimprimir_faltantes_btn,
            self.reimprimir_intervalo_btn,
            self.historico_btn,
            self.historico_mes_btn,
            self.exportar_relatorio_btn,
            self.log_btn,
            self.teste_pagina_btn,
            self.config_btn,
            self.testar_conexao_btn,
        ):
            b.setStyleSheet(
                "background:#24292e;color:#eeeeee;padding:8px 18px;border-radius:6px;"
                "font-size: 14px;border: none;"
            )
            botoes.addWidget(b)
        self.testar_conexao_btn.hide()
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

    def _aplicar_tema_escuro(self) -> None:
        """Aplica esquema de cores escuro à aplicação."""

        p = QPalette()
        p.setColor(QPalette.Window, QColor(30, 30, 30))
        p.setColor(QPalette.WindowText, Qt.white)
        p.setColor(QPalette.Base, QColor(45, 45, 45))
        p.setColor(QPalette.Text, Qt.white)
        p.setColor(QPalette.Button, QColor(45, 45, 45))
        p.setColor(QPalette.ButtonText, Qt.white)
        self.setPalette(p)

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
        """Preenche as listas de seleção com valores padrão e recentes."""

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

    def _atualizar_listas_recentes(
        self, categoria: str, emissor: str, municipio: str
    ) -> None:
        atualizar_recentes(categoria, emissor, municipio)
        recentes = carregar_recentes_listas()
        self._reordenar_combo(self.categoria_input, recentes.get("categoria", []))
        self._reordenar_combo(self.emissor_input, recentes.get("emissor", []))
        self._reordenar_combo(self.municipio_input, recentes.get("municipio", []))

    def _limpar_campos(self) -> None:
        """Restaura os campos do formulário para os valores iniciais."""

        self.saida_input.clear()
        for combo in (self.categoria_input, self.emissor_input, self.municipio_input):
            combo.setCurrentIndex(0)
        self.volumes_input.setValue(1)

    def _salvar_template_config(self, texto: str) -> None:
        """Persistir seleção de template."""

        self.config["template"] = texto
        salvar_config(self.config)

    def _salvar_retry_config(self, estado: int) -> None:
        """Persistir opção de repetição automática."""

        self.config["retry_automatico"] = bool(estado)
        salvar_config(self.config)

    def _abrir_configuracoes(self) -> None:
        """Mostra a janela de configurações."""

        dlg = ConfigDialog(self, self.config)
        if dlg.exec_():
            self.config.update(dlg.obter_config())
            salvar_config(self.config)
            idx = self.template_input.findText(self.config.get("template", "Padrão"))
            if idx >= 0:
                self.template_input.setCurrentIndex(idx)
            self.retry_checkbox.setChecked(bool(self.config.get("retry_automatico")))
            self._agendar_backup_diario()
            self._verificar_impressora()

    def _verificar_impressora(self) -> None:
        """Verifica a existência de impressora padrão e ajusta a UI."""

        nome = descobrir_impressora_padrao()
        if nome is None:
            self.imprimir_btn.setEnabled(False)
            self.testar_conexao_btn.show()
            self._atualizar_status("⚠️ Nenhuma impressora detectada", "orange")
        else:
            self.imprimir_btn.setEnabled(True)
            self.testar_conexao_btn.hide()
            self._atualizar_status("🟢 Pronto")
            self.config["ultima_impressora"] = nome
            salvar_config(self.config)

    def _atualizar_status(
        self, mensagem: str = "🟢 Pronto", cor: str = "white"
    ) -> None:
        """Atualiza a mensagem de status exibida ao usuário.

        Args:
            mensagem (str, optional): Texto a ser mostrado. Padrão "🟢 Pronto".
            cor (str, optional): Cor do texto. Padrão ``white``.
        """

        self.status_label.setText(mensagem)
        self.status_label.setStyleSheet(f"color:{cor};padding:5px")

    def _abrir_historico(self) -> None:
        """Abre o arquivo CSV de histórico no sistema operacional."""

        import subprocess

        caminho = recurso_caminho("historico_impressoes.csv")
        if os.path.exists(caminho):
            subprocess.Popen(["start", "", caminho], shell=True)
        else:
            QMessageBox.information(
                self, "Histórico", "O arquivo de histórico ainda não existe."
            )

    def _imprimir_etiqueta(self) -> None:
        """Coleta dados do formulário e solicita a impressão."""

        self._atualizar_status("🖨️ Imprimindo…")
        saida = str(self.saida_input.text()).strip()
        categoria = self.categoria_input.currentText()
        emissor = self.emissor_input.currentText()
        municipio = self.municipio_input.currentText()
        volumes = self.volumes_input.value()
        data_hora = datetime.now().strftime("%d/%m/%Y %H:%M")

        if saida == "":
            QMessageBox.warning(self, "Campo obrigatório", "Preencha o campo Saída.")
            self._atualizar_status()
            return

        ok, erro = imprimir_etiqueta(
            saida,
            categoria,
            emissor,
            municipio,
            volumes,
            data_hora,
            self.contagem_total,
            self.contagem_mensal,
            repetir_em_falha=self.retry_checkbox.isChecked(),
        )

        if not ok:
            self._atualizar_status("⚠️ Erro na impressão", "orange")
            logger.error("Erro na impressão: %s", erro)
            QMessageBox.critical(self, "Erro", f"{erro['code']}: {erro['message']}")
            return

        try:
            self.contagem_total += volumes
            self.contagem_mensal += volumes
            salvar_contagem(self.contagem_total, self.contagem_mensal)

            salvar_historico(saida, categoria, emissor, municipio, volumes, data_hora)
            self.ultima_etiqueta = EtiquetaInfo(
                saida=saida,
                categoria=categoria,
                emissor=emissor,
                municipio=municipio,
                volumes=volumes,
                data_hora=data_hora,
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

    def _imprimir_teste(self) -> None:
        """Imprime uma página de teste padrão."""

        self._atualizar_status("🖨️ Imprimindo teste…")
        ok, erro = imprimir_pagina_teste(
            repetir_em_falha=self.retry_checkbox.isChecked()
        )
        if ok:
            self._atualizar_status("✅ Página de teste impressa", "lightgreen")
        else:
            self._atualizar_status("⚠️ Erro na impressão de teste", "orange")
            logger.error("Erro na impressão de teste: %s", erro)
            QMessageBox.critical(self, "Erro", f"{erro['code']}: {erro['message']}")

    def _reimprimir_ultima(self) -> None:
        """Reimprime a última etiqueta gerada, se houver."""

        if self.ultima_etiqueta is None:
            QMessageBox.information(
                self, "Nenhuma etiqueta", "Nenhuma etiqueta foi impressa ainda."
            )
            return
        dados = self.ultima_etiqueta
        ok, erro = imprimir_etiqueta(
            dados["saida"],
            dados["categoria"],
            dados["emissor"],
            dados["municipio"],
            dados["volumes"],
            dados["data_hora"],
            self.contagem_total,
            self.contagem_mensal,
            repetir_em_falha=self.retry_checkbox.isChecked(),
        )
        if ok:
            self._atualizar_status("♻️ Reimpressão concluída", "lightblue")
        else:
            self._atualizar_status("⚠️ Erro na reimpressão", "orange")
            logger.error("Erro na reimpressão: %s", erro)
            QMessageBox.critical(self, "Erro", f"{erro['code']}: {erro['message']}")

    def _reimprimir_faltantes(self) -> None:
        """Reimprime apenas as etiquetas que faltaram de um lote."""

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
            from persistence import salvar_contagem, salvar_historico

            ok, erro = imprimir_etiqueta(
                dados["saida"],
                dados["categoria"],
                dados["emissor"],
                dados["municipio"],
                faltantes,
                dados["data_hora"],
                self.contagem_total,
                self.contagem_mensal,
                inicio_indice=inicio,
                total_exibicao=total,
                repetir_em_falha=self.retry_checkbox.isChecked(),
            )

            if not ok:
                self._atualizar_status("⚠️ Erro na reimpressão de faltantes", "orange")
                logger.error("Erro na reimpressão de faltantes: %s", erro)
                QMessageBox.critical(self, "Erro", f"{erro['code']}: {erro['message']}")
                return

            # Atualiza contadores e histórico apenas com as faltantes
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
        """Reimprime um intervalo específico da última etiqueta."""

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
            ok, erro = imprimir_etiqueta(
                dados["saida"],
                dados["categoria"],
                dados["emissor"],
                dados["municipio"],
                volumes,
                dados["data_hora"],
                self.contagem_total,
                self.contagem_mensal,
                inicio_indice=inicio,
                total_exibicao=total,
                repetir_em_falha=self.retry_checkbox.isChecked(),
            )
            if ok:
                self._atualizar_status("♻️ Intervalo reimpresso", "lightblue")
            else:
                self._atualizar_status("⚠️ Erro na reimpressão do intervalo", "orange")
                logger.error("Erro na reimpressão do intervalo: %s", erro)
                QMessageBox.critical(self, "Erro", f"{erro['code']}: {erro['message']}")
        except Exception as e:
            self._atualizar_status("⚠️ Erro na reimpressão do intervalo", "orange")
            logger.exception("Erro na reimpressão do intervalo")
            QMessageBox.critical(self, "Erro", str(e))

    def _abrir_log(self) -> None:
        """Abre o arquivo de log gerado pela aplicação."""

        if not os.path.exists(LOG_FILE):
            QMessageBox.information(
                self, "Log", "O arquivo de log ainda não foi criado."
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(LOG_FILE))

    def _mostrar_historico_mensal(self) -> None:
        """Exibe um resumo das etiquetas impressas por mês."""

        hist = carregar_historico_mensal()
        if not hist:
            QMessageBox.information(self, "Histórico Mensal", "Nenhum dado encontrado.")
            return
        texto = "Histórico de Etiquetas por Mês:\n\n"
        for mes, total in sorted(hist.items()):
            texto += f"Mês: {mes}   —   Total: {total}\n"
        QMessageBox.information(self, "Histórico Mensal", texto)

    def _exportar_relatorio_mes_atual(self) -> None:
        """Exporta o relatório consolidado do mês atual."""

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
        """Atualiza o texto que mostra os totais de etiquetas."""

        nome_mes = datetime.now().strftime("%m/%Y")
        self._contagem_label.setText(
            "Etiquetas do mês: "
            f"<span style='font-weight:600'>{self.contagem_mensal}</span> "
            "&nbsp;|&nbsp; "
            f"Total geral: <span style='font-weight:600'>{self.contagem_total}</span> "
            f"<span style='color:#888;font-size:13px'>(Mês: {nome_mes})</span>"
        )
