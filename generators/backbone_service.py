from infrahub_sdk.generator import InfrahubGenerator


async def find_interface(client, site_id):
    devices = await client.filters(kind="InfraDevice", role__value="edge", site__ids=[site_id])

    if len(devices) == 0:
        raise ValueError("Couldn't find devices")

    device = devices[0]
    interfaces = await client.filters(
        kind="InfraInterfaceL3",
        device__ids=[device.id],
        role__value="backbone",
        include=["connected_endpoint", "ip_addresses", "device"],
    )

    if len(interfaces) == 0:
        raise ValueError("Couldn't find interfaces")

    return interfaces[0]


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
            role="backbone",
        )

        await circuit.save(allow_upsert=True)

        interface_a = await find_interface(self.client, site_a_id)
        interface_b = await find_interface(self.client, site_b_id)

        if not interface_a.connected_endpoint.initialized:
            connected_endpoint_a = await self.client.create(
                kind="InfraCircuitEndpoint", circuit=circuit, site=site_a_id, connected_endpoint=interface_a
            )
            await connected_endpoint_a.save(allow_upsert=True)
        else:
            await interface_a.connected_endpoint.fetch()

            if (
                not interface_a.connected_endpoint.typename == "InfraCircuitEndpoint"
                or not interface_a.connected_endpoint.peer.circuit.id == circuit.id
            ):
                raise ValueError(f"{interface_a.name.value} on {interface_a.device.peer.name} is already connected!")

        if not interface_b.connected_endpoint.initialized:
            connected_endpoint_b = await self.client.create(
                kind="InfraCircuitEndpoint", circuit=circuit, site=site_b_id, connected_endpoint=interface_b
            )
            await connected_endpoint_b.save(allow_upsert=True)
        else:
            await interface_b.connected_endpoint.fetch()

            if (
                not interface_b.connected_endpoint.typename == "InfraCircuitEndpoint"
                or not interface_b.connected_endpoint.peer.circuit.id == circuit.id
            ):
                raise ValueError(f"{interface_b.name.value} on {interface_b.device.peer.name} is already connected!")

        # allocate an IP prefix for the service

        internal_networks_pool = await self.client.get(kind="CoreIPPrefixPool", name__value="Internal networks pool")

        prefix = await self.client.allocate_next_ip_prefix(
            resource_pool=internal_networks_pool,
            prefix_length=31,
            member_type="address",
            data={"is_pool": True},
            identifier=f"{service_name}-{service_id}",
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
            ip_namespace={"id": "default"},
        )
        await circuit_address_pool.save(allow_upsert=True)

        interface_a_ip = await self.client.allocate_next_ip_address(
            resource_pool=circuit_address_pool,
        )
        interface_a.ip_addresses.add(interface_a_ip)
        await interface_a.save(allow_upsert=True)

        interface_b_ip = await self.client.allocate_next_ip_address(
            resource_pool=circuit_address_pool,
        )
        interface_b.ip_addresses.add(interface_b_ip)
        await interface_b.save(allow_upsert=True)
