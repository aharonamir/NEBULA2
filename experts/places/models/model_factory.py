from .places_model import PlacesModel
from .places365_model import Places365Model

from typing import List

def get_places_model_list() -> List[str]:
    return ["places365"]


def get_places_model(type: str) -> PlacesModel:
    if type == "places365":
        return Places365Model
    else:
        raise ValueError(f"Unsupported model type '{type}'.")


def create_places_model(type: str) -> PlacesModel:
    model_class = get_places_model(type)
    return model_class()
