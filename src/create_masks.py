import argparse
import os, sys
import numpy as np
import torch
import torch.utils.data
from PIL import Image
import cv2
from tqdm import tqdm
from multiprocessing.pool import Pool
import torchvision
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
from torchvision.models.detection.mask_rcnn import MaskRCNNPredictor
from abakit.utilities.file_location import FileLocationManager 
from abakit.utilities.shell_tools import workernoshell, get_image_size
from abakit.utilities.masking import combine_dims, merge_mask

from sql_setup import CREATE_FULL_RES_MASKS
from lib.sqlcontroller import SqlController
from lib.utilities_process import test_dir
import warnings
warnings.filterwarnings("ignore")

def create_final(animal):
    fileLocationManager = FileLocationManager(animal)
    COLORED = os.path.join(fileLocationManager.prep, 'masks', 'thumbnail_colored')
    MASKS = os.path.join(fileLocationManager.prep, 'masks', 'thumbnail_masked')
    error = test_dir(animal, COLORED, True, same_size=False)
    if len(error) > 0:
        print(error)
        sys.exit()

    os.makedirs(MASKS, exist_ok=True)

    files = sorted(os.listdir(COLORED))
    for file in tqdm(files):
        filepath = os.path.join(COLORED, file)
        maskpath = os.path.join(MASKS, file)

        if os.path.exists(maskpath):
            continue

        mask = cv2.imread(filepath, cv2.IMREAD_UNCHANGED)
        mask = mask[:,:,2]
        mask[mask>0] = 255
        cv2.imwrite(maskpath, mask.astype(np.uint8))


def get_model_instance_segmentation(num_classes):
    # load an instance segmentation model pre-trained pre-trained on COCO
    model = torchvision.models.detection.maskrcnn_resnet50_fpn(pretrained=True)
    # get number of input features for the classifier
    in_features = model.roi_heads.box_predictor.cls_score.in_features
    # replace the pre-trained head with a new one
    model.roi_heads.box_predictor = FastRCNNPredictor(in_features, num_classes)
    # now get the number of input features for the mask classifier
    in_features_mask = model.roi_heads.mask_predictor.conv5_mask.in_channels
    hidden_layer = 256
    # and replace the mask predictor with a new one
    model.roi_heads.mask_predictor = MaskRCNNPredictor(in_features_mask, hidden_layer, num_classes)
    return model

def create_mask(animal, downsample, njobs):

    fileLocationManager = FileLocationManager(animal)
    modelpath = os.path.join('/net/birdstore/Active_Atlas_Data/data_root/brains_info/masks/mask.model.pth')
    loaded_model = get_model_instance_segmentation(num_classes=2)
    if os.path.exists(modelpath):
        loaded_model.load_state_dict(torch.load(modelpath,map_location=torch.device('cpu')))
    else:
        print('no model to load')

    ##### Create directories


    if not downsample:
        sqlController = SqlController(animal)
        sqlController.set_task(animal, CREATE_FULL_RES_MASKS)
        INPUT = os.path.join(fileLocationManager.prep, 'CH1', 'full')
        ##### Check if files in dir are valid
        error = test_dir(animal, INPUT, downsample, same_size=False)
        if len(error) > 0:
            print(error)
            sys.exit()

        THUMBNAIL = os.path.join(fileLocationManager.prep, 'masks', 'thumbnail_masked')
        ##### Check if files in dir are valid
        ##error = test_dir(animal, THUMBNAIL, full=False, same_size=False)
        MASKED = os.path.join(fileLocationManager.prep, 'masks', 'full_masked')
        os.makedirs(MASKED, exist_ok=True)
        files = sorted(os.listdir(INPUT))
        commands = []
        for i, file in enumerate(tqdm(files)):
            infile = os.path.join(INPUT, file)
            thumbfile = os.path.join(THUMBNAIL, file)

            outpath = os.path.join(MASKED, file)
            if os.path.exists(outpath):
                continue
            try:
                width, height = get_image_size(infile)
            except:
                print(f'Could not open {infile}')
            size = f'{width}x{height}!'
            cmd = ['convert', thumbfile, '-resize', size, '-depth', '8', outpath]
            commands.append(cmd)

        with Pool(njobs) as p:
            p.map(workernoshell, commands)
    else:

        transform = torchvision.transforms.ToTensor()
        INPUT = os.path.join(fileLocationManager.prep, 'CH1/normalized')
        COLORED = os.path.join(fileLocationManager.prep, 'masks', 'thumbnail_colored')
        error = test_dir(animal, INPUT, downsample, same_size=False)
        if len(error) > 0:
            print(error)
            sys.exit()

        os.makedirs(COLORED, exist_ok=True)

        files = sorted(os.listdir(INPUT))
        debug = False
        for file in tqdm(files):
            filepath = os.path.join(INPUT, file)
            maskpath = os.path.join(COLORED, file)

            if os.path.exists(maskpath):
                continue

            img = Image.open(filepath)
            input = transform(img)
            input = input.unsqueeze(0)
            loaded_model.eval()
            with torch.no_grad():
                pred = loaded_model(input)
            pred_score = list(pred[0]['scores'].detach().numpy())
            if debug:
                print(file, pred_score[0])
            masks = [(pred[0]['masks']>0.5).squeeze().detach().cpu().numpy()]
            mask = masks[0]
            dims = mask.ndim
            if dims > 2:
                mask = combine_dims(mask)

            raw_img = np.array(img)
            mask = mask.astype(np.uint8)
            mask[mask>0] = 255

            merged_img = merge_mask(raw_img, mask)
            del mask
            cv2.imwrite(maskpath, merged_img)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Work on Animal')
    parser.add_argument('--animal', help='Enter the animal', required=True)
    parser.add_argument('--downsample', help='Enter true or false', required=False, default='true')
    parser.add_argument('--njobs', help='How many processes to spawn', default=4, required=False)
    parser.add_argument('--final', help='Enter true or false', required=False, default='false')

    args = parser.parse_args()
    animal = args.animal
    downsample = bool({'true': True, 'false': False}[str(args.downsample).lower()])
    final = bool({'true': True, 'false': False}[str(args.final).lower()])
    njobs = int(args.njobs)

    if final:
         create_final(animal)
    else:
         create_mask(animal, downsample, njobs)
       



