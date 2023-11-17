from .avdbgp import AristaBGP
from .avd_config import AristaConfig
from .openconfig import OCBGPNeighbors, OCInterfaces

INFRAHUB_TRANSFORMS = [AristaBGP, AristaConfig, OCInterfaces, OCBGPNeighbors]
