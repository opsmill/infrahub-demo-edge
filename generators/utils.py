from typing import Union

from infrahub_sdk import InfrahubClient, InfrahubNode
from infrahub_sdk.node import RelatedNode, Attribute

class InheritanceException(Exception):
    pass


async def inherit_attribute_from_hierarchy(
    client: InfrahubClient, node: InfrahubNode, attribute: str
) -> Union[int, str, bool, InfrahubNode]:
    if hasattr(node, attribute):
        attr = getattr(node, attribute)
        if isinstance(attr, RelatedNode) and attr.schema.cardinality == "one":
            await attr.fetch()
            return attr.peer
        elif isinstance(attr, RelatedNode) and attr.schema.cardinality == "many":
            raise InheritanceException(f"Relationships of cardinality many are not supported!")
        elif isinstance(attr, Attribute):
            return attr.value

    if not hasattr(node, "parent"):
        raise InheritanceException(f"Could not resolve {attribute} for {node.typename}")

    await node.parent.fetch()

    if not node.parent.peer:
        raise InheritanceException(f"Could not resolve {attribute} for {node.typename}")

    return await inherit_attribute_from_hierarchy(client, node.parent.peer, attribute)
