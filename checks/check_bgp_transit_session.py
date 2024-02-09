from infrahub_sdk.checks import InfrahubCheck


class SonyBGPSessionCheck(InfrahubCheck):
    query = "check_bgp_transit_session"

    def validate(self, data):
        print("yep")
