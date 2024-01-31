import asyncio
import logging
import os

from typing import Union

from infrahub_sdk import Config, InfrahubClient, InfrahubNode


class InheritanceException(Exception):
    pass


async def inherit_attribute_from_hierarchy(
    client: InfrahubClient, node: InfrahubNode, attribute: str
) -> Union[int, str, bool]:
    if hasattr(node, attribute):
        return getattr(node, attribute).value

    if not hasattr(node, "parent"):
        raise InheritanceException(f"Could not resolve {attribute} for {node.typename}")

    await node.parent.fetch()

    if not node.parent.peer:
        raise InheritanceException(f"Could not resolve {attribute} for {node.typename}")

    return await inherit_attribute_from_hierarchy(client, node.parent.peer, attribute)


async def run(client: InfrahubClient, log, branch: str = "main"):

    for service in await client.all(
        "SonyBGPTransitPeering",
        branch=branch,
        populate_store=True,
        prefetch_relationships=True,
    ):
        await service.location.fetch()
        await service.asn.fetch()
        await service.asn.peer.organization.fetch()

        try:
            inbound_policy = await inherit_attribute_from_hierarchy(
                client, service.location.peer, "transit_policy_in"
            )
        except InheritanceException:
            inbound_policy = None
            
        try:
            outbound_policy = await inherit_attribute_from_hierarchy(
                client, service.location.peer, "transit_policy_out"
            )
        except InheritanceException:
            outbound_policy = None

        transit_port = await client.get(
            kind="SonyTransitPort",
            branch=branch,
            asn__asn__value=service.asn.peer.asn.value,
            location__name__value=service.location.peer.name.value,
        )

        await transit_port.ip_address.fetch()
        await transit_port.connected_endpoint.fetch()
        await transit_port.connected_endpoint.peer.device.fetch()
        await transit_port.connected_endpoint.peer.ip_addresses.fetch()

        sony_asn = await client.get(
            "InfraAutonomousSystem", branch=branch, asn__value=33353
        )

        # TODO: deletion https://github.com/opsmill/infrahub/pull/2028
        bgp_session = await client.create(
            "InfraBGPSession",
            name=f"Sony > {service.asn.peer.organization.peer.name.value}",
            branch=branch,
            type="EXTERNAL",
            status="active",
            role="transit",
            local_as=sony_asn,
            import_policies=inbound_policy,
            export_policies=outbound_policy,
            remote_as=transit_port.asn,
            local_ip=transit_port.connected_endpoint.peer.ip_addresses.peers[0],
            remote_ip=transit_port.ip_address.peer,
            device=transit_port.connected_endpoint.peer.device.peer,
        )
        await bgp_session.save(allow_upsert=True)


if __name__ == "__main__":
    config = Config(api_token=os.getenv("INFRAHUB_API_TOKEN"))
    client = asyncio.run(InfrahubClient.init(config=config))
    asyncio.run(run(client=client, log=logging, branch="sony-cogent-transit-london"))
