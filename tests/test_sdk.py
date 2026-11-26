"""Public package interoperability, identity protection and template boundaries."""
import json,os
from pathlib import Path
import socket,sys,threading,unittest
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'sdk'));sys.path.insert(1,str(ROOT/'wifi_helper/app'))
import wifi_helper.client as sdk
import wifi_helper.protocol as client_protocol
import protocol as server_protocol
from wifi_helper import Client,RadioLease

class SdkTests(unittest.TestCase):
    def test_public_sdk_redeems_ticket_with_independently_versioned_server(self):
        a,b=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
        a.settimeout(2);b.settimeout(2)
        errors=[];seen=[]
        def server():
            try:seen.append(server_protocol.server_handshake(b,lambda ticket:('lease','wlan1')))
            except BaseException as exc:errors.append(exc)
            finally:b.close()
        worker=threading.Thread(target=server);worker.start()
        try:
            with patch.object(client_protocol,'APP_VERSION','99.0.0'),patch.object(server_protocol,'APP_VERSION','1.0.0'):
                client_protocol.client_handshake(a,'a'*64)
        finally:a.close();worker.join(3)
        self.assertEqual(errors,[])
        self.assertEqual(seen,[('lease','wlan1')])

    def test_rejected_ticket_is_reported_to_the_client(self):
        a,b=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
        a.settimeout(2);b.settimeout(2)
        def redeem(ticket):raise ValueError('Unknown or expired ticket')
        def server():
            try:server_protocol.server_handshake(b,redeem)
            except ValueError:server_protocol.send(b,{'error':'Unknown or expired ticket'})
            finally:b.close()
        worker=threading.Thread(target=server);worker.start()
        try:
            with self.assertRaisesRegex(client_protocol.HelperRejected,'expired'):client_protocol.client_handshake(a,'b'*64)
        finally:a.close();worker.join(3)

    def test_host_option_accepts_name_with_optional_port_and_rejects_garbage(self):
        self.assertEqual(client_protocol.helper_address({}),('4c7fee11-wifi-helper',4817))
        self.assertEqual(client_protocol.helper_address({'wifi_helper_host':'local-wifi-helper:9000'}),('local-wifi-helper',9000))
        for bad in ('http://x','host/path','a b','host:99999','-bad'):
            with self.assertRaises(ValueError):client_protocol.helper_address({'wifi_helper_host':bad})

    def test_release_checks_mac_before_any_cleanup_and_is_idempotent(self):
        active=Mock(interface='wlan1',phy='phy0',mac='02:00:00:00:00:01',power_save='off')
        link=[{'ifindex':5,'address':active.mac}]
        with patch.object(sdk,'command',return_value=json.dumps(link)),patch.object(sdk,'same_device'):
            radio=RadioLease(active,sdk._Log(None))
            with patch('wifi_helper.wifi.cleanup',return_value=True) as cleanup:
                radio.release();radio.release()
                cleanup.assert_called_once();active.release.assert_called_once()
            radio=RadioLease(active,sdk._Log(None))
            with patch.object(sdk,'command',return_value='[{"address":"00:00:00:00:00:02"}]'),patch('wifi_helper.wifi.cleanup') as cleanup:
                with self.assertRaisesRegex(RuntimeError,'MAC changed'):radio.release()
                cleanup.assert_not_called()

    def test_partial_local_acquisition_closes_lease_and_signals_fatal(self):
        lost=threading.Event();client=Client('4c7fee11-wifi-helper',lost=lost)
        with patch.object(sdk,'Lease') as lease,patch.object(sdk,'RadioLease',side_effect=RuntimeError('gone')):
            with self.assertRaises(RuntimeError):client.acquire('wlan1')
            lease.return_value.close.assert_called_once()
        self.assertTrue(lost.is_set())

    def test_example_is_documentation_not_an_extra_installable_app(self):
        self.assertEqual(len(list(ROOT.rglob('config.yaml'))),1)
        self.assertTrue((ROOT/'examples/minimal_app/config.yaml.example').is_file())
        profile=(ROOT/'examples/minimal_app/apparmor.txt').read_text()
        self.assertNotIn('capability sys_admin',profile)
        self.assertIn('/share/wifi-helper-private/',profile)


class IdentityTests(unittest.TestCase):
    def test_only_actual_helper_hostnames_become_deep_links(self):
        import broker
        for hostname,expected in [('abcdef01-wifi-helper','abcdef01_wifi_helper'),('local-wifi-helper','local_wifi_helper'),('abcd1234-untuyaos3',None),('untrusted/host',None)]:
            with patch.object(broker.socket,'gethostname',return_value=hostname):
                self.assertEqual(broker.addon_slug(),expected)
