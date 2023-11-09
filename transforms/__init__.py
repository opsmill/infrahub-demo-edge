from .avdbgp import AristaBGP
from .openconfig import OCBGPNeighbors, OCInterfaces

INFRAHUB_TRANSFORMS = [AristaBGP, OCInterfaces, OCBGPNeighbors]
