from transforms.openconfig import OCInterfaces, OCBGPNeighbors
from infrahub_sdk.ctl.utils import find_graphql_query



async def test_oc_interfaces_standard(helper, root_directory, client_sync):

    transform = OCInterfaces()
    query = find_graphql_query(name=transform.query, directory=root_directory)
    data = client_sync.execute_graphql(
            query=query,
            variables={"device": "ord1-edge1"}
        )

    response = await transform.transform(data=data)
    assert "openconfig-interfaces:interface" in response
    assert len(response["openconfig-interfaces:interface"]) > 2


async def test_oc_bgp_neighbors_standard(helper, root_directory, client_sync):

    transform = OCBGPNeighbors()
    query = find_graphql_query(name=transform.query, directory=root_directory)
    data = client_sync.execute_graphql(
            query=query,
            variables={"device": "ord1-edge1"}
        )

    response = await transform.transform(data=data)

    assert "openconfig-bgp:neighbors" in response
    assert "neighbor" in response["openconfig-bgp:neighbors"]
    assert len(response["openconfig-bgp:neighbors"]["neighbor"]) > 2