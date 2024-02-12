from infrahub_sdk.checks import InfrahubCheck
from typing import Any, Dict, List, Optional

def connected_on_ixp(interface: Dict[str, Any], ixp_peer: Dict[str, Any]) -> bool:
    if interface["connected_endpoint"]["node"] == None:
        return False
    if  "InfraIXPEndpoint" != interface["connected_endpoint"]["node"]["__typename"]:
        return False
    if interface["connected_endpoint"]["node"]["ixp"]["node"] == None:
        return False
    ixp = interface["connected_endpoint"]["node"]["ixp"]["node"]["id"]

    if ixp_peer["ixp"]["node"] == None:
        return False
    return ixp_peer["ixp"]["node"]["id"] == ixp

def get_interface_by_ip(ip_address: Dict[str, Any], interfaces: Dict[str, Any]) -> (bool, Optional[Dict[str, Any]]):
    for interface_node in interfaces["edges"]:
        interface = interface_node["node"]

        for intf_ip_address in interface["ip_addresses"]["edges"]:
            if intf_ip_address["node"]["id"] == ip_address["id"]:
                return (True, interface)
    return (False,  None)

def get_ixp_peer_by_ip(ip_address: Dict[str, Any], ixp_peers: Dict[str, Any]) -> (bool, Optional[Dict[str, Any]]):
    for ixp_peer_node in ixp_peers["edges"]:
        ixp_peer = ixp_peer_node["node"]
        if ixp_peer["ipaddress"]["node"]["id"] == ip_address["id"]:
            return (True, ixp_peer)
    return (False, None)


class SonyBGPSessionCheck(InfrahubCheck):
    query = "check_bgp_transit_session"

    def validate(self, data):
        for bgp_session_node in data["data"]["InfraBGPSession"]["edges"]:
            bgp_session = bgp_session_node["node"]

            local_ip = bgp_session["local_ip"]["node"]
            remote_ip = bgp_session["remote_ip"]["node"]

            found, interface = get_interface_by_ip(local_ip, data["data"]["InfraInterfaceL3"])
            if not found:
                self.log_error(
                    message=f"BGP Session {bgp_session['name']} has a local IP that is not assigned to any Interface",
                    object_id=local_ip["id"],
                    object_type="InfraIPAddress"
                )

            found, ixp_peer = get_ixp_peer_by_ip(remote_ip, data["data"]["InfraIXPPeer"])
            if not found:
                self.log_error(
                    message=f"BGP Session {bgp_session['name']} has a remote IP that is not assigned to any IXP Peer",
                    object_id=remote_ip["id"],
                    object_type="InfraIPAddress",
                )

            if not connected_on_ixp(interface, ixp_peer):
                self.log_error(
                    message=f"BGP Session {bgp_session['name']} endpoints are not conneced to the same IXP",
                    object_id=bgp_session['name'],
                    object_type="InfraBGPSession",
                )
