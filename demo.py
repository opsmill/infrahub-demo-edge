import uuid
from asyncio import run as aiorun
import time
import os
import pendulum
import re

from pygnmi.client import gNMIclient
from git import Repo
import typer
import httpx
from rich import print as rprint
import difflib
from rich.console import Console
from rich.table import Table

app = typer.Typer()

INFRAHUB_URL = "http://localhost:8000"

ARISTA_PORT = os.getenv("ARISTA_PORT", "6030")
ARISTA_USERNAME = os.getenv("ARISTA_USERNAME", "admin")
ARISTA_PASSWORD = os.getenv("ARISTA_PASSWORD", "admin")

OC_BGP_BASE_PATH = f"openconfig:/network-instances/network-instance[name=default]/protocols/protocol[name=BGP]/bgp"
OC_BGP_NEIGHBOR_PATH = f"{OC_BGP_BASE_PATH}/neighbors/neighbor"

QUERY_GET_DEVICES = """
    query ($branch: String!) {
        device (branch: $branch) {
            id
            name {
                value
            }
            role {
                slug {
                    value
                }
            }
        }
    }
"""

QUERY_GET_DEVICE_MANAGEMENT_IP = """
    query ($branch: String!, $device: String!) {
        device (name__value: $device, branch: $branch) {
            id
            name {
                value
            }
            interfaces(role__slug: "management") {
                id
                ip_addresses {
                    address {
                        value
                    }
                }
            }
        }
    }
"""

QUERY_GET_INTERFACE = """
    query ($branch: String!, $device: String!, $interface: String!) {
        device (branch: $branch, name__value: $device) {
            id
            interfaces(name__value: $interface) {
                id
                name {
                    value
                }
                enabled {
                    value
                }
            }
        }
    }
"""

QUERY_GET_INTERFACE_ALL = """
    query ($branch: String!, $device: String!, $rebase: Boolean!) {
        device (branch: $branch, name__value: $device, rebase: $rebase) {
            id
            interfaces {
                id
                name {
                    value
                }
                enabled {
                    value
                }
                description {
                    value
                }
                status {
                    slug {
                        value
                    }
                }
                role {
                    slug {
                        value
                    }
                }
            }
        }
    }
"""

QUERY_GET_BGP_ALL = """
    query ($branch: String!, $device: String!, $rebase: Boolean!) {
        bgp_session (branch: $branch, device__name__value: $device, rebase: $rebase) {
		    id
            type {
                value
            }
            peer_group {
                name {
                    value
                }
            }
            local_ip {
                address {
                    value
                }
            }
            remote_ip {
                address {
                    value
                }
            }
            local_as {
                asn {
                    value
                }
            }
            remote_as {
                asn {
                    value
                }
            }
            description {
                value
            }
            status {
                slug {
                    value
                }
            }
            role {
                slug {
                    value
                }
            }
        }
    }
"""

QUERY_GET_DEVICE_CIRCUIT = """
    query ($branch: String!, $device: String!, $rebase: Boolean!) {
        device (branch: $branch, name__value: $device, rebase: $rebase) {
            interfaces {
                name {
                    value
                }
                connected_circuit {
                    circuit {
                        id
                        circuit_id {
                            value
                        }
                        vendor_id {
                            value
                        }
                        type {
                            value
                        }
                        role {
                            slug {
                                value
                            }
                        }
                        status {
                            slug {
                                value
                            }
                        }
                        provider {
                            name {
                                value
                            }
                        }
                    }
                }
            }
        }
    }
"""


QUERY_GET_CIRCUIT = """
    query ($branch: String!, $circuit: String!, $rebase: Boolean!) {
        circuit (branch: $branch, circuit_id__value: $circuit, rebase: $rebase) {
            id
            circuit_id {
                value
            }
            vendor_id {
                value
            }
            type {
                value
            }
            role {
                slug {
                    value
                }
            }
            status {
                slug {
                    value
                }
            }
            provider {
                name {
                    value
                }
            }
        }
    }
"""
BRANCH_CREATE_DATA_ONLY = """
    mutation($branch: String!) {
        branch_create(data: { name: $branch, is_data_only: true }) {
            ok
            object {
                id
                name
            }
        }
    }
    """

BRANCH_CREATE = """
    mutation($branch: String!) {
        branch_create(data: { name: $branch }) {
            ok
            object {
                id
                name
            }
        }
    }
    """


BRANCH_MERGE = """
    mutation($branch: String!) {
        branch_merge(data: { name: $branch }) {
            ok
            object {
                id
                name
            }
        }
    }
    """

BRANCH_VALIDATE = """
    mutation($branch: String!) {
        branch_validate(data: { name: $branch }) {
            ok
            object {
                id
                name
            }
        }
    }
    """

BRANCH_REBASE = """
    mutation($branch: String!) {
        branch_rebase(data: { name: $branch }) {
            ok
            object {
                id
                name
            }
        }
    }
    """

INTERFACE_UPDATE_ADMIN_STATUS = """
    mutation($branch: String!, $interface_id: String!, $admin_status: Boolean!) {
        interface_update(branch: $branch, data: { id: $interface_id, enabled: { value: $admin_status}}){
            ok
            object {
                name {
                    value
                }
                enabled {
                    value
                }
            }
        }
    }
"""

CIRCUIT_UPDATE_STATUS = """
    mutation($branch: String!, $circuit_id: String!, $status: String!) {
        circuit_update(branch: $branch, data: { id: $circuit_id, status: $status}){
            ok
            object {
                status {
                    slug {
                        value
                    }
                }
            }
        }
    }
"""

INTERFACE_UPDATE_DESCRIPTION = """
    mutation($branch: String!, $interface_id: String!, $description: String!) {
        interface_update(branch: $branch, data: { id: $interface_id, description: { value: $description}}){
            ok
            object {
                name {
                    value
                }
                description {
                    value
                }
            }
        }
    }
"""


async def execute_query(client, query, variables=None, timeout=10, params=None):
    payload = {"query": query, "variables": variables}
    params = params if params else {}
    response = await client.post(
        f"{INFRAHUB_URL}/graphql", json=payload, timeout=timeout, params=params
    )
    response.raise_for_status()
    return response.json()


async def get_bgp_neighbor_config(client, device, timeout=10, params=None):

    params = params if params else {}
    params["device"] = device

    response = await client.get(
        f"{INFRAHUB_URL}/openconfig/network-instances/network-instance/protocols/protocol/bgp/neighbors", timeout=timeout, params=params
    )
    response.raise_for_status()
    return response.json()


async def get_rfile(client, rfile_name: str, params: dict, branch: str = "main"):

    if not params:
        params = {"branch": branch}
    else:
        params["branch"] = branch

    url = f"{INFRAHUB_URL}/rfile/{rfile_name}?branch={branch}"
    response = await client.get(url, params=params)
    response.raise_for_status()
    return response.text


def print_config(previous, new):

    previous = previous if previous else new
    console = Console()
    diff = difflib.ndiff(previous.split("\n"), new.split("\n"))
    for line in diff:

        if line.startswith("-"):
            console.print(f"[red]{line}")
        elif line.startswith("+"):
            console.print(f"[green]{line}")
        else:
            console.print(line)


async def _change_admin_status(device: str, interface: str, branch: str = "main"):
    console = Console()
    async with httpx.AsyncClient() as client:

        # Get the UUID of the interface and check it's current status
        response = await execute_query(
            client,
            QUERY_GET_INTERFACE,
            {"branch": branch, "device": device, "interface": interface},
        )
        interface_id = response["data"]["device"][0]["interfaces"][0]["id"]
        interface_status = response["data"]["device"][0]["interfaces"][0]["enabled"][
            "value"
        ]
        interface_status_text = "enabled" if interface_status else "disabled"
        console.print(
            f"Interface '{interface}' ({interface_id[:8]}) on '{device}', is currently '{interface_status_text}'"
        )
        # rprint(response)

        # Generate a new Branch name
        new_branch_name = f"update-intf-{str(uuid.uuid4())[:8]}"
        response = await execute_query(
            client, BRANCH_CREATE_DATA_ONLY, {"branch": new_branch_name}, timeout=60
        )
        console.print(f"Created the branch '{new_branch_name}' for this change")
        # rprint(response)

        # Update the status of the interface
        response = await execute_query(
            client,
            INTERFACE_UPDATE_ADMIN_STATUS,
            {
                "branch": new_branch_name,
                "interface_id": interface_id,
                "admin_status": not interface_status,
            },
        )
        console.print(
            f"Updated the admin status of the interface to {not interface_status} in {new_branch_name}"
        )
        # rprint(response)

        # Merge the branch
        response = await execute_query(
            client, BRANCH_MERGE, {"branch": new_branch_name}, timeout=60
        )
        if "errors" in response:
            for error in response["errors"]:
                console.print(f"[red]ERROR[/] {error['message']}")
        elif response["data"]["branch_merge"]["ok"]:
            console.print(
                f"[green]SUCCESS[/] Interface '{interface}' ({interface_id[:8]}) on '{device}' successfully updated"
            )


async def _change_circuit_status(circuit: str, status: str, branch: str = "main"):
    console = Console()
    async with httpx.AsyncClient() as client:

        # Get the status of the Circuit and check it's current status
        response = await execute_query(
            client,
            QUERY_GET_CIRCUIT,
            {"branch": branch, "circuit": circuit, "rebase": False},
        )
        rprint(response)
        circuit_id = response["data"]["circuit"][0]["id"]
        current_status = response["data"]["circuit"][0]["status"]["slug"]["value"]

        if current_status == status:
            console.print(
                f"Circuit '{circuit}' ({circuit_id[:8]}) status is already '{current_status}', nothing to do"
            )
            return False

        console.print(
            f"Circuit '{circuit}' ({circuit_id[:8]}), is currently '{current_status}'"
        )

        # Generate a new Branch name
        new_branch_name = f"update-circuit-{str(uuid.uuid4())[:8]}"
        response = await execute_query(
            client, BRANCH_CREATE_DATA_ONLY, {"branch": new_branch_name}, timeout=60
        )
        console.print(f"Created the branch '{new_branch_name}' for this change")

        # Update the status of the circuit
        response = await execute_query(
            client,
            CIRCUIT_UPDATE_STATUS,
            {
                "branch": new_branch_name,
                "circuit_id": circuit_id,
                "status": status,
            },
        )
        console.print(
            f"Updated the status of the Circuit to `{status}` in `{new_branch_name}`"
        )

        # Merge the branch
        response = await execute_query(
            client, BRANCH_MERGE, {"branch": new_branch_name}, timeout=60
        )
        if "errors" in response:
            for error in response["errors"]:
                console.print(f"[red]ERROR[/] {error['message']}")
        elif response["data"]["branch_merge"]["ok"]:
            console.print(
                f"[green]SUCCESS[/] Circuit '{circuit}' ({circuit_id[:8]}) successfully updated"
            )


async def _update_description(
    device: str, interface: str, description: str, branch: str
):

    if not branch:
        repo = Repo(".")
        branch = str(repo.active_branch)

    console = Console()
    async with httpx.AsyncClient() as client:

        # Get the UUID of the interface and check it's current status
        response = await execute_query(
            client,
            QUERY_GET_INTERFACE,
            {"branch": branch, "device": device, "interface": interface},
        )
        interface_id = response["data"]["device"][0]["interfaces"][0]["id"]
        console.print(
            f"Updating description of '{interface}' ({interface_id[:8]}) on '{device}', (branch '{branch}')"
        )

        # Update the description of the interface
        response = await execute_query(
            client,
            INTERFACE_UPDATE_DESCRIPTION,
            {
                "branch": branch,
                "interface_id": interface_id,
                "description": description,
            },
        )

        if "errors" in response:
            for error in response["errors"]:
                console.print(f"[red]ERROR[/] {error['message']}")
        elif response["data"]["interface_update"]["ok"]:
            console.print(
                f"[green]SUCCESS[/] Interface '{interface}' ({interface_id[:8]}) on '{device}' successfully updated, (branch '{branch}')"
            )


async def _list_interface(device: str, branch: str, rebase: bool):
    """List all interfaces for a given device."""

    if not branch:
        repo = Repo(".")
        branch = str(repo.active_branch)

    async with httpx.AsyncClient() as client:

        # Get the UUID of the interface and check it's current status
        response = await execute_query(
            client,
            QUERY_GET_INTERFACE_ALL,
            {"branch": branch, "device": device, "rebase": rebase},
        )

        table = Table(title=f"Device {device} | Interfaces | branch '{branch}'")

        table.add_column("Name", justify="right", style="cyan", no_wrap=True)
        table.add_column("Status")
        table.add_column("Role")
        table.add_column("Description")
        table.add_column("Enabled")
        table.add_column("UUID (short)")

        for intf in response["data"]["device"][0]["interfaces"]:
            table.add_row(
                intf["name"]["value"],
                intf["status"]["slug"]["value"],
                intf["role"]["slug"]["value"],
                intf["description"]["value"],
                "[green]True" if intf["enabled"]["value"] else "[red]False",
                str(intf["id"])[:8],
            )

        console = Console()
        console.print(table)


async def _list_bgp_session(devices: str, branch: str, rebase: bool, internal: bool):
    """List all BGP Session for a given device."""

    if not branch:
        repo = Repo(".")
        branch = str(repo.active_branch)


    table = Table(title=f"Devices : {devices} | BGP SESSION | branch '{branch}'")
    table.add_column("Device")
    table.add_column("Local IP")
    table.add_column("Local AS")
    table.add_column("Remote IP")
    table.add_column("Remote AS")
    table.add_column("Peer Group")
    table.add_column("Status")
    table.add_column("Role")
    table.add_column("Type")
    table.add_column("UUID (short)")

    device_list = devices.split(",")

    async with httpx.AsyncClient() as client:

        for device in device_list:
            # Get the UUID of the interface and check it's current status
            response = await execute_query(
                client,
                QUERY_GET_BGP_ALL,
                {"branch": branch, "device": device, "rebase": rebase},
            )

            for item in response["data"]["bgp_session"]:


                status_value = item["status"]["slug"]["value"]
                status = f"[green]{status_value}" if status_value == "active" else status_value

                type_value = item["type"]["value"]
                type_str = f"[blue]{type_value}" if type_value == "INTERNAL" else f"[cyan]{type_value}"

                if not internal and type_value == "INTERNAL":
                    continue

                table.add_row(
                    device,
                    "[magenta3]" + item['local_ip']['address']['value'],
                    str(item['local_as']['asn']['value']),
                    "[magenta3]" + item['remote_ip']['address']['value'],
                    str(item['remote_as']['asn']['value']),
                    item["peer_group"]["name"]["value"] if item["peer_group"] else "",
                    status,
                    item["role"]["slug"]["value"],
                    type_str,
                    str(item["id"])[:8],
                )

    console = Console()
    console.print(table)



async def _list_circuit(devices: str, branch: str, rebase: bool):
    """List all Circuit for a given device."""

    if not branch:
        repo = Repo(".")
        branch = str(repo.active_branch)

    table = Table(title=f"Devices {devices} | Circuit | branch '{branch}'")
    table.add_column("Device")
    table.add_column("Circuit ID")
    table.add_column("Vendor Circuit ID")
    table.add_column("Status")
    table.add_column("Role")
    table.add_column("Type")
    table.add_column("UUID (short)")

    device_list = devices.split(",")

    async with httpx.AsyncClient() as client:

        for device in device_list:

            # Get the UUID of the interface and check it's current status
            response = await execute_query(
                client,
                QUERY_GET_DEVICE_CIRCUIT,
                {"branch": branch, "device": device, "rebase": rebase},
            )

            for item in response["data"]["device"][0]["interfaces"]:

                if not item["connected_circuit"]:
                    continue

                circuit = item["connected_circuit"]["circuit"]

                status_value = circuit["status"]["slug"]["value"]
                status = f"[green]{status_value}" if status_value == "active" else status_value

                type_value = circuit["type"]["value"]
                type_str = f"[blue]{type_value}" if type_value == "INTERNAL" else f"[cyan]{type_value}"

                table.add_row(
                    device,
                    circuit["circuit_id"]["value"],
                    circuit["vendor_id"]["value"],
                    status,
                    circuit["role"]["slug"]["value"],
                    type_str,
                    str(circuit["id"])[:8],
                )

    console = Console()
    console.print(table)

async def _watch_config(
    device: str, branch: str, interval: int, rfile_name: str = "device_startup"
):
    """Get the configuration for a device via the API and watch for an update"""

    console = Console()
    current_config = None

    if not branch:
        repo = Repo(".")
        branch = str(repo.active_branch)

    async with httpx.AsyncClient() as client:
        while True:

            new_config = await get_rfile(
                client=client,
                rfile_name=rfile_name,
                params={"device": device},
                branch=branch,
            )

            if new_config != current_config:
                console.print(f"Configuration for '{device}' on branch '{branch}'")
                print("-" * 40)
                print_config(current_config, new_config)
                print("-" * 40)

            current_config = new_config

            time.sleep(interval)


async def _generate_topology(branch: str):
    """Get the topology file for containerlab from the API and save it locally"""

    console = Console()
    current_config = None

    if not branch:
        repo = Repo(".")
        branch = str(repo.active_branch)

    TOPOLOGY_FILENAME = "topology.clabs.yml"
    async with httpx.AsyncClient() as client:

        topology_file = await get_rfile(
            client=client, rfile_name="clab_topology", branch=branch, params={}
        )

        with open("topology.clabs.yml", "w") as f:
            f.write(topology_file)

    console.print(
        f"Saved new topology file in '{TOPOLOGY_FILENAME}' (branch '{branch}')"
    )


async def _generate_startup_config(branch: str):
    """Get the topology file for containerlab from the API and save it locally"""

    console = Console()
    current_config = None

    if not branch:
        repo = Repo(".")
        branch = str(repo.active_branch)

    async with httpx.AsyncClient() as client:
        # Get the list of all devices
        response = await execute_query(
            client,
            QUERY_GET_DEVICES,
            {"branch": branch},
        )

        for device in response["data"]["device"]:
            device_name = device["name"]["value"]

            startup_config = await get_rfile(
                client=client,
                rfile_name="device_startup",
                branch=branch,
                params={"device": device_name},
            )

            CONFIG_LOCATION = f"configs/startup/{device_name}.cfg"

            with open(CONFIG_LOCATION, "w") as f:
                f.write(startup_config)

            console.print(
                f"Saved new config file for '{device_name}' in '{CONFIG_LOCATION}' (branch '{branch}')"
            )


@app.command()
def list_interface(device: str, branch: str = None, rebase: bool = False):
    """List all interfaces for a given device."""
    aiorun(_list_interface(device=device, branch=branch, rebase=rebase))

@app.command()
def list_bgp_session(devices: str, branch: str = None, rebase: bool = False, internal: bool = True):
    """List all BGP Session for one or multiple device."""
    aiorun(_list_bgp_session(devices=devices, branch=branch, rebase=rebase, internal=internal))

@app.command()
def list_circuit(devices: str, branch: str = None, rebase: bool = False):
    """List all Circuit for one or multiple device."""
    aiorun(_list_circuit(devices=devices, branch=branch, rebase=rebase))

@app.command()
def change_circuit_status(circuit: str, status: str):
    """Update the status of a Circuit in a new branch and merge automatically."""
    aiorun(_change_circuit_status(circuit=circuit, status=status))

@app.command()
def change_admin_status(device: str, interface: str):
    """Flip the admin status of an interface in a new branch and merge automatically."""
    aiorun(_change_admin_status(device=device, interface=interface))


@app.command()
def update_description(
    device: str, interface: str, description: str, branch: str = None
):
    """Update the description of an interface."""
    aiorun(
        _update_description(
            device=device, interface=interface, description=description, branch=branch
        )
    )


@app.command()
def watch_config(device: str, interval: int = 10, branch: str = None):
    """Get the configuration for a device via the API and watch for an update"""
    aiorun(_watch_config(device=device, branch=branch, interval=interval))


@app.command()
def generate_topology(branch: str = None):
    """Generate the configuration for Container Lab"""
    aiorun(_generate_topology(branch=branch))


@app.command()
def generate_startup_config(branch: str = None):
    """Generate the configuration for Container Lab"""
    aiorun(_generate_startup_config(branch=branch))


@app.command()
def sync():

    command = "rsync --exclude='.git' --exclude='.vscode' -avzh ~/projects/infrahub-demo-edge boone:projects"
    stream = os.popen(command)
    print(stream.read())


@app.command()
def generate_time():
    """Get the configuration for a device via the API and watch for an update"""

    now = pendulum.now(tz="UTC")

    rprint(f"- 30 min  : '{now.subtract(minutes=30).to_iso8601_string()}'")
    rprint(f"- 15 min  : '{now.subtract(minutes=15).to_iso8601_string()}'")
    rprint(f"- 5 min   : '{now.subtract(minutes=5).to_iso8601_string()}'")
    rprint(f"   NOW    : '{now.to_iso8601_string()}'")
    rprint(f"+ 5 min   : '{now.add(minutes=5).to_iso8601_string()}'")
    rprint(f"+ 15 min  : '{now.add(minutes=15).to_iso8601_string()}'")
    rprint(f"+ 30 min  : '{now.add(minutes=30).to_iso8601_string()}'")


async def _manage_bgp_session(device: str, branch: str = None, interval: int = 10):

    console = Console()
    current_config = None

    if not branch:
        repo = Repo(".")
        branch = str(repo.active_branch)

    console.log(f"-- Manage BGP Sessions for '{device}' (interval: {interval}) --")

    async with httpx.AsyncClient() as client:
        # Get the list of all devices
        response = await execute_query(
            client,
            QUERY_GET_DEVICE_MANAGEMENT_IP,
            {"branch": branch, "device": device},
        )

    mgmt_ip_address = response["data"]["device"][0]["interfaces"][0]["ip_addresses"][0]["address"]["value"].split("/")[0]

    # Add a Loop
    while True:
        device_conn = {
            "target": (mgmt_ip_address, ARISTA_PORT),
            "username": ARISTA_USERNAME,
            "password": ARISTA_PASSWORD,
            "insecure":True
        }

        def extract_config_from_device_session(session):

            regex = re.compile("\[neighbor\-address=(.*)\]")
            result = regex.search(session.get("path"))
            session_id = result.group(1)

            session_config = {
                "neighbor-address": session_id,
                "config": None
            }
            for key, value in session.get("val").items():
                if ":config" in key:
                    session_config["config"] = value

            return session_config

        async with httpx.AsyncClient() as client:
            infrahub_bgp_config = await get_bgp_neighbor_config(client=client, device=device)

        with gNMIclient(**device_conn) as gc:
            response = gc.get(path=[OC_BGP_NEIGHBOR_PATH], encoding="json_ietf")
            device_sessions = response.get("notification")[0].get("update", [])

            device_bgp_config = {
                'openconfig-bgp:neighbors': {
                'neighbor': [ extract_config_from_device_session(session) for session in device_sessions]
                }
            }

            # rprint(infrahub_bgp_config)
            # rprint(device_bgp_config)

            update = []
            create = []

            for intended_session in infrahub_bgp_config['openconfig-bgp:neighbors']['neighbor']:
                found = False
                for existing_session in device_bgp_config['openconfig-bgp:neighbors']['neighbor']:

                    if intended_session["neighbor-address"] != existing_session["neighbor-address"]:
                        continue

                    if intended_session["neighbor-address"] == existing_session["neighbor-address"]:
                        found = True
                    if intended_session["config"] != existing_session["config"]:

                        update = (f"{OC_BGP_NEIGHBOR_PATH}[neighbor-address={intended_session['neighbor-address']}]", {"config": intended_session["config"]} )
                        result = gc.set(update=[update])
                        console.log(f"[orange]UPDATED[/] Session '{intended_session['neighbor-address']}'")

                if not found:
                    update=(f"{OC_BGP_NEIGHBOR_PATH}[neighbor-address={intended_session['neighbor-address']}]", {"config": intended_session["config"]} )
                    result = gc.set(update=[update])
                    console.log(f"[orange]ADDED[/] Session '{intended_session['neighbor-address']}'")

            if not create and not update:
                console.log(f"All BGP sessions are already present")

        time.sleep(interval)

@app.command()
def manage_bgp_session(device: str, branch: str = None):
    aiorun(_manage_bgp_session(device=device, branch=branch))

if __name__ == "__main__":
    app()
