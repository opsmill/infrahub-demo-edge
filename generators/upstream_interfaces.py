from infrahub_sdk.generator import InfrahubGenerator


class Generator(InfrahubGenerator):
    async def generate(self, data: dict) -> None:

        upstream_interface = data["InfraInterfaceL3"]["edges"][0]["node"]

        provider = None
        circuit_id = None
        role: str = upstream_interface["role"]["value"]
        status: str = upstream_interface["status"]["value"]
        if upstream_interface["connected_endpoint"]:
            connected_endpoint = upstream_interface["connected_endpoint"]["node"]
            if connected_endpoint["circuit"]["node"]:
                circuit = connected_endpoint["circuit"]["node"]
                provider: str = circuit["provider"]["node"]["name"]["value"]
                circuit_id: str = circuit["vendor_id"]["value"]

        if provider:
            new_description = f"{role.upper()}: {provider.title()}-{circuit_id.upper()} ({status.lower()})"
            obj = await self.client.get(kind=upstream_interface["__typename"], id=upstream_interface["id"])
            obj.description = new_description
            await obj.save(allow_upsert=True)
