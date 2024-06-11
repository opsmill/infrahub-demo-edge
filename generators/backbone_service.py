#!/usr/bin/env python3
from infrahub_sdk.generator import InfrahubGenerator

async def find_interface(client, site_id):
    devices = await client.filters(
        kind="InfraDevice",
        role__value="edge",
        site__ids=[site_id]
    )

    if len(devices) == 0:
        raise ValueError("Couldn't find devices")

    device = devices[0]
    interfaces = await client.filters(
        kind="InfraInterfaceL3",
        device__ids=[device.id],
        role__value="backbone",
        include=["connected_endpoint", "ip_addresses"]
   )

    if len(interfaces) == 0:
        raise ValueError("Couldn't find interfaces")

    interface = interfaces[0]

    return interface
    

class Generator(InfrahubGenerator):
    async def generate(self, data: dict) -> None:
        service_id = data["InfraBackBoneService"]["edges"][0]["node"]["id"]
        service_name = data["InfraBackBoneService"]["edges"][0]["node"]["name"]["value"]
        circuit_id = data["InfraBackBoneService"]["edges"][0]["node"]["circuit_id"]["value"]
        internal_circuit_id = data["InfraBackBoneService"]["edges"][0]["node"]["internal_circuit_id"]["value"]
        site_a_id = data["InfraBackBoneService"]["edges"][0]["node"]["site_a"]["node"]["id"]
        site_b_id = data["InfraBackBoneService"]["edges"][0]["node"]["site_b"]["node"]["id"]
        provider_id = data["InfraBackBoneService"]["edges"][0]["node"]["provider"]["node"]["id"]

        circuit = await self.client.create(
            kind="InfraCircuit",
            provider={"id": provider_id},
            vendor_id=circuit_id,
            circuit_id=internal_circuit_id,
            status="active",
            role="backbone"
        )

        await circuit.save(allow_upsert=True)

        interface_a = await find_interface(self.client, site_a_id)
        interface_b = await find_interface(self.client, site_b_id)

        connected_endpoint_a = await self.client.create(
            kind="InfraCircuitEndpoint",
            circuit=circuit,
            connected_endpoint=interface_a
        )
        await connected_endpoint_a.save(allow_upsert=True)

        connected_endpoint_b = await self.client.create(
            kind="InfraCircuitEndpoint",
            circuit=circuit,
            connected_endpoint=interface_b
        )
        await connected_endpoint_b.save(allow_upsert=True)
        
        # allocate an IP prefix for the service

        internal_networks_pool = await self.client.get(
            kind="CoreIPPrefixPool",
            name__value="Internal networks pool"
        )

        prefix = await self.client.allocate_next_ip_prefix(
            resource_pool=internal_networks_pool,
            size=31,
            member_type="address",
            identifier=f"{service_name}-{service_id}"
        )
        await prefix.save(allow_upsert=True)

        # create a new pool
        circuit_address_pool = await self.client.create(
            kind="CoreIPAddressPool",
            name=f"{service_name}-{service_id}",
            default_address_type="IpamIPAddress",
            default_prefix_size=31,
            resources=[prefix],
            is_pool=True,
            ip_namespace={"id": "default"}
        )
        await circuit_address_pool.save(allow_upsert=True)

        interface_a.ip_addresses.add(circuit_address_pool)
        await interface_a.save(allow_upsert=True)

        interface_b.ip_addresses.add(circuit_address_pool)
        await interface_b.save(allow_upsert=True)

        interface_a = await self.client.get(kind="InfraInterfaceL3", id=interface_a.id, include=["ip_addresses"]) 
        interface_b = await self.client.get(kind="InfraInterfaceL3", id=interface_b.id, include=["ip_addresses"]) 

        await interface_a.ip_addresses.peers[-1].fetch()
        await interface_b.ip_addresses.peers[-1].fetch()

        ip_a = interface_a.ip_addresses.peers[-1].peer
        ip_b = interface_b.ip_addresses.peers[-1].peer

        asn = await self.client.get(kind="InfraAutonomousSystem", organization__name__value="Duff")

        bgp_session_a = await self.client.create(
            kind="InfraBGPSession",
            type="INTERNAL",
            status="active",
            role="backbone",
            local_ip=ip_a,
            remote_ip=ip_b,
            device={"id": interface_a.device.id},
            remote_as=asn
        )
        await bgp_session_a.save()
       
        bgp_session_b = await self.client.create(
            kind="InfraBGPSession",
            type="INTERNAL",
            status="active",
            role="backbone",
            local_ip=ip_b,
            remote_ip=ip_a,
            device={"id": interface_b.device.id},
            remote_as=asn
        )
        await bgp_session_b.save()
