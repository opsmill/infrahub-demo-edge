from collections import defaultdict

from infrahub.checks import InfrahubCheck


class InfrahubCheckTransitCircuitRedundancy(InfrahubCheck):

    query = "check_transit_circuit_redundancy"

    def validate(self):

        transit_per_site = defaultdict(lambda: defaultdict(int))

        for circuit in self.data["data"]["circuit"]:
            circuit_id = circuit["id"]
            status = circuit["status"]["slug"]["value"]

            for endpoint in circuit["endpoints"]:
                site_name = endpoint["site"]["name"]["value"]
                transit_per_site[site_name]["total"] += 1
                transit_per_site[site_name][status] += 1

        for site_name, site in transit_per_site.items():
            if site.get("active", 0) / site["total"] < 0.6:
                self.log_error(
                    message=f"{site_name} has less than 60% of transit circuit operational ({site.get('active', 0)}/{site['total']})",
                    object_id=circuit_id,
                    object_type="circuit",
                )


INFRAHUB_CHECKS = [InfrahubCheckTransitCircuitRedundancy]

