#!/usr/bin/env python3
# Copyright (c) Facebook, Inc. and its affiliates.

from abc import abstractmethod
import torch

class PlacesModel(torch.nn.Module):
    def __init__(self):
        super().__init__()

    @abstractmethod
    def forward(self, image, metadata=None):
        pass

    @abstractmethod
    def save(self, label):
        pass
