import importlib.util
import pathlib
import struct
import unittest
import ast
import json


class VendorProbeSafety(unittest.TestCase):
    def module(self):
        spec = importlib.util.spec_from_file_location(
            'vendor_profile_probe_safety',
            pathlib.Path(__file__).with_name('vendor_profile_probe_safety.py'))
        self.assertIsNotNone(spec)
        self.assertTrue(pathlib.Path(spec.origin).exists(),
                        'The bounded vendor probe safety implementation is missing')
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_only_exact_factory_followup_frames_are_built(self):
        mod = self.module()
        for index, parameter in enumerate((1, 2)):
            frame = mod.followup_frame(parameter, 0xF001 + index)
            words = struct.unpack('<16I', frame)
            expected = [0] * 16
            expected[0] = 0xFE | ((0xF001 + index) << 16)
            expected[10] = parameter
            self.assertEqual(tuple(expected), words)
        for value in (-1, 0, 3, 0xFFFFFFFF, True, 1.0, '1'):
            with self.assertRaises(ValueError):
                mod.followup_frame(value, 0xF001)

    def test_repetition_and_out_of_order_commands_fail_closed(self):
        mod = self.module()
        probe = mod.ProbeSequence()
        with self.assertRaises(ValueError):
            probe.take(2, 0xF001)
        probe.take(1, 0xF001)
        with self.assertRaises(ValueError):
            probe.take(1, 0xF002)
        probe.take(2, 0xF002)
        with self.assertRaises(ValueError):
            probe.take(2, 0xF003)

    def test_frames_require_exact_source_evidence_and_supported_opcodes(self):
        mod = self.module()
        table = bytes.fromhex(
            '00010500020001010c01020502011e02021903011e030219'
            '04012904021cff3819ff401cff4820ff5023') + bytes(258)
        log = bytearray(1024)
        struct.pack_into('<I', log, 0xFD * 4, 1)
        struct.pack_into('<I', log, 0xFE * 4, 1)
        mod.validate_evidence(table, b'\x01', '19062091e48a', bytes(log))
        for bad_table, flag, firmware, effects in (
            (table[:41], b'\x01', '19062091e48a', bytes(log)),
            (bytes(300), b'\x01', '19062091e48a', bytes(log)),
            (table, b'\x00', '19062091e48a', bytes(log)),
            (table, b'\x01', 'different', bytes(log)),
            (table, b'\x01', '19062091e48a', bytes(1024)),
            (table, b'\x01', '19062091e48a', bytes(log[:512])),
        ):
            with self.assertRaises(ValueError):
                mod.validate_evidence(bad_table, flag, firmware, effects)

    def test_invalid_completion_is_not_interpreted(self):
        mod = self.module()
        good = struct.pack('<IIHHHH', 41, 0, 1, 0, 0xF001, 1)
        self.assertEqual(41, mod.completion_result(good, 0xF001, 1))
        for bad in (
            good[:15], struct.pack('<IIHHHH', 41, 0, 1, 1, 0xF001, 1),
            struct.pack('<IIHHHH', 41, 0, 1, 0, 0xF002, 1),
            struct.pack('<IIHHHH', 41, 0, 1, 0, 0xF001, 0),
            struct.pack('<IIHHHH', 41, 0, 1, 0, 0xF001, 3),
        ):
            with self.assertRaises(ValueError):
                mod.completion_result(bad, 0xF001, 1)

    def test_standard_reads_cannot_become_writes_or_arbitrary_commands(self):
        mod = self.module()
        self.assertTrue(hasattr(mod, 'standard_read_frame'),
                        'The standard read allowlist is missing')
        for opcode, cdw10, size in ((2, 0x00FF0005, 1024),
                                   (2, 0x007F0002, 512),
                                   (0x0A, 2, 0)):
            frame = mod.standard_read_frame(opcode, cdw10, size, 0xF001)
            words = struct.unpack('<16I', frame)
            self.assertEqual(words[0], opcode | (0xF001 << 16))
            self.assertEqual(words[6], 0x200400 if size else 0)
            self.assertEqual(words[10], cdw10)
            self.assertTrue(all(words[i] == 0 for i in (2, 3, 4, 5, 7, 8, 9, 11, 12, 13, 14, 15)))
        for opcode, cdw10, size in ((0xFD, 1, 0), (0xFE, 1, 0),
                                   (0x81, 0, 512), (0x09, 2, 0),
                                   (0x10, 0, 0), (0x80, 0, 0),
                                   (0x84, 2, 0), (2, 0x007F0005, 512),
                                   (2, 0x00FF0005, 512)):
            with self.assertRaises(ValueError):
                mod.standard_read_frame(opcode, cdw10, size, 0xF001)

    def test_factory_replay_is_exact_and_cannot_repeat_or_select_other_values(self):
        mod = self.module()
        self.assertTrue(hasattr(mod, 'FactoryProfile4Replay'),
                        'The exact original profile replay guard is missing')
        replay = mod.FactoryProfile4Replay()
        with self.assertRaises(ValueError):
            replay.take(1, 0xF001)
        expected = ((0xFD, 1, 0x29), (0xFE, 1, 0),
                    (0xFD, 2, 0x1C), (0xFE, 2, 0))
        for index, (opcode, parameter, value) in enumerate(expected):
            frame = replay.take(index, 0xF001 + index)
            words = struct.unpack('<16I', frame)
            wanted = [0] * 16
            wanted[0] = opcode | ((0xF001 + index) << 16)
            wanted[10] = parameter
            wanted[11] = value
            self.assertEqual(tuple(wanted), words)
            with self.assertRaises(ValueError):
                replay.take(index, 0xF010 + index)
        with self.assertRaises(ValueError):
            replay.take(4, 0xF010)

    def test_reset_experiment_writes_and_verifies_before_second_reset(self):
        mod = self.module()
        source = pathlib.Path(__file__).with_name('ugreen_vendor_followup_probe.py').read_text()
        tree = ast.parse(source)
        flow = next(node for node in tree.body if isinstance(node, ast.Try))
        start = next(i for i, node in enumerate(flow.body)
                     if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                     and isinstance(node.value.func, ast.Name)
                     and node.value.func.id == 'rebuild_diagnostic_queue')
        events = []
        settings = {1: 0, 2: 0}
        printed = []
        def rebuild():
            events.append('reset')
            settings.update({1: 0, 2: 0})
        def submit(frame):
            words = struct.unpack('<16I', frame)
            opcode = words[0] & 255
            parameter = words[10]
            events.append((opcode, parameter, words[11]))
            if opcode == 0xFD:
                settings[parameter] = words[11]
            return (settings[parameter] if opcode == 0xFE else 0), b''
        effects = bytearray(1024)
        for opcode in (0xFD, 0xFE):
            struct.pack_into('<I', effects, opcode * 4, 1)
        scope = dict(rebuild_diagnostic_queue=rebuild, standard_read=lambda *args: (0, bytes(effects)),
                     validate_evidence=mod.validate_evidence, table=mod.FACTORY_PREFIX + bytes(258),
                     flag=b'\x01', evidence={'original_bridge_firmware': '19062091e48a'},
                     health=lambda: None, reset_persistence_requested=True,
                     ProbeSequence=mod.ProbeSequence, sequence=mod.FactoryProfile4Replay(),
                     command_id=0xF003, submit=submit, struct=struct,
                     replay_requested=True, json=json, print=lambda value, **kwargs: printed.append(value),
                     verify_profile4_readback=getattr(mod, 'verify_profile4_readback', lambda value: None))
        exec(compile(ast.Module(body=flow.body[start:], type_ignores=[]), 'reset experiment flow', 'exec'), scope)
        self.assertEqual(events, ['reset', (0xFD, 1, 0x29), (0xFE, 1, 0),
                                 (0xFD, 2, 0x1C), (0xFE, 2, 0),
                                 'reset', (0xFE, 1, 0), (0xFE, 2, 0)])
        readback = next(json.loads(x) for x in printed if x.startswith('{"after_controller_reset"'))
        self.assertFalse(readback['physical_usb_reconnect_between_write_and_readback'])
        self.assertEqual([x['completion_dword0'] for x in readback['after_controller_reset']], [0, 0])

    def test_factory_values_must_read_back_before_claiming_verified(self):
        mod = self.module()
        self.assertTrue(hasattr(mod, 'verify_profile4_readback'), 'Factory readback guard missing')
        rows = [{'opcode': '0xfd', 'parameter': 1, 'value': 41, 'completion_dword0': 0},
                {'opcode': '0xfe', 'parameter': 1, 'value': 0, 'completion_dword0': 41},
                {'opcode': '0xfd', 'parameter': 2, 'value': 28, 'completion_dword0': 0},
                {'opcode': '0xfe', 'parameter': 2, 'value': 0, 'completion_dword0': 28}]
        mod.verify_profile4_readback(rows)
        for bad in (rows[:3], rows[::-1], [*rows[:1], {**rows[1], 'completion_dword0': 0}, *rows[2:]],
                    [*rows[:3], {**rows[3], 'completion_dword0': 0}]):
            with self.assertRaises(ValueError):
                mod.verify_profile4_readback(bad)


if __name__ == '__main__':
    unittest.main()
