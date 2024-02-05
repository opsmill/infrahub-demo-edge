from typing import Union

from infrahub_sdk import InfrahubClient, InfrahubNode


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
