import queue
import unittest
from unittest.mock import Mock, patch

import testador_comandos as tester


class BluetoothTests(unittest.TestCase):
    def setUp(self):
        self.app = tester.CommandTester.__new__(tester.CommandTester)
        self.app.serial_connection = None
        self.app.serial_key = None

    def test_bluetooth_uses_persistent_serial_without_echo(self):
        device = Mock(is_open=True)
        with patch.object(tester, "serial") as serial_module, patch.object(
            tester, "exchange_serial", return_value="OK"
        ) as exchange:
            serial_module.Serial.return_value = device
            connection = ("Bluetooth", "COM8", 115200, 3.0)
            self.assertEqual(self.app._exchange(connection, "info"), "OK")
            self.app._exchange(connection, "reason")
            serial_module.Serial.assert_called_once()
            device.open.assert_called_once()
            self.assertFalse(device.dtr)
            self.assertFalse(device.rts)
            exchange.assert_called_with(device, "reason", 3.0, require_echo=False)
            self.app._disconnect_serial()
            device.close.assert_called_once()
            self.assertIsNone(self.app.serial_connection)

    def test_bluetooth_byte_limit(self):
        with patch.object(self.app, "_open_serial"), patch.object(
            tester, "exchange_serial", return_value="OK"
        ):
            connection = ("Bluetooth", "COM8", 115200, 3.0)
            self.assertEqual(self.app._exchange(connection, "x" * 255), "OK")
            for payload in ("x" * 256, "ç" * 128, "info\nreboot", ""):
                with self.subTest(payload=payload):
                    with self.assertRaises(ValueError):
                        self.app._exchange(connection, payload)

    def test_usb_still_requires_echo_and_udp_stays_udp(self):
        with patch.object(self.app, "_open_serial"), patch.object(
            tester, "exchange_serial", return_value="USB"
        ) as serial_exchange, patch.object(tester, "exchange_udp", return_value="UDP") as udp:
            self.assertEqual(self.app._exchange(("Serial", "COM5", 115200, 3.0), "info"), "USB")
            serial_exchange.assert_called_once_with(None, "info", 3.0, require_echo=True)
            self.assertEqual(self.app._exchange(("UDP", "192.168.1.2", 4210, 3.0), "info"), "UDP")
            udp.assert_called_once_with("192.168.1.2", 4210, "info", 3.0)

    def test_help_parser_loads_device_specific_commands_and_parameters(self):
        help_text = (
            "COMANDOS ESP32-C6\n"
            "[SISTEMA]\n"
            "help\ninfo\nstatus\n"
            "[REDE]\n"
            "wifi_add:SSID:senha\nwifi_list\n"
            "[HORARIO]\n"
            "set_time:AAAA-MM-DD HH:MM:SS\n"
            "[TELA]\n"
            "tela:0..9\n"
            "[LED]\n"
            "led_rgb:R:G:B (0..255)\n"
        )

        specs = {spec.name: spec for spec in tester.parse_device_commands(help_text)}

        self.assertTrue(
            {"help", "wifi_add", "wifi_list", "set_time", "tela", "led_rgb"} <= specs.keys()
        )
        self.assertIn("Argumento", specs["tela"].parameters)
        self.assertEqual(
            specs["set_time"].parameters,
            "Argumento (AAAA-MM-DD HH:MM:SS)",
        )
        self.assertTrue(specs["set_time"].confirmation)
        self.assertEqual(
            tester.build_payload(specs["led_rgb"], "-3", "3", "250", "500", "255:0:64"),
            "led_rgb:255:0:64",
        )
        with self.assertRaisesRegex(ValueError, "argumento"):
            tester.build_payload(specs["tela"], "-3", "3", "250", "500")

    def test_help_parser_handles_categorized_device_help(self):
        help_text = (
            "-> Sistema: help, info, status, version, alive, uptime, reboot\n"
            "-> Hardware: temp, cpu, chip_info, ram, heap, heap_min, flash\n"
            "-> Rede: net_info, wifi_status, ssid, mac, rssi, ip\n"
            "         wifi_add:SSID|SENHA | wifi_clear | wifi_clear:SSID\n"
            "-> Hora: time, date, ntp_status, set_fuso:N, dst_on, dst_off, dst_status\n"
            "-> Clima: clima, clima_sync\n"
        )

        names = {spec.name for spec in tester.parse_device_commands(help_text)}

        self.assertTrue(
            {"help", "wifi_add", "wifi_clear", "set_fuso", "dst_status", "clima_sync"}
            <= names
        )
        self.assertNotIn("sistema", names)
        self.assertNotIn("hardware", names)

    def test_help_parser_handles_central_command_range_and_identity(self):
        help_text = (
            "===== COMANDOS ACEITOS =====\n"
            "--- CONFIGURACOES ---\n"
            "set_escravo[1-4]:[IP]\n"
            "--- SD CARD ---\n"
            "sd_list[:/pasta] / sd_read:/arq\n"
        )
        names = {spec.name for spec in tester.parse_device_commands(help_text)}

        self.assertTrue({f"set_escravo{index}" for index in range(1, 5)} <= names)
        self.assertTrue({"sd_list", "sd_read"} <= names)
        self.assertFalse({"configuracoes", "card", "sd"} & names)
        self.assertEqual(tester.parse_device_commands("> help\n"), [])

    def test_help_parser_ignores_documentation_and_argument_notes(self):
        help_text = (
            "Comandos Disponiveis:\n"
            "INFO / STATUS / VERSION / BUILD / REASON\n"
            "OTA: pagina /ota ou Arduino IDE pela rede (sem senha)\n"
            "LED_ON / LED_OFF / SET_RGB:R,G,B\n"
            "IR_TX - Pulso infravermelho\n"
            "P = pulsos; I = intervalo em ms\n"
            "X = fuso UTC (ex.: -3)\n"
        )

        names = {spec.name for spec in tester.parse_device_commands(help_text)}

        self.assertTrue({"info", "status", "set_rgb", "ir_tx"} <= names)
        self.assertFalse({"ota", "p", "x", "ms"} & names)

    def test_device_discovery_loads_commands_from_identified_firmware(self):
        self.app.events = queue.Queue()
        connection = ("UDP", "192.168.1.20", 4210, 3.0)
        responses = {
            "name": "M5NanoC6\n",
            "help": "help\ninfo\nset_rgb:R,G,B\n",
        }
        with patch.object(
            self.app,
            "_exchange",
            side_effect=lambda _connection, command: responses[command],
        ) as exchange:
            self.app._discover_device(connection)

        event, (identity, commands) = self.app.events.get_nowait()
        self.assertEqual(event, "commands")
        self.assertEqual(identity, "M5NanoC6")
        self.assertIn("set_rgb", {spec.name for spec in commands})
        self.assertEqual(
            [call.args[1] for call in exchange.call_args_list],
            ["name", "help"],
        )

    def test_name_response_parsing_skips_serial_framing(self):
        self.assertEqual(
            tester.parse_device_identity(
                "> name\n[RESPOSTA]\nESP32_Central\n[FIM RESPOSTA]\n"
            ),
            "ESP32_Central",
        )

    def test_device_discovery_fails_when_name_is_not_supported(self):
        self.app.events = queue.Queue()
        with patch.object(
            self.app,
            "_exchange",
            side_effect=["Comando 'name' nao reconhecido\n"],
        ):
            self.app._discover_device(("UDP", "192.168.1.20", 4210, 3.0))

        event, value = self.app.events.get_nowait()
        self.assertEqual((event, value), ("identify_failed", None))
        with self.assertRaises(ValueError):
            tester.parse_device_identity("Comando 'name' nao reconhecido\n")

    def test_central_identification_uses_local_commands_when_help_is_broken(self):
        self.app.events = queue.Queue()
        responses = {
            "name": "ESP32_Central\n",
            "help": "Central Local:\nComando desconhecido.\n",
        }
        with patch.object(
            self.app,
            "_exchange",
            side_effect=lambda _connection, command: responses[command],
        ) as exchange:
            self.app._discover_device(("UDP", "192.168.1.20", 4210, 3.0))

        events = [self.app.events.get_nowait() for _ in range(4)]
        self.assertEqual(events[0][0], "log")
        self.assertIn("AVISO:", events[0][1])
        event, (identity, commands) = events[1]
        self.assertEqual(event, "commands")
        self.assertEqual(identity, "ESP32_Central")
        names = {spec.name for spec in commands}
        self.assertTrue({"name", "sd_remount", "set_escravo4"} <= names)
        self.assertNotIn("desconhecido", names)
        self.assertEqual(
            [call.args[1] for call in exchange.call_args_list],
            ["name", "help"],
        )

    def test_custom_command_uses_identified_device_confirmation(self):
        spec = tester.CommandSpec(
            "wifi_clear",
            "Firmware",
            "Apaga redes Wi-Fi.",
            "Apagar as redes Wi-Fi salvas?",
        )
        self.app.available_commands = [spec]
        self.app.command_var = Mock(get=Mock(return_value="WIFI_CLEAR"))
        with patch.object(self.app, "_confirm", return_value=False) as confirm, patch.object(
            self.app, "_start_worker"
        ) as start_worker:
            self.app._send_custom()

        confirm.assert_called_once_with(spec)
        start_worker.assert_not_called()

    def test_read_without_echo_collects_chunks_and_stops_after_quiet(self):
        device = Mock()
        device.in_waiting = 0
        device.write.return_value = 5
        device.read.side_effect = [b"primeira\r\n", b"segunda\r\n"] + [b""] * 100
        ticks = iter(i * 0.1 for i in range(200))
        with patch.object(tester.time, "monotonic", side_effect=lambda: next(ticks)):
            result = tester.exchange_serial(device, "info", 10.0, require_echo=False)
        self.assertEqual(result, "primeira\r\nsegunda\r\n")
        self.assertLess(device.read.call_count, 15)
        device.write.assert_called_once_with(b"info\n")

    def test_read_clima_waits_for_final_response(self):
        device = Mock()
        device.in_waiting = 0
        device.write.return_value = 11
        device.read.side_effect = [b"Atualizando...\n"] + [b""] * 4 + [
            b"Clima Atualizado -> OK\n"
        ] + [b""] * 100
        ticks = iter(i * 0.1 for i in range(200))
        with patch.object(tester.time, "monotonic", side_effect=lambda: next(ticks)):
            result = tester.exchange_serial(device, "clima_sync", 10.0, require_echo=False)
        self.assertIn("Clima Atualizado -> OK", result)

    def test_communication_failure_releases_port(self):
        self.app.serial_connection = Mock(is_open=True)
        self.app.serial_key = ("COM8", 115200)
        device = self.app.serial_connection
        with patch.object(tester, "serial"), patch.object(
            tester, "exchange_serial", side_effect=OSError("Disconnected")
        ):
            with self.assertRaises(OSError):
                self.app._exchange(("Bluetooth", "COM8", 115200, 3.0), "info")
        device.close.assert_called_once()
        self.assertIsNone(self.app.serial_key)


if __name__ == "__main__":
    unittest.main()
