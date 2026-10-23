import struct
import pathlib
import ast
import unittest
import tcg_ro as t
import ssd_reset_format as fmt
import reset_safety as safety
import extract_firmware_challenge as extract
import tempfile
import json

class CodecTests(unittest.TestCase):
    def test_private_scripts_compile_without_opening_a_device(self):
        base=pathlib.Path(__file__).parent
        for name in ('tcg_ro.py','reset_safety.py','ssd_reset_format.py','ugreen_tcg_session_probe.py','extract_firmware_challenge.py'):
            compile((base/name).read_text(),str(base/name),'exec')

    def test_extractor_rejects_unknown_images_and_never_overwrites_a_secret(self):
        for code in (b'',b'\0'*extract.CODE_SIZE):
            with self.assertRaises(ValueError):extract.extract_challenge(code)
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/'synthetic-challenge'
            extract.save_private(path,b'ABCDE'+b'\0'*27)
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            with self.assertRaises(FileExistsError):extract.save_private(path,b'F'*32)
            self.assertEqual(path.read_bytes(),b'ABCDE'+b'\0'*27)

    def test_local_extraction_matches_the_successfully_tested_private_challenge(self):
        base=pathlib.Path(__file__).parent
        code=base/'original-controller-code.bin'
        candidate=base/'private-firmware-auth-challenge.bin'
        if not code.exists() or not candidate.exists():self.skipTest('Owner firmware not bundled')
        self.assertEqual(extract.extract_challenge(code.read_bytes()),candidate.read_bytes())

    def test_completed_reset_record_is_private_and_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/'private-result.json'
            proof={'reset_method_status':0,'locking_enabled':False,'locked':False}
            safety.save_private_completion(path,proof)
            self.assertEqual(json.loads(path.read_text()),proof)
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            with self.assertRaises(FileExistsError):safety.save_private_completion(path,{'changed':True})
            self.assertEqual(json.loads(path.read_text()),proof)

    def test_erase_authorization_requires_exact_target_scope_and_current_approval(self):
        auth={'approved':True,'target_usb_serial':'SYNTHETIC_USB','target_ssd_serial':'SYNTHETIC_SSD',
              'firmware':fmt.FIRMWARE,'scope':safety.SCOPE,'approved_at_unix':1000}
        safety.validate_authorization(auth,'SYNTHETIC_USB','SYNTHETIC_SSD',fmt.FIRMWARE,1001)
        for change in ({'approved':False},{'approved':1},{'target_ssd_serial':'PRIMARY'},
                       {'target_usb_serial':'OTHER'},{'firmware':'OTHER'},{'scope':'repair'},
                       {'approved_at_unix':1002},{'approved_at_unix':float('nan')},
                       {'approved_at_unix':-90000}):
            with self.assertRaises(RuntimeError):
                safety.validate_authorization({**auth,**change},'SYNTHETIC_USB','SYNTHETIC_SSD',fmt.FIRMWARE,1001)
        proof={'model':fmt.MODEL,'firmware':fmt.FIRMWARE,'target_usb_serial':'SYNTHETIC_USB',
               'target_ssd_serial':'SYNTHETIC_SSD','reset_method_status':0,'locking_enabled':False,
               'locked':False,'completed_at_unix':1001}
        safety.validate_reset_proof(proof,auth,1002)
        for change in ({'reset_method_status':False},{'reset_method_status':1},{'locking_enabled':True},
                       {'locked':True},{'completed_at_unix':999},{'target_ssd_serial':'PRIMARY'},
                       {'firmware':'OTHER'},{'model':'OTHER'}):
            with self.assertRaises(RuntimeError):safety.validate_reset_proof({**proof,**change},auth,1002)

    def test_live_transport_reset_guard_requires_one_authenticated_sid_session(self):
        # Compile only this pure gate from the backend. No top-level USB I/O.
        source=pathlib.Path(__file__).with_name('ugreen_tcg_session_probe.py').read_text()
        node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='validate_outbound')
        scope={'tcg':t,'struct':struct,'factory_msid':None,'firmware_candidate':b'ABCDE'+b'\0'*27,
               'erase_requested':True,'erase_sent':False,'authenticated_sid_session':None,
               'authentication_attempted':False,'check_firmware_admin1':False,
               'check_firmware_sid':True,'check_factory_admin1':False}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'reset gate','exec'),scope)
        payload=t.packet(t.factory_reset(),hsn=105,tsn=7,firmware_candidate=scope['firmware_candidate'],allow_factory_reset=True)
        with self.assertRaises(RuntimeError):scope['validate_outbound'](payload)
        self.assertFalse(scope['erase_sent'])
        scope['authenticated_sid_session']=(105,8)
        with self.assertRaises(RuntimeError):scope['validate_outbound'](payload)
        scope['authenticated_sid_session']=(105,7)
        scope['validate_outbound'](payload)
        self.assertTrue(scope['erase_sent'])
        with self.assertRaises(RuntimeError):scope['validate_outbound'](payload)

    def test_no_write_or_authentication_body_can_be_wrapped(self):
        for method in ('0000000600000017','0000000600000202','0000000600000011','000000060000001c'):
            with self.assertRaises(ValueError):
                t.packet(t.call(t.MSID,bytes.fromhex(method),b''))
        with self.assertRaises(ValueError):t.get_columns(t.MSID,0,7)
        with self.assertRaises(ValueError):t.start_session(t.MSID)

    def test_start_session_is_anonymous_and_gets_are_restricted(self):
        body=t.start_session(t.ADMIN_SP)
        self.assertEqual(t.tokens(body)[4:8],[105,t.ADMIN_SP,1,t.EL])
        self.assertNotIn(t.SN,t.tokens(body))

    def test_authentication_requires_current_factory_value_and_exact_admin1_call(self):
        factory=b'A'*32
        body=t.authenticate_factory_admin1(factory)
        with self.assertRaises(ValueError):t.packet(body,hsn=105,tsn=1)
        with self.assertRaises(ValueError):t.packet(body,hsn=105,tsn=1,factory_msid=b'B'*32)
        self.assertEqual(len(t.packet(body,hsn=105,tsn=1,factory_msid=factory)),512)
        with self.assertRaises(ValueError):t.authenticate_factory_admin1(b'short')

    def test_firmware_session_matches_raw_challenge_and_authority_encoding(self):
        candidate=b'ABCDE'+b'\0'*27  # Synthetic; never the extracted credential.
        body=t.start_credential_session(t.LOCKING_SP,t.ADMIN1,candidate)
        tok=t.tokens(body)
        self.assertEqual(tok[4:16],[105,t.LOCKING_SP,1,t.SN,0,candidate,t.EN,t.SN,3,t.ADMIN1,t.EN,t.EL])
        with self.assertRaises(ValueError):t.packet(body)
        with self.assertRaises(ValueError):t.packet(body,firmware_candidate=b'wrong'+b'\0'*27)
        self.assertEqual(len(t.packet(body,firmware_candidate=candidate)),512)
        with self.assertRaises(ValueError):t.start_credential_session(t.ADMIN_SP,t.ADMIN1,candidate)

    def test_revert_requires_explicit_enable_and_can_only_keep_global_key(self):
        candidate=b'ABCDE'+b'\0'*27
        body=t.revert_keep_global()
        self.assertEqual(t.tokens(body)[4:8],[t.SN,0x60000,1,t.EN])
        with self.assertRaises(ValueError):t.packet(body,hsn=105,tsn=1,firmware_candidate=candidate)
        with self.assertRaises(ValueError):t.packet(body,firmware_candidate=candidate,allow_revert_keep_global=True)
        self.assertEqual(len(t.packet(body,hsn=105,tsn=1,firmware_candidate=candidate,allow_revert_keep_global=True)),512)
        for args in (b'',t.SN+t.uint(0x60000)+b'\0'+t.EN):
            with self.assertRaises(ValueError):
                t.packet(t.call(t.THIS_SP,t.REVERT_SP,args),hsn=105,tsn=1,firmware_candidate=candidate,allow_revert_keep_global=True)

    def test_range_audit_is_bounded_and_can_decode_large_lba_values(self):
        self.assertEqual(t.range_uid(1),bytes.fromhex('0000080200030001'))
        with self.assertRaises(ValueError):t.range_uid(17)
        self.assertEqual(t.tokens(b'\x88'+(0x100000000).to_bytes(8,'big')),[0x100000000])

    def test_erasing_reset_is_separately_armed_and_uses_admin_sp_revert(self):
        candidate=b'ABCDE'+b'\0'*27
        body=t.factory_reset()
        # Golden wire body from AdminSP.Revert[] and standard method-status trailer.
        self.assertEqual(body.hex(),'f8a80000020500000001a80000000600000202f0f1f9f0000000f1')
        with self.assertRaises(ValueError):t.packet(body,hsn=105,tsn=1,firmware_candidate=candidate)
        with self.assertRaises(ValueError):t.packet(body,hsn=105,tsn=1,firmware_candidate=candidate,allow_revert_keep_global=True)
        with self.assertRaises(ValueError):t.packet(body,firmware_candidate=candidate,allow_factory_reset=True)
        self.assertEqual(len(t.packet(body,hsn=105,tsn=1,firmware_candidate=candidate,allow_factory_reset=True)),512)
        with self.assertRaises(ValueError):
            t.packet(t.call(t.THIS_SP,t.REVERT_TPER,b''),hsn=105,tsn=1,firmware_candidate=candidate,allow_factory_reset=True)

    def test_format_guard_rejects_primary_internal_ambiguous_and_wrong_serial(self):
        serial='SYNTHETIC_SECONDARY'
        row={'device_model':fmt.MODEL,'device_serial':serial,'device_revision':fmt.FIRMWARE,
             'bsd_name':'disk11','size_in_bytes':fmt.SIZE}
        self.assertEqual(fmt.find_target([row],serial),'disk11')
        for rows in ([row,row],[],[{**row,'device_model':'Creator Pro SSD'}],[{**row,'bsd_name':'disk0'}]):
            with self.assertRaises(RuntimeError):fmt.find_target(rows,serial)
        smart={'model_name':fmt.MODEL,'serial_number':serial,'firmware_version':fmt.FIRMWARE}
        info={'DeviceIdentifier':'disk11','WholeDisk':True,'Internal':False,'TotalSize':fmt.SIZE}
        fmt.validate_target('disk11',serial,smart,info)
        for bad in ({**info,'Internal':True},{**info,'WholeDisk':False},{**info,'DeviceIdentifier':'disk4'},{**info,'TotalSize':1}):
            with self.assertRaises(RuntimeError):fmt.validate_target('disk11',serial,smart,bad)
        with self.assertRaises(RuntimeError):fmt.validate_target('disk11',serial,{**smart,'serial_number':'OTHER'},info)

    def test_packet_has_exact_lengths_and_session_byte_order(self):
        body=t.get_columns(t.MSID,3,3)
        wire=t.packet(body,hsn=105,tsn=0x12345678)
        self.assertEqual(len(wire),512)
        self.assertEqual(wire[4:8],bytes.fromhex('7ffe0000'))
        self.assertEqual(wire[20:28],bytes.fromhex('1234567800000069'))
        self.assertEqual(struct.unpack_from('>I',wire,52)[0],len(body))
        self.assertEqual(struct.unpack_from('>I',wire,16)[0]+20,56+((len(body)+3)//4)*4)
        self.assertEqual(wire[56:56+len(body)],body)

    def test_status_codes_are_not_confused_with_transport_success(self):
        for status in (0,1,0x12):
            body=t.SL+t.EL+t.EOD+t.SL+t.uint(status)+b'\0\0'+t.EL
            # A synthetic response uses the same envelope layout as a request.
            sub=struct.pack('>6sHI',b'\0'*6,0,len(body))+body
            sub+=b'\0'*((-len(sub))%4)
            pkt=struct.pack('>IIIHHII',4,105,0,0,0,0,len(sub))+sub
            cp=struct.pack('>IHHIII',0,0x7ffe,0,0,0,len(pkt))+pkt
            self.assertEqual(t.response(cp)['status'],status)

    def test_truncated_and_misaddressed_responses_rejected(self):
        wire=t.packet(t.EOS,hsn=105,tsn=1)
        self.assertEqual(t.response(wire)['tokens'],[t.EOS])
        for n in (0,19,21,55):
            with self.assertRaises(ValueError):t.response(wire[:n])
        wrong=bytearray(wire);wrong[4:6]=b'\x12\x34'
        with self.assertRaises(ValueError):t.response(wrong)
        wrong=bytearray(wire);struct.pack_into('>I',wrong,52,2048)
        with self.assertRaises(ValueError):t.response(wrong)

    def test_atom_lengths_and_values(self):
        for number in (0,63,64,255,256,65535,65536,0xffffffff):
            self.assertEqual(t.tokens(t.uint(number)),[number])
        for size in (1,8,15,16,512):
            self.assertEqual(t.tokens(t.blob(b'x'*size)),[b'x'*size])
        for bad in (b'\xa8tiny',b'\xd0',b'\xd0\x10short',b'\x84\x01'):
            with self.assertRaises(ValueError):t.tokens(bad)

if __name__=='__main__':unittest.main()
