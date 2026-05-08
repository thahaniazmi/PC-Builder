from .gamestreet import GameStreetProvider
from .nanotek import NanotekProvider
from .disrupt import DisruptProvider
from .tecroot import TecRootProvider

PROVIDERS = {
    "gamestreet": GameStreetProvider,
    "nanotek": NanotekProvider,
    "tecroot": TecRootProvider,
    "disrupt": DisruptProvider,
}
