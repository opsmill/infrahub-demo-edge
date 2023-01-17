
from infrahub.transforms import InfrahubTransform


class OCInterfaces(InfrahubTransform):

    query = "oc_interfaces"
    url = "openconfig/interfaces"

    async def transform(self, data):
        response_payload = {}
        response_payload["openconfig-interfaces:interface"] = []

        for intf in data.get("device")[0].get("interfaces"):

            intf_name = intf["name"]["value"]

            intf_config = {
                "name": intf_name,
                "config": {"enabled": intf["enabled"]["value"]},
            }

            if intf["description"] and intf["description"]["value"]:
                intf_config["config"]["description"] = intf["description"]["value"]

            if intf["ip_addresses"]:
                intf_config["subinterfaces"] = {"subinterface": []}

            for idx, ip in enumerate(intf["ip_addresses"]):

                address, mask = ip["address"]["value"].split("/")
                intf_config["subinterfaces"]["subinterface"].append(
                    {
                        "index": idx,
                        "openconfig-if-ip:ipv4": {
                            "addresses": {"address": [{"ip": address, "config": {"ip": address, "prefix-length": mask}}]},
                            "config": {"enabled": True},
                        },
                    }
                )

            response_payload["openconfig-interfaces:interface"].append(intf_config)

        return response_payload

class OCBGPNeighbors(InfrahubTransform):

    query = "oc_bgp_neighbors"
    url = "openconfig/network-instances/network-instance/protocols/protocol/bgp/neighbors"

    async def transform(self, data):

        response_payload = {}

        response_payload["openconfig-bgp:neighbors"] = {"neighbor": []}

        for session in data.get("bgp_session"):

            neighbor_address = session["remote_ip"]["address"]["value"].split("/")[0]
            session_data = {"neighbor-address": neighbor_address, "config": {"neighbor-address": neighbor_address}}

            if session["peer_group"]:
                session_data["config"]["peer-group"] = session["peer_group"]["name"]["value"]

            if session["remote_as"]:
                session_data["config"]["peer-as"] = session["remote_as"]["asn"]["value"]

            if session["local_as"]:
                session_data["config"]["local-as"] = session["local_as"]["asn"]["value"]

            response_payload["openconfig-bgp:neighbors"]["neighbor"].append(session_data)

        return response_payload

INFRAHUB_TRANSFORMS = [OCInterfaces, OCBGPNeighbors]