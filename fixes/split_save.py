import numpy as np
import os, sys
from tqdm import tqdm
import cv2
from nipy.labs.mask import compute_mask
from skimage import io

BASEINPUT = '/net/birdstore/Active_Atlas_Data/data_root/pipeline_data/CHATM3/preps'
INPUT = os.path.join(BASEINPUT, 'CH0/thumbnail')
files = sorted(os.listdir(INPUT))
os.makedirs(os.path.join(BASEINPUT, 'CH1/thumbnail'), exist_ok=True)
os.makedirs(os.path.join(BASEINPUT, 'CH2/thumbnail'), exist_ok=True)
os.makedirs(os.path.join(BASEINPUT, 'CH3/thumbnail'), exist_ok=True)

os.makedirs(os.path.join(BASEINPUT, 'CH1/thumbnail_cleaned'), exist_ok=True)
os.makedirs(os.path.join(BASEINPUT, 'CH2/thumbnail_cleaned'), exist_ok=True)
os.makedirs(os.path.join(BASEINPUT, 'CH3/thumbnail_cleaned'), exist_ok=True)


for file in tqdm(files):
    infile = os.path.join(INPUT, file)
    img = cv2.imread(infile)
    ch1_img = img[:,:,0]
    ch2_img = img[:,:,1]
    ch3_img = img[:,:,2]
    ch1_outpath = os.path.join(BASEINPUT, 'CH1/thumbnail', file)
    ch2_outpath = os.path.join(BASEINPUT, 'CH2/thumbnail', file)
    ch3_outpath = os.path.join(BASEINPUT, 'CH3/thumbnail', file)
    cv2.imwrite(ch1_outpath, ch1_img.astype(np.uint8))
    cv2.imwrite(ch2_outpath, ch2_img.astype(np.uint8))
    cv2.imwrite(ch3_outpath, ch3_img.astype(np.uint8))


for channel in [1,2,3]:
    INPUT = os.path.join(BASEINPUT, f'CH{channel}/thumbnail')
    files = sorted(os.listdir(INPUT))

    for file in tqdm(files):
        infile = os.path.join(INPUT, file)
        img = io.imread(infile)
        mask = compute_mask(img, m=0.2, M=0.9, cc=False, opening=2, exclude_zeros=True)
        mask = mask.astype(int)
        mask[mask==0] = 0
        mask[mask==1] = 255
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.dilate(mask.astype(np.uint8), kernel, iterations=2)
        mask = mask.astype(np.uint8)
        fixed = cv2.bitwise_and(img, img, mask=mask)
        BASEOUTPUT = os.path.join(BASEINPUT, f'CH{channel}/thumbnail_cleaned')
        outpath = os.path.join(BASEOUTPUT, file)
        os.makedirs(BASEOUTPUT, exist_ok=True)
        cv2.imwrite(outpath, fixed.astype(np.uint8))
