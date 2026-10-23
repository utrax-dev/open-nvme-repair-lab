"""Pure guards for two exact factory-followup command frames.

These guards bound an experiment; they do not establish command semantics,
read-only behavior, setting persistence, or a performance-unlock mechanism.
The separate factory replay has no caller-supplied parameter values.
"""
import struct

FACTORY_PREFIX = bytes.fromhex(
    '00010500020001010c01020502011e02021903011e030219'
    '04012904021cff3819ff401cff4820ff5023')


def validate_evidence(table, enabled, firmware, effects):
    if (len(table) != 300 or table[:42] != FACTORY_PREFIX or
            enabled != b'\x01' or firmware != '19062091e48a'):
        raise ValueError('Reviewed original-controller table evidence required')
    if len(effects) != 1024:
        raise ValueError('A complete live Admin Command Effects table is required')
    for opcode in (0xFD, 0xFE):
        if struct.unpack_from('<I', effects, opcode * 4)[0] != 1:
            raise ValueError('Live vendor-command support differs from reviewed evidence')


def followup_frame(parameter, cid):
    if type(parameter) is not int or parameter not in (1, 2):
        raise ValueError('Only the two observed factory parameters are permitted')
    if type(cid) is not int or not 0xF001 <= cid <= 0xFFFF:
        raise ValueError('Invalid diagnostic command identifier')
    words = [0] * 16
    words[0] = 0xFE | (cid << 16)
    words[10] = parameter
    return struct.pack('<16I', *words)


class ProbeSequence:
    def __init__(self):
        self.next_parameter = 1

    def take(self, parameter, cid):
        frame = followup_frame(parameter, cid)
        if parameter != self.next_parameter:
            raise ValueError('Repeated, exhausted or out-of-order vendor probe')
        self.next_parameter += 1  # Consume before any hardware submission.
        return frame


class FactoryProfile4Replay:
    """One exact four-frame sequence from the original enabled factory table."""
    def __init__(self):
        self.next_index = 0

    def take(self, index, cid):
        if type(index) is not int or index != self.next_index or not 0 <= index < 4:
            raise ValueError('Repeated, exhausted or out-of-order factory replay')
        if type(cid) is not int or not 0xF001 <= cid <= 0xFFFF:
            raise ValueError('Invalid diagnostic command identifier')
        opcode, parameter, value = (
            (0xFD, 1, 0x29), (0xFE, 1, 0),
            (0xFD, 2, 0x1C), (0xFE, 2, 0))[index]
        words = [0] * 16
        words[0] = opcode | (cid << 16)
        words[10] = parameter
        words[11] = value
        self.next_index += 1
        return struct.pack('<16I', *words)


def verify_profile4_readback(rows):
    expected = [
        {'opcode': '0xfd', 'parameter': 1, 'value': 41, 'completion_dword0': 0},
        {'opcode': '0xfe', 'parameter': 1, 'value': 0, 'completion_dword0': 41},
        {'opcode': '0xfd', 'parameter': 2, 'value': 28, 'completion_dword0': 0},
        {'opcode': '0xfe', 'parameter': 2, 'value': 0, 'completion_dword0': 28}]
    if rows != expected:
        raise ValueError('Exact factory sequence and written-value readbacks required')


def completion_result(cqe, cid, phase):
    if len(cqe) != 16:
        raise ValueError('Incomplete NVMe completion')
    result, reserved, sqhead, sqid, actual_cid, status = struct.unpack('<IIHHHH', cqe)
    if (reserved != 0 or sqhead >= 4 or sqid != 0 or actual_cid != cid or
            status & 1 != phase or status >> 1 != 0):
        raise ValueError('NVMe completion identity, phase or status did not verify')
    return result


def standard_read_frame(opcode, cdw10, size, cid):
    if (opcode, cdw10, size) not in (
            (2, 0x00FF0005, 1024), (2, 0x007F0002, 512), (0x0A, 2, 0)):
        raise ValueError('Standard command is outside the fixed read allowlist')
    if type(cid) is not int or not 0xF001 <= cid <= 0xFFFF:
        raise ValueError('Invalid diagnostic command identifier')
    words = [0] * 16
    words[0] = opcode | (cid << 16)
    words[1] = 0xFFFFFFFF if opcode == 2 and cdw10 == 0x007F0002 else 0
    words[6] = 0x200400 if size else 0
    words[10] = cdw10
    return struct.pack('<16I', *words)
