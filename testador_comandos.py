"""GUI UDP e serial para testar comandos do ESP32."""

from __future__ import annotations

import argparse

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None
import queue
import socket
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, ttk
from typing import Callable


DEFAULT_PORT = 4210
DEFAULT_TIMEOUT = 3.0
RESPONSE_QUIET_PERIOD = 0.4


@dataclass(frozen=True)
class CommandSpec:
    name: str
    group: str
    description: str
    confirmation: str = ""
    parameters: str = ""


COMMANDS = [
    CommandSpec("help", "Sistema", "Lista os comandos disponíveis."),
    CommandSpec("info", "Sistema", "Informações gerais do dispositivo."),
    CommandSpec("status", "Sistema", "Estado do Wi-Fi, NTP e memória."),
    CommandSpec("uptime", "Sistema", "Tempo desde a inicialização."),
    CommandSpec("reason", "Sistema", "Motivo do último reset."),
    CommandSpec("version", "Sistema", "Versão do firmware."),
    CommandSpec("build", "Sistema", "Data e hora da compilação."),
    CommandSpec("alive", "Sistema", "Verifica a resposta básica da rede."),
    CommandSpec("desliga", "Sistema", "Sono profundo; volta por RESET.", "Colocar o ESP32 em sono profundo?"),
    CommandSpec("reboot", "Sistema", "Reinicia o dispositivo.", "Confirma o reinício remoto?"),
    CommandSpec("temp", "Sistema", "Temperatura da CPU."),
    CommandSpec("cpu", "Sistema", "Modelo, revisão, núcleos e frequência da CPU."),
    CommandSpec("ram", "Sistema", "Uso e disponibilidade da RAM."),
    CommandSpec("flash", "Sistema", "Informações da memória flash."),
    CommandSpec("init", "Sistema", "Motivo do reset."),
    CommandSpec("heap", "Sistema", "Memória heap livre."),
    CommandSpec("heap_min", "Sistema", "Menor valor de heap livre desde o boot."),
    CommandSpec("chip_info", "Sistema", "Informações do chip e do SDK."),
    CommandSpec("flash_info", "Sistema", "Capacidade da flash e espaço OTA."),
    CommandSpec("health", "Sistema", "Executa o diagnóstico de saúde."),
    CommandSpec("selftest", "Sistema", "Executa os testes internos."),
    CommandSpec("reset_wifi", "Rede", "Apaga as credenciais Wi-Fi e reinicia.",
                "Apagar todas as redes Wi-Fi salvas e reiniciar?"),
    CommandSpec("net_info", "Rede", "IP, gateway, máscara, DNS e RSSI."),
    CommandSpec("mac", "Rede", "Endereço MAC do dispositivo."),
    CommandSpec("rssi", "Rede", "Intensidade do sinal Wi-Fi."),
    CommandSpec("ip", "Rede", "Endereço IP atual."),
    CommandSpec("ssid", "Rede", "SSID conectado."),
    CommandSpec("channel", "Rede", "Canal Wi-Fi atual."),
    CommandSpec("wifi_status", "Rede", "Resumo da conexão Wi-Fi."),
    CommandSpec("time", "Horário", "Hora local atual."),
    CommandSpec("date", "Horário", "Data local atual."),
    CommandSpec("ntp_status", "Horário", "Estado da sincronização NTP."),
    CommandSpec("set_fuso", "Horário", "Define o fuso UTC entre -12 e +14.",
                "Alterar e salvar o fuso horário do dispositivo?", "Fuso UTC"),
    CommandSpec("dst_on", "Horário", "Ativa horário de verão.",
                "Alterar a configuração de horário de verão?"),
    CommandSpec("dst_off", "Horário", "Desativa horário de verão.",
                "Alterar a configuração de horário de verão?"),
    CommandSpec("led_on", "LED", "Acende o LED."),
    CommandSpec("led_off", "LED", "Apaga o LED."),
    CommandSpec("led_breath", "LED", "Ativa o efeito de respiração do LED."),
    CommandSpec("led_pisca", "LED", "Pisca um número definido de vezes.",
                parameters="Pulsos / intervalo (ms)"),
    CommandSpec("led_blink", "LED", "Pisca continuamente.",
                parameters="Intervalo (ms)"),
    CommandSpec("sd_status", "SD", "Estado, tipo e capacidade do cartão."),
    CommandSpec("sd_list", "SD", "Lista arquivos (padrão: /).", parameters="Pasta (ex.: /)"),
    CommandSpec("sd_read", "SD", "Lê um arquivo (até 1000 bytes finais).", parameters="Arquivo (ex.: /log.txt)"),
    CommandSpec("sd_write", "SD", "Grava texto, substituindo o arquivo.",
                "Sobrescrever o arquivo?", "Arquivo:texto (ex.: /a.txt:ola)"),
    CommandSpec("sd_append", "SD", "Adiciona uma linha ao arquivo.", parameters="Arquivo:texto"),
    CommandSpec("sd_del", "SD", "Apaga um arquivo.", "Apagar o arquivo?", "Arquivo"),
    CommandSpec("sd_mkdir", "SD", "Cria uma pasta.", parameters="Pasta"),
    CommandSpec("sd_rmdir", "SD", "Remove uma pasta vazia.", "Remover a pasta?", "Pasta"),
    CommandSpec("sd_log", "SD", "Mostra o fim do log (/log.txt)."),
    CommandSpec("sd_clear_log", "SD", "Apaga o log.", "Apagar /log.txt?"),
    CommandSpec("sd_test", "SD", "Teste de escrita/leitura no cartão."),
    CommandSpec("clima", "Clima", "Últimos dados meteorológicos disponíveis."),
    CommandSpec("clima_age", "Clima", "Tempo desde a última atualização do clima."),
    CommandSpec("clima_sync", "Clima", "Solicita atualização imediata pela internet."),
    CommandSpec("scan", "Rede", "Varre as redes Wi-Fi visíveis (Central)."),
    CommandSpec("psram", "Sistema", "Uso da PSRAM (Central)."),
    CommandSpec("lastcmd", "Central", "Último comando processado pela Central."),
    CommandSpec("cmdcount", "Central", "Total de comandos processados pela Central."),
    CommandSpec("vago", "Central", "Slot de comando reservado da Central."),
    CommandSpec("set_escravo1", "Central", "Define o IP do escravo 1.",
                "Alterar o IP do escravo 1?", "IP (ex.: 192.168.0.50)"),
    CommandSpec("set_escravo2", "Central", "Define o IP do escravo 2.",
                "Alterar o IP do escravo 2?", "IP (ex.: 192.168.0.51)"),
    CommandSpec("set_escravo3", "Central", "Define o IP do escravo 3.",
                "Alterar o IP do escravo 3?", "IP (ex.: 192.168.0.52)"),
    CommandSpec("set_escravo4", "Central", "Define o IP do escravo 4.",
                "Alterar o IP do escravo 4?", "IP (ex.: 192.168.0.53)"),
    CommandSpec("desligar", "Central", "Desliga o display e entra em modo economia (Central).",
                "Desligar a Central?"),
]

COMMAND_BY_NAME = {spec.name: spec for spec in COMMANDS}
GROUPS = ("Sistema", "Rede", "Horário", "LED", "SD", "Clima", "Central")


def build_payload(
    spec: CommandSpec,
    timezone: str,
    pulse_count: str,
    pulse_interval: str,
    blink_interval: str,
    sd_arg: str = "",
) -> str:
    if spec.name.startswith("sd_") and spec.parameters:
        arg = sd_arg.strip()
        if not arg.startswith("/") or ".." in arg:
            raise ValueError("O argumento SD deve começar com / (ex.: /log.txt).")
        return f"{spec.name}:{arg}"

    if spec.name.startswith("set_escravo"):
        ip = sd_arg.strip()
        parts = ip.split(".")
        if len(parts) != 4 or not all(x.isdigit() and 0 <= int(x) <= 255 for x in parts):
            raise ValueError("Informe um IPv4 válido no campo Argumento (ex.: 192.168.0.50).")
        return f"{spec.name}:{ip}"

    if spec.name == "set_fuso":
        try:
            offset = int(timezone)
        except ValueError as exc:
            raise ValueError("O fuso deve ser um número inteiro entre -12 e +14.") from exc
        if not -12 <= offset <= 14:
            raise ValueError("O fuso deve estar entre -12 e +14.")
        return f"set_fuso:{offset}"

    if spec.name == "led_pisca":
        try:
            pulses = int(pulse_count)
            interval = int(pulse_interval)
        except ValueError as exc:
            raise ValueError("Pulsos e intervalo devem ser números inteiros.") from exc
        if not 1 <= pulses <= 100 or not 1 <= interval <= 5000:
            raise ValueError("Use de 1 a 100 pulsos e intervalo de 1 a 5000 ms.")
        return f"led_pisca:{pulses}:{interval}"

    if spec.name == "led_blink":
        try:
            interval = int(blink_interval)
        except ValueError as exc:
            raise ValueError("O intervalo deve ser um número inteiro.") from exc
        if not 50 <= interval <= 60000:
            raise ValueError("O intervalo deve estar entre 50 e 60000 ms.")
        return f"led_blink:{interval}"

    return spec.name


def exchange_udp(
    host: str,
    port: int,
    payload: str,
    timeout: float,
) -> str:
    """Envia um comando e junta as respostas UDP até um período sem novos dados."""
    response_parts: list[str] = []
    deadline = time.monotonic() + timeout

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        udp.settimeout(min(timeout, RESPONSE_QUIET_PERIOD))
        udp.sendto(payload.encode("utf-8"), (host, port))

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            udp.settimeout(min(remaining, RESPONSE_QUIET_PERIOD))
            try:
                data, _ = udp.recvfrom(65535)
            except socket.timeout:
                if response_parts:
                    combined = "".join(response_parts)
                    if payload != "clima_sync" or "Clima Atualizado ->" in combined or "Falha ao atualizar clima:" in combined:
                        break
                continue
            response_parts.append(data.decode("utf-8", errors="replace"))

    return "".join(response_parts)


def exchange_serial(device, payload: str, timeout: float) -> str:
    """Mantém a porta aberta e envia LF, conforme o receptor do firmware."""
    device.reset_input_buffer()
    packet = payload.encode("utf-8") + b"\n"
    if device.write(packet) != len(packet):
        raise OSError("Escrita serial incompleta.")
    parts = bytearray()
    deadline = time.monotonic() + timeout
    last_data = None
    echo = ("> " + payload + "\n").encode("utf-8")
    while time.monotonic() < deadline:
        chunk = device.read(max(1, min(device.in_waiting, 4096)))
        if chunk:
            parts.extend(chunk)
            last_data = time.monotonic()
        elif last_data is not None and time.monotonic() - last_data >= RESPONSE_QUIET_PERIOD:
            normalized = bytes(parts).replace(b"\r", b"")
            if payload == "clima_sync":
                complete = b"Clima Atualizado ->" in normalized or b"Falha ao atualizar clima:" in normalized
            else:
                complete = echo in normalized
            if complete:
                break
    return parts.decode("utf-8", errors="replace")


class CommandTester:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("ESP32 - Testador de comandos UDP / Serial")
        self.serial_connection = None
        self.serial_key = None
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.geometry("1000x700")
        self.root.minsize(820, 560)

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.selected_spec: CommandSpec | None = None

        self.transport_var = tk.StringVar(value="UDP")
        self.serial_port_var = tk.StringVar()
        self.baud_var = tk.StringVar(value="115200")
        self.host_var = tk.StringVar()
        self.port_var = tk.StringVar(value=str(DEFAULT_PORT))
        self.timeout_var = tk.StringVar(value=str(DEFAULT_TIMEOUT))
        self.search_var = tk.StringVar()
        self.command_var = tk.StringVar()
        self.timezone_var = tk.StringVar(value="-3")
        self.pulses_var = tk.StringVar(value="3")
        self.pulse_interval_var = tk.StringVar(value="250")
        self.blink_interval_var = tk.StringVar(value="500")
        self.sd_arg_var = tk.StringVar(value="/")
        self.status_var = tk.StringVar(value="Escolha UDP ou Serial e configure a conexão.")

        self._build_ui()
        self.search_var.trace_add("write", lambda *_: self._populate_commands())
        self._populate_commands()
        self.root.after(100, self._process_events)

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        connection = ttk.LabelFrame(self.root, text="Conexão UDP / Serial")
        connection.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        connection.columnconfigure(1, weight=1)
        ttk.Label(connection, text="IP / hostname:").grid(row=0, column=0, padx=6, pady=6)
        ttk.Entry(connection, textvariable=self.host_var).grid(
            row=0, column=1, sticky="ew", padx=6, pady=6
        )
        ttk.Label(connection, text="Porta:").grid(row=0, column=2, padx=6, pady=6)
        ttk.Entry(connection, textvariable=self.port_var, width=7).grid(
            row=0, column=3, padx=6, pady=6
        )
        ttk.Label(connection, text="Timeout (s):").grid(row=0, column=4, padx=6, pady=6)
        ttk.Entry(connection, textvariable=self.timeout_var, width=7).grid(
            row=0, column=5, padx=6, pady=6
        )

        ttk.Label(connection, text="Transporte:").grid(row=1, column=0, padx=6, pady=6)
        ttk.Combobox(connection, textvariable=self.transport_var, values=("UDP", "Serial"),
                     state="readonly", width=10).grid(row=1, column=1, sticky="w", padx=6)
        ttk.Label(connection, text="Porta serial:").grid(row=1, column=2, padx=6)
        self.serial_ports = ttk.Combobox(connection, textvariable=self.serial_port_var, width=18)
        self.serial_ports.grid(row=1, column=3, padx=6)
        ttk.Label(connection, text="Baud:").grid(row=1, column=4, padx=6)
        ttk.Entry(connection, textvariable=self.baud_var, width=8).grid(row=1, column=5, padx=6)
        ttk.Button(connection, text="Atualizar portas", command=self._refresh_ports).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=6, pady=4)
        ttk.Label(connection, text="Serial: feche o Monitor Serial da IDE. Instalação: python -m pip install pyserial").grid(
            row=2, column=2, columnspan=4, sticky="w", padx=6, pady=4)
        self._refresh_ports()

        body = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        body.grid(row=1, column=0, sticky="nsew", padx=10, pady=6)
        self.root.rowconfigure(1, weight=1)

        command_panel = ttk.LabelFrame(body, text="Comandos do firmware")
        details_panel = ttk.LabelFrame(body, text="Executar comando")
        body.add(command_panel, weight=1)
        body.add(details_panel, weight=2)
        command_panel.rowconfigure(1, weight=1)
        command_panel.columnconfigure(0, weight=1)
        details_panel.columnconfigure(1, weight=1)

        ttk.Entry(command_panel, textvariable=self.search_var).grid(
            row=0, column=0, sticky="ew", padx=6, pady=6
        )
        self.command_list = tk.Listbox(command_panel, exportselection=False)
        self.command_list.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        self.command_list.bind("<<ListboxSelect>>", self._select_command)

        self.description_label = ttk.Label(
            details_panel,
            text="Selecione um comando à esquerda ou envie um comando personalizado.",
            wraplength=440,
        )
        self.description_label.grid(
            row=0, column=0, columnspan=2, sticky="w", padx=8, pady=8
        )

        ttk.Label(details_panel, text="Fuso UTC:").grid(
            row=1, column=0, sticky="w", padx=8, pady=4
        )
        ttk.Entry(details_panel, textvariable=self.timezone_var, width=12).grid(
            row=1, column=1, sticky="w", padx=8, pady=4
        )
        ttk.Label(details_panel, text="Pulsos / intervalo (ms):").grid(
            row=2, column=0, sticky="w", padx=8, pady=4
        )
        pulse_frame = ttk.Frame(details_panel)
        pulse_frame.grid(row=2, column=1, sticky="w", padx=8, pady=4)
        ttk.Entry(pulse_frame, textvariable=self.pulses_var, width=6).pack(
            side=tk.LEFT
        )
        ttk.Label(pulse_frame, text=" / ").pack(side=tk.LEFT)
        ttk.Entry(pulse_frame, textvariable=self.pulse_interval_var, width=8).pack(
            side=tk.LEFT
        )
        ttk.Label(details_panel, text="Pisca contínuo (ms):").grid(
            row=3, column=0, sticky="w", padx=8, pady=4
        )
        ttk.Entry(details_panel, textvariable=self.blink_interval_var, width=12).grid(
            row=3, column=1, sticky="w", padx=8, pady=4
        )

        ttk.Label(details_panel, text="Argumento (SD / IP):").grid(
            row=4, column=0, sticky="w", padx=8, pady=4
        )
        ttk.Entry(details_panel, textvariable=self.sd_arg_var).grid(
            row=4, column=1, sticky="ew", padx=8, pady=4
        )

        ttk.Label(details_panel, text="Comando personalizado:").grid(
            row=5, column=0, sticky="w", padx=8, pady=(10, 4)
        )
        ttk.Entry(details_panel, textvariable=self.command_var).grid(
            row=5, column=1, sticky="ew", padx=8, pady=(10, 4)
        )

        buttons = ttk.Frame(details_panel)
        buttons.grid(row=6, column=0, columnspan=2, sticky="ew", padx=8, pady=8)
        self.send_button = ttk.Button(buttons, text="Enviar selecionado", command=self._send_selected)
        self.send_button.pack(side=tk.LEFT, padx=(0, 6))
        self.raw_button = ttk.Button(buttons, text="Enviar personalizado", command=self._send_custom)
        self.raw_button.pack(side=tk.LEFT, padx=6)
        self.all_button = ttk.Button(
            buttons, text="Testar comandos seguros", command=self._run_all
        )
        self.all_button.pack(side=tk.LEFT, padx=6)

        ttk.Label(
            details_panel,
            text="Comandos que reiniciam ou alteram configurações pedem confirmação individual.",
        ).grid(row=7, column=0, columnspan=2, sticky="w", padx=8, pady=4)

        output_frame = ttk.LabelFrame(self.root, text="Respostas do dispositivo")
        output_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=6)
        output_frame.rowconfigure(0, weight=1)
        output_frame.columnconfigure(0, weight=1)
        self.output = tk.Text(output_frame, wrap=tk.WORD, state=tk.DISABLED, height=12)
        self.output.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        scrollbar = ttk.Scrollbar(output_frame, command=self.output.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=6)
        self.output.configure(yscrollcommand=scrollbar.set)

        ttk.Label(self.root, textvariable=self.status_var, anchor=tk.W).grid(
            row=3, column=0, sticky="ew", padx=12, pady=(0, 8)
        )

    def _populate_commands(self) -> None:
        search = self.search_var.get().strip().lower()
        self.command_list.delete(0, tk.END)
        self.visible_commands = [
            command
            for command in COMMANDS
            if search in command.name.lower()
            or search in command.group.lower()
            or search in command.description.lower()
        ]
        for command in self.visible_commands:
            marker = "  [confirmação]" if command.confirmation else ""
            self.command_list.insert(
                tk.END,
                f"{command.group}  |  {command.name}{marker}",
            )

    def _select_command(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        selection = self.command_list.curselection()
        if not selection:
            return
        self.selected_spec = self.visible_commands[selection[0]]
        self.command_var.set("")
        self.description_label.configure(
            text=f"{self.selected_spec.name}: {self.selected_spec.description}"
        )

    def _refresh_ports(self) -> None:
        ports = [p.device for p in list_ports.comports()] if list_ports else []
        self.serial_ports.configure(values=ports)
        if ports and not self.serial_port_var.get():
            self.serial_port_var.set(ports[0])

    def _close(self) -> None:
        if self.worker and self.worker.is_alive():
            self.status_var.set("Aguardando a operação terminar para fechar...")
            self.root.after(100, self._close)
            return
        if self.serial_connection is not None:
            self.serial_connection.close()
        self.root.destroy()

    def _connection_values(self) -> tuple[str, str, int, float]:
        mode = self.transport_var.get()
        try:
            timeout = float(self.timeout_var.get())
        except ValueError as exc:
            raise ValueError("Timeout deve ser numérico.") from exc
        if not 0.2 <= timeout <= 120:
            raise ValueError("O timeout deve estar entre 0,2 e 120 segundos.")
        if mode == "Serial":
            if serial is None:
                raise ValueError("Instale a dependência: python -m pip install pyserial")
            host = self.serial_port_var.get().strip()
            if not host:
                raise ValueError("Selecione ou digite a porta serial (ex.: COM5).")
            try:
                port = int(self.baud_var.get())
            except ValueError as exc:
                raise ValueError("Baud deve ser um número inteiro.") from exc
            if not 1 <= port <= 4000000:
                raise ValueError("Baud deve estar entre 1 e 4000000.")
        else:
            host = self.host_var.get().strip()
            if not host:
                raise ValueError("Informe o IP ou hostname do ESP32.")
            try:
                port = int(self.port_var.get())
            except ValueError as exc:
                raise ValueError("Porta UDP deve ser numérica.") from exc
            if not 1 <= port <= 65535:
                raise ValueError("A porta deve estar entre 1 e 65535.")
        return mode, host, port, timeout

    def _exchange(self, connection: tuple[str, str, int, float], payload: str) -> str:
        mode, host, port, timeout = connection
        if payload == "clima_sync":
            timeout = max(timeout, 35.0)
        if mode == "UDP":
            return exchange_udp(host, port, payload, timeout)
        data = payload.encode("utf-8")
        if b"\r" in data or b"\n" in data or len(data) > 256:
            raise ValueError("Serial aceita uma linha de até 256 bytes por comando.")
        key = (host, port)
        if self.serial_connection is None or self.serial_key != key or not self.serial_connection.is_open:
            if self.serial_connection is not None:
                self.serial_connection.close()
            device = serial.Serial(port=None, baudrate=port, timeout=0.05, write_timeout=2)
            # Evita solicitar reset por DTR/RTS ao abrir a porta.
            device.dtr = False
            device.rts = False
            device.port = host
            device.open()
            self.serial_connection = device
            self.serial_key = key
        try:
            return exchange_serial(self.serial_connection, payload, timeout)
        except OSError:
            self.serial_connection.close()
            self.serial_connection = None
            self.serial_key = None
            raise

    def _command_payload(self, spec: CommandSpec) -> str:
        return build_payload(
            spec,
            self.timezone_var.get().strip(),
            self.pulses_var.get().strip(),
            self.pulse_interval_var.get().strip(),
            self.blink_interval_var.get().strip(),
            self.sd_arg_var.get(),
        )

    def _confirm(self, spec: CommandSpec) -> bool:
        if not spec.confirmation:
            return True
        return messagebox.askyesno(
            "Confirmar comando",
            f"{spec.confirmation}\n\nComando: {spec.name}",
            parent=self.root,
        )

    def _send_selected(self) -> None:
        if not self.selected_spec:
            messagebox.showinfo("Comando", "Selecione um comando na lista.")
            return
        spec = self.selected_spec
        if not self._confirm(spec):
            return
        try:
            payload = self._command_payload(spec)
            connection = self._connection_values()
        except ValueError as exc:
            messagebox.showerror("Dados inválidos", str(exc))
            return
        self._start_worker(
            lambda: self._send_one(connection, spec, payload)
        )

    def _send_custom(self) -> None:
        payload = self.command_var.get().strip()
        if not payload:
            messagebox.showinfo("Comando personalizado", "Digite o comando.")
            return
        command_name = payload.partition(":")[0]
        spec = COMMAND_BY_NAME.get(command_name)
        if spec and not self._confirm(spec):
            return
        try:
            connection = self._connection_values()
        except ValueError as exc:
            messagebox.showerror("Dados inválidos", str(exc))
            return
        self._start_worker(lambda: self._send_one(connection, None, payload))

    def _send_one(
        self,
        connection: tuple[str, str, int, float],
        spec: CommandSpec | None,
        payload: str,
    ) -> None:
        mode, host, port, timeout = connection
        self.events.put(("status", f"Enviando {payload} via {mode} para {host}:{port}..."))
        self.events.put(("log", f">>> {payload}"))
        try:
            response = self._exchange(connection, payload)
        except (OSError, ValueError) as exc:
            self.events.put(("log", f"ERRO de comunicação: {exc}"))
            self.events.put(("status", "Falha na comunicação. Na serial, verifique a porta e feche outros monitores."))
            return

        if response:
            self.events.put(("log", response.rstrip()))
            self.events.put(("status", f"Resposta recebida para {payload}."))
        else:
            self.events.put(("log", f"TIMEOUT: sem resposta para {payload}."))
            self.events.put(("status", f"Sem resposta para {payload}."))

    def _run_all(self) -> None:
        try:
            connection = self._connection_values()
            payloads = [
                (spec, self._command_payload(spec))
                for spec in COMMANDS
                if not spec.confirmation
            ]
        except ValueError as exc:
            messagebox.showerror("Dados inválidos", str(exc))
            return
        self._start_worker(lambda: self._send_batch(connection, payloads))

    def _send_batch(
        self,
        connection: tuple[str, str, int, float],
        payloads: list[tuple[CommandSpec, str]],
    ) -> None:
        mode, host, port, timeout = connection
        skipped = len(COMMANDS) - len(payloads)
        self.events.put(("status", f"Executando {len(payloads)} comandos seguros; "
                                   f"{skipped} protegidos por confirmação serão ignorados."))
        self.events.put(("log", f"=== LOTE: {len(payloads)} comandos ==="))

        for index, (spec, payload) in enumerate(payloads, start=1):
            self.events.put(("status", f"[{index}/{len(payloads)}] {payload}"))
            self.events.put(("log", f"\n>>> [{index}/{len(payloads)}] {payload}"))
            try:
                response = self._exchange(connection, payload)
            except (OSError, ValueError) as exc:
                self.events.put(("log", f"ERRO de comunicação: {exc}"))
                break

            if response:
                self.events.put(("log", response.rstrip()))
            else:
                self.events.put(("log", "TIMEOUT: sem resposta."))

            time.sleep(0.15)

        self.events.put(("status", "Lote de comandos concluído."))

    def _start_worker(self, operation: Callable[[], None]) -> None:
        if self.worker and self.worker.is_alive():
            self.status_var.set("Aguarde o comando atual terminar.")
            return

        self._set_buttons_enabled(False)
        self.worker = threading.Thread(target=operation, daemon=True)
        self.worker.start()

    def _set_buttons_enabled(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        self.send_button.configure(state=state)
        self.raw_button.configure(state=state)
        self.all_button.configure(state=state)

    def _process_events(self) -> None:
        while True:
            try:
                event, value = self.events.get_nowait()
            except queue.Empty:
                break

            if event == "status":
                self.status_var.set(str(value))
            elif event == "log":
                self.output.configure(state=tk.NORMAL)
                self.output.insert(tk.END, f"{value}\n")
                self.output.see(tk.END)
                self.output.configure(state=tk.DISABLED)

        if self.worker and not self.worker.is_alive():
            self._set_buttons_enabled(True)
        self.root.after(100, self._process_events)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list",
        action="store_true",
        help="lista os comandos reconhecidos pelo firmware atual e encerra",
    )
    args = parser.parse_args()

    if args.list:
        for command in COMMANDS:
            suffix = " [confirmacao]" if command.confirmation else ""
            print(f"{command.group:10} {command.name}{suffix}")
        return

    root = tk.Tk()
    CommandTester(root)
    root.mainloop()


if __name__ == "__main__":
    main()
