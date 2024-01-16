import os

from pprint import pprint

from infrahub_sdk import Config, InfrahubClientSync

config = Config(api_token=os.getenv("INFRAHUB_API_TOKEN"))
client = InfrahubClientSync.init(address="http://localhost:8000", config=config)

meshes = client.all("SonyRegionMesh", include=["site"], populate_store=True)

site_ids = [mesh.site.id for mesh in meshes]

for mesh in meshes:
    mesh.site.fetch()
    mesh.site.peer.asn.fetch()

    devices = client.filters("InfraDevice", site__ids=[mesh.site.id], role__values=mesh.device_roles.value, populate_store=True)

    interfaces = client.filters("InfraInterface", device__ids=[device.id for device in devices], role__values=mesh.interface_roles.value, include=["ip_addresses"], populate_store=True)

    for interface in interfaces:
        interface.ip_addresses.fetch()

    session_endpoints = {
        device.name.value: {
            "device": device,
            "interface": interface
        }
        for interface in interfaces
        for device in devices
        if interface.device.id == device.id
    }


    for src_device, src_data in session_endpoints.items():
        destinations = session_endpoints.copy()
        destinations.pop(src_device)

        # TODO: look at upsert
        for _, dst_data in destinations.items():
            session = client.create(
                kind="InfraBGPSession",
                type="INTERNAL",
                status="provisionning",
                import_policies="import_policy_1",
                export_policies="export_policy_2",
                role="backbone",
                local_as=mesh.site.peer.asn.id,
                remote_as=mesh.site.peer.asn.id,
                local_ip =src_data["interface"].ip_addresses.peers[0].id,
                remote_ip =dst_data["interface"].ip_addresses.peers[0].id,
                device=src_data["device"].id,
                peer_group=mesh.peer_group.id,
            )
            session.save()
