import torch
from torch.autograd import Variable as V
import torchvision.models as models
from torchvision import transforms as trn
from torch.nn import functional as F
import os
import sys
import numpy as np
import cv2
from .places_model import PlacesModel


class Places365Model(PlacesModel):

    def __init__(self):
        # load the labels
        self.classes, self.labels_IO, self.labels_attribute, self.W_attribute = self.load_labels()
        # load the model
        self.features_blobs = []
        self.model = self.load_model()
        # load the transformer
        self.tf = self.returnTF() # image transformer
        # get the softmax weight
        self.params = list(self.model.parameters())
        self.weight_softmax = self.params[-2].data.numpy()
        self.weight_softmax[self.weight_softmax<0] = 0
        self.scence_cat_num =  int(os.getenv('PLACES_SCENE_CATS', '5'))
        self.scene_attrib_num =  int(os.getenv('PLACES_SCENE_ATTRS', '5'))


     # hacky way to deal with the Pytorch 1.0 update
    def recursion_change_bn(self, module):
        if isinstance(module, torch.nn.BatchNorm2d):
            module.track_running_stats = 1
        else:
            for i, (name, module1) in enumerate(module._modules.items()):
                module1 = self.recursion_change_bn(module1)
        return module

    def load_labels(self):
        # prepare all the labels
        # scene category relevant
        file_name_category = 'categories_places365.txt'
        if not os.access(file_name_category, os.W_OK):
            synset_url = 'https://raw.githubusercontent.com/csailvision/places365/master/categories_places365.txt'
            os.system('wget ' + synset_url)
        classes = list()
        with open(file_name_category) as class_file:
            for line in class_file:
                classes.append(line.strip().split(' ')[0][3:])
        classes = tuple(classes)

        # indoor and outdoor relevant
        file_name_IO = 'IO_places365.txt'
        if not os.access(file_name_IO, os.W_OK):
            synset_url = 'https://raw.githubusercontent.com/csailvision/places365/master/IO_places365.txt'
            os.system('wget ' + synset_url)
        with open(file_name_IO) as f:
            lines = f.readlines()
            labels_IO = []
            for line in lines:
                items = line.rstrip().split()
                labels_IO.append(int(items[-1]) -1) # 0 is indoor, 1 is outdoor
        labels_IO = np.array(labels_IO)

        # scene attribute relevant
        file_name_attribute = 'labels_sunattribute.txt'
        if not os.access(file_name_attribute, os.W_OK):
            synset_url = 'https://raw.githubusercontent.com/csailvision/places365/master/labels_sunattribute.txt'
            os.system('wget ' + synset_url)
        with open(file_name_attribute) as f:
            lines = f.readlines()
            labels_attribute = [item.rstrip() for item in lines]
        file_name_W = 'W_sceneattribute_wideresnet18.npy'
        if not os.access(file_name_W, os.W_OK):
            synset_url = 'http://places2.csail.mit.edu/models_places365/W_sceneattribute_wideresnet18.npy'
            os.system('wget ' + synset_url)
        W_attribute = np.load(file_name_W)

        return classes, labels_IO, labels_attribute, W_attribute

    def hook_feature(self, module, input, output):
        self.features_blobs.append(np.squeeze(output.data.cpu().numpy()))

    def returnCAM(self, feature_conv, weight_softmax, class_idx):
        # generate the class activation maps upsample to 256x256
        size_upsample = (256, 256)
        nc, h, w = feature_conv.shape
        output_cam = []
        for idx in class_idx:
            cam = weight_softmax[class_idx].dot(feature_conv.reshape((nc, h*w)))
            cam = cam.reshape(h, w)
            cam = cam - np.min(cam)
            cam_img = cam / np.max(cam)
            cam_img = np.uint8(255 * cam_img)
            output_cam.append(cv2.resize(cam_img, size_upsample))
        return output_cam

    def returnTF(self):
    # load the image transformer
        tf = trn.Compose([
            trn.Resize((224,224)),
            trn.ToTensor(),
            trn.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ])
        return tf


    def load_model(self):
        # this model has a last conv feature map as 14x14

        model_file = 'wideresnet18_places365.pth.tar'
        # model_file = 'resnet50_places365.pth.tar'
        if not os.access(model_file, os.W_OK):
            os.system('wget http://places2.csail.mit.edu/models_places365/' + model_file)
            os.system('wget https://raw.githubusercontent.com/csailvision/places365/master/wideresnet.py')

        import wideresnet
        model = wideresnet.resnet18(num_classes=365)
        checkpoint = torch.load(model_file, map_location=lambda storage, loc: storage)
        state_dict = {str.replace(k,'module.',''): v for k,v in checkpoint['state_dict'].items()}
        model.load_state_dict(state_dict)

        # hacky way to deal with the upgraded batchnorm2D and avgpool layers...
        for i, (name, module) in enumerate(model._modules.items()):
            module = self.recursion_change_bn(model)
        model.avgpool = torch.nn.AvgPool2d(kernel_size=14, stride=1, padding=0)

        model.eval()



        # the following is deprecated, everything is migrated to python36

        ## if you encounter the UnicodeDecodeError when use python3 to load the model, add the following line will fix it. Thanks to @soravux
        #from functools import partial
        #import pickle
        #pickle.load = partial(pickle.load, encoding="latin1")
        #pickle.Unpickler = partial(pickle.Unpickler, encoding="latin1")
        #model = torch.load(model_file, map_location=lambda storage, loc: storage, pickle_module=pickle)

        model.eval()
        # hook the feature extractor
        features_names = ['layer4','avgpool'] # this is the last conv layer of the resnet
        for name in features_names:
            model._modules.get(name).register_forward_hook(self.hook_feature)
        return model

    def forward(self, image, metadata=None):
        input_img = V(self.tf(image).unsqueeze(0))
        # forward pass
        logit = self.model.forward(input_img)
        h_x = F.softmax(logit, 1).data.squeeze()
        probs, idx = h_x.sort(0, True)
        probs = probs.numpy()
        idx = idx.numpy()
        ## Generate info for image:
        # { "io": "outdoor", "cat": [{ "home_theater": 0.228, "grotto": 0.059 }], "attr": ["natural light", "open area", "no horizon"] }
        frame_info = dict()
        # io
        io_image = np.mean(self.labels_IO[idx[:10]]) # vote for the indoor or outdoor
        frame_info['io'] = 'indoor' if io_image < 0.5 else 'outdoor'
        # cat
        cats = []
        for i in range(0, self.scence_cat_num):
            cats.append({probs[i]: self.classes[idx[i]]})
            # print('{:.3f} -> {}'.format(probs[i], self.classes[idx[i]]))
        frame_info['cat'] = cats

        # attributes
        responses_attribute = self.W_attribute.dot(self.features_blobs[1])
        idx_a = np.argsort(responses_attribute)
        frame_info['attr'] = [self.labels_attribute[idx_a[i]] for i in range(-1,-10,-1)]
        # print('--SCENE ATTRIBUTES:')
        # print(', '.join([self.labels_attribute[idx_a[i]] for i in range(-1,-10,-1)]))
        return frame_info