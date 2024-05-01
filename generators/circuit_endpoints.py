from infrahub_sdk.generator import InfrahubGenerator


class Generator(InfrahubGenerator):
    async def generate(self, data: dict) -> None:
        # Extract the first node in the 'InfraInterfaceL3' edges array
        circuits = data["InfraCircuit"]["edges"]

        for circuit in circuits:
            id = circuit["node"]["id"]
            provider = circuit["node"]["provider"]["node"]
            circuit_id: str = circuit["node"]["circuit_id"]["value"]
            vendor_id: str = circuit["node"]["vendor_id"]["value"]
            # role: str = circuit["node"]["role"]["value"]

            if circuit["node"]["endpoints"]["count"] != 0:
                continue  # There is already endpoint, no need to add more :)

            for i in range(1, 3):  # range(1, 3) will generate numbers 1 and 2
                data = {
                    "circuit": {"id": id},
                    "description": {"value": f"{circuit_id} - ({provider}x{vendor_id})"},
                }
                if i == 1:
                    data.description += " A Side"
                elif i == 2:
                    data.description += " Z Side"

                obj = await self.client.create(kind="InfraCircuitEndpoint", data=data)
                await obj.save(allow_upsert=True)
