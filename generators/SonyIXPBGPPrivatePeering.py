import asyncio
import logging
import os

from typing import Union

from infrahub_sdk import Config, InfrahubClient, InfrahubNode


from utils import inherit_attribute_from_hierarchy, InheritanceException


async def run(client: InfrahubClient, log: logging.Logger, branch: str) -> None:
    for service in await client.all(
        "SonyIXPBGPPrivatePeering",
        branch=branch,
        populate_store=True,
        prefetch_relationships=True,
    ):
        await service.asn.fetch()
        await service.asn.peer.organization.fetch()

        await service.ixp.fetch()
        await service.ixp.peer.locations.fetch()

        try:
            inbound_policy = await inherit_attribute_from_hierarchy(
                client, service.ixp.peer.locations.peers[0].peer, "transit_policy_in"
            )
        except InheritanceException:
            inbound_policy = None

        try:
            outbound_policy = await inherit_attribute_from_hierarchy(
                client, service.ixp.peer.locations.peers[0], "transit_policy_out"
            )
        except InheritanceException:
            outbound_policy = None

        ixp_peers = await client.filters(
            kind="InfraIXPPeer",
            branch=branch,
            asn__ids=[service.asn.id],
            ixp__ids=[service.ixp.id]
        )

        ixp_endpoints = await client.filters(
            kind="InfraIXPEndpoint",
            branch=branch,
            ixp__ids=[service.ixp.id]
        )

        sessions = []
        if service.redundant.value:
            raise NotImplementedError("Redundant IXP Services have not been implemented yet")

        ixp_peer = ixp_peers[0]
        await ixp_peer.ipaddress.fetch()

        local_endpoint = ixp_endpoints[0]
        await local_endpoint.connected_endpoint.fetch()
        await local_endpoint.connected_endpoint.peer.ip_addresses.fetch()
        await local_endpoint.connected_endpoint.peer.device.fetch()

        local_asn = await client.get(
            "InfraAutonomousSystem", branch=branch, asn__value=33353
        )


        breakpoint()
        bgp_session = await client.create(
            kind="InfraBGPSession",
            name=f"Sony > {service.asn.peer.organization.peer.name.value}",
            branch=branch,
            type="EXTERNAL",
            status="active",
            role="transit",
            local_asn=local_asn,
            import_policies=inbound_policy,
            export_policies=outbound_policy,
            remote_as=service.asn.peer,
            local_ip = local_endpoint.connected_endpoint.peer.ip_addresses.peers[0],
            remote_ip = ixp_peer.ipaddress.peer,
            device = local_endpoint.connected_endpoint.peer.device.peer,
        )
        await bgp_session.save(allow_upsert=True)

if __name__ == "__main__":
    config = Config(api_token=os.getenv("INFRAHUB_API_TOKEN"))
    client = asyncio.run(InfrahubClient.init(config=config))
    asyncio.run(run(client=client, log=logging, branch="sony-cogent-transit-london"))
