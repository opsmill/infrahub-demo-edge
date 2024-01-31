import copy
import logging
import uuid
from collections import defaultdict
from ipaddress import IPv4Network
from typing import Dict, List

from infrahub_sdk import UUIDT, InfrahubClient, InfrahubNode, NodeStore
from infrahub_sdk.exceptions import GraphQLError

# flake8: noqa
# pylint: skip-file

LOCATIONS = {
    "Europe": {
        "countries": {
            "Belgium": {},
            "Germany": {
                "Frankfurt": {
                    "south": {
                        "building-3": {
                            "floor-32": {
                                "suite-325": {
                                    "rack-3255": ["ord1-core1", "ord1-edge1"]
                                }
                            },
                            "floor-33": {
                                "suite-338": {
                                    "rack-3389": ["ord1-core2", "ord1-edge2"]
                                }
                            }
                        }
                    }
                }
            },
            "United Kingdom": {
                "London": {
                    "north": {
                        "Equinix LD8": {
                            "floor-59": {
                                "suite-596": {
                                    "rack-5964": ["lnd1-core1", "lnd1-core2"]
                                }
                            }
                        }
                    },
                },
            },
        },
        "transit_policy_out": "RM_TRANSIT_EMEA_OUT",
        "transit_policy_in": "RM_TRANSIT_EMEA_IN",
    },
    "Africa": {"countries": {"Morocco": {}}, "transit_policy_out": "RM_TRANSIT_AFRICA_OUT"},
    "Asia": {"countries": {"India": {}, "Japan": {}}, "transit_policy_out": "RM_TRANSIT_ASIA_OUT"},
    "Oceania": {"countries": {"Australia": {}}, "transit_policy_out": "RM_TRANSIT_OCEANIA_OUT"},
    "North America": {
        "countries": {
            "United States of America": {
                "Atlanta": {"north": {}, "south": {}},
                "Denver": {
                    "west": {
                        "building-1": {
                            "floor-11": {
                                "suite-111": {
                                    "rack-1111": ["den1-core1", "den1-edge1"]
                                },
                                "suite-112": {
                                    "rack-1121": []
                                }
                            },
                            "floor-12": {
                                "suite-121": {
                                    "rack-1211": []
                                }
                            }   
                        },
                        "building-2": {
                            "floor-21": {
                                "suite-211": {
                                    "rack-2111": []
                                },
                                "suite-212": {
                                    "rack-2121": []
                                }
                            },
                            "floor-22": {
                                "suite-221": {
                                    "rack-2211": ["den1-core2", "den1-edge2" ] 
                                }
                            }   
                        },
                    },
                }
            },
        },
        "transit_policy_out": "RM_TRANSIT_NORTH_AMERICA_OUT",
    },
    "South America": {"countries": {"Brazil": {}}, "transit_policy_out": "RM_SOUTH_AMERICA_OUT"},
}

SITES = ["atl", "ord", "lnd", "den", "dfw", "jfk", "bkk", "sfo", "iah", "mco"]

PLATFORMS = (
    ("Cisco IOS", "ios", "ios", "cisco_ios", "ios"),
    ("Cisco NXOS SSH", "nxos_ssh", "nxos_ssh", "cisco_nxos", "nxos"),
    ("Juniper JunOS", "junos", "junos", "juniper_junos", "junos"),
    ("Arista EOS", "eos", "eos", "arista_eos", "eos"),
)

DEVICES = (
    ("edge1", "active", "7280R3", "profile1", "edge", ["red", "green"], "Arista EOS"),
    ("edge2", "active", "ASR1002-HX", "profile1", "edge", ["red", "blue", "green"], "Cisco IOS"),
    ("core1", "drained", "MX204", "profile1", "core", ["blue"], "Juniper JunOS"),
    ("core2", "provisionning", "MX204", "profile1", "core", ["red"], "Juniper JunOS"),
)

INTERNAL_AS_RANGE = list(range(64_512, 65_535))

NETWORKS_POOL_INTERNAL = IPv4Network("10.0.0.0/8").subnets(new_prefix=16)
LOOPBACK_POOL = next(NETWORKS_POOL_INTERNAL).hosts()
P2P_NETWORK_POOL = next(NETWORKS_POOL_INTERNAL).subnets(new_prefix=31)
NETWORKS_POOL_EXTERNAL = IPv4Network("203.0.113.0/24").subnets(new_prefix=29)

MANAGEMENT_IPS = IPv4Network("172.20.20.0/27").hosts()

ACTIVE_STATUS = "active"
BACKBONE_ROLE = "backbone"


def site_names_generator(nbr_site=2) -> List[str]:
    """Generate a list of site names by iterating over the list of SITES defined above and by increasing the id.

    site_names_generator(nbr_site=5)
        result >> ["atl1", "ord1", "jfk1", "den1", "dfw1"]

    site_names_generator(nbr_site=12)
        result >> ["atl1", "ord1", "jfk1", "den1", "dfw1", "iad1", "bkk1", "sfo1", "iah1", "mco1", "atl2", "ord2"]
    """

    site_names: List[str] = []

    # Calculate how many loop over the entire list we need to make
    # and how many site we need to generate on the last loop
    nbr_loop = (int(nbr_site / len(SITES))) + 1
    nbr_last_loop = nbr_site % len(SITES) or len(SITES)

    for idx in range(1, 1 + nbr_loop):
        nbr_this_loop = len(SITES)
        if idx == nbr_loop:
            nbr_this_loop = nbr_last_loop

        site_names.extend([f"{site}{idx}" for site in SITES[:nbr_this_loop]])

    return site_names


P2P_NETWORKS_POOL = {
    ("atl1", "edge1", "ord1", "edge1"): next(P2P_NETWORK_POOL).hosts(),
    ("atl1", "edge1", "lnd1", "edge1"): next(P2P_NETWORK_POOL).hosts(),
    ("lnd1", "edge1", "ord1", "edge1"): next(P2P_NETWORK_POOL).hosts(),
    ("atl1", "edge2", "ord1", "edge2"): next(P2P_NETWORK_POOL).hosts(),
    ("atl1", "edge2", "lnd1", "edge2"): next(P2P_NETWORK_POOL).hosts(),
    ("lnd1", "edge2", "ord1", "edge2"): next(P2P_NETWORK_POOL).hosts(),
}

BACKBONE_CIRCUIT_IDS = [
    "DUFF-1543451",
    "DUFF-6535773",
    "DUFF-5826854",
    "DUFF-8263953",
    "DUFF-7324064",
    "DUFF-4867430",
    "DUFF-4654456",
]

INTERFACE_MGMT_NAME = {
    "7280R3": "Management0",
    "ASR1002-HX": "Management0",
    "MX204": "MGMT",
}

INTERFACE_L3_NAMES = {
    "7280R3": [
        "Ethernet1",
        "Ethernet2",
        "Ethernet3",
        "Ethernet4",
        "Ethernet5",
        "Ethernet6",
        "Ethernet7",
        "Ethernet8",
        "Ethernet9",
        "Ethernet10",
    ],
    "ASR1002-HX": [
        "Ethernet1",
        "Ethernet2",
        "Ethernet3",
        "Ethernet4",
        "Ethernet5",
        "Ethernet6",
        "Ethernet7",
        "Ethernet8",
        "Ethernet9",
        "Ethernet10",
    ],
    "MX204": ["et-0/0/0", "et-0/0/1", "et-0/0/2"],
}
INTERFACE_L2_NAMES = {
    "7280R3": ["Ethernet11", "Ethernet12"],
    "ASR1002-HX": ["Ethernet11", "Ethernet12"],
    "MX204": ["et-0/0/3"],
}

INTERFACE_ROLES_MAPPING = {
    "edge": [
        "peer",
        "peer",
        "backbone",
        "backbone",
        "transit",
        "transit",
        "spare",
        "spare",
        "peering",
        "spare",
        "spare",
        "spare",
    ],
    "core": [
        "backbone",
        "backbone",
        "backbone",
        "spare",
    ],
}

TAGS = ["blue", "green", "red"]

ORGANIZATIONS = (
    ["Sony Interactive Entertainment Europe Limited", 25562],
    ["Sony Interactive Entertainment LLC", 33353],
    ["Colt", 8220],
    ["Verizon", 701],
    ["GTT", 3257],
    ["Hurricane Electric", 6939],
    ["Lumen", 3356],
    ["Zayo", 6461],
    ["Duff", 64496],
    ["Equinix", 24115],
    ["Arelion", 1299],
    ["Cogent Communications", 174],
    ["NTT America, Inc", 2914],
    ["TATA Communications (America) Inc", 6453],
    ["KDDI CORPORATION ", 2516],
    ["Telecom Italia Sparkle S.p.A", 6762],
    ["PCCW Global, Inc.", 3491],
    ["Comcast Cable Communications, LLC", 7922],
)

INTERFACE_OBJS: Dict[str, List[InfrahubNode]] = defaultdict(list)

ACCOUNTS = (
    ("pop-builder", "Script", "Password123", "read-write"),
    ("CRM Synchronization", "Script", "Password123", "read-write"),
    ("Jack Bauer", "User", "Password123", "read-only"),
    ("Chloe O'Brian", "User", "Password123", "read-write"),
    ("David Palmer", "User", "Password123", "read-write"),
    ("Operation Team", "User", "Password123", "read-only"),
    ("Engineering Team", "User", "Password123", "read-write"),
    ("Architecture Team", "User", "Password123", "read-only"),
)


GROUPS = (
    ("edge_router", "Edge Router"),
    ("core_router", "Core Router"),
    ("cisco_devices", "Cisco Devices"),
    ("arista_devices", "Arista Devices"),
    ("transit_interfaces", "Transit Interface"),
)

BGP_PEER_GROUPS = (
    ("POP_INTERNAL", "IMPORT_INTRA_POP", "EXPORT_INTRA_POP", "Duff", "Duff"),
    ("POP_GLOBAL", "IMPORT_POP_GLOBAL", "EXPORT_POP_GLOBLA", "Duff", None),
    ("TRANSIT_DEFAULT", "IMPORT_TRANSIT", "EXPORT_PUBLIC_PREFIX", "Duff", None),
    ("TRANSIT_TELIA", "IMPORT_TRANSIT", "EXPORT_PUBLIC_PREFIX", "Duff", "Arelion"),
    ("IX_DEFAULT", "IMPORT_IX", "EXPORT_PUBLIC_PREFIX", "Duff", None),
)

VLANS = (
    ("200", "server"),
    ("400", "management"),
)

store = NodeStore()

async def generate_internal_asn(client: InfrahubClient, asn: int, organization: str, branch: str) -> InfrahubNode:
    org = await client.get("CoreOrganization", name__value=organization)

    asn = {
        "asn": {"value": asn},
        "name": {"value": f"AS{asn}"},
        "organization": {"id": org.id}
    }

    obj = await client.create(branch=branch, kind="InfraAutonomousSystem", data=asn)
    await obj.save()
    return obj
    

async def group_add_member(client: InfrahubClient, group: InfrahubNode, members: List[InfrahubNode], branch: str):
    members_str = ["{ id: " + f'"{member.id}"' + " }" for member in members]
    query = """
    mutation {
        RelationshipAdd(
            data: {
                id: "%s",
                name: "members",
                nodes: [ %s ]
            }
        ) {
            ok
        }
    }
    """ % (
        group.id,
        ", ".join(members_str),
    )

    await client.execute_graphql(query=query, branch_name=branch)

async def create_connnection_transit_port(client: InfrahubClient, log: logging.Logger, branch: str):

    remote_ip_addr = await client.create(branch=branch, kind="InfraIPAddress", data={"address": {"value": "203.0.113.74/24"}})
    await remote_ip_addr.save()

    local_ip_addr= await client.create(branch=branch, kind="InfraIPAddress", data={"address": {"value": "203.0.113.75/24"}})
    await local_ip_addr.save()

    asn = await client.get(branch=branch, kind="InfraAutonomousSystem", asn__value=174)
    location = await client.get(branch=branch, kind="SonyRegion", name__value="London")

    sony_interface = await client.get(branch=branch, kind="InfraInterface", device__name__value="lnd1-edge1", name__value="Ethernet5")
    sony_interface.ip_addresses.add(local_ip_addr)
    await sony_interface.save()

    transit_port = await client.create(branch=branch, kind="SonyTransitPort", data={"name": "Cogen London Transit Port", "speed": 10000, "bandwidth": 4000, "asn": asn, "location": location, "ip_address": remote_ip_addr, "connected_endpoint": sony_interface})
    await transit_port.save()
    
async def create_location_hierarchy(client: InfrahubClient, log: logging.Logger, branch: str):
    for continent, data in LOCATIONS.items():
        infra_continent = await client.create(
            kind="SonyContinent",
            data={"name": continent, "transit_policy_out": data.get("transit_policy_out", "")}
        )
        await infra_continent.save()
        log.info(f"- Created {infra_continent._schema.kind} - {infra_continent.name.value}")

        for country, regions in data["countries"].items():
            infra_country = await client.create(kind="SonyCountry", data={
                "name": country,
                "parent": infra_continent
            })
            await infra_country.save()
            log.info(f"- Created {infra_country._schema.kind} - {infra_country.name.value}")

            for region, metros in regions.items():
                infra_region = await client.create(kind="SonyRegion", data={
                    "name": region,
                    "parent": infra_country
                })
                await infra_region.save()

                for metro, buildings in metros.items():
                    infra_metro = await client.create(kind="SonyMetro", data={
                        "name": metro,
                        "parent": infra_region
                    })
                await infra_metro.save()
                for building, floors in buildings.items():
                    infra_building = await client.create(kind="SonyBuilding", data={
                        "name": building,
                        "parent": infra_metro
                    })
                    await infra_building.save()
                    for floor, suites in floors.items():
                        infra_floor = await client.create(kind="SonyFloor", data={
                            "name": floor,
                            "parent": infra_building
                        })
                        await infra_floor.save()
                        for suite, racks in suites.items():
                            infra_suite = await client.create(kind="SonySuite", data={
                                "name": suite,
                                "parent": infra_floor
                            })
                            await infra_suite.save()
                            for rack, devices in racks.items():
                                infra_rack = await client.create(kind="SonyRack", data={
                                    "name": rack,
                                    "parent": infra_suite
                                })
                                await infra_rack.save()

                                for device in devices:
                                    infra_device = await client.get("InfraDevice", name__value=device)
                                    infra_device.location = infra_rack
                                    await infra_device.save()

async def create_branch_sony_cogent_transit(client: InfrahubClient, log: logging.Logger):
    new_branch = "sony-cogent-transit-london"
    await client.branch.create(
        branch_name=new_branch,
        data_only=True,
        description=f"Transit to Cogent in London",
    )
    log.info(f"- Creating branch: {new_branch!r}")
    

async def generate_site(client: InfrahubClient, log: logging.Logger, branch: str, site_name: str):
    group_eng = store.get("Engineering Team")
    group_ops = store.get("Operation Team")
    account_pop = store.get("pop-builder")
    account_crm = store.get("CRM Synchronization")

    internal_asn = await generate_internal_asn(client=client, branch=branch, asn=INTERNAL_AS_RANGE.pop(0), organization="Sony Interactive Entertainment LLC")

    group_edge_router = store.get(kind="CoreStandardGroup", key="edge_router")
    group_core_router = store.get(kind="CoreStandardGroup", key="core_router")
    group_cisco_devices = store.get(kind="CoreStandardGroup", key="cisco_devices")
    group_arista_devices = store.get(kind="CoreStandardGroup", key="arista_devices")
    group_transit_interfaces = store.get(kind="CoreStandardGroup", key="transit_interfaces")

    # --------------------------------------------------
    # Create the Site
    # --------------------------------------------------
    site = await client.create(
        branch=branch,
        kind="BuiltinLocation",
        name={"value": site_name, "is_protected": True, "source": account_crm.id},
        type={"value": "SITE", "is_protected": True, "source": account_crm.id},
        asn={"id": internal_asn.id, "source": account_crm.id},
    )
    await site.save()
    log.info(f"- Created {site._schema.kind} - {site.name.value}")

    peer_networks = {
        0: next(P2P_NETWORK_POOL).hosts(),
        1: next(P2P_NETWORK_POOL).hosts(),
    }

    # --------------------------------------------------
    # Create the site specific VLAN
    # --------------------------------------------------
    for vlan in VLANS:
        vlan_role = vlan[1]
        vlan_name = f"{site_name}_{vlan[1]}"
        obj = await client.create(
            branch=branch,
            kind="InfraVLAN",
            name={"value": f"{site_name}_{vlan[1]}", "is_protected": True, "source": account_pop.id},
            vlan_id={"value": int(vlan[0]), "is_protected": True, "owner": group_eng.id, "source": account_pop.id},
            status={"value": ACTIVE_STATUS, "owner": group_ops.id},
            role={"value": vlan_role, "source": account_pop.id, "is_protected": True, "owner": group_eng.id},
        )
        await obj.save()
        store.set(key=vlan_name, node=obj)

    for idx, device in enumerate(DEVICES):
        device_name = f"{site_name}-{device[0]}"
        device_status = device[1]
        device_role = device[4]
        device_type = device[2]
        platform_id = store.get(kind="InfraPlatform", key=device[6]).id

        obj = await client.create(
            branch=branch,
            kind="InfraDevice",
            site={"id": site.id, "source": account_pop.id, "is_protected": True},
            name={"value": device_name, "source": account_pop.id, "is_protected": True},
            status={"value": device_status, "owner": group_ops.id},
            type={"value": device[2], "source": account_pop.id},
            role={"value": device_role, "source": account_pop.id, "is_protected": True, "owner": group_eng.id},
            tags=[store.get(kind="BuiltinTag", key=tag_name).id for tag_name in device[5]],
            platform={"id": platform_id, "source": account_pop.id, "is_protected": True},
        )
        await obj.save()
        store.set(key=device_name, node=obj)
        log.info(f"- Created {obj._schema.kind} - {obj.name.value}")

        # Add device to groups
        if "edge" in device_role:
            await group_add_member(client=client, group=group_edge_router, members=[obj], branch=branch)
        elif "core" in device_role:
            await group_add_member(client=client, group=group_core_router, members=[obj], branch=branch)

        if "Arista" in device[6]:
            await group_add_member(client=client, group=group_arista_devices, members=[obj], branch=branch)
        elif "Cisco" in device[6]:
            await group_add_member(client=client, group=group_cisco_devices, members=[obj], branch=branch)

        # Loopback Interface
        intf = await client.create(
            branch=branch,
            kind="InfraInterfaceL3",
            device={"id": obj.id, "is_protected": True},
            name={"value": "Loopback0", "source": account_pop.id, "is_protected": True},
            enabled=True,
            status=ACTIVE_STATUS,
            role="loopback",
            speed=1000,
        )
        await intf.save()

        ip = await client.create(
            branch=branch,
            kind="InfraIPAddress",
            interface={"id": intf.id, "source": account_pop.id},
            address={"value": f"{str(next(LOOPBACK_POOL))}/32", "source": account_pop.id},
        )
        await ip.save()
        store.set(key=f"{device_name}-loopback", node=ip)

        # Management Interface
        intf = await client.create(
            branch=branch,
            kind="InfraInterfaceL3",
            device={"id": obj.id, "is_protected": True},
            name={"value": INTERFACE_MGMT_NAME[device_type], "source": account_pop.id},
            enabled={"value": True, "owner": group_eng.id},
            status={"value": ACTIVE_STATUS, "owner": group_eng.id},
            role={
                "value": "management",
                "source": account_pop.id,
                "is_protected": True,
            },
            speed=1000,
        )
        await intf.save()
        ip = await client.create(
            branch=branch, kind="InfraIPAddress", interface=intf.id, address=f"{str(next(MANAGEMENT_IPS))}/24"
        )
        await ip.save()

        # set the IP address of the device to the management interface IP address
        obj.primary_address = ip
        await obj.save()

        # L3 Interfaces
        for intf_idx, intf_name in enumerate(INTERFACE_L3_NAMES[device_type]):
            intf_role = INTERFACE_ROLES_MAPPING[device[4]][intf_idx]

            intf = await client.create(
                branch=branch,
                kind="InfraInterfaceL3",
                device={"id": obj.id, "is_protected": True},
                name=intf_name,
                speed=10000,
                enabled=True,
                status={"value": ACTIVE_STATUS, "owner": group_ops.id},
                role={"value": intf_role, "source": account_pop.id},
            )
            await intf.save()

            store.set(key=f"{device_name}-l3-{intf_idx}", node=intf)
            INTERFACE_OBJS[device_name].append(intf)

            address = None
            if intf_role == "peer":
                address = f"{str(next(peer_networks[intf_idx]))}/31"

            if intf_role in ["transit", "peering"] and "edge" in device_role:
                subnet = next(NETWORKS_POOL_EXTERNAL).hosts()
                address = f"{str(next(subnet))}/29"
                peer_address = f"{str(next(subnet))}/29"

            if not address:
                continue

            if address:
                ip = await client.create(
                    branch=branch,
                    kind="InfraIPAddress",
                    interface={"id": intf.id, "source": account_pop.id},
                    address={"value": address, "source": account_pop.id},
                )
                await ip.save()

        # L2 Interfaces
        for intf_idx, intf_name in enumerate(INTERFACE_L2_NAMES[device_type]):
            intf_role = "server"

            intf = await client.create(
                branch=branch,
                kind="InfraInterfaceL2",
                device={"id": obj.id, "is_protected": True},
                name=intf_name,
                speed=10000,
                enabled=True,
                status={"value": ACTIVE_STATUS, "owner": group_ops.id},
                role={"value": intf_role, "source": account_pop.id},
                l2_mode="Access",
                untagged_vlan={"id": store.get(kind="InfraVLAN", key=f"{site_name}_server").id},
            )
            await intf.save()

    # --------------------------------------------------
    # Connect both devices within the Site together with 2 interfaces
    # --------------------------------------------------
    for idx in range(0, 2):
        intf1 = store.get(kind="InfraInterfaceL3", key=f"{site_name}-edge1-l3-{idx}")
        intf2 = store.get(kind="InfraInterfaceL3", key=f"{site_name}-edge2-l3-{idx}")

        intf1.description.value = f"Connected to {site_name}-edge2 {intf2.name.value}"
        await intf1.save()

        intf2.description.value = f"Connected to {site_name}-edge1 {intf1.name.value}"
        await intf2.save()

        log.info(f" - Connected '{site_name}-edge1::{intf1.name.value}' <> '{site_name}-edge2::{intf2.name.value}'")

    return site_name


async def branch_scenario_add_transit(client: InfrahubClient, log: logging.Logger, site_name: str):
    """
    Create a new branch and Add a new transit link with GTT on the edge1 device of the given site.
    """
    log.info("Create a new branch and Add a new transit link with GTT on the edge1 device of the given site")
    device_name = f"{site_name}-edge1"

    new_branch_name = f"{site_name}-add-transit"
    new_branch = await client.branch.create(
        branch_name=new_branch_name, data_only=True, description=f"Add a new Transit link in {site_name}"
    )
    log.info(f"- Creating branch: {new_branch_name!r}")
    # Querying the object for now, need to pull from the store instead
    site = await client.get(branch=new_branch_name, kind="BuiltinLocation", name__value=site_name)
    device = await client.get(branch=new_branch_name, kind="InfraDevice", name__value=device_name)
    gtt_organization = await client.get(branch=new_branch_name, kind="CoreOrganization", name__value="GTT")

    role_spare = "spare"

    intfs = await client.filters(
        branch=new_branch_name, kind="InfraInterfaceL3", device__ids=[device.id], role__value=role_spare
    )
    intf = intfs[0]
    log.info(f" - Adding new Transit on '{device_name}::{intf.name.value}'")

    # Allocate a new subnet and calculate new IP Addresses
    subnet = next(NETWORKS_POOL_EXTERNAL).hosts()
    address = f"{str(next(subnet))}/29"
    peer_address = f"{str(next(subnet))}/29"

    peer_ip = await client.create(
        branch=new_branch_name,
        kind="InfraIPAddress",
        address=peer_address,
    )
    await peer_ip.save()

    ip = await client.create(
        branch=new_branch_name,
        kind="InfraIPAddress",
        interface={"id": intf.id},
        address={"value": address},
    )
    await ip.save()

    circuit_id_unique = str(uuid.UUID(int=abs(hash(f"{device_name}-transit-{address}"))))[24:]
    circuit_id = f"DUFF-{circuit_id_unique}"

    circuit = await client.create(
        branch=new_branch_name,
        kind="InfraCircuit",
        circuit_id=circuit_id,
        vendor_id=f"{gtt_organization.name.value.upper()}-{UUIDT().short()}",
        provider=gtt_organization.id,
        status=ACTIVE_STATUS,
        role="transit",
    )
    await circuit.save()
    log.info(f"  - Created {circuit._schema.kind} - {gtt_organization.name.value} [{circuit.vendor_id.value}]")

    endpoint1 = await client.create(
        branch=new_branch_name,
        kind="InfraCircuitEndpoint",
        site=site,
        circuit=circuit.id,
        connected_interface=intf.id,
    )
    await endpoint1.save()

    intf.description.value = f"Connected to {gtt_organization.name.value} via {circuit_id}"
    await intf.save()


async def branch_scenario_replace_ip_addresses(client: InfrahubClient, log: logging.Logger, site_name: str):
    """
    Create a new Branch and Change the IP addresses between edge1 and edge2 on the selected site
    """
    device1_name = f"{site_name}-edge1"
    device2_name = f"{site_name}-edge2"

    new_branch_name = f"{site_name}-update-edge-ips"
    new_branch = await client.branch.create(
        branch_name=new_branch_name,
        data_only=True,
        description=f"Change the IP addresses between edge1 and edge2 in {site_name}",
    )
    log.info("Create a new Branch and Change the IP addresses between edge1 and edge2 on the selected site")
    log.info(f"- Creating branch: {new_branch_name!r}")

    new_peer_network = next(P2P_NETWORK_POOL).hosts()

    device1 = await client.get(branch=new_branch_name, kind="InfraDevice", name__value=device1_name)
    device2 = await client.get(branch=new_branch_name, kind="InfraDevice", name__value=device2_name)
    role_peer = "peer"

    peer_intfs_dev1 = sorted(
        await client.filters(
            branch=new_branch_name, kind="InfraInterfaceL3", device__ids=[device1.id], role__value=role_peer
        ),
        key=lambda x: x.name.value,
    )
    peer_intfs_dev2 = sorted(
        await client.filters(
            branch=new_branch_name, kind="InfraInterfaceL3", device__ids=[device2.id], role__value=role_peer
        ),
        key=lambda x: x.name.value,
    )

    # Querying the object for now, need to pull from the store instead
    peer_ip = await client.create(
        branch=new_branch_name,
        kind="InfraIPAddress",
        interface={"id": peer_intfs_dev1[0].id},
        address=f"{str(next(new_peer_network))}/31",
    )
    await peer_ip.save()
    log.info(f" - Replaced {device1_name}-{peer_intfs_dev1[0].name.value} IP to {peer_ip.address.value}")

    ip = await client.create(
        branch=new_branch_name,
        kind="InfraIPAddress",
        interface={"id": peer_intfs_dev2[0].id},  # , "source": account_pop.id},
        address={"value": f"{str(next(new_peer_network))}/31"},  # , "source": account_pop.id},
    )
    await ip.save()
    log.info(f" - Replaced {device2_name}-{peer_intfs_dev2[0].name.value} IP to {ip.address.value}")


async def branch_scenario_remove_colt(client: InfrahubClient, log: logging.Logger, site_name: str):
    """
    Create a new Branch and Delete Colt Transit Circuit
    """
    log.info("Create a new Branch and Delete Colt Transit Circuit")
    new_branch_name = f"{site_name}-delete-transit"
    new_branch = await client.branch.create(
        branch_name=new_branch_name, data_only=True, description=f"Delete transit circuit with colt in {site_name}"
    )
    log.info(f"- Creating branch: {new_branch_name!r}")

    # TODO need to update the role on the interface and need to delete the IP Address
    # for idx in range(1, 3):
    #     device_name = f"{site_name}-edge{idx}"
    #     device = await client.get(branch=new_branch_name, kind="InfraDevice", name__value=device_name)
    #     intf = await client.get(branch=new_branch_name, kind="InfraInterfaceL3", device__id=device.id, name__value="Ethernet5")

    # Delete circuits
    get_circuits_query = """
    query($site_name: String!) {
        InfraCircuitEndpoint(site__name__value: $site_name) {
            edges {
                node {
                    id
                    circuit {
                        node {
                            id
                            circuit_id {
                                value
                            }
                            provider {
                                node {
                                    name {
                                        value
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    """
    circuits = await client.execute_graphql(
        branch_name=new_branch_name, query=get_circuits_query, variables={"site_name": site_name}
    )
    colt_circuits = [
        circuit
        for circuit in circuits["InfraCircuitEndpoint"]["edges"]
        if circuit["node"]["circuit"]["node"]["provider"]["node"]["name"]["value"] == "Colt"
    ]

    for item in colt_circuits:
        circuit_id = item["node"]["circuit"]["node"]["circuit_id"]["value"]
        circuit_endpoint = await client.get(branch=new_branch_name, kind="InfraCircuitEndpoint", id=item["node"]["id"])
        await circuit_endpoint.delete()

        circuit = await client.get(
            branch=new_branch_name, kind="InfraCircuit", id=item["node"]["circuit"]["node"]["id"]
        )
        await circuit.delete()
        log.info(f" - Deleted Colt [{circuit_id}]")


async def branch_scenario_conflict_device(client: InfrahubClient, log: logging.Logger, site_name: str):
    """
    Create a new Branch and introduce some conflicts
    """
    log.info("Create a new Branch and introduce some conflicts")
    device1_name = f"{site_name}-edge1"
    f"{site_name}-edge2"

    new_branch_name = f"{site_name}-maintenance-conflict"
    new_branch = await client.branch.create(
        branch_name=new_branch_name,
        data_only=True,
        description=f"Put {device1_name} in maintenance mode",
    )
    log.info(f"- Creating branch: {new_branch_name!r}")

    maintenance_status = "maintenance"
    provisionning_status = "provisionning"
    drained_status = "drained"

    # Update Device 1 Status both in the Branch and in Main
    device1_branch = await client.get(branch=new_branch_name, kind="InfraDevice", name__value=device1_name)

    device1_branch.status.value = maintenance_status
    await device1_branch.save()

    intf1_branch = await client.get(
        branch=new_branch_name, kind="InfraInterfaceL3", device__ids=[device1_branch.id], name__value="Ethernet1"
    )
    intf1_branch.enabled.value = False
    intf1_branch.status.value = drained_status
    await intf1_branch.save()

    device1_main = await client.get(kind="InfraDevice", name__value=device1_name)

    device1_main.status.value = provisionning_status
    await device1_main.save()

    intf1_main = await client.get(kind="InfraInterfaceL3", device__ids=[device1_branch.id], name__value="Ethernet1")
    intf1_main.enabled.value = False
    await intf1_main.save()


async def branch_scenario_conflict_platform(client: InfrahubClient, log: logging.Logger):
    """
    Create a new Branch and introduce some conflicts on the platforms for node ADD and DELETE
    """
    log.info("Create a new Branch and introduce some conflicts on the platforms for node ADD and DELETE")
    new_branch_name = f"platform-conflict"
    new_branch = await client.branch.create(
        branch_name=new_branch_name,
        data_only=True,
        description=f"Add new platform",
    )
    log.info(f"- Creating branch: {new_branch_name!r}")

    # Create a new Platform object with the same name, both in the branch and in main
    platform1_branch = await client.create(
        branch=new_branch_name, kind="InfraPlatform", name="Cisco IOS XR", netmiko_device_type="cisco_xr"
    )
    await platform1_branch.save()
    platform1_main = await client.create(kind="InfraPlatform", name="Cisco IOS XR", netmiko_device_type="cisco_xr")
    await platform1_main.save()

    # Delete an existing Platform object on both in the Branch and in Main
    platform2_branch = await client.get(branch=new_branch_name, kind="InfraPlatform", name__value="Cisco NXOS SSH")
    await platform2_branch.delete()
    platform2_main = await client.get(kind="InfraPlatform", name__value="Cisco NXOS SSH")
    await platform2_main.delete()

    # Delete an existing Platform object in the branch and update it in main
    platform3_branch = await client.get(branch=new_branch_name, kind="InfraPlatform", name__value="Juniper JunOS")
    await platform3_branch.delete()
    platform3_main = await client.get(kind="InfraPlatform", name__value="Juniper JunOS")
    platform3_main.nornir_platform.value = "juniper_junos"
    await platform3_main.save()


# ---------------------------------------------------------------
# Use the `infrahubctl run` command line to execute this script
#
#   infrahubctl run models/infrastructure_edge.py
#
# ---------------------------------------------------------------
async def run(client: InfrahubClient, log: logging.Logger, branch: str):
    SITE_NAMES = site_names_generator(nbr_site=5)

    # ------------------------------------------
    # Create User Accounts, Groups, Organizations & Platforms
    # ------------------------------------------
    log.info(f"Creating User Accounts, Groups & Organizations & Platforms")
    for account in ACCOUNTS:
        try:
            obj = await client.create(
                branch=branch,
                kind="CoreAccount",
                data={"name": account[0], "password": account[2], "type": account[1], "role": account[3]},
            )
            await obj.save()
        except GraphQLError:
            pass
        store.set(key=account[0], node=obj)
        log.info(f"- Created {obj._schema.kind} - {obj.name.value}")

    batch = await client.create_batch()
    for group in GROUPS:
        obj = await client.create(branch=branch, kind="CoreStandardGroup", data={"name": group[0], "label": group[1]})

        batch.add(task=obj.save, node=obj)
        store.set(key=group[0], node=obj)

    for org in ORGANIZATIONS:
        obj = await client.create(
            branch=branch, kind="CoreOrganization", data={"name": {"value": org[0], "is_protected": True}}
        )
        batch.add(task=obj.save, node=obj)
        store.set(key=org[0], node=obj)

    for platform in PLATFORMS:
        obj = await client.create(
            branch=branch,
            kind="InfraPlatform",
            data={
                "name": platform[0],
                "nornir_platform": platform[1],
                "napalm_driver": platform[2],
                "netmiko_device_type": platform[3],
                "ansible_network_os": platform[4],
            },
        )
        batch.add(task=obj.save, node=obj)
        store.set(key=platform[0], node=obj)


    # Create all Groups, Accounts and Organizations
    async for node, _ in batch.execute():
        log.info(f"- Created {node._schema.kind} - {node.name.value}")

    account_pop = store.get("pop-builder")
    account_cloe = store.get("Chloe O'Brian")

    # ------------------------------------------
    # Create Autonommous Systems
    # ------------------------------------------
    log.info(f"Creating Autonommous Systems")
    batch = await client.create_batch()
    for org in ORGANIZATIONS:
        obj = await client.create(
            branch=branch,
            kind="InfraAutonomousSystem",
            data={
                "name": {"value": f"AS{org[1]}", "source": account_pop.id, "owner": account_cloe.id},
                "asn": {"value": org[1], "source": account_pop.id, "owner": account_cloe.id},
                "organization": {"id": store.get(kind="CoreOrganization", key=org[0]).id, "source": account_pop.id},
            },
        )
        batch.add(task=obj.save, node=obj)
        store.set(key=org[0], node=obj)

    async for node, _ in batch.execute():
        log.info(f"- Created {node._schema.kind} - {node.name.value}")

    # ------------------------------------------
    # Create BGP Peer Groups
    # ------------------------------------------
    log.info(f"Creating BGP Peer Groups")
    batch = await client.create_batch()
    for peer_group in BGP_PEER_GROUPS:
        remote_as_id = None
        remote_as = store.get(kind="InfraAutonomousSystem", key=peer_group[4], raise_when_missing=False)
        if remote_as:
            remote_as_id = remote_as.id

        obj = await client.create(
            branch=branch,
            kind="InfraBGPPeerGroup",
            name={"value": peer_group[0], "source": account_pop.id},
            import_policies={"value": peer_group[1], "source": account_pop.id},
            export_policies={"value": peer_group[2], "source": account_pop.id},
            local_as=store.get(kind="InfraAutonomousSystem", key=peer_group[3]).id,
            remote_as=remote_as_id,
        )
        batch.add(task=obj.save, node=obj)
        store.set(key=peer_group[0], node=obj)

    async for node, _ in batch.execute():
        log.info(f"- Created {node._schema.kind} - {node.name.value}")

    # ------------------------------------------
    # Create Tags
    # ------------------------------------------
    batch = await client.create_batch()

    log.info("Creating Tags")
    for tag in TAGS:
        obj = await client.create(branch=branch, kind="BuiltinTag", name={"value": tag, "source": account_pop.id})
        batch.add(task=obj.save, node=obj)
        store.set(key=tag, node=obj)

    async for node, _ in batch.execute():
        log.info(f"- Created {node._schema.kind} - {node.name.value}")

    internal_as = store.get(kind="InfraAutonomousSystem", key="Duff")

    # ------------------------------------------
    # Create Sites
    # ------------------------------------------
    log.info("Creating Site and associated objects (Device, Circuit, BGP Sessions)")
    batch = await client.create_batch()

    for site_name in SITE_NAMES:
        batch.add(task=generate_site, site_name=site_name, client=client, branch=branch, log=log)

    async for _, response in batch.execute():
        log.debug(f"Site {response} Creation Completed")

    # --------------------------------------------------
    # CREATE Backbone Links & Circuits
    # --------------------------------------------------
    log.info("Creating Backbone Links & Circuits")
    for idx, backbone_link in enumerate(P2P_NETWORKS_POOL.keys()):
        site1 = backbone_link[0]
        site2 = backbone_link[2]
        device = backbone_link[1]

        # Build a new list with the names of the other sites for later
        other_site_site1 = copy.copy(SITE_NAMES)
        other_site_site1.remove(site1)
        other_site_site1 = sorted(other_site_site1)

        other_site_site2 = copy.copy(SITE_NAMES)
        other_site_site2.remove(site2)
        other_site_site2 = sorted(other_site_site2)

        intf1 = INTERFACE_OBJS[f"{site1}-{device}"][other_site_site1.index(site2) + 2]
        intf2 = INTERFACE_OBJS[f"{site2}-{device}"][other_site_site2.index(site1) + 2]

        circuit_id = BACKBONE_CIRCUIT_IDS[idx]

        if idx <= 2:
            provider_name = "Lumen"
        else:
            provider_name = "Zayo"

        provider = store.get(kind="CoreOrganization", key=provider_name)
        obj = await client.create(
            branch=branch,
            kind="InfraCircuit",
            description=f"Backbone {site1} <-> {site2}",
            circuit_id=BACKBONE_CIRCUIT_IDS[idx],
            vendor_id=f"{provider_name.upper()}-{UUIDT().short()}",
            provider=provider,
            # type="DARK FIBER",
            status=ACTIVE_STATUS,
            role=BACKBONE_ROLE,
        )
        await obj.save()
        log.info(f"- Created {obj._schema.kind} - {provider_name} [{obj.vendor_id.value}]")

        # Create Circuit Endpoints
        endpoint1 = await client.create(
            branch=branch,
            kind="InfraCircuitEndpoint",
            description=f"Endpoint {circuit_id} to {site1}-{device}",
            site=site1,
            circuit=obj,
            connected_endpoint=intf1,
        )
        await endpoint1.save()

        endpoint2 = await client.create(
            branch=branch,
            kind="InfraCircuitEndpoint",
            description=f"Endpoint {circuit_id} to {site2}-{device}",
            site=site2,
            circuit=obj,
            connected_endpoint=intf2,
        )
        await endpoint2.save()

        # Create IP Address
        intf11_address = f"{str(next(P2P_NETWORKS_POOL[backbone_link]))}/31"
        intf21_address = f"{str(next(P2P_NETWORKS_POOL[backbone_link]))}/31"
        intf11_ip = await client.create(
            branch=branch,
            kind="InfraIPAddress",
            interface={"id": intf1.id, "source": account_pop.id},
            address={"value": intf11_address, "source": account_pop.id},
        )
        await intf11_ip.save()
        intf21_ip = await client.create(
            branch=branch,
            kind="InfraIPAddress",
            interface={"id": intf2.id, "source": account_pop.id},
            address={"value": intf21_address, "source": account_pop.id},
        )
        await intf21_ip.save()

        # Update Interface
        intf11 = await client.get(branch=branch, kind="InfraInterfaceL3", id=intf1.id)
        intf11.description.value = f"Backbone: Connected to {site2}-{device} via {circuit_id}"
        await intf11.save()

        intf21 = await client.get(branch=branch, kind="InfraInterfaceL3", id=intf2.id)
        intf21.description.value = f"Backbone: Connected to {site1}-{device} via {circuit_id}"
        await intf21.save()

        log.info(f" - Connected '{site1}-{device}::{intf1.name.value}' <> '{site2}-{device}::{intf2.name.value}'")

    await create_location_hierarchy(client, log, branch)
    await create_connnection_transit_port(client, log, branch)

    # --------------------------------------------------
    # Create some changes in additional branches
    #  Scenario 1 - Add a Peering
    #  Scenario 2 - Change the IP Address between 2 edges
    #  Scenario 3 - Delete a Circuit + Peering
    #  Scenario 4 - Create some Relatioinship One and Attribute conflicts on a device
    #  Scenario 5 - Create some Node ADD and DELETE conflicts on some platform objects
    # --------------------------------------------------
    if branch == "main":
        await branch_scenario_add_transit(
            site_name=SITE_NAMES[1],
            client=client,
            log=log,
        )
        await branch_scenario_replace_ip_addresses(site_name=SITE_NAMES[2], client=client, log=log)
        await branch_scenario_remove_colt(site_name=SITE_NAMES[0], client=client, log=log)
        await branch_scenario_conflict_device(site_name=SITE_NAMES[3], client=client, log=log)
        await branch_scenario_conflict_platform(client=client, log=log)
        await create_branch_sony_cogent_transit(client=client, log=log)
